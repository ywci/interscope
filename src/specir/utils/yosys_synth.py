# src/specir/utils/yosys_synth.py
#
# Yosys synthesis utility for extracting area, delay, and (optionally) power
# metrics from Verilog RTL.

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from specir.utils.config_loader import get_config, get_project_root
from specir.utils.logger import get_logger

logger = get_logger(__name__)


class YosysSynthesisError(Exception):
    """Raised when Yosys synthesis fails."""
    pass


def synthesize_rtl(
    verilog_path: Path,
    top_module: str,
    output_dir: Optional[Path] = None,
    library: Optional[str] = None,
    flatten: bool = True,
    extra_args: Optional[List[str]] = None,
    timeout: int = 300,
) -> Dict[str, Any]:
    """
    Run Yosys synthesis on a Verilog file and return area/delay estimates.

    The flow uses the built‑in ``synth`` command (or a custom script) to
    produce a gate‑level netlist from which area and cell count are
    extracted.  If a liberty file is provided via *library*, timing
    information is also reported.

    Args:
        verilog_path: Path to the input Verilog file.
        top_module: Name of the top‑level module.
        output_dir: Optional directory for generated netlists/reports.
        library: Path to a Liberty (.lib) file for technology mapping.
        flatten: Whether to flatten the design before synthesis.
        extra_args: Extra command‑line arguments passed to Yosys.
        timeout: Maximum runtime in seconds.

    Returns:
        A dictionary with keys:
            area (float or None): Total area in technology units.
            cells (int or None): Number of cells after mapping.
            delay (float or None): Estimated critical path delay (ps).
            netlist (Path or None): Path to the synthesised Verilog file.
            log (str): Full Yosys log.
    """
    config = get_config()
    yosys_path = shutil.which("yosys") or config.get("tools", {}).get("yosys")
    if not yosys_path:
        raise YosysSynthesisError(
            "Yosys not found.  Install it or set 'tools.yosys' in conf/config.yaml."
        )

    verilog_path = verilog_path.resolve()
    if not verilog_path.exists():
        raise FileNotFoundError(f"Verilog file not found: {verilog_path}")

    if output_dir is None:
        output_dir = Path(tempfile.mkdtemp(prefix="specir_synth_"))
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    tcl_script = output_dir / "synth.ys"
    netlist_file = output_dir / f"{top_module}_synth.v"
    log_file = output_dir / "synth.log"

    lines = []
    lines.append(f"read_verilog {verilog_path}")
    if flatten:
        lines.append(f"hierarchy -top {top_module}")
        lines.append("flatten")
    else:
        lines.append(f"hierarchy -check -top {top_module}")

    if library:
        lines.append(f"synth -top {top_module}")
        lines.append(f"dfflibmap -liberty {library}")
        lines.append(f"abc -liberty {library}")
    else:
        lines.append(f"synth -top {top_module}")

    lines.append(f"write_verilog -noattr {netlist_file}")
    lines.append("tee -o {} stat".format(str(log_file)))
    tcl_script.write_text("\n".join(lines))

    cmd = [yosys_path, "-s", str(tcl_script)]
    if extra_args:
        cmd.extend(extra_args)

    logger.info("Running Yosys synthesis: %s", " ".join(cmd))
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(output_dir),
        )
    except subprocess.TimeoutExpired:
        raise YosysSynthesisError(f"Yosys synthesis timed out after {timeout}s")

    if result.returncode != 0:
        logger.error("Yosys stderr:\n%s", result.stderr)
        raise YosysSynthesisError(
            f"Yosys synthesis failed with code {result.returncode}:\n{result.stderr[:1000]}"
        )

    log_text = result.stdout + "\n" + result.stderr
    logger.debug("Yosys output:\n%s", log_text[:2000])

    area = _parse_area(log_text)
    cells = _parse_cell_count(log_text)
    delay = _parse_delay(log_text)

    return {
        "area": area,
        "cells": cells,
        "delay": delay,
        "netlist": netlist_file if netlist_file.exists() else None,
        "log": log_text,
    }


def _parse_area(log: str) -> Optional[float]:
    """Extract total area from Yosys stat output.

    Looks for lines such as:
        Area: 1234.56 um^2
    or
        Chip area for top module: 1234.56
    """
    for line in log.splitlines():
        line = line.strip()
        if line.startswith("Chip area for top module"):
            parts = line.split(":")
            if len(parts) >= 2:
                try:
                    return float(parts[1].strip().split()[0])
                except ValueError:
                    pass
        if line.startswith("Area:"):
            # Typical format: "Area: 1234.56 um^2"
            tokens = line.split()
            for token in tokens:
                try:
                    return float(token)
                except ValueError:
                    continue
    return None


def _parse_cell_count(log: str) -> Optional[int]:
    """Extract number of cells after mapping.

    Looks for lines like:
        Number of cells:              1234
    """
    for line in log.splitlines():
        if "Number of cells:" in line:
            parts = line.split(":")
            if len(parts) >= 2:
                try:
                    return int(parts[1].strip())
                except ValueError:
                    pass
    return None


def _parse_delay(log: str) -> Optional[float]:
    """Extract critical path delay from a timing report (if available).

    For simplicity, we look for lines containing 'Delay' and a number.
    """
    for line in log.splitlines():
        if "Delay" in line:
            # Example: "Delay: 1234.56 ps"
            tokens = line.split()
            for token in tokens:
                try:
                    return float(token)
                except ValueError:
                    continue
    return None


def synthesize_from_config(
    verilog_path: Path,
    top_module: str,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Convenience function that uses configuration defaults."""
    if config is None:
        config = get_config()
    synth_cfg = config.get("synthesis", {})
    return synthesize_rtl(
        verilog_path=verilog_path,
        top_module=top_module,
        library=synth_cfg.get("library"),
        flatten=synth_cfg.get("flatten", True),
        timeout=synth_cfg.get("timeout", 300),
    )
