# src/specir/verification/simulation.py
#
# Simulation runner that uses the patched Verilog from koika_to_rtl.
# Optionally generates assertions (SVA, VHDL PSL, Verilog OVL) alongside the RTL.
# Resolves parameterized types before generating the testbench.
# If enabled in config, automatically splits monolithic ite‑rules
# before synthesis (see `split_monolithic_rules` in config.yaml).

import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, List
from specir.dialects import spec_ir
from specir.lowering import koika_to_rtl
from specir.lowering.split_rules import split_rules
from specir.lowering.spec_to_assert import convert as spec_to_assert_convert
from specir.lowering.assert_to_sva import convert as assert_to_sva_convert
from specir.lowering.assert_to_vhdl import convert as assert_to_vhdl_convert
from specir.lowering.assert_to_verilog_ovl import convert as assert_to_verilog_ovl_convert
from specir.backends import verilator_sim
from specir.utils.config_loader import get_config, get_project_root
from specir.utils.logger import get_logger
from specir.utils.result_types import SimulationReport

logger = get_logger(__name__)


class SimulationError(Exception):
    """Raised when simulation fails."""
    pass


def _safe_width(data_type: str) -> int:
    """Return bit width, defaulting to 32 if the type string cannot be parsed."""
    try:
        return _koika_width(data_type)
    except (ValueError, KeyError):
        logger.warning("Could not parse width from type '%s'; defaulting to 32.", data_type)
        return 32


def _koika_width(data_type: str) -> int:
    """Return bit width. Assumes the type is already concrete (no parameters)."""
    if data_type == "bool":
        return 1
    if data_type.startswith("bits<"):
        return int(data_type[5:-1])
    raise ValueError(f"Unrecognized type: {data_type}")


def _resolve_type(type_spec: str, params: Dict[str, int]) -> str:
    """Replace parameter names in a type string with their integer values."""
    result = type_spec
    for name, value in params.items():
        result = result.replace(name, str(value))
    return result


def _generate_input_testbench(
    design_name: str,
    output_dir: Path,
    inputs: List[spec_ir.Interface],
    cycles: int,
    params: Dict[str, int],
    rst_active: int = 0,
    rst_inactive: int = 1
) -> Path:
    """Generate a Verilator testbench that drives the given input signals."""
    tb_path = output_dir / "sim_main.cpp"
    decls, drives = [], []
    for inp in inputs:
        name = inp.name
        port_name = f"Inp_{name}"          # matches the injected ports
        resolved_type = _resolve_type(inp.data_type, params)
        w = _safe_width(resolved_type)
        if w <= 32:
            ctype = "uint32_t"
        else:
            ctype = "uint64_t"
        mask = (1 << w) - 1 if w < 64 else 0xFFFFFFFFFFFFFFFF
        decls.append(f"    {ctype} {name} = 0;")
        drives.append(f"        top->{port_name} = {name};")
        drives.append(f"        if (cycle % 5 == 0) {name} = ~{name} & 0x{mask:X};")

    tb_content = f"""// Auto-generated SpecIR testbench for {design_name} with input driving
#include "V{design_name}.h"
#include "verilated.h"
#include "verilated_vcd_c.h"

int main(int argc, char** argv) {{
    Verilated::commandArgs(argc, argv);
    V{design_name}* top = new V{design_name};

    Verilated::traceEverOn(true);
    VerilatedVcdC* tfp = new VerilatedVcdC;
    top->trace(tfp, 99);
    tfp->open("sim.vcd");

{chr(10).join(decls)}

    // Reset (active-low)
    top->clk = 0; top->rst_n = {rst_active}; top->eval(); tfp->dump(0);
    top->clk = 1; top->eval(); tfp->dump(1);
    top->clk = 0; top->eval(); tfp->dump(2);
    top->rst_n = {rst_inactive};

    for (int cycle = 0; cycle < {cycles}; cycle++) {{
        top->clk = 1;
{chr(10).join(drives)}
        top->eval();
        tfp->dump(cycle * 2 + 3);

        top->clk = 0;
        top->eval();
        tfp->dump(cycle * 2 + 4);
    }}

    tfp->close();
    delete tfp;
    delete top;
    return 0;
}}
"""
    tb_path.write_text(tb_content)
    logger.info("Generated input‑driven testbench: %s", tb_path)
    return tb_path


def _generate_assertions(
    spec_module: spec_ir.SpecModule,
    assert_lang: str,
    output_dir: Path
) -> Optional[Path]:
    """
    Generate assertions for the design in the requested language.
    Returns the path to the generated assertion file, or None if generation fails.
    """
    try:
        assert_mod = spec_to_assert_convert(spec_module)
    except Exception as e:
        logger.warning("Could not convert spec to assert dialect: %s", e)
        return None

    lang_map = {
        "sva": (assert_to_sva_convert, ".sv"),
        "vhdl": (assert_to_vhdl_convert, ".vhd"),
        "verilog_ovl": (assert_to_verilog_ovl_convert, ".v")
    }
    if assert_lang not in lang_map:
        logger.warning("Unsupported assertion language: %s", assert_lang)
        return None

    converter, suffix = lang_map[assert_lang]
    try:
        code = converter(assert_mod)
    except Exception as e:
        logger.warning("Assertion lowering to %s failed: %s", assert_lang, e)
        return None

    assertions_dir = output_dir / "assertions"
    assertions_dir.mkdir(parents=True, exist_ok=True)
    file_path = assertions_dir / f"{spec_module.name}_assertions{suffix}"
    file_path.write_text(code, encoding="utf-8")
    logger.info("Assertions written to %s", file_path)
    return file_path


def _collect_verilator_coverage(obj_dir: Path, top_module: str) -> Optional[float]:
    """
    Attempt to extract Verilator coverage percentage from a simulation run.
    Verilator must have been invoked with ``--coverage`` (or equivalent).
    Returns a float in [0, 100] or None if coverage data is unavailable or
    the extraction tool cannot be run.
    """
    coverage_dat = obj_dir / "coverage.dat"
    if not coverage_dat.exists():
        logger.debug("No coverage.dat found in %s", obj_dir)
        return None

    # Try to run `verilator_coverage` to produce a text report
    verilator_coverage = shutil.which("verilator_coverage")
    if not verilator_coverage:
        logger.debug("verilator_coverage tool not available; skipping coverage extraction.")
        return None

    try:
        # Generate an annotated coverage report (text)
        annotate_dir = obj_dir / "coverage_annotated"
        annotate_dir.mkdir(exist_ok=True)
        cmd = [
            verilator_coverage,
            "--annotate", str(annotate_dir),
            "--annotate-min", "1",
            str(coverage_dat)
        ]
        subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=True)

        # Read the summary file (if generated) or parse total percentage
        summary_file = annotate_dir / "coverage_summary.txt"
        if summary_file.exists():
            text = summary_file.read_text()
            # Search for something like "Coverage: 85.2%"
            match = re.search(r"Coverage[:\s]+([0-9]+(?:\.[0-9]+)?)\s*%", text, re.IGNORECASE)
            if match:
                return float(match.group(1))
        else:
            # Fallback: parse the top-level annotated HTML? Not robust.
            pass
    except Exception as e:
        logger.warning("Failed to extract Verilator coverage: %s", e)

    return None


def simulate_design(
    spec_module: spec_ir.SpecModule,
    output_dir: Optional[Path] = None,
    cycles: Optional[int] = None,
    config: Optional[Dict[str, Any]] = None,
    verilator_path: Optional[str] = None,
    koika_path: Optional[str] = None,
    assert_lang: Optional[str] = None,
    collect_coverage: bool = False,
) -> SimulationReport:
    """
    Simulate a design from a SpecModule, producing a VCD trace.

    Args:
        spec_module: The SpecIR spec dialect module.
        output_dir: Directory for build artifacts and VCD.
        cycles: Number of simulation cycles (default from config).
        config: Optional config dict (uses global config if None).
        verilator_path: Path to Verilator executable.
        koika_path: Path to the Kōika compiler executable.
        assert_lang: If provided, generate assertions in this language.
        collect_coverage: If True, attempt to enable Verilator coverage and
                          extract the final coverage percentage.

    Returns:
        A SimulationReport containing the outcome, VCD path, coverage, and timing.
    """
    if output_dir is None:
        design_name = spec_module.name
        build_dir = get_config("directories.build", "build")
        output_dir = get_project_root() / build_dir / design_name / "sim"
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if cycles is None:
        cycles = get_config("verification.simulation_cycles", 1000)
    if config is None:
        config = get_config()
    if koika_path is None:
        koika_path = config.get("verification", {}).get("koika_path")

    # Optional rule splitting
    if config.get("verification", {}).get("split_monolithic_rules", False):
        logger.info("Applying rule‑splitting pass (split_monolithic_rules = true).")
        spec_module = split_rules(spec_module)

    design_name = spec_module.name

    # Resolve parameters for type widths
    params: Dict[str, int] = {}
    for name, param_info in spec_module.parameters.items():
        if not isinstance(param_info, dict):
            continue
        default = param_info.get("default")
        if isinstance(default, int):
            params[name] = default
        elif isinstance(default, str):
            try:
                params[name] = int(default)
            except ValueError:
                logger.warning("Could not parse parameter '%s' default '%s' as int; skipping.", name, default)

    # 1. Synthesize with Kōika (Coq DSL) → patched Verilog with input ports
    rtl_dir = output_dir / "rtl"
    rtl_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Lowering SpecIR → RTL (Kōika Coq DSL) ...")
    try:
        koika_to_rtl.convert(spec_module, rtl_dir, koika_path=koika_path)
    except Exception as e:
        raise SimulationError(f"Kōika synthesis failed: {e}") from e

    verilog_path = rtl_dir / f"{design_name}.v"
    if not verilog_path.exists():
        raise SimulationError(f"Verilog file not found: {verilog_path}")

    # 2. Optionally generate assertions
    if assert_lang:
        _generate_assertions(spec_module, assert_lang, output_dir)

    # 3. Generate testbench
    tb_path = output_dir / "sim_main.cpp"
    if spec_module.inputs:
        tb_path = _generate_input_testbench(
            design_name, output_dir, spec_module.inputs, cycles, params
        )
    else:
        verilator_sim.generate_testbench(
            top_module=design_name,
            output_path=tb_path,
            vcd_filename="sim.vcd",
            cycles=cycles
        )

    # 4. Run Verilator (with coverage if requested)
    vcd_file = output_dir / "traces" / f"{design_name}.vcd"
    vcd_file.parent.mkdir(parents=True, exist_ok=True)

    # Build extra Verilator args
    extra_args = ["-Wno-fatal", "--assert"]
    if collect_coverage:
        extra_args.append("--coverage")
        logger.info("Verilator coverage collection enabled.")

    obj_dir = output_dir / "obj"
    logger.info("Running Verilator simulation for %d cycles...", cycles)
    try:
        vcd_result = verilator_sim.simulate(
            rtl_module_or_path=verilog_path,
            top_module=design_name,
            output_dir=obj_dir,
            vcd_path=vcd_file,
            cycles=cycles,
            verilator_path=verilator_path or config.get("verification", {}).get("verilator_path"),
            testbench_path=tb_path,
            extra_verilator_args=extra_args,
        )
    except Exception as e:
        raise SimulationError(f"Verilator simulation failed: {e}") from e

    # 5. Collect coverage if requested
    coverage_pct = None
    if collect_coverage:
        # obj_dir contains the build directory (obj_dir/obj_dir/Vtop)
        # The actual Verilator obj_dir is obj_dir / "obj_dir"
        build_dir_cov = obj_dir / "obj_dir"
        if build_dir_cov.exists():
            coverage_pct = _collect_verilator_coverage(build_dir_cov, design_name)
        else:
            logger.debug("Expected Verilator obj_dir not found for coverage: %s", build_dir_cov)

    logger.info("Simulation complete. VCD: %s", vcd_result)
    return SimulationReport(
        design_name=design_name,
        success=True,
        cycles=cycles,
        coverage=coverage_pct,
        vcd_path=str(vcd_result),
        metadata={"simulation_tool": "verilator"},
    )