# src/specir/cli/check.py
#
# CLI subcommand `check` – verifies properties from a .specir file
# against an abstract trace YAML (as produced by the `lift` subcommand).

import argparse
import sys
from pathlib import Path

import yaml

from specir.parser.parser import parse_specir
from specir.verification.property_checker import check_all_properties
from specir.utils.logger import setup_logging, get_logger

logger = get_logger(__name__)


def _setup_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="specir check",
        description="Check properties in a SpecIR design against an abstract trace."
    )
    parser.add_argument("trace", type=str, help="Path to abstract trace YAML file (from `lift`)")
    parser.add_argument("--spec", "-s", type=str, required=True,
                        help="Path to the original .specir file")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    return parser


def check_trace(args: argparse.Namespace) -> int:
    """Execute the check command."""
    log_level = "DEBUG" if args.debug else "INFO"
    setup_logging(level=log_level)

    trace_path = Path(args.trace).resolve()
    if not trace_path.exists():
        logger.error(f"Trace file not found: {trace_path}")
        return 1

    spec_path = Path(args.spec).resolve()
    if not spec_path.exists():
        logger.error(f"Spec file not found: {spec_path}")
        return 1

    try:
        spec = parse_specir(spec_path)
    except Exception as e:
        logger.error(f"Failed to parse spec: {e}")
        return 1

    if not hasattr(spec, "module") or not spec.module:
        logger.error("Parsed spec does not contain a module")
        return 1

    try:
        with open(trace_path, "r", encoding="utf-8") as f:
            trace_data = yaml.safe_load(f)
    except Exception as e:
        logger.error(f"Failed to load trace YAML: {e}")
        return 1

    if "cycles" not in trace_data or not isinstance(trace_data["cycles"], list):
        logger.error("Invalid trace format: missing 'cycles' list")
        return 1

    trace_cycles = trace_data["cycles"]

    try:
        results = check_all_properties(spec.module.properties, trace_cycles)
    except Exception as e:
        logger.error(f"Property checking failed: {e}")
        return 1

    print("\n===== Property Check Summary =====")
    all_hold = True
    for result in results:
        name = result.name
        holds = result.holds
        vacuous = result.vacuous
        status = "PASS" if holds else "FAIL"
        if vacuous:
            status += " (vacuous)"
        print(f"{status}: {name}")
        if not holds:
            all_hold = False
            if result.failing_cycle is not None:
                print(f"   Failing cycle: {result.failing_cycle}")
            if result.detail:
                print(f"   Detail: {result.detail}")
    print("==================================\n")

    return 0 if all_hold else 1


def main() -> int:
    parser = _setup_arg_parser()
    args = parser.parse_args()
    return check_trace(args)


if __name__ == "__main__":
    sys.exit(main())
