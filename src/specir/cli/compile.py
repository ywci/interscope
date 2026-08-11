# src/specir/cli/compile.py
#
# CLI subcommand `compile` – parses a .specir file, lowers to the
# chosen backend, and generates output (RTL, Coq, ACL2, assertions).
# Uses the canonical AST-to-SpecIR conversion and the consolidated
# synthesis pass (koika_to_rtl) for RTL generation.
# Optionally runs Verilator simulation after RTL generation.
# If enabled in config, automatically splits monolithic ite‑rules
# before lowering (see `split_monolithic_rules` in config.yaml).

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Optional, Dict, List
from specir.parser.parser import parse_specir
from specir.parser.validator import validate_specir_file
from specir.lowering.ast_to_spec import convert_ast_to_spec_module
from specir.lowering.split_rules import split_rules
from specir.utils.logger import setup_logging, get_logger
from specir.utils.config_loader import load_config, get_project_root
from specir.utils.result_types import CompilationReport, BackendResult

logger = get_logger(__name__)


def _setup_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="specir compile",
        description="Compile a SpecIR specification to various backends."
    )
    parser.add_argument("input", type=str, help="Path to the .specir file")
    parser.add_argument("--out-dir", "-o", type=str, default=None,
                        help="Output directory (default: build/<design_name>/ under project root)")
    parser.add_argument("--backend", "-b", choices=["koika", "acl2", "assert"], default="koika",
                        help="Target backend (default: koika)")
    parser.add_argument("--assert-lang", choices=["sva", "vhdl", "verilog_ovl"], default="sva",
                        help="When backend=assert, choose assertion language (default: sva)")
    parser.add_argument("--no-rtl", action="store_true",
                        help="Skip RTL generation (only produce Coq/ACL2/assert files)")
    parser.add_argument("--simulate", action="store_true",
                        help="After RTL generation, run Verilator simulation and produce a VCD trace")
    parser.add_argument("--cycles", type=int, default=None,
                        help="Number of cycles for simulation (default from config)")
    parser.add_argument("--verilator-path", type=str, default=None,
                        help="Path to verilator executable (auto‑detected if omitted)")
    parser.add_argument("--koika-path", type=str, default=None,
                        help="Path to the Kōika compiler executable (default from config or PATH)")
    parser.add_argument("--output-format", choices=["json", "text"], default="text",
                        help="Output format: json for structured data, text for human-readable summary (default: text)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    return parser


def _extract_width(data_type: str) -> Optional[int]:
    """Return bit width from a type string like 'bits<8>'."""
    if data_type == "bool":
        return 1
    if data_type.startswith("bits<"):
        try:
            return int(data_type[5:-1])
        except ValueError:
            pass
    return None


def _timed_backend_compile(backend_name: str, func, *args, **kwargs) -> BackendResult:
    """Execute a compilation function, capturing result, duration and errors."""
    start = time.time()
    try:
        result = func(*args, **kwargs)
        success = result == 0
        duration = time.time() - start
        return BackendResult(
            backend=backend_name,
            success=success,
            duration=duration,
            error_message=None if success else "Compilation failed (see logs)"
        )
    except Exception as e:
        duration = time.time() - start
        logger.error("Backend %s compilation error: %s", backend_name, e)
        return BackendResult(
            backend=backend_name,
            success=False,
            duration=duration,
            error_message=str(e)
        )


def compile_spec(args: argparse.Namespace) -> int:
    """Execute the compile command."""
    log_level = "DEBUG" if args.debug else "INFO"
    setup_logging(level=log_level)

    config = load_config()

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
        base_out = Path(args.out_dir).resolve()
    else:
        base_out = get_project_root() / config.get("directories", {}).get("build", "build")
    out_dir = base_out / design_name
    out_dir.mkdir(parents=True, exist_ok=True)

    report = CompilationReport(
        design_name=design_name,
        input_file=str(input_path)
    )

    logger.info(f"Compiling '{design_name}' → {args.backend} (output: {out_dir})")

    try:
        if args.backend == "koika":
            results = _compile_koika(spec_module, out_dir, args, config)
        elif args.backend == "acl2":
            results = _compile_acl2(spec_module, out_dir, args)
        elif args.backend == "assert":
            results = _compile_assert(spec_module, out_dir, args)
        else:
            logger.error(f"Unsupported backend: {args.backend}")
            return 1

        report.results.extend(results)

        if args.simulate and args.backend == "koika" and not args.no_rtl:
            _run_simulation(spec_module, out_dir, args, config)

        if args.output_format == "json":
            print(json.dumps(report.to_dict(), indent=2))
        else:
            _print_human_readable(report)

        return 0 if report.overall_success() else 1

    except NotImplementedError as e:
        logger.error(f"Backend '{args.backend}' not fully implemented: {e}")
        return 1
    except Exception as e:
        logger.error(f"Compilation failed: {e}")
        logger.debug("Traceback:", exc_info=True)
        return 1


def _run_simulation(spec_module, out_dir, args, config) -> int:
    """Run Verilator simulation after successful Kōika compilation."""
    from specir.verification.simulation import simulate_design, SimulationError

    sim_dir = out_dir / "sim"
    sim_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Running Verilator simulation for '{spec_module.name}'...")
    try:
        vcd_file = simulate_design(
            spec_module=spec_module,
            output_dir=sim_dir,
            cycles=args.cycles,
            config=config,
            verilator_path=args.verilator_path,
            koika_path=args.koika_path
        )
        logger.info(f"Simulation complete. VCD: {vcd_file}")
        logger.info(f"Next: specir lift {vcd_file} --mapping {out_dir / 'rtl' / 'mapping.json'}")
        return 0
    except SimulationError as e:
        logger.error(f"Simulation failed: {e}")
        return 1


def _compile_koika(spec_module, out_dir, args, config) -> List[BackendResult]:
    """Compile to Kōika/Coq (verification model) and optionally RTL (synthesis)."""
    from specir.lowering.spec_to_koika import convert as spec_to_koika_convert
    from specir.lowering.koika_to_rtl import convert as koika_rtl_convert

    results = []

    logger.info("Lowering spec → Kōika verification model...")
    start = time.time()
    try:
        koika_mod = spec_to_koika_convert(spec_module)
        coq_dir = out_dir / "coq"
        coq_dir.mkdir(exist_ok=True)
        coq_file = coq_dir / f"{spec_module.name}.v"
        coq_code = koika_mod.to_coq_code() if hasattr(koika_mod, 'to_coq_code') else _generate_coq_from_module(koika_mod)
        coq_file.write_text(coq_code, encoding="utf-8")
        logger.info(f"Coq/Kōika verification file written to {coq_file}")
        results.append(BackendResult(
            backend="koika",
            success=True,
            duration=time.time() - start,
            output_file=str(coq_file)
        ))
    except Exception as e:
        logger.error(f"Failed to write Coq file: {e}")
        results.append(BackendResult(
            backend="koika",
            success=False,
            duration=time.time() - start,
            error_message=str(e)
        ))
        return results  # No RTL if Coq failed

    if not args.no_rtl:
        logger.info("Lowering SpecIR → RTL (Kōika synthesis)...")
        start = time.time()
        rtl_dir = out_dir / "rtl"
        rtl_dir.mkdir(exist_ok=True)
        try:
            rtl_container = koika_rtl_convert(
                spec_module,
                rtl_dir,
                koika_path=args.koika_path,
            )
            results.append(BackendResult(
                backend="rtl",
                success=True,
                duration=time.time() - start,
                output_file=str(rtl_dir / f"{spec_module.name}.v")
            ))
        except Exception as e:
            logger.error(f"RTL generation failed: {e}")
            results.append(BackendResult(
                backend="rtl",
                success=False,
                duration=time.time() - start,
                error_message=str(e)
            ))

    return results


def _compile_acl2(spec_module, out_dir, args) -> List[BackendResult]:
    from specir.lowering.spec_to_acl2 import convert as spec_to_acl2_convert

    logger.info("Lowering spec → acl2...")
    start = time.time()
    try:
        acl2_mod = spec_to_acl2_convert(spec_module)
        acl2_dir = out_dir / "acl2"
        acl2_dir.mkdir(exist_ok=True)
        acl2_file = acl2_dir / f"{spec_module.name}.lisp"
        acl2_code = acl2_mod.to_acl2_code() if hasattr(acl2_mod, 'to_acl2_code') else _generate_acl2_from_module(acl2_mod)
        acl2_file.write_text(acl2_code, encoding="utf-8")
        logger.info(f"ACL2 file written to {acl2_file}")
        return [BackendResult(
            backend="acl2",
            success=True,
            duration=time.time() - start,
            output_file=str(acl2_file)
        )]
    except Exception as e:
        logger.error(f"Failed to write ACL2 file: {e}")
        return [BackendResult(
            backend="acl2",
            success=False,
            duration=time.time() - start,
            error_message=str(e)
        )]


def _compile_assert(spec_module, out_dir, args) -> List[BackendResult]:
    """Compile to unified assert dialect, then lower to target assertion language."""
    from specir.lowering.spec_to_assert import convert as spec_to_assert_convert
    from specir.lowering.assert_to_sva import convert as assert_to_sva_convert
    from specir.lowering.assert_to_vhdl import convert as assert_to_vhdl_convert
    from specir.lowering.assert_to_verilog_ovl import convert as assert_to_verilog_ovl_convert

    logger.info("Lowering spec → assert...")
    start = time.time()
    try:
        assert_mod = spec_to_assert_convert(spec_module)
    except Exception as e:
        logger.error(f"Failed to lower to assert: {e}")
        return [BackendResult(
            backend=args.assert_lang,
            success=False,
            duration=time.time() - start,
            error_message=str(e)
        )]

    signal_widths: Dict[str, int] = {}
    for state_op in spec_module.state_ops:
        w = _extract_width(state_op.data_type)
        if w is not None:
            signal_widths[state_op.state_name] = w
    for inp in spec_module.inputs:
        w = _extract_width(inp.data_type)
        if w is not None:
            signal_widths[inp.name] = w
    for outp in spec_module.outputs:
        w = _extract_width(outp.data_type)
        if w is not None:
            signal_widths[outp.name] = w

    if args.assert_lang == "sva":
        converter = assert_to_sva_convert
        suffix = ".sv"
        gen_func = lambda: converter(assert_mod, signal_widths=signal_widths)
    elif args.assert_lang == "vhdl":
        converter = assert_to_vhdl_convert
        suffix = ".vhd"
        gen_func = lambda: converter(assert_mod)
    elif args.assert_lang == "verilog_ovl":
        converter = assert_to_verilog_ovl_convert
        suffix = ".v"
        gen_func = lambda: converter(assert_mod)
    else:
        logger.error(f"Unsupported assertion language: {args.assert_lang}")
        return [BackendResult(backend=args.assert_lang, success=False, duration=0, error_message="Unsupported language")]

    start_gen = time.time()
    try:
        output_code = gen_func()
        assert_dir = out_dir / "assertions"
        assert_dir.mkdir(exist_ok=True)
        out_file = assert_dir / f"{spec_module.name}{suffix}"
        out_file.write_text(output_code, encoding="utf-8")
        logger.info(f"Assertions written to {out_file}")
        return [BackendResult(
            backend=args.assert_lang,
            success=True,
            duration=time.time() - start_gen,
            output_file=str(out_file)
        )]
    except Exception as e:
        logger.error(f"Assertion generation failed: {e}")
        return [BackendResult(
            backend=args.assert_lang,
            success=False,
            duration=time.time() - start_gen,
            error_message=str(e)
        )]


def _generate_coq_from_module(koika_mod) -> str:
    """Generate a simple Coq file from a KoikaModule."""
    lines = [f"(* Generated from SpecIR design {koika_mod.name} *)", "Require Import Koika.", ""]
    for state_def in koika_mod.state_definitions:
        lines.append(state_def)
    for rule in koika_mod.rule_ops:
        if hasattr(rule, 'coq_definition'):
            lines.append(rule.coq_definition)
        else:
            lines.append(f"Definition {rule.rule_name} : rule := {{ ... }}.   (* placeholder *)")
    if koika_mod.design_op:
        lines.append(f"Definition {koika_mod.design_op.design_name} : design := ... .")
    for thm in koika_mod.theorem_ops:
        lines.append(f"Theorem {thm.theorem_name} : {thm.statement}.")
        lines.append("Proof. Admitted.")
        lines.append("")
    return "\n".join(lines) + "\n"


def _generate_acl2_from_module(acl2_mod) -> str:
    """Generate a simple ACL2 Lisp file from an ACL2Module."""
    parts = [f";; Generated from SpecIR design {acl2_mod.name}"]
    for defun in acl2_mod.defuns:
        parts.append(str(defun))
    for defthm in acl2_mod.defthms:
        parts.append(str(defthm))
    return "\n".join(parts) + "\n"


def _print_human_readable(report: CompilationReport) -> None:
    """Print a human‑readable compilation summary (original style)."""
    print(f"""
┌──────────────────────────────────────────┐
│  SpecIR Compilation Summary              │
├──────────────────────────────────────────┤
│  Design:     {report.design_name:<28} │
│  Input:      {report.input_file:<28} │
├──────────────────────────────────────────┤
│  Generated files / status:               │""")
    for res in report.results:
        status = "✓" if res.success else "✗"
        print(f"│    {status} {res.backend:<10} {res.output_file or res.error_message or 'N/A'}")
    print(f"└──────────────────────────────────────────┘")
    print()


def main() -> int:
    parser = _setup_arg_parser()
    args = parser.parse_args()
    return compile_spec(args)


if __name__ == "__main__":
    sys.exit(main())
