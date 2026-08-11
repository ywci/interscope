# src/specir/cli/sim.py
#
# CLI subcommand `sim` – parses a .specir file, compiles it to RTL
# (via Kōika), builds a Verilator simulation, runs it, and produces
# a VCD trace. Uses the canonical AST-to-SpecIR converter.
# If enabled in config, automatically splits monolithic ite‑rules
# before simulation (see `split_monolithic_rules` in config.yaml).

import argparse
import json
import sys
from pathlib import Path
from typing import Optional
from specir.parser.parser import parse_specir
from specir.parser.validator import validate_specir_file
from specir.lowering.ast_to_spec import convert_ast_to_spec_module
from specir.lowering.split_rules import split_rules
from specir.verification.simulation import simulate_design, SimulationError
from specir.utils.logger import setup_logging, get_logger
from specir.utils.config_loader import load_config, get_project_root
from specir.utils.result_types import SimulationReport

logger = get_logger(__name__)


def _setup_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="specir sim",
        description="Compile a SpecIR design to RTL and run Verilator simulation."
    )
    parser.add_argument("input", type=str, help="Path to the .specir file")
    parser.add_argument("--out-dir", "-o", type=str, default=None,
                        help="Output directory for generated files (default: build/<design>/sim)")
    parser.add_argument("--cycles", "-c", type=int, default=None,
                        help="Number of simulation cycles (default from config)")
    parser.add_argument("--verilator-path", type=str, default=None,
                        help="Path to verilator executable (auto‑detected if omitted)")
    parser.add_argument("--koika-path", type=str, default=None,
                        help="Path to the Kōika compiler executable (default from config or PATH)")
    parser.add_argument("--output-format", choices=["json", "text"], default="text",
                        help="Output format: json for structured data, text for human-readable summary (default: text)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    return parser


def sim_spec(args: argparse.Namespace) -> int:
    """Execute the sim command."""
    log_level = "DEBUG" if args.debug else "INFO"
    setup_logging(level=log_level)

    config = load_config()
    project_root = get_project_root()

    input_path = Path(args.input).resolve()
    if not input_path.exists():
        logger.error(f"Input file not found: {input_path}")
        return 1

    try:
        validate_specir_file(input_path)
    except Exception as e:
        logger.error(f"Schema validation failed: {e}")
        return 1

    try:
        ast_doc = parse_specir(input_path)
    except Exception as e:
        logger.error(f"Parsing failed: {e}")
        return 1

    if not hasattr(ast_doc, "module") or not ast_doc.module:
        logger.error("Parsed spec does not contain a module")
        return 1

    try:
        spec_module = convert_ast_to_spec_module(ast_doc.module)
    except Exception as e:
        logger.error(f"AST → SpecModule conversion failed: {e}")
        return 1

    if config.get("verification", {}).get("split_monolithic_rules", False):
        logger.info("Applying rule‑splitting pass (split_monolithic_rules = true).")
        try:
            spec_module = split_rules(spec_module)
        except Exception as e:
            logger.error(f"Rule splitting failed: {e}")
            return 1

    design_name = spec_module.name
    if args.out_dir:
        out_dir = Path(args.out_dir).resolve()
    else:
        out_dir = project_root / config.get("directories", {}).get("build", "build") / design_name / "sim"
    out_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Simulating design '{design_name}' for {args.cycles or 'default'} cycles...")

    try:
        report = simulate_design(
            spec_module=spec_module,
            output_dir=out_dir,
            cycles=args.cycles,
            config=config,
            verilator_path=args.verilator_path,
            koika_path=args.koika_path
        )
        logger.info(f"Simulation finished. VCD: {report.vcd_path}")

        if args.output_format == "json":
            print(json.dumps(report.to_dict(), indent=2))
        else:
            _print_human_readable(report)

        return 0 if report.success else 1

    except SimulationError as e:
        logger.error(f"Simulation failed: {e}")
        report = SimulationReport(
            design_name=design_name,
            success=False,
            error_message=str(e),
        )
        if args.output_format == "json":
            print(json.dumps(report.to_dict(), indent=2))
        else:
            _print_human_readable(report)
        return 1
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        report = SimulationReport(
            design_name=design_name,
            success=False,
            error_message=str(e),
        )
        if args.output_format == "json":
            print(json.dumps(report.to_dict(), indent=2))
        else:
            _print_human_readable(report)
        return 1


def _print_human_readable(report: SimulationReport) -> None:
    """Print a human‑readable simulation summary."""
    status = "PASS" if report.success else "FAIL"
    print(f"\n===== Simulation Result: {status} =====")
    print(f"  Design:      {report.design_name}")
    print(f"  Cycles:      {report.cycles or 'N/A'}")
    print(f"  VCD trace:   {report.vcd_path or 'N/A'}")
    if report.error_message:
        print(f"  Error:       {report.error_message}")
    if report.duration is not None:
        print(f"  Duration:    {report.duration:.2f}s")
    print("=" * 40 + "\n")


def main() -> int:
    parser = _setup_arg_parser()
    args = parser.parse_args()
    return sim_spec(args)


if __name__ == "__main__":
    sys.exit(main())
