# scripts/extract_mapping.py
#
# Standalone script that extracts SpecIR mapping information from a Verilog
# file containing ``//@specir`` annotations.  The output is a JSON file in the
# same format as ``mapping.json`` produced by the Kōika compiler.
#
# Usage:
#   python scripts/extract_mapping.py <verilog_file> [--output mapping.json]

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional, Set

try:
    _SCRIPT_DIR = Path(__file__).resolve().parent
    _PROJECT_ROOT = _SCRIPT_DIR.parent
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

    from specir.backends.koika_compiler import _extract_mapping_from_verilog
    HAS_PROJECT = True
except ImportError:
    HAS_PROJECT = False


def _standalone_extract(verilog_path: Path, design_name: str) -> Dict[str, Any]:
    """
    Fallback mapping extractor (does not depend on the project package).

    Extracts PERF-specific fields from annotations:
    - signal_group: Group for the signal (control, data, state, input, output)
    - relevant_properties: List of property names this signal is relevant to
    - is_relevant_for_proof: Whether this signal matters for proofs

    Annotation format:
        //@specir: <kind> = <ref> [group=<group>] [prop=<prop>]

    Examples:
        //@specir: register = head group=state prop=fifo_no_overflow
        //@specir: rule_condition = do_enqueue.condition group=control
        //@specir: input = data_in group=input prop=fifo_no_overflow
    """
    entries = []

    # Enhanced regex for PERF fields
    annotation_re = re.compile(
        r"//@specir:\s*(\w+)\s*=\s*(\S+)(?:\s+group=(\w+))?(?:\s+prop=([\w,]+))?"
    )
    reg_re = re.compile(
        r"(?:reg|wire)\s*(?:\[[\w\-: ]+\]\s*)?([\w]+)\s*;"
    )

    with open(verilog_path, "r") as f:
        for line in f:
            if "//@specir" not in line:
                continue

            # Extract the annotation part
            ann_match = annotation_re.search(line)
            if not ann_match:
                continue

            kind = ann_match.group(1)
            ref = ann_match.group(2)
            group = ann_match.group(3) if ann_match.group(3) else "state"
            prop_str = ann_match.group(4) if ann_match.group(4) else ""

            # Parse relevant_properties (comma-separated)
            relevant_properties = []
            if prop_str:
                relevant_properties = [p.strip() for p in prop_str.split(",") if p.strip()]

            # Try to extract the signal name from the same line
            code_part = line.split("//@specir")[0]
            reg_match = reg_re.search(code_part)
            signal = reg_match.group(1) if reg_match else ref

            entry = {
                "rtl_signal": signal,
                "specir_ref": f"module.state[name={ref}]",
                "kind": kind,
                "width": None,
                # PERF-specific fields
                "signal_group": group,
                "relevant_properties": relevant_properties,
                "is_relevant_for_proof": bool(relevant_properties) or group in ("state", "control"),
            }
            entries.append(entry)

    return {
        "design": design_name,
        "mapping": entries,
    }


def build_property_signal_index(mapping_data: Dict[str, Any]) -> Dict[str, List[str]]:
    """
    Build a reverse index mapping property names to relevant signal names.

    This is used by PERF's trace_alignment dimension to quickly find signals
    relevant to a specific proof obligation.

    Args:
        mapping_data: The mapping dictionary (with 'mapping' key).

    Returns:
        Dictionary: property_name -> list of RTL signal names.
    """
    index: Dict[str, List[str]] = {}
    for entry in mapping_data.get("mapping", []):
        relevant_props = entry.get("relevant_properties", [])
        rtl_signal = entry.get("rtl_signal", "")

        # Also add entries based on specir_ref heuristic
        # (e.g., if specir_ref contains "property[name=...]")
        specir_ref = entry.get("specir_ref", "")
        import re
        match = re.search(r"property\[name=([^\]]+)\]", specir_ref)
        if match:
            prop_name = match.group(1)
            if prop_name not in index:
                index[prop_name] = []
            if rtl_signal not in index[prop_name]:
                index[prop_name].append(rtl_signal)

        for prop in relevant_props:
            if prop not in index:
                index[prop] = []
            if rtl_signal not in index[prop]:
                index[prop].append(rtl_signal)

    return index


def filter_signals_by_group(mapping_data: Dict[str, Any], group: str) -> List[Dict[str, Any]]:
    """
    Filter mapping entries by signal group.

    Args:
        mapping_data: The mapping dictionary.
        group: The group name to filter by.

    Returns:
        List of mapping entries belonging to the specified group.
    """
    return [
        entry for entry in mapping_data.get("mapping", [])
        if entry.get("signal_group") == group
    ]


def get_relevant_signals(mapping_data: Dict[str, Any], property_name: str) -> List[str]:
    """
    Get RTL signal names relevant to a specific property.

    Uses the property-signal index built by build_property_signal_index.

    Args:
        mapping_data: The mapping dictionary.
        property_name: Name of the property.

    Returns:
        List of RTL signal names relevant to the property.
    """
    index = build_property_signal_index(mapping_data)
    return index.get(property_name, [])


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Extract SpecIR mapping from Verilog //@specir annotations.\n\n"
            "PERF fields (group, prop) are extracted from annotations:\n"
            "  //@specir: <kind> = <ref> [group=<group>] [prop=<prop>]\n\n"
            "Examples:\n"
            "  //@specir: register = head group=state prop=fifo_no_overflow\n"
            "  //@specir: rule_condition = do_enqueue.condition group=control"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("verilog", type=str, help="Path to Verilog file")
    parser.add_argument(
        "--output", "-o", type=str, default=None,
        help="Output JSON file (default: <design>_mapping.json)"
    )
    parser.add_argument(
        "--design", "-d", type=str, default=None,
        help="Design name (default: stem of Verilog file)"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Print detailed information"
    )
    args = parser.parse_args()

    verilog_path = Path(args.verilog).resolve()
    if not verilog_path.exists():
        print(f"Error: Verilog file not found: {verilog_path}", file=sys.stderr)
        sys.exit(1)

    design_name = args.design or verilog_path.stem
    output_path = Path(args.output) if args.output else verilog_path.with_name(f"{design_name}_mapping.json")

    print(f"Extracting mapping from: {verilog_path}")
    print(f"Design name: {design_name}")

    if HAS_PROJECT:
        mapping_obj = _extract_mapping_from_verilog(verilog_path, design_name)
        mapping_dict = mapping_obj.to_json()
    else:
        mapping_dict = _standalone_extract(verilog_path, design_name)

    # Build PERF indices
    property_index = build_property_signal_index(mapping_dict)
    if args.verbose:
        print("\nProperty-Signal Index:")
        for prop, signals in property_index.items():
            print(f"  {prop}: {len(signals)} signals")

        print("\nSignal groups:")
        groups: Dict[str, int] = {}
        for entry in mapping_dict.get("mapping", []):
            group = entry.get("signal_group", "unknown")
            groups[group] = groups.get(group, 0) + 1
        for group, count in groups.items():
            print(f"  {group}: {count} signals")

    # Add PERF fields to the output (already present)
    with open(output_path, "w") as f:
        json.dump(mapping_dict, f, indent=2)

    num_entries = len(mapping_dict.get("mapping", []))
    print(f"\nExtracted {num_entries} mapping entries -> {output_path}")

    if args.verbose:
        print("\nPERF fields included:")
        perf_fields = ["signal_group", "relevant_properties", "is_relevant_for_proof"]
        print(f"  {', '.join(perf_fields)}")
        print("  (property-signal index available via build_property_signal_index)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
