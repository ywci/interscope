# scripts/vcd_to_trace.py
#
# Standalone script to convert a VCD file into a TraceModule (trace dialect)
# and print a summary of signals and cycles.  Useful for debugging the VCD parser.

import argparse
import sys
import json
from pathlib import Path
from typing import List, Dict, Any, Optional

_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from specir.lifting.vcd_to_trace import convert
from specir.dialects.trace_ir import TraceModule, TracePropertyEvaluation, TraceCycleData
from specir.utils.logger import get_logger, setup_logging

logger = get_logger(__name__)


def extract_failing_trace(
    trace_mod: TraceModule,
    property_name: str,
    window: int = 5,
    relevant_signals: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Extract a window of cycles around a failure for PERF reflection.

    This is the primary function used by PERF's trace_alignment dimension.
    It extracts the cycles around the failing point, optionally filtered
    by relevant signals.

    Args:
        trace_mod: The TraceModule from VCD conversion.
        property_name: Name of the failed property.
        window: Number of cycles before and after the failing cycle to include.
        relevant_signals: Optional list of signal names to include.

    Returns:
        Dictionary with:
            property_name: str
            failing_cycle: int
            window_start: int
            window_end: int
            window: List of {cycle, values} dicts
            signals_available: List of signal names
            property_details: Optional details
            vacuous: bool
    """
    # Find the property evaluation result
    eval_result = None
    for ev in trace_mod.property_evaluations:
        if ev.property_name == property_name:
            eval_result = ev
            break

    if eval_result is None:
        return {
            "property_name": property_name,
            "error": f"Property '{property_name}' not evaluated on this trace",
            "window": [],
            "signals_available": [],
        }

    if eval_result.holds:
        return {
            "property_name": property_name,
            "error": f"Property '{property_name}' holds (no failure to extract)",
            "window": [],
            "signals_available": [],
        }

    failing_cycle = eval_result.failing_cycle
    if failing_cycle is None:
        # No specific cycle recorded; use the last cycle
        failing_cycle = len(trace_mod.cycles) - 1 if trace_mod.cycles else 0

    start = max(0, failing_cycle - window)
    end = min(len(trace_mod.cycles), failing_cycle + window + 1)

    window_data = []
    for i in range(start, end):
        cycle_data = trace_mod.get_all_values_at_cycle(i)
        if cycle_data is None:
            cycle_data = {}
        window_data.append({
            "cycle": i,
            "values": cycle_data,
        })

    # Get all signal names available in this window
    signals_available = set()
    for wd in window_data:
        signals_available.update(wd["values"].keys())

    result = {
        "property_name": property_name,
        "failing_cycle": failing_cycle,
        "window_start": start,
        "window_end": end - 1,
        "window": window_data,
        "signals_available": sorted(signals_available),
        "property_details": eval_result.details,
        "vacuous": eval_result.vacuous,
    }

    # Filter by relevant signals if provided
    if relevant_signals:
        keep_set = set(relevant_signals)
        filtered_window = []
        for wd in result["window"]:
            filtered_window.append({
                "cycle": wd["cycle"],
                "values": {k: v for k, v in wd["values"].items() if k in keep_set},
            })
        result["window"] = filtered_window
        result["signals_available"] = [s for s in result["signals_available"] if s in keep_set]

    return result


def filter_relevant_signals(
    trace_mod: TraceModule,
    relevant_signals: List[str],
) -> TraceModule:
    """
    Filter the trace to only include relevant signals.

    This is used by PERF to reduce the trace size for reflection.

    Args:
        trace_mod: The original TraceModule.
        relevant_signals: List of signal names to keep.

    Returns:
        A new TraceModule containing only the relevant signals.
    """
    import copy
    filtered = copy.deepcopy(trace_mod)

    keep_set = set(relevant_signals)

    # Filter signals
    filtered.signals = [
        s for s in trace_mod.signals
        if s.signal_name in keep_set
    ]

    # Filter annotations
    filtered.annotations = [
        a for a in trace_mod.annotations
        if a.signal_name in keep_set
    ]

    # Filter cycle values
    for cycle in filtered.cycles:
        cycle.values = {
            k: v for k, v in cycle.values.items()
            if k in keep_set
        }

    # Rebuild signal groups
    filtered.signal_groups = {}
    for ann in filtered.annotations:
        group = ann.signal_group
        if group not in filtered.signal_groups:
            filtered.signal_groups[group] = []
        filtered.signal_groups[group].append(ann.signal_name)

    return filtered


def filter_by_group(
    trace_mod: TraceModule,
    group: str,
) -> TraceModule:
    """
    Filter the trace to only include signals from a specific group.

    This is used by PERF to focus on control signals, data signals, etc.

    Args:
        trace_mod: The original TraceModule.
        group: Group name ("control", "data", "state", "input", "output").

    Returns:
        A new TraceModule containing only signals from the specified group.
    """
    relevant_signals = trace_mod.get_signals_by_group(group)
    return filter_relevant_signals(trace_mod, relevant_signals)


def get_signal_groups_summary(trace_mod: TraceModule) -> Dict[str, List[str]]:
    """
    Get a summary of signal groups with their signal names.

    This is used by PERF for efficient trace processing.

    Args:
        trace_mod: The TraceModule.

    Returns:
        Dictionary mapping group name to list of signal names.
    """
    return trace_mod.get_all_signal_groups()


def _setup_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Convert a VCD file to a trace dialect and show summary.\n\n"
            "PERF options:\n"
            "  --extract-fail <property>  Extract a window around a property failure\n"
            "  --window N                 Number of cycles before/after failure (default: 5)\n"
            "  --filter-group <group>     Filter trace by signal group\n"
            "  --show-groups              Show signal group summary"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("vcd", type=str, help="Path to VCD file")
    parser.add_argument(
        "--mapping", "-m", type=str, default=None,
        help="Optional mapping.json file for annotations"
    )
    parser.add_argument(
        "--output", "-o", type=str, default=None,
        help="Output trace YAML file (default: <vcd>.trace.yaml)"
    )

    # PERF-specific options
    parser.add_argument(
        "--extract-fail", "-e", type=str, default=None,
        help="Extract a window around a property failure for PERF reflection"
    )
    parser.add_argument(
        "--window", "-w", type=int, default=5,
        help="Number of cycles before/after failure (default: 5)"
    )
    parser.add_argument(
        "--filter-group", "-g", type=str, default=None,
        choices=["control", "data", "state", "input", "output"],
        help="Filter trace by signal group"
    )
    parser.add_argument(
        "--show-groups", action="store_true",
        help="Show signal group summary"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Print detailed information"
    )
    return parser


def main() -> int:
    parser = _setup_arg_parser()
    args = parser.parse_args()

    vcd_path = Path(args.vcd).resolve()
    if not vcd_path.exists():
        print(f"Error: VCD file not found: {vcd_path}", file=sys.stderr)
        return 1

    mapping_path = Path(args.mapping) if args.mapping else None
    if mapping_path and not mapping_path.exists():
        print(f"Error: mapping file not found: {mapping_path}", file=sys.stderr)
        return 1

    setup_logging(level="DEBUG" if args.verbose else "INFO")

    print(f"Parsing VCD file: {vcd_path}")
    trace_mod = convert(vcd_path, mapping_file=mapping_path)

    # Apply group filtering if requested
    if args.filter_group:
        trace_mod = filter_by_group(trace_mod, args.filter_group)
        print(f"Filtered to group: {args.filter_group}")

    # Print summary
    print(f"Trace module: {trace_mod.module_op.trace_name}")
    print(f"  Clock: {trace_mod.clock.clock_name if trace_mod.clock else 'none'}")
    print(f"  Signals: {len(trace_mod.signals)}")
    print(f"  Annotations: {len(trace_mod.annotations)}")
    print(f"  Cycles: {len(trace_mod.cycles)}")

    # Show signal groups if requested
    if args.show_groups:
        print("\nSignal groups:")
        groups = trace_mod.get_all_signal_groups()
        for group, signals in groups.items():
            print(f"  {group}: {len(signals)} signals")
            if args.verbose:
                print(f"    {', '.join(signals[:10])}{' ...' if len(signals) > 10 else ''}")

    # Extract failing trace if requested
    if args.extract_fail:
        result = extract_failing_trace(
            trace_mod,
            args.extract_fail,
            window=args.window,
        )
        print("\nFailing trace extraction:")
        if "error" in result:
            print(f"  Error: {result['error']}")
        else:
            print(f"  Property: {result['property_name']}")
            print(f"  Failing cycle: {result['failing_cycle']}")
            print(f"  Window: cycles {result['window_start']} to {result['window_end']}")
            print(f"  Signals available: {len(result['signals_available'])}")
            if args.verbose:
                print(f"    {', '.join(result['signals_available'][:20])}")
            print(f"  Vacuous: {result.get('vacuous', False)}")
            if result.get('property_details'):
                print(f"  Details: {result['property_details']}")
            # Print the first few cycles of the window
            print("\n  Window data (first 3 cycles):")
            for wd in result["window"][:3]:
                values_str = ", ".join(
                    f"{k}={v}" for k, v in list(wd["values"].items())[:5]
                )
                print(f"    Cycle {wd['cycle']}: {values_str}")

    # Output YAML if requested
    if args.output:
        output_path = Path(args.output).resolve()
    else:
        output_path = vcd_path.parent / f"{vcd_path.stem}.trace.yaml"

    # Convert to YAML (simple dump of cycle data)
    import yaml
    trace_data = {
        "trace": {
            "name": trace_mod.module_op.trace_name,
            "clock": trace_mod.clock.clock_name if trace_mod.clock else None,
            "cycles": [
                {
                    "cycle": c.cycle,
                    "values": c.values,
                }
                for c in trace_mod.cycles
            ]
        }
    }
    if trace_mod.property_evaluations:
        trace_data["trace"]["property_evaluations"] = [
            eval_.to_dict() for eval_ in trace_mod.property_evaluations
        ]

    with open(output_path, "w") as f:
        yaml.dump(trace_data, f, default_flow_style=False)

    print(f"\nTrace data written to: {output_path}")

    return 0


__all__ = [
    "convert",
    "extract_failing_trace",
    "filter_relevant_signals",
    "filter_by_group",
    "get_signal_groups_summary",
    "TraceModule",
    "TracePropertyEvaluation",
]


if __name__ == "__main__":
    sys.exit(main())
