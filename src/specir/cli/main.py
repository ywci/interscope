# src/specir/cli/main.py
#
# Central CLI entry point for InterScope.
# Supports batch processing of multiple .specir files, structured output,
# and external configuration overriding.
#
# When run without --batch, behaviour is identical to the previous
# per‑command entry points (compile, verify, sim, …).
#
# Examples:
#   python -m specir.cli.main compile examples/fifo/fifo.specir
#   python -m specir.cli.main --batch benchmarks/ --compile --output-format json --report-file results.json

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
from specir.utils.logger import setup_logging, get_logger
from specir.utils.config_loader import load_config, get_project_root
from specir.utils.batch import find_specir_files
from specir.utils.reporting import (
    write_json_report,
    write_compilation_csv,
    write_verification_csv,
    write_simulation_csv,
    aggregate_compilation_reports,
    aggregate_verification_reports,
    aggregate_simulation_reports,
)
from specir.utils.result_types import (
    CompilationReport,
    VerificationReport,
    SimulationReport,
    BackendResult,
    ProofObligationResult,
    Status,
)

logger = get_logger(__name__)

def _parse_global_options(argv: Sequence[str]) -> argparse.Namespace:
    """Parse only the global options, leaving the sub‑command and its arguments untouched."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "--batch", nargs="?", const=".", default=None,
        help="Process all .specir files in the given directory (default: current directory)."
    )
    parser.add_argument(
        "--output-format", choices=["json", "text"], default="text",
        help="Output format (default: text)."
    )
    parser.add_argument(
        "--report-file", type=str, default=None,
        help="Save aggregated results to this file (JSON/CSV)."
    )
    parser.add_argument(
        "--config", type=str, default=None,
        help="Path to an external YAML configuration file to merge."
    )
    parser.add_argument(
        "--debug", action="store_true",
        help="Enable debug logging."
    )

    parser.add_argument("remaining", nargs=argparse.REMAINDER)
    args, _ = parser.parse_known_args(argv)
    return args


def _setup_config(global_args: argparse.Namespace) -> None:
    """Load (and optionally merge) configuration before any command runs."""
    external = None
    if global_args.config:
        external = Path(global_args.config).resolve()
        if not external.exists():
            logger.error("External config file not found: %s", external)
            sys.exit(1)
    load_config(force_reload=True, external_config_path=external)


_VALID_COMMANDS = {
    "compile", "verify", "sim", "check", "lift", "query",
    "validate-config", "vcd-to-trace", "extract-mapping",
}

def _run_single(global_args: argparse.Namespace) -> int:
    """Run the requested sub‑command on a single file (backward‑compatible behaviour)."""
    if not global_args.remaining:
        logger.error("No command specified.  Use --help for usage.")
        return 1

    cmd = global_args.remaining[0]
    if cmd.startswith("--"):
        cmd = cmd[2:]

    if cmd not in _VALID_COMMANDS:
        logger.error("Unknown command '%s'.  Use --help for usage.", cmd)
        return 1

    extra_args = []
    if global_args.output_format != "text" and "--output-format" not in global_args.remaining:
        extra_args.extend(["--output-format", global_args.output_format])

    tmp_config = None
    if global_args.config:
        from specir.utils.config_loader import load_config as reload_cfg
        config = reload_cfg()
        fd, tmp_path = tempfile.mkstemp(suffix=".yaml", prefix="specir_merged_")
        os.close(fd)
        tmp_path = Path(tmp_path)
        import yaml
        with open(tmp_path, "w") as f:
            yaml.dump(config, f)
        os.environ["SPECIR_CONFIG"] = str(tmp_path)
        tmp_config = tmp_path

    try:
        if cmd == "compile":
            from specir.cli.compile import main as mod_main
        elif cmd == "verify":
            from specir.cli.verify import main as mod_main
        elif cmd == "sim":
            from specir.cli.sim import main as mod_main
        elif cmd == "check":
            from specir.cli.check import main as mod_main
        elif cmd == "lift":
            from specir.cli.lift import main as mod_main
        elif cmd == "query":
            from specir.cli.query import main as mod_main
        elif cmd == "validate-config":
            from specir.cli.validate_config import main as mod_main
        elif cmd == "vcd-to-trace":
            return subprocess.call([sys.executable, str(get_project_root() / "scripts" / "vcd_to_trace.py")] + global_args.remaining[1:])
        elif cmd == "extract-mapping":
            return subprocess.call([sys.executable, str(get_project_root() / "scripts" / "extract_mapping.py")] + global_args.remaining[1:])
        else:
            logger.error("Unhandled command '%s'.", cmd)
            return 1

        old_argv = sys.argv
        sys.argv = [sys.argv[0]] + global_args.remaining[1:] + extra_args
        try:
            return mod_main()
        finally:
            sys.argv = old_argv
    finally:
        if tmp_config and tmp_config.exists():
            try:
                tmp_config.unlink()
            except Exception:
                pass
        if "SPECIR_CONFIG" in os.environ:
            del os.environ["SPECIR_CONFIG"]


_BATCHABLE = {"compile", "verify", "sim"}

def _run_batch(global_args: argparse.Namespace) -> int:
    if not global_args.remaining:
        logger.error("No sub‑command given for batch mode.")
        return 1
    cmd = global_args.remaining[0]
    if cmd.startswith("--"):
        cmd = cmd[2:]
    if cmd not in _BATCHABLE:
        logger.error("Batch mode is only supported for compile, verify, and sim (got '%s').", cmd)
        return 1

    batch_dir = Path(global_args.batch).resolve()
    if not batch_dir.is_dir():
        logger.error("Batch directory not found: %s", batch_dir)
        return 1

    files = find_specir_files(batch_dir)
    if not files:
        logger.warning("No .specir files found in %s", batch_dir)
        return 0

    logger.info("Batch mode: %d .specir file(s) found.", len(files))

    reports: List[Any] = []
    success_count = 0
    fail_count = 0

    for idx, spec_file in enumerate(files, 1):
        logger.info("[%d/%d] %s", idx, len(files), spec_file.name)
        try:
            report = _run_command_on_file(cmd, spec_file, global_args)
            reports.append(report)
            if isinstance(report, (CompilationReport, SimulationReport)):
                if report.overall_success() if hasattr(report, 'overall_success') else report.success:
                    success_count += 1
                else:
                    fail_count += 1
            elif isinstance(report, VerificationReport):
                if report.overall_status == Status.PASS:
                    success_count += 1
                else:
                    fail_count += 1
        except Exception as exc:
            logger.error("Failed to process %s: %s", spec_file, exc)
            fail_count += 1
            continue

    summary = None
    if cmd == "compile":
        summary = aggregate_compilation_reports(reports)
    elif cmd == "verify":
        summary = aggregate_verification_reports(reports)
    elif cmd == "sim":
        summary = aggregate_simulation_reports(reports)

    if global_args.output_format == "json":
        print(json.dumps({"summary": summary, "detail": [r.to_dict() for r in reports]}, indent=2, default=str))
    else:
        _print_batch_summary(cmd, success_count, fail_count, summary)

    if global_args.report_file:
        ext = Path(global_args.report_file).suffix.lower()
        if ext == ".csv":
            if cmd == "compile":
                write_compilation_csv(reports, global_args.report_file)
            elif cmd == "verify":
                write_verification_csv(reports, global_args.report_file)
            elif cmd == "sim":
                write_simulation_csv(reports, global_args.report_file)
        else:
            write_json_report({"summary": summary, "detail": [r.to_dict() for r in reports]}, global_args.report_file)

    return 0 if fail_count == 0 else 1


def _run_command_on_file(cmd: str, spec_file: Path, global_args: argparse.Namespace) -> Any:
    """
    Execute `specir <cmd> <spec_file>` with JSON output and parse the result
    into the appropriate dataclass.
    """
    args = [sys.executable, "-m", "specir.cli.main", cmd, str(spec_file),
            "--output-format", "json"]

    if global_args.debug:
        args.append("--debug")

    proc = subprocess.run(args, capture_output=True, text=True, timeout=600)
    if proc.returncode != 0:
        raise RuntimeError(f"Command failed (exit {proc.returncode}): {proc.stderr}")

    raw = proc.stdout.strip()
    if not raw:
        raise RuntimeError("Empty output from subprocess")

    data = json.loads(raw)
    if cmd == "compile":
        return CompilationReport(
            design_name=data["design_name"],
            input_file=data["input_file"],
            timestamp=data.get("timestamp", ""),
            results=[BackendResult(**r) for r in data.get("results", [])],
        )
    elif cmd == "verify":
        obligations = []
        for o in data.get("obligations", []):
            obligations.append(ProofObligationResult(
                property=o["property"],
                status=Status(o["status"]),
                backend=o.get("backend", ""),
                iterations=o.get("iterations"),
                proof_script=o.get("proof_script"),
                error_message=o.get("error_message"),
                duration=o.get("duration"),
                details=o.get("details", {}),
            ))
        return VerificationReport(
            design_name=data["design_name"],
            backend=data["backend"],
            timestamp=data.get("timestamp", ""),
            obligations=obligations,
        )
    elif cmd == "sim":
        return SimulationReport(
            design_name=data["design_name"],
            success=data["success"],
            cycles=data.get("cycles"),
            coverage=data.get("coverage"),
            vcd_path=data.get("vcd_path"),
            error_message=data.get("error_message"),
            duration=data.get("duration"),
            metadata=data.get("metadata", {}),
        )
    else:
        raise ValueError(f"Unsupported batch command: {cmd}")


def _print_batch_summary(cmd: str, ok: int, fail: int, summary: Optional[Dict[str, Any]]) -> None:
    """Human‑readable batch result."""
    print(f"\nBatch {cmd} finished: {ok} succeeded, {fail} failed.")
    if summary:
        print(json.dumps(summary, indent=2, default=str))


def main() -> int:
    global_args = _parse_global_options(sys.argv[1:])

    log_level = "DEBUG" if global_args.debug else "INFO"
    setup_logging(level=log_level)

    _setup_config(global_args)

    if global_args.batch is not None:
        return _run_batch(global_args)
    else:
        return _run_single(global_args)


if __name__ == "__main__":
    sys.exit(main())
