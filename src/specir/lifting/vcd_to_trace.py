# src/specir/lifting/vcd_to_trace.py
#
# Converts a VCD (Value Change Dump) file into a TraceModule
# (trace dialect). Uses a built-in minimal parser for the
# Verilator-compatible subset. Optionally attaches SpecIR
# annotations from a mapping JSON file.

from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from collections import defaultdict
from specir.dialects import trace_ir
from specir.utils.logger import get_logger

logger = get_logger(__name__)


def _parse_vcd(vcd_path: Path) -> trace_ir.TraceModule:
    """
    Minimal VCD parser for the subset produced by Verilator.

    Returns a TraceModule with hierarchical signal names and cycle‑by‑cycle
    values sampled at rising edges of the first detected clock.
    """
    trace_mod = trace_ir.TraceModule(
        module_op=trace_ir.TraceModuleOp(trace_name=vcd_path.stem)
    )

    with open(vcd_path, "r") as f:
        lines = f.readlines()

    signals_info: Dict[str, int] = {}   # full hierarchical name -> bit width
    id_to_name: Dict[str, str] = {}     # VCD identifier code -> full name
    id_to_width: Dict[str, int] = {}    # VCD identifier code -> bit width
    clock_id: Optional[str] = None
    initial_values: Dict[str, str] = {} # id code -> value (from $dumpvars)

    i = 0
    n = len(lines)

    while i < n:
        line = lines[i].strip()
        i += 1

        if line.startswith("$var"):
            # Collect tokens until we see "$end" (may be on a later line)
            var_tokens: List[str] = line.split()
            while i < n and "$end" not in var_tokens:
                var_tokens.extend(lines[i].strip().split())
                i += 1
            # Remove leading "$var" and trailing "$end"
            if var_tokens[0] == "$var":
                var_tokens.pop(0)
            if var_tokens and var_tokens[-1] == "$end":
                var_tokens.pop()

            # Expected minimum tokens: type, width, identifier_code, name...
            if len(var_tokens) >= 3:
                var_type = var_tokens[0]
                width_str = var_tokens[1]
                identifier = var_tokens[2]
                # The signal name is the rest of the tokens joined by spaces
                name = " ".join(var_tokens[3:]) if len(var_tokens) > 3 else identifier

                try:
                    width = int(width_str)
                except ValueError:
                    width = 1

                signals_info[name] = width
                id_to_name[identifier] = name
                id_to_width[identifier] = width

                # Heuristic: first wire/reg named "clk" or "clock" is the clock
                if clock_id is None and var_type in ("wire", "reg") and name.lower() in ("clk", "clock"):
                    clock_id = identifier

        elif line == "$dumpvars":
            # Read initial values until $end
            while i < n:
                inner = lines[i].strip()
                i += 1
                if inner == "$end":
                    break
                # Parse value assignment: bxxxx code, Bxxxx code, 0/1/x/z code
                if inner.startswith("b") or inner.startswith("B") or inner.startswith("r"):
                    parts = inner.split()
                    if len(parts) >= 2:
                        initial_values[parts[1]] = parts[0]
                elif inner and inner[0] in "01xXzZ":
                    initial_values[inner[1:]] = inner[0]

        elif line == "$enddefinitions":
            break

    if not id_to_name:
        logger.warning("No signals found in VCD header; trace will be empty.")
        return trace_mod

    for name, width in signals_info.items():
        trace_mod.signals.append(trace_ir.TraceSignalOp(signal_name=name, width=width))

    if clock_id:
        clock_name = id_to_name[clock_id]
        trace_mod.clock = trace_ir.TraceClockOp(clock_name=clock_name, edge="posedge")
    else:
        logger.warning("No clock signal found in VCD; will treat each timestamp as a separate cycle.")

    current_time = 0
    changes: Dict[int, Dict[str, str]] = defaultdict(dict)

    while i < n:
        line = lines[i].strip()
        i += 1
        if not line:
            continue
        if line.startswith("#"):
            try:
                current_time = int(line[1:])
            except ValueError:
                continue
        elif line.startswith("b") or line.startswith("B") or line.startswith("r"):
            parts = line.split()
            if len(parts) >= 2:
                changes[current_time][parts[1]] = parts[0]
        elif line and line[0] in "01xXzZ":
            changes[current_time][line[1:]] = line[0]

    sorted_times = sorted(changes.keys())
    cycle_times: List[int] = []

    if clock_id:
        # Apply initial value if present, else assume 0
        prev_val = initial_values.get(clock_id, "0")
        for t in sorted_times:
            val = changes[t].get(clock_id)
            if val is not None and prev_val in ("0", "x", "X", "z", "Z") and val == "1":
                cycle_times.append(t)
            if val is not None:
                prev_val = val
    else:
        cycle_times = sorted_times

    if not cycle_times:
        logger.warning("No clock edges found; trace will have 0 cycles.")
        return trace_mod

    current_values: Dict[str, Optional[str]] = {}
    # Seed with initial values from $dumpvars
    for code, val in initial_values.items():
        name = id_to_name.get(code)
        if name:
            current_values[name] = val

    # Fill missing signals with None
    for name in signals_info:
        if name not in current_values:
            current_values[name] = None

    time_idx = 0
    cycle_num = 0

    for cycle_time in cycle_times:
        # Advance time to cycle_time, updating current values
        while time_idx < len(sorted_times) and sorted_times[time_idx] <= cycle_time:
            t = sorted_times[time_idx]
            for code, val in changes[t].items():
                name = id_to_name.get(code)
                if name:
                    current_values[name] = val
            time_idx += 1

        # Build cycle data (only non‑None values)
        cycle_vals = {}
        for name, val in current_values.items():
            if val is not None:
                cycle_vals[name] = val

        trace_mod.add_cycle(cycle_num, cycle_vals)
        cycle_num += 1

    logger.info(
        "Parsed VCD: %d signals, %d cycles",
        len(trace_mod.signals),
        len(trace_mod.cycles),
    )
    return trace_mod


def convert(vcd_path: Path, mapping_file: Optional[Path] = None) -> trace_ir.TraceModule:
    """
    Convert a VCD file to a TraceModule.

    Args:
        vcd_path: Path to the VCD file.
        mapping_file: Optional JSON file with RTL‑to‑SpecIR mappings.

    Returns:
        TraceModule containing the trace data.
    """
    if not vcd_path.exists():
        raise FileNotFoundError(f"VCD file not found: {vcd_path}")

    trace_mod = _parse_vcd(vcd_path)

    # If a mapping file is provided, attach annotations
    if mapping_file and mapping_file.exists():
        import json
        with open(mapping_file, "r") as f:
            mapping_data = json.load(f)
        for entry in mapping_data.get("mapping", []):
            ann = trace_ir.TraceAnnotationOp(
                signal_name=entry["rtl_signal"],
                specir_ref=entry["specir_ref"],
                kind=entry["kind"],
            )
            trace_mod.annotations.append(ann)

    return trace_mod
