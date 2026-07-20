#!/usr/bin/env python3
"""
Standalone script that extracts SpecIR mapping information from a Verilog
file containing ``//@specir`` annotations.  The output is a JSON file in the
same format as ``mapping.json`` produced by the Kōika compiler.

Usage:
  python scripts/extract_mapping.py <verilog_file> [--output mapping.json]
"""

import argparse
import json
import re
import sys
from pathlib import Path

try:
    _SCRIPT_DIR = Path(__file__).resolve().parent
    _PROJECT_ROOT = _SCRIPT_DIR.parent
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

    from specir.backends.koika_compiler import _extract_mapping_from_verilog
    HAS_PROJECT = True
except ImportError:
    HAS_PROJECT = False

def _standalone_extract(verilog_path: Path, design_name: str) -> dict:
    """Fallback mapping extractor (does not depend on the project package)."""
    entries = []
    annotation_re = re.compile(r"//@specir:\s*(\w+)\s*=\s*(\S+)")
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
            kind, ref = ann_match.group(1), ann_match.group(2)

            # Try to extract the signal name from the same line
            code_part = line.split("//@specir")[0]
            reg_match = reg_re.search(code_part)
            signal = reg_match.group(1) if reg_match else ref

            entries.append({
                "rtl_signal": signal,
                "specir_ref": f"module.state[name={ref}]",
                "kind": kind,
                "width": None,
            })

    return {
        "design": design_name,
        "mapping": entries,
    }

def main():
    parser = argparse.ArgumentParser(
        description="Extract SpecIR mapping from Verilog //@specir annotations."
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

    with open(output_path, "w") as f:
        json.dump(mapping_dict, f, indent=2)

    num_entries = len(mapping_dict.get("mapping", []))
    print(f"Extracted {num_entries} mapping entries → {output_path}")

if __name__ == "__main__":
    main()
