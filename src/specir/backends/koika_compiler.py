# src/specir/backends/koika_compiler.py
#
# Low-level wrapper for the Kōika compiler (cuttlec).
# Maintained for backward compatibility and for direct invocation
# when an OCaml (.ml) file already exists.
#
# For the full synthesis pipeline (SpecIR → Verilog), use
# ``specir.lowering.koika_to_rtl.convert`` instead—it handles
# OCaml generation automatically and invokes the compiler internally.

import subprocess
from pathlib import Path
from typing import Optional
from specir.dialects import rtl_ir
from specir.utils.logger import get_logger

logger = get_logger(__name__)


class KoikaCompilationError(Exception):
    """Raised when the Kōika compiler fails."""
    pass


def compile_ocaml_to_verilog(
    design_name: str,
    output_dir: Path,
    koika_path: Optional[str] = None
) -> rtl_ir.RTLModuleContainer:
    """
    Compile an existing OCaml (.ml) file to Verilog using the Kōika compiler.

    The file ``<output_dir>/<design_name>.ml`` must already exist.  This
    function is a thin wrapper around ``cuttlec``; it does **not** perform
    Coq‑to‑OCaml extraction or SpecIR‑to‑OCaml generation.

    Args:
        design_name: Base name of the design (also the OCaml module name).
        output_dir: Directory containing ``<design_name>.ml``; receives the
                    generated Verilog and an empty mapping file.
        koika_path: Optional path to the ``koika`` executable.  If ``None``,
                    the system ``PATH`` is searched.

    Returns:
        RTLModuleContainer with the generated RTL module and an empty mapping.

    Raises:
        KoikaCompilationError: If the compiler is not found, fails, or does
                               not produce a Verilog file.
    """
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    compiler = _find_compiler(koika_path)

    ml_file = output_dir / f"{design_name}.ml"
    if not ml_file.exists():
        raise KoikaCompilationError(f"Missing OCaml file: {ml_file}")

    cmd = [
        str(compiler),
        str(ml_file),
        "-T", "verilog",
        "-o", str(output_dir)
    ]
    logger.info("Invoking Kōika compiler: %s", " ".join(cmd))

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(output_dir)
        )
    except subprocess.TimeoutExpired:
        raise KoikaCompilationError("Kōika compilation timed out.")
    except FileNotFoundError:
        raise KoikaCompilationError(
            f"Kōika compiler not found at '{compiler}'. "
            "Please install the Kōika toolchain and ensure 'koika' is on your PATH."
        )

    if result.returncode != 0:
        logger.error("Kōika compiler stderr:\n%s", result.stderr)
        raise KoikaCompilationError(
            f"Kōika compilation failed with code {result.returncode}:\n{result.stderr[:1000]}"
        )

    logger.info("Kōika compilation succeeded.")

    verilog_path = output_dir / f"{design_name}.v"
    if not verilog_path.exists():
        nested = output_dir / f"{design_name}.v" / f"{design_name}.v"
        if nested.exists():
            verilog_path = nested
        else:
            for candidate in sorted(output_dir.rglob("*.v")):
                verilog_path = candidate
                break

    if not verilog_path.exists():
        raise KoikaCompilationError(
            f"Kōika compiler did not produce a Verilog file in {output_dir}"
        )

    logger.info("Verilog output: %s", verilog_path)

    mapping = rtl_ir.RTLMapping(design_name=design_name, entries=[])
    mapping_path = output_dir / "mapping.json"
    with open(mapping_path, "w") as f:
        import json
        json.dump(mapping.to_json(), f, indent=2)

    rtl_module = rtl_ir.RTLModule(
        name=design_name,
        raw_verilog=verilog_path.read_text(),
        file_path=verilog_path
    )
    container = rtl_ir.RTLModuleContainer(
        modules={design_name: rtl_module},
        mapping=mapping,
        design_name=design_name
    )
    return container


def _find_compiler(koika_path: Optional[str]) -> Path:
    if koika_path:
        candidate = Path(koika_path)
        if candidate.exists():
            return candidate
        raise KoikaCompilationError(f"Kōika compiler not found at '{koika_path}'")

    import shutil
    path = shutil.which("koika")
    if path:
        return Path(path)

    for loc in [Path.home() / ".opam" / "default" / "bin" / "koika",
                Path("/usr/local/bin/koika")]:
        if loc.exists():
            return loc

    raise KoikaCompilationError(
        "Kōika compiler not found. Install the Kōika toolchain and ensure 'koika' is on your PATH, "
        "or set 'koika_path' in conf/config.yaml."
    )
