# src/specir/backends/verilator_sim.py
#
# Builds and runs Verilator simulation from generated RTL (Verilog).
# Produces a VCD trace file for subsequent lifting and analysis.

import subprocess
import shutil
import tempfile
from pathlib import Path
from typing import Dict, Any, List, Optional, Union
from specir.utils.logger import get_logger

logger = get_logger(__name__)


class VerilatorError(Exception):
    """Raised when Verilator build or simulation fails."""
    pass


_DEFAULT_TESTBENCH_TEMPLATE = """
// Auto-generated SpecIR testbench for {top_module}
#include "V{top_module}.h"
#include "verilated.h"
#include "verilated_vcd_c.h"

int main(int argc, char** argv) {{
    Verilated::commandArgs(argc, argv);
    V{top_module}* top = new V{top_module};

    // Enable tracing
    Verilated::traceEverOn(true);
    VerilatedVcdC* tfp = new VerilatedVcdC;
    top->trace(tfp, 99);
    tfp->open("{vcd_filename}");

    // Apply reset
    top->clk = 0;
    top->rst_n = {rst_active};
    top->eval();
    tfp->dump(0);

    top->clk = 1;
    top->eval();
    tfp->dump(1);
    top->clk = 0;
    top->eval();
    tfp->dump(2);

    // Release reset
    top->rst_n = {rst_inactive};

    // Run simulation for {cycles} cycles
    for (int cycle = 0; cycle < {cycles}; cycle++) {{
        // Rising edge
        top->clk = 1;
        top->eval();
        tfp->dump(cycle * 2 + 3);

        // Falling edge
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


def generate_testbench(
    top_module: str,
    output_path: Path,
    vcd_filename: str = "sim.vcd",
    cycles: int = 1000,
    rst_active: int = 0,
    rst_inactive: int = 1
) -> Path:
    """
    Generate a simple C++ testbench for Verilator simulation.

    Args:
        top_module: Name of the top-level Verilog module.
        output_path: Path for the generated testbench .cpp file.
        vcd_filename: Name of the VCD file to generate (not full path).
        cycles: Number of clock cycles to simulate.
        rst_active: Value of rst_n during reset (0 = active-low).
        rst_inactive: Value of rst_n after reset (1 = inactive).

    Returns:
        Path to the generated testbench file.
    """
    content = _DEFAULT_TESTBENCH_TEMPLATE.format(
        top_module=top_module,
        vcd_filename=vcd_filename,
        cycles=cycles,
        rst_active=rst_active,
        rst_inactive=rst_inactive
    )
    output_path.write_text(content)
    logger.info("Generated testbench: %s", output_path)
    return output_path


def build_simulation(
    rtl_paths: List[Path],
    top_module: str,
    output_dir: Path,
    verilator_path: Optional[str] = None,
    trace_enable: bool = True,
    testbench_path: Optional[Path] = None,
    extra_verilator_args: Optional[List[str]] = None
) -> Path:
    """
    Build a Verilator simulation executable.

    Args:
        rtl_paths: List of Verilog source files.
        top_module: Name of the top-level module.
        output_dir: Directory for build artifacts (obj_dir will be created here).
        verilator_path: Path to verilator executable (auto-detected if None).
        trace_enable: Enable VCD tracing (--trace flag).
        testbench_path: Optional user-provided testbench .cpp file.
                         If None, an auto-generated one is used.
        extra_verilator_args: Additional arguments passed to verilator.

    Returns:
        Path to the simulation executable.

    Raises:
        VerilatorError: If verilator is not found or build fails.
    """
    verilator = verilator_path or shutil.which("verilator")
    if not verilator:
        raise VerilatorError(
            "Verilator not found. Install it or set 'verilator_path' in config.yaml."
        )

    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if testbench_path is None:
        testbench_path = output_dir / "sim_main.cpp"
        generate_testbench(
            top_module=top_module,
            output_path=testbench_path,
            vcd_filename="sim.vcd"
        )

    cmd = [verilator, "--cc", "--exe", "--build", "-j", "0", "-Wall"]

    if trace_enable:
        cmd.append("--trace")

    cmd.extend(["--top-module", top_module])
    cmd.extend(["--Mdir", str(output_dir / "obj_dir")])

    if extra_verilator_args:
        cmd.extend(extra_verilator_args)

    for p in rtl_paths:
        cmd.append(str(p))
    cmd.append(str(testbench_path))

    logger.info("Building simulation: %s", " ".join(cmd))

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(output_dir)
        )
    except subprocess.TimeoutExpired:
        raise VerilatorError("Verilator build timed out (5 minutes)")

    if result.returncode != 0:
        logger.error("Verilator build failed:\n%s", result.stderr)
        raise VerilatorError(
            f"Verilator build failed with code {result.returncode}:\n"
            f"{result.stderr[:1000]}"
        )

    sim_exe = output_dir / "obj_dir" / f"V{top_module}"
    if not sim_exe.exists():
        for candidate in (output_dir / "obj_dir").glob("V*"):
            if candidate.is_file() and not candidate.suffix:
                sim_exe = candidate
                break

    if not sim_exe.exists():
        raise VerilatorError(
            f"Simulation executable not found after build. "
            f"Expected: {sim_exe}"
        )

    logger.info("Simulation executable: %s", sim_exe)
    return sim_exe


def run_simulation(
    sim_exe: Path,
    vcd_path: Path,
    cycles: int = 1000,
    timeout: int = 300
) -> Path:
    """
    Run a Verilator simulation executable.

    Args:
        sim_exe: Path to the simulation executable.
        vcd_path: Desired path for the VCD output file.
        cycles: Number of clock cycles to simulate (passed to testbench via env? The testbench
                currently has cycles baked in; this parameter is for potential future use).
        timeout: Maximum simulation wall-clock time in seconds.

    Returns:
        Path to the generated VCD file.

    Raises:
        VerilatorError: If simulation fails or times out.
    """
    logger.info("Running simulation: %s", sim_exe)

    try:
        result = subprocess.run(
            [str(sim_exe)],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(sim_exe.parent)
        )
    except subprocess.TimeoutExpired:
        raise VerilatorError(
            f"Simulation timed out after {timeout}s. "
            "Increase 'simulation_timeout' in config.yaml or reduce cycles."
        )

    if result.returncode != 0:
        logger.error("Simulation failed:\n%s", result.stderr)
        raise VerilatorError(
            f"Simulation exited with code {result.returncode}:\n"
            f"{result.stderr[:1000]}"
        )

    generated_vcd = sim_exe.parent / "sim.vcd"
    if not generated_vcd.exists():
        for candidate in sim_exe.parent.glob("*.vcd"):
            generated_vcd = candidate
            break

    if not generated_vcd.exists():
        raise VerilatorError(
            f"VCD file not found after simulation. "
            f"Expected: {generated_vcd}"
        )

    vcd_path = Path(vcd_path).resolve()
    vcd_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(generated_vcd, vcd_path)

    logger.info("VCD trace written to %s (%d bytes)", vcd_path, vcd_path.stat().st_size)

    return vcd_path


def simulate(
    rtl_module_or_path: Union["RTLModuleContainer", Path, str],
    top_module: Optional[str] = None,
    output_dir: Optional[Path] = None,
    vcd_path: Optional[Path] = None,
    cycles: int = 1000,
    testbench_path: Optional[Path] = None,
    verilator_path: Optional[str] = None,
    keep_build: bool = False,
    coverage: bool = False,
    extra_verilator_args: Optional[List[str]] = None,
) -> Path:
    """
    High-level function: build and run a Verilator simulation.

    This is the primary entry point called by the SpecIR CLI and
    integration tests.

    Args:
        rtl_module_or_path: Either an RTLModuleContainer (from rtl dialect)
                           or a Path/string to a Verilog file.
        top_module: Top-level module name (auto-detected from RTL container
                   if not provided).
        output_dir: Directory for build artifacts and VCD.
        vcd_path: Explicit path for the VCD file. If None, written to
                  output_dir / "sim.vcd".
        cycles: Number of clock cycles to simulate.
        testbench_path: Optional user-provided testbench .cpp file.
        verilator_path: Path to verilator executable.
        keep_build: If True, keep the obj_dir build directory.
        coverage: If True, enable Verilator coverage collection (--coverage).
        extra_verilator_args: Additional Verilator command-line arguments
                              (default: ["-Wno-fatal", "--assert"]).

    Returns:
        Path to the generated VCD file.

    Raises:
        VerilatorError: If any step fails.
    """
    from specir.dialects.rtl_ir import RTLModuleContainer

    if isinstance(rtl_module_or_path, RTLModuleContainer):
        container = rtl_module_or_path
        top_module = top_module or container.design_name
        rtl_paths = []
        for mod in container.modules.values():
            if mod.file_path and mod.file_path.exists():
                rtl_paths.append(mod.file_path)
            else:
                if output_dir:
                    tmp = output_dir / f"{mod.name}.v"
                else:
                    tmp = Path(tempfile.mkdtemp()) / f"{mod.name}.v"
                tmp.parent.mkdir(parents=True, exist_ok=True)
                tmp.write_text(mod.raw_verilog, encoding="utf-8")
                rtl_paths.append(tmp)
        if not rtl_paths:
            raise VerilatorError("No Verilog sources found in RTLModuleContainer")
    elif isinstance(rtl_module_or_path, (str, Path)):
        rtl_paths = [Path(rtl_module_or_path)]
        if not top_module:
            raise ValueError("top_module must be specified when passing a single Verilog file")
    else:
        raise TypeError(
            f"Expected RTLModuleContainer, Path, or str, got {type(rtl_module_or_path)}"
        )

    if output_dir is None:
        output_dir = Path(tempfile.mkdtemp(prefix="specir_sim_"))
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if vcd_path is None:
        vcd_path = output_dir / "sim.vcd"
    vcd_path = Path(vcd_path)

    # Build extra args
    ver_args = extra_verilator_args if extra_verilator_args is not None else []
    if coverage:
        ver_args.append("--coverage")
        logger.info("Verilator coverage collection enabled.")
    # Ensure default arguments are present unless explicitly overridden
    default_args = ["-Wno-fatal", "--assert"]
    for arg in default_args:
        if arg not in ver_args:
            ver_args.append(arg)

    sim_exe = build_simulation(
        rtl_paths=rtl_paths,
        top_module=top_module,
        output_dir=output_dir,
        verilator_path=verilator_path,
        trace_enable=True,
        testbench_path=testbench_path,
        extra_verilator_args=ver_args,
    )

    try:
        vcd = run_simulation(
            sim_exe=sim_exe,
            vcd_path=vcd_path,
            cycles=cycles
        )
    finally:
        if not keep_build:
            obj_dir = output_dir / "obj_dir"
            if obj_dir.exists():
                shutil.rmtree(obj_dir, ignore_errors=True)
                logger.debug("Cleaned up build directory: %s", obj_dir)

    return vcd


def simulate_from_config(
    rtl_path: Path,
    top_module: str,
    config: Optional[Dict[str, Any]] = None
) -> Path:
    """
    Run simulation using settings from the global configuration.

    Supports the current flat configuration structure (e.g.,
    ``verification.simulation_cycles``) and, for forward compatibility,
    also checks a nested ``verification.simulation.cycles`` key.

    Args:
        rtl_path: Path to the Verilog file.
        top_module: Top-level module name.
        config: Optional config dict (uses global config if None).

    Returns:
        Path to the generated VCD file.
    """
    if config is None:
        from specir.utils.config_loader import get_config
        config = get_config()

    verif_cfg = config.get("verification", {})

    sim_cfg = verif_cfg.get("simulation", {})
    cycles = verif_cfg.get("simulation_cycles", sim_cfg.get("cycles", 1000))

    verilator_path = verif_cfg.get("verilator_path")

    build_dir = config.get("directories", {}).get("build", "build")
    output_dir = Path(build_dir) / "sim"

    keep_build = sim_cfg.get("keep_build", False)

    return simulate(
        rtl_module_or_path=rtl_path,
        top_module=top_module,
        output_dir=output_dir,
        cycles=cycles,
        verilator_path=verilator_path,
        keep_build=keep_build
    )