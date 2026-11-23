# src/isir/verification/sat_gate/rtlil.py
#
# Static RTLIL elaboration + signal mapping. This is the Path A static
# frontend: Yosys runs the pass script, and the flattened RTLIL exposes the named
# signals that the dual-encoder agreement cross-checks against the dynamic path.

import re
import subprocess
from pathlib import Path
from typing import Dict, List, Optional


class RtlilError(Exception):
    pass


PASS_SCRIPT = (
    "hierarchy -check -top {top}; proc; flatten; "
    "async2sync; formalff -clk2ff; setundef -undriven -anyseq; memory -nomap; "
    "techmap; opt_clean; write_rtlil {out}"
)


def run_yosys_pass(rtl_file: Path, top: str, out_dir: Path) -> str:
    """Run the  Yosys pass script; return the flattened RTLIL text."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{top}.rtlil"
    script = PASS_SCRIPT.format(top=top, out=out)
    r = subprocess.run(
        ["yosys", "-p", f"read_verilog -sv {rtl_file}; {script}", "-q"],
        capture_output=True, text=True,
)
    if r.returncode != 0:
        raise RtlilError(r.stderr[-500:])
    return out.read_text()


def _wire_match(line: str) -> Optional[tuple]:
    """Match ``wire [width N] input|output|inout [id] name`` -> (width, name)."""
    m = re.match(r"\s*wire(?: width (\d+))? (?:input|output|inout)(?: \d+)? (\S+)", line)
    if not m:
        return None
    width = int(m.group(1)) if m.group(1) else 1
    return width, m.group(2)


def parse_rtlil(rtlil_text: str) -> Dict[str, List[dict]]:
    """Parse a minimal RTLIL: wires (name + width) and cells (type + name)."""
    wires: List[dict] = []
    cells: List[dict] = []
    for line in rtlil_text.splitlines():
        s = line.strip()
        wm = _wire_match(s)
        if wm:
            width, name = wm
            wires.append({"width": width, "name": name})
            continue
        m = re.match(r"cell (\S+) (\S+)", s)
        if m:
            cells.append({"type": m.group(1), "name": m.group(2)})
    return {"wires": wires, "cells": cells}


def signal_map(rtlil_text: str) -> Dict[str, int]:
    """Signal name -> width over all wires (ports and internal signals).

    The direct-path output port ``\\count_out`` maps to the ISIR state ``count``
    via the emitter's mapping; the dual-encoder test reconciles the two names.
    """
    sig: Dict[str, int] = {}
    for line in rtlil_text.splitlines():
        wm = _wire_match(line)
        if wm:
            width, name = wm
            sig[name.replace("\\", "")] = width
    return sig
