# src/specir/cli/lift.py
#
# CLI subcommand `lift` – converts a VCD trace to an abstract SpecIR trace YAML.
# Uses an optional mapping file to annotate signals with semantic meaning.

import yaml
import argparse
import sys
from pathlib import Path
from specir.lifting import vcd_to_trace, trace_to_spec
from specir.parser.parser import parse_specir
from specir.lowering.ast_to_spec import convert_ast_to_spec_module
from specir.utils.logger import setup_logging, get_logger

logger = get_logger(__name__)


def _setup_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="specir lift",
        description="Lift a VCD simulation trace to an abstract SpecIR trace (YAML)."
    )
    parser.add_argument("vcd", type=str, help="Path to the VCD file")
    parser.add_argument("--spec", "-s", type=str, required=True,
                        help="Path to the original .specir file (for state/rule/interface info)")
    parser.add_argument("--mapping", "-m", type=str, default=None,
                        help="Path to mapping.json (RTL signal to SpecIR reference)")
    parser.add_argument("--out", "-o", type=str, default=None,
                        help="Output YAML file (default: <vcd>.abstract.yaml)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    return parser


def lift_trace(args: argparse.Namespace) -> int:
    """Execute the lift command."""
    log_level = "DEBUG" if args.debug else "INFO"
    setup_logging(level=log_level)

    vcd_path = Path(args.vcd).resolve()
    if not vcd_path.exists():
        logger.error(f"VCD file not found: {vcd_path}")
        return 1

    spec_path = Path(args.spec).resolve()
    if not spec_path.exists():
        logger.error(f"Spec file not found: {spec_path}")
        return 1

    mapping_path = Path(args.mapping).resolve() if args.mapping else None
    if mapping_path and not mapping_path.exists():
        logger.error(f"Mapping file not found: {mapping_path}")
        return 1

    try:
        spec_ast = parse_specir(spec_path)
    except Exception as e:
        logger.error(f"Failed to parse spec: {e}")
        return 1

    logger.info(f"Converting VCD {vcd_path} to trace dialect...")
    try:
        trace_mod = vcd_to_trace.convert(vcd_path, mapping_file=mapping_path)
    except Exception as e:
        logger.error(f"VCD conversion failed: {e}")
        return 1

    try:
        spec_module = convert_ast_to_spec_module(spec_ast.module)
    except Exception as e:
        logger.error(f"AST to SpecModule conversion failed: {e}")
        return 1

    logger.info("Lifting trace to abstract SpecIR format...")
    try:
        abstract_trace = trace_to_spec.convert(trace_mod, spec_module)
    except Exception as e:
        logger.error(f"Trace lifting failed: {e}")
        return 1

    if args.out:
        out_path = Path(args.out).resolve()
    else:
        out_path = vcd_path.parent / f"{vcd_path.stem}.abstract.yaml"

    with open(out_path, "w", encoding="utf-8") as f:
        yaml.dump(abstract_trace, f, default_flow_style=False, sort_keys=False)

    logger.info(f"Abstract trace written to {out_path}")
    return 0


def main() -> int:
    parser = _setup_arg_parser()
    args = parser.parse_args()
    return lift_trace(args)


if __name__ == "__main__":
    sys.exit(main())
