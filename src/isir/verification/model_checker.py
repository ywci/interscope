# src/isir/verification/model_checker.py
#
# Model-checking engine that wraps external formal tools
# (SymbiYosys / sby) to verify generated SVA assertions.
# Supports BMC and induction (IC3-like) modes.

import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional, List, Dict, Any
from isir.utils.logger import get_logger
from isir.utils.config_loader import get_config

logger = get_logger(__name__)


class ModelCheckError(Exception):
    """Raised when the model checking process fails."""
    pass


def run_model_check(
    rtl_path: Path,
    assertions_path: Path,
    top_module: str,
    engine: str = "bmc",
    depth: Optional[int] = None,
    timeout: Optional[int] = None,
    extra_args: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Run a model checker on the given RTL and assertion files.

    Args:
        rtl_path:        Path to the Verilog RTL file.
        assertions_path: Path to the SystemVerilog assertions file (SVA).
        top_module:      Name of the top‑level module.
        engine:          Verification engine – 'bmc' (bounded model checking)
                         or 'induction' (k‑induction / IC3).  Default: 'bmc'.
        depth:           Maximum depth for the engine (overrides config).
        timeout:         Timeout in seconds (overrides config).
        extra_args:      Additional command‑line arguments for the tool.

    Returns:
        A dictionary with keys:
            success (bool)             : True if all assertions hold.
            status (str)               : 'proved', 'disproved', 'inconclusive',
                                         or 'error'.
            counterexample_trace (Path or None) : Path to a VCD trace if a
                                                  counterexample was found.
            output (str)               : Raw stdout+stderr from the tool.
            error (str or None)        : Error message if the run itself failed.
            duration (float)           : Wall‑clock time in seconds.
            details (dict)             : Additional info (engine, depth, timeout, etc.).
    """
    start_time = time.time()
    config = get_config()
    mc_config = config.get("verification", {}).get("model_checker", {})

    tool = mc_config.get("tool_path") or shutil.which("sby")
    if not tool:
        raise ModelCheckError(
            "SymbiYosys (sby) not found.  Install it or set "
            "'verification.model_checker.tool_path' in conf/config.yaml."
        )

    if depth is None:
        if engine == "bmc":
            depth = config.get("verification", {}).get("bmc_max_depth", 100)
        else:
            depth = config.get("verification", {}).get("ic3_max_steps", 1000)
    if timeout is None:
        timeout = config.get("verification", {}).get("formal_timeout", 300)

    work_dir = Path(tempfile.mkdtemp(prefix="isir_mc_"))
    try:
        prevalidate = mc_config.get("prevalidate", False)
        if prevalidate:
            if not _prevalidate_files(rtl_path, assertions_path, top_module):
                logger.warning(
                    "Yosys pre‑validation failed. Continuing with SymbiYosys anyway; "
                    "sby will provide more detailed error output."
                )

        sby_file = work_dir / "design.sby"
        _write_sby_file(
            sby_file,
            rtl_path=rtl_path.resolve(),
            assertions_path=assertions_path.resolve(),
            top_module=top_module,
            engine=engine,
            depth=depth,
            timeout=timeout
        )

        cmd = [tool, "-f", str(sby_file)]
        if extra_args:
            cmd.extend(extra_args)

        logger.info("Running model checker: %s", " ".join(cmd))

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout + 30,
                cwd=str(work_dir)
            )
        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            return {
                "success": False,
                "status": "inconclusive",
                "counterexample_trace": None,
                "output": "",
                "error": f"Model checking timed out after {timeout}s.",
                "duration": duration,
                "details": {"engine": engine, "depth": depth, "timeout": timeout}
            }

        output = result.stdout + "\n" + result.stderr
        logger.debug("Model checker output:\n%s", output)

        status, counter_trace = _parse_sby_output(output, work_dir)
        duration = time.time() - start_time

        if status == "proved":
            logger.info("Model checking succeeded – all properties hold.")
            return {
                "success": True,
                "status": "proved",
                "counterexample_trace": None,
                "output": output,
                "error": None,
                "duration": duration,
                "details": {"engine": engine, "depth": depth, "timeout": timeout}
            }
        elif status == "disproved":
            logger.warning("Model checker found a counterexample.")
            return {
                "success": False,
                "status": "disproved",
                "counterexample_trace": counter_trace,
                "output": output,
                "error": None,
                "duration": duration,
                "details": {"engine": engine, "depth": depth, "timeout": timeout}
            }
        else:
            logger.error("Model checking inconclusive or failed. Output:\n%s", output)
            return {
                "success": False,
                "status": "inconclusive",
                "counterexample_trace": None,
                "output": output,
                "error": f"Model checking did not produce a definitive result. Output:\n{output[-2000:]}",
                "duration": duration,
                "details": {"engine": engine, "depth": depth, "timeout": timeout}
            }

    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def _prevalidate_files(rtl_path: Path, assertions_path: Path, top_module: str) -> bool:
    """
    Run Yosys in a read‑only mode to check that the RTL and assertion
    files can be parsed without syntax errors.

    Args:
        rtl_path:        Path to the RTL Verilog file.
        assertions_path: Path to the assertions file.
        top_module:      Name of the top‑level module.

    Returns:
        True if both files parse cleanly, False otherwise.
    """
    yosys = shutil.which("yosys")
    if not yosys:
        logger.debug("Yosys not found; skipping pre‑validation.")
        return False

    # Create a temporary script for Yosys.
    with tempfile.NamedTemporaryFile(mode='w', suffix='.ys', delete=False) as f:
        f.write(f"read_verilog -sv {rtl_path}\n")
        f.write(f"read_verilog -sv -formal {assertions_path}\n")
        f.write(f"hierarchy -top {top_module}\n")
        f.write("proc\n")   # Light processing to catch obvious issues.
        script_path = Path(f.name)

    try:
        result = subprocess.run(
            [yosys, "-s", str(script_path)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            logger.info("Yosys pre‑validation succeeded.")
            return True
        else:
            logger.warning("Yosys pre‑validation failed:\n%s", result.stderr[:1000])
            return False
    except Exception as e:
        logger.debug("Yosys pre‑validation exception: %s", e)
        return False
    finally:
        script_path.unlink(missing_ok=True)


def _write_sby_file(
    sby_path: Path,
    rtl_path: Path,
    assertions_path: Path,
    top_module: str,
    engine: str,
    depth: int,
    timeout: int
) -> None:
    """
    Write a SymbiYosys .sby script for the given design.

    The script uses explicit ``read_verilog`` commands:

    - ``read_verilog -sv <rtl>``       : Read the RTL design.
    - ``read_verilog -sv -formal <assertions>``
                                       : Read the SVA assertions in formal mode.
    - ``prep -top <top_module>``       : Prepare the design for verification.

    This ordering and the ``-formal`` flag are important for correct
    handling of SystemVerilog Assertions by Yosys/SymbiYosys.
    """
    mode = "bmc" if engine == "bmc" else "prove"
    options = f"mode {mode}\ndepth {depth}\ntimeout {timeout}"

    content = f"""[options]
{options}

[engines]
smtbmc z3

[script]
read_verilog -sv {rtl_path}
read_verilog -sv -formal {assertions_path}
prep -top {top_module}

[files]
{assertions_path}
{rtl_path}
"""
    sby_path.write_text(content, encoding="utf-8")
    logger.debug("Wrote SymbiYosys script to %s", sby_path)


def _parse_sby_output(output: str, work_dir: Path) -> tuple:
    """
    Examine SymbiYosys output to determine the verification status.

    Returns (status, counterexample_trace_path) where status is one of
    'proved', 'disproved', 'inconclusive', and trace_path is a Path or None.
    """
    lines = output.splitlines()
    for line in lines:
        line_upper = line.upper()
        if "DONE (" in line_upper:
            if "PASS" in line_upper:
                return ("proved", None)
            elif "FAIL" in line_upper:
                trace = work_dir / "design" / "trace.vcd"
                if trace.exists():
                    return ("disproved", trace)
                alt_trace = work_dir / "design" / "engine_0" / "trace.vcd"
                if alt_trace.exists():
                    return ("disproved", alt_trace)
                return ("disproved", None)
            else:
                return ("inconclusive", None)
    return ("error", None)


def _extract_width(data_type: str) -> Optional[int]:
    """Return bit width from a type string like 'bits<8>'."""
    if data_type == "bool":
        return 1
    if data_type.startswith("bits<"):
        try:
            return int(data_type[5:-1])
        except ValueError:
            pass
    return None


def _find_verilog(rtl_dir: Path, design_name: str) -> Optional[Path]:
    """Locate the generated top-level Verilog file."""
    direct = rtl_dir / f"{design_name}.v"
    if direct.exists():
        return direct
    nested = rtl_dir / f"{design_name}.v" / f"{design_name}.v"
    if nested.exists():
        return nested
    for candidate in sorted(rtl_dir.rglob("*.v")):
        return candidate
    return None


def run_mc_audit(
    spec_module,
    out_dir: Path,
    engine: str = "bmc",
    depth: Optional[int] = None,
    timeout: Optional[int] = None,
    koika_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Run SymbiYosys BMC as an *independent audit* of the spec's top-level
    properties (the ``properties``/``invariants`` lowered to SVA assertions).

    Lower the spec to Verilog RTL + SystemVerilog assertions, then invoke the
    model checker.  This is the cross-tool confirmation of the Coq proof (a
    different engine over a different representation), not a per-strategy gate.
    """
    from isir.lowering.koika_to_rtl import convert as rtl_convert
    from isir.lowering.isir_to_assert import convert as assert_convert
    from isir.lowering.assert_to_sva import convert as sva_convert

    out_dir = Path(out_dir).resolve()
    rtl_dir = out_dir / "rtl"
    assertions_dir = out_dir / "assertions"
    rtl_dir.mkdir(parents=True, exist_ok=True)
    assertions_dir.mkdir(parents=True, exist_ok=True)

    design_name = spec_module.name

    # 1. RTL.
    try:
        rtl_convert(spec_module, rtl_dir, koika_path=koika_path)
    except Exception as e:
        raise ModelCheckError(f"RTL generation failed: {e}") from e
    rtl_file = _find_verilog(rtl_dir, design_name)
    if rtl_file is None:
        raise ModelCheckError(f"Could not locate generated Verilog for '{design_name}'.")

    # 2. SVA assertions (the top-level properties become `assert property`).
    try:
        assert_mod = assert_convert(spec_module)
        signal_widths: Dict[str, int] = {}
        for s in getattr(spec_module, "state_ops", []) or []:
            w = _extract_width(getattr(s, "data_type", "") or "")
            if w is not None:
                signal_widths[getattr(s, "state_name", "")] = w
        for inp in getattr(spec_module, "inputs", []) or []:
            w = _extract_width(getattr(inp, "data_type", "") or "")
            if w is not None:
                signal_widths[getattr(inp, "name", "")] = w
        for outp in getattr(spec_module, "outputs", []) or []:
            w = _extract_width(getattr(outp, "data_type", "") or "")
            if w is not None:
                signal_widths[getattr(outp, "name", "")] = w
        sva_code = sva_convert(assert_mod, signal_widths=signal_widths)
    except Exception as e:
        raise ModelCheckError(f"SVA generation failed: {e}") from e

    assertions_file = assertions_dir / f"{design_name}_assertions.sv"
    assertions_file.write_text(sva_code, encoding="utf-8")
    logger.info("Generated audit RTL (%s) and SVA (%s).", rtl_file, assertions_file)

    # 3. Run SymbiYosys.
    return run_model_check(
        rtl_file,
        assertions_file,
        design_name,
        engine=engine,
        depth=depth,
        timeout=timeout,
    )
