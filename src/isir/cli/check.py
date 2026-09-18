# src/isir/cli/check.py
#
# CLI subcommand `check` – verifies properties from a .isir file
# against an abstract trace YAML (as produced by the `lift` subcommand).

import argparse
import sys
from pathlib import Path

import jsonschema
import yaml

from isir.parser.parser import parse_isir
from isir.verification.property_checker import check_all_properties
from isir.utils.logger import setup_logging, get_logger

logger = get_logger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
TRACE_SCHEMA_PATH = PROJECT_ROOT / "conf" / "schemas" / "trace_schema.yaml"


def _setup_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="isir check",
        description="Check properties in an ISIR design against an abstract trace."
    )
    parser.add_argument(
        "trace",
        type=str,
        help="Path to abstract trace YAML file (from `isir lift`)",
    )
    parser.add_argument(
        "--spec", "-s",
        type=str,
        required=True,
        help="Path to the original .isir file",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--no-validate",
        action="store_true",
        help="Skip JSON-schema validation of the trace file",
    )
    return parser


def _load_trace_schema() -> dict:
    """Load the abstract trace JSON schema from conf/schemas/."""
    if not TRACE_SCHEMA_PATH.exists():
        raise FileNotFoundError(f"Trace schema not found: {TRACE_SCHEMA_PATH}")
    with TRACE_SCHEMA_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _validate_trace(trace_data: dict, schema: dict) -> None:
    """Validate the trace dict against the schema.

    Raises:
        jsonschema.ValidationError: if the trace does not conform.
        jsonschema.SchemaError: if the schema itself is invalid.
    """
    jsonschema.validate(instance=trace_data, schema=schema)


def _extract_cycles(trace_data: dict) -> list:
    """Return the list of cycles from a trace dict.

    Supports both formats:
      - wrapped:   {"trace": {"cycles": [...]}}   (new schema)
      - flat:      {"cycles": [...]}              (legacy)
    """
    if isinstance(trace_data.get("cycles"), list):
        return trace_data["cycles"]
    trace = trace_data.get("trace")
    if isinstance(trace, dict) and isinstance(trace.get("cycles"), list):
        return trace["cycles"]
    return []


def check_trace(args: argparse.Namespace) -> int:
    """Execute the check command."""
    log_level = "DEBUG" if args.debug else "INFO"
    setup_logging(level=log_level)

    trace_path = Path(args.trace).resolve()
    if not trace_path.exists():
        logger.error("Trace file not found: %s", trace_path)
        return 1

    spec_path = Path(args.spec).resolve()
    if not spec_path.exists():
        logger.error("Spec file not found: %s", spec_path)
        return 1

    try:
        spec = parse_isir(spec_path)
    except Exception as e:
        logger.error("Failed to parse spec: %s", e)
        return 1

    if not hasattr(spec, "module") or not spec.module:
        logger.error("Parsed spec does not contain a module")
        return 1

    try:
        with open(trace_path, "r", encoding="utf-8") as f:
            trace_data = yaml.safe_load(f)
    except Exception as e:
        logger.error("Failed to load trace YAML: %s", e)
        return 1

    if not isinstance(trace_data, dict):
        logger.error("Invalid trace format: top-level YAML must be a mapping")
        return 1

    if not args.no_validate:
        try:
            schema = _load_trace_schema()
            _validate_trace(trace_data, schema)
            logger.debug("Trace validated against schema: %s", TRACE_SCHEMA_PATH)
        except jsonschema.ValidationError as e:
            logger.error("Trace schema validation failed: %s", e.message)
            logger.error("  Path: %s", list(e.path))
            logger.error("  Schema path: %s", list(e.schema_path))
            return 1
        except jsonschema.SchemaError as e:
            logger.error("Trace schema itself is invalid: %s", e.message)
            return 1
        except FileNotFoundError as e:
            logger.warning("Trace schema not available; skipping validation: %s", e)
        except Exception as e:
            logger.warning("Could not validate trace: %s", e)

    trace_cycles = _extract_cycles(trace_data)
    if not trace_cycles:
        logger.error(
            "Invalid trace format: no 'cycles' list found "
            "(expected either top-level 'cycles' or 'trace.cycles')"
        )
        return 1

    try:
        results = check_all_properties(spec.module.properties, trace_cycles)
    except Exception as e:
        logger.error("Property checking failed: %s", e)
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
