#!/usr/bin/env python3
"""
Standalone script to convert a VCD file into a TraceModule (trace dialect)
and print a summary of signals and cycles.  Useful for debugging the VCD parser.

Usage:
  python scripts/vcd_to_trace.py <vcd_file> [--mapping mapping.json]
"""

import argparse
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from specir.lifting.vcd_to_trace import convert

def main():
    parser = argparse.ArgumentParser(
        description="Convert a VCD file to a trace dialect and show summary."
    )
    parser.add_argument("vcd", type=str, help="Path to VCD file")
    parser.add_argument(
        "--mapping", "-m", type=str, default=None,
        help="Optional mapping.json file for annotations"
    )
    args = parser.parse_args()

    vcd_path = Path(args.vcd).resolve()
    if not vcd_path.exists():
        print(f"Error: VCD file not found: {vcd_path}", file=sys.stderr)
        sys.exit(1)

    mapping_path = Path(args.mapping) if args.mapping else None
    if mapping_path and not mapping_path.exists():
        print(f"Error: mapping file not found: {mapping_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Parsing VCD file: {vcd_path}")
    trace_mod = convert(vcd_path, mapping_file=mapping_path)

    print(f"Trace module: {trace_mod.module_op.trace_name}")
    print(f"  Clock: {trace_mod.clock.clock_name if trace_mod.clock else 'none'}")
    print(f"  Signals: {len(trace_mod.signals)}")
    print(f"  Annotations: {len(trace_mod.annotations)}")
    print(f"  Cycles: {len(trace_mod.cycles)}")

    for i, cycle in enumerate(trace_mod.cycles[:3]):
        print(f"  Cycle {cycle.cycle}: {list(cycle.values.keys())[:5]}...")

if __name__ == "__main__":
    main()
