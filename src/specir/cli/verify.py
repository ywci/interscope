# src/specir/cli/verify.py
#
# CLI subcommand `verify` – runs proof obligations on a SpecIR design
# using the selected backend (Kōika/Coq, ACL2, or model checking).
# For model checking, RTL and assertions are generated and verified
# with an external model checker (SymbiYosys / sby).
# If enabled in config, automatically splits monolithic ite‑rules
# before verification (see `split_monolithic_rules` in config.yaml).

import argparse
import sys
import json
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
from specir.parser.parser import parse_specir
from specir.parser.validator import validate_specir_file
from specir.lowering.ast_to_spec import convert_ast_to_spec_module
from specir.lowering.split_rules import split_rules
from specir.lowering.spec_to_koika import convert as spec_to_koika_convert
from specir.lowering.spec_to_acl2 import convert as spec_to_acl2_convert
from specir.lowering.spec_to_assert import convert as spec_to_assert_convert
from specir.lowering.assert_to_sva import convert as assert_to_sva_convert
from specir.lowering.koika_to_rtl import convert as koika_to_rtl_convert
from specir.verification.model_checker import run_model_check, ModelCheckError
from specir.utils.logger import setup_logging, get_logger
from specir.utils.config_loader import load_config, get_project_root, _validate_config
from specir.verification.proof.proof_skill import LLMProofSkill, ProofResult
from specir.verification.perf.perf_config import PERFConfig, validate_perf_against_config
from specir.verification.perf.perf_stats import PERFStats
from specir.verification.perf.perf_diagnostics import print_diagnostics  # NEW
from specir.utils.result_types import (
    VerificationReport,
    ProofObligationResult,
    Status,
)

logger = get_logger(__name__)


def _canonical_backend(backend: Optional[str]) -> Optional[str]:
    """Convert a backend string to the canonical form: ``koika``, ``acl2``, or
    ``model_checking``.  Handles legacy typos and the macron spelling.
    """
    if not backend:
        return None
    b = backend.lower().replace("ō", "o")
    if b.startswith("koi"):
        return "koika"
    if b == "acl2":
        return "acl2"
    if b in ("model_checking", "modelchecking", "mc"):
        return "model_checking"
    return None


def _setup_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="specir verify",
        description=(
            "Prove proof obligations in a SpecIR design using theorem provers, "
            "model checking, or PERF (Proof tree Exploration with Reflective Feedback)."
        )
    )
    parser.add_argument("input", type=str, help="Path to the .specir file")
    parser.add_argument(
        "--backend", "-b", choices=["koika", "acl2", "model_checking"], default=None,
        help="Override backend for all obligations (otherwise uses obligation's backend)"
    )
    parser.add_argument("--out-dir", "-o", type=str, default=None,
                        help="Output directory for generated proof artifacts (default: build/verify/<design>)")
    parser.add_argument("--max-attempts", type=int, default=None,
                        help="Maximum repair attempts (overrides config, theorem proving only)")
    parser.add_argument("--report", "-r", type=str, default=None,
                        help="Save verification report to this JSON file")
    parser.add_argument("--output-format", choices=["json", "text"], default="text",
                        help="Output format: json for structured data, text for summary (default: text)")
    parser.add_argument("--no-llm", action="store_true",
                        help="Disable LLM assistance (theorem proving only)")
    parser.add_argument("--show-proof", action="store_true",
                        help="Print the generated proof script for each successful obligation")

    parser.add_argument("--perf", action="store_true",
                        help="Enable PERF (Proof tree Exploration with Reflective Feedback)")
    parser.add_argument("--no-perf", action="store_true",
                        help="Disable PERF (fall back to greedy repair)")
    parser.add_argument("--perf-stats", action="store_true",
                        help="Print PERF traversal statistics (nodes, depth, tokens, diagnostics)")
    parser.add_argument("--no-pareto", action="store_true",
                        help="Disable Pareto pruning (for ablation experiments)")
    parser.add_argument("--no-trace-alignment", action="store_true",
                        help="Disable trace alignment dimension (for ablation)")
    parser.add_argument("--no-reflection", action="store_true",
                        help="Disable reflection feedback (for ablation)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Parse and validate only (no execution)")

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


def _print_perf_stats(stats: PERFStats) -> None:
    """Pretty‑print PERF traversal statistics using the diagnostics module."""
    if stats is None:
        return
    print()
    # Use the new diagnostics module for a richer report.
    print_diagnostics(stats)
    print()


def _print_summary(report: VerificationReport, show_proof: bool = False) -> None:
    """Print a human‑readable verification summary, optionally including proof scripts."""
    passed = sum(1 for o in report.obligations if o.status == Status.PASS)
    failed = len(report.obligations) - passed
    print(f"\n===== Verification Summary: {passed} passed, {failed} failed =====\n")
    for obl in report.obligations:
        status_label = "PASS" if obl.status == Status.PASS else "FAIL"
        print(f"{status_label}: {obl.property} ({obl.backend})")
        if obl.status != Status.PASS and obl.error_message:
            print(f"   Error: {obl.error_message[:200]}")
        if show_proof and obl.status == Status.PASS and obl.proof_script:
            print(f"   Proof:\n{obl.proof_script}")
    print(f"\n===== {'All properties hold' if failed == 0 else 'Some properties failed'} =====\n")


def verify_spec(args: argparse.Namespace) -> int:
    """Execute the verify command."""
    log_level = "DEBUG" if args.debug else "INFO"
    setup_logging(level=log_level)

    config = load_config()
    project_root = get_project_root()

    if args.perf:
        config['proof']['perf']['enabled'] = True
        config['provers']['koika']['use_proof_library'] = False
        logger.info("PERF enabled via --perf flag")
    elif args.no_perf:
        config['proof']['perf']['enabled'] = False
        logger.info("PERF disabled via --no-perf flag")

    perf_cfg = config.setdefault("proof", {}).setdefault("perf", {})
    if args.no_pareto:
        perf_cfg["scoring_tournament_size"] = 0
        logger.info("Ablation: Pareto pruning disabled")
    if args.no_trace_alignment:
        dims = perf_cfg.get("dimensions", [])
        if "trace_alignment" in dims:
            dims.remove("trace_alignment")
            perf_cfg["dimensions"] = dims
            logger.info("Ablation: trace_alignment dimension removed")
    if args.no_reflection:
        perf_cfg["use_reflection"] = False
        logger.info("Ablation: reflection feedback disabled")

    try:
        _validate_config(config)
    except ValueError as e:
        logger.error(f"Configuration validation failed: {e}")
        return 1

    if args.dry_run:
        logger.info("DRY RUN: Configuration and spec are valid.")
        input_path = Path(args.input).resolve()
        if not input_path.exists():
            logger.error(f"Input file not found: {input_path}")
            return 1
        try:
            validate_specir_file(input_path)
            ast_doc = parse_specir(input_path)
            if not hasattr(ast_doc, "module") or not ast_doc.module:
                logger.error("Parsed spec does not contain a module")
                return 1
            spec_module = convert_ast_to_spec_module(ast_doc.module)
            logger.info(f"Design: {spec_module.name}")
            logger.info(f"Obligations: {len(spec_module.proof_obligations)}")
            logger.info("Dry run completed successfully.")
            return 0
        except Exception as e:
            logger.error(f"Dry run failed: {e}")
            return 1

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
        base_out = project_root / config.get("directories", {}).get("build", "build") / "verify"
    out_dir = base_out / design_name
    out_dir.mkdir(parents=True, exist_ok=True)

    obligations = spec_module.proof_obligations
    if not obligations:
        logger.warning("No proof obligations found in the specification.")
        return 0

    # Filter obligations by backend if specified
    if args.backend:
        target_backend = _canonical_backend(args.backend)
        filtered = []
        for po in obligations:
            engine = po.get("engine") if isinstance(po, dict) else getattr(po, "engine", "theorem_proving")
            if target_backend == "model_checking":
                if engine == "model_checking":
                    filtered.append(po)
            else:
                po_backend = po.get("backend") if isinstance(po, dict) else getattr(po, "backend", None)
                if _canonical_backend(po_backend) == target_backend:
                    filtered.append(po)
        if not filtered:
            logger.warning(f"No proof obligations match backend '{args.backend}'.")
            return 0
        obligations = filtered

    theorem_obligations = []
    mc_obligations = []
    for po in obligations:
        engine = po.get("engine") if isinstance(po, dict) else getattr(po, "engine", "theorem_proving")
        if engine == "model_checking":
            mc_obligations.append(po)
        else:
            theorem_obligations.append(po)

    rtl_dir = None
    assertions_dir = None
    rtl_file = None
    assertions_file = None
    koika_needs_mc_prep = False

    use_mc_lemmas = config.get("provers", {}).get("koika", {}).get("use_mc_lemmas", False)
    if use_mc_lemmas:
        # Check if any theorem obligation uses Koika backend
        for po in theorem_obligations:
            backend = po.get("backend") if isinstance(po, dict) else getattr(po, "backend", "")
            if _canonical_backend(backend) == "koika":
                koika_needs_mc_prep = True
                break

    if koika_needs_mc_prep:
        logger.info("Preparing RTL and SVA for MC lemma injection.")
        rtl_dir = out_dir / "mc_prep" / "rtl"
        assertions_dir = out_dir / "mc_prep" / "assertions"
        rtl_dir.mkdir(parents=True, exist_ok=True)
        assertions_dir.mkdir(parents=True, exist_ok=True)

        try:
            # Generate RTL via Koika
            rtl_container = koika_to_rtl_convert(spec_module, rtl_dir)
            rtl_file = rtl_dir / f"{design_name}.v"
            if not rtl_file.exists():
                nested = rtl_dir / f"{design_name}.v" / f"{design_name}.v"
                if nested.exists():
                    rtl_file = nested
                else:
                    # search
                    for candidate in sorted(rtl_dir.rglob("*.v")):
                        rtl_file = candidate
                        break
            if not rtl_file or not rtl_file.exists():
                logger.error("Could not locate generated Verilog file for MC prep.")
                koika_needs_mc_prep = False
        except Exception as e:
            logger.error("RTL generation for MC prep failed: %s", e)
            koika_needs_mc_prep = False

        if koika_needs_mc_prep and rtl_file and rtl_file.exists():
            try:
                # Generate SVA assertions
                assert_mod = spec_to_assert_convert(spec_module)
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
                sva_code = assert_to_sva_convert(assert_mod, signal_widths=signal_widths)
                assertions_file = assertions_dir / f"{design_name}_assertions.sv"
                assertions_file.write_text(sva_code, encoding="utf-8")
            except Exception as e:
                logger.error("Assertion generation for MC prep failed: %s", e)
                koika_needs_mc_prep = False
                assertions_file = None

    # Build context for proof skill
    context: Dict[str, Any] = {
        "spec_module": spec_module,
        "config": config,
    }
    if koika_needs_mc_prep and rtl_file and assertions_file:
        context["rtl_file_path"] = str(rtl_file)
        context["assertions_file_path"] = str(assertions_file)
        logger.info("Provided RTL and assertions paths for automatic MC lemma injection.")

    results: List[ProofObligationResult] = []

    if theorem_obligations:
        backend_files: Dict[str, str] = {}
        backends_needed: set = set()

        for po in theorem_obligations:
            backend = po.get("backend") if isinstance(po, dict) else getattr(po, "backend", "koika")
            canonical = _canonical_backend(backend)
            if canonical == "koika":
                backends_needed.add("koika")
            elif canonical == "acl2":
                backends_needed.add("acl2")

        if "koika" in backends_needed:
            coq_dir = out_dir / "coq"
            coq_dir.mkdir(exist_ok=True)
            coq_file = coq_dir / f"{design_name}.v"
            try:
                koika_mod = spec_to_koika_convert(spec_module)
                coq_code = "\n".join(koika_mod.state_definitions)
                coq_file.write_text(coq_code, encoding="utf-8")
                backend_files["koika"] = str(coq_file)
                logger.info(f"Coq/Kōika file written to {coq_file}")
            except Exception as e:
                logger.error(f"Failed to generate Coq file: {e}")
                return 1

        if "acl2" in backends_needed:
            acl2_dir = out_dir / "acl2"
            acl2_dir.mkdir(exist_ok=True)
            acl2_file = acl2_dir / f"{design_name}.lisp"
            try:
                acl2_mod = spec_to_acl2_convert(spec_module)
                acl2_code = acl2_mod.to_acl2_code() if hasattr(acl2_mod, "to_acl2_code") else _generate_acl2_from_module(acl2_mod)
                acl2_file.write_text(acl2_code, encoding="utf-8")
                backend_files["acl2"] = str(acl2_file)
                logger.info(f"ACL2 file written to {acl2_file}")
            except Exception as e:
                logger.error(f"Failed to generate ACL2 file: {e}")
                return 1

        try:
            proof_skill = LLMProofSkill(config=config)
            if args.max_attempts is not None:
                proof_skill.max_repair_attempts = args.max_attempts
            if args.no_llm:
                logger.warning("--no-llm flag is experimental; LLM may still be used for repair.")
        except Exception as e:
            logger.error(f"Failed to initialize proof skill: {e}")
            return 1

        for po in theorem_obligations:
            prop_name = po.get("property") if isinstance(po, dict) else getattr(po, "property", "unknown")
            backend_raw = po.get("backend") if isinstance(po, dict) else getattr(po, "backend", "koika")
            canonical = _canonical_backend(backend_raw) or "koika"
            logger.info(f"Proving '{prop_name}' with backend {canonical}")

            start_time = time.time()
            po_context = dict(context)  # copy
            po_context["obligation"] = po

            if canonical == "koika":
                if "koika" not in backend_files:
                    logger.error("Coq file not generated; cannot prove.")
                    results.append(ProofObligationResult(
                        property=prop_name,
                        status=Status.ERROR,
                        backend=canonical,
                        error_message="Coq file missing"
                    ))
                    continue
                po_context["coq_file_path"] = backend_files["koika"]
                po_context["theorem_name"] = f"{prop_name}_proved"
            else:  # acl2
                if "acl2" not in backend_files:
                    logger.error("ACL2 file not generated; cannot prove.")
                    results.append(ProofObligationResult(
                        property=prop_name,
                        status=Status.ERROR,
                        backend=canonical,
                        error_message="ACL2 file missing"
                    ))
                    continue
                po_context["acl2_file_path"] = backend_files["acl2"]
                po_context["theorem_name"] = f"{prop_name}_correct"
                statement = _extract_acl2_statement(acl2_mod, prop_name)
                po_context["theorem_statement"] = statement

            try:
                result: ProofResult = proof_skill.prove(po, po_context)
            except Exception as e:
                logger.error(f"Proof attempt for '{prop_name}' failed with exception: {e}")
                results.append(ProofObligationResult(
                    property=prop_name,
                    status=Status.ERROR,
                    backend=canonical,
                    error_message=str(e),
                    duration=time.time() - start_time
                ))
                continue

            duration = time.time() - start_time
            status = Status.PASS if result.success else Status.FAIL
            proof_script = result.proof_script if (args.show_proof or args.debug) else None

            if result.success:
                logger.info(f"  PASS: {prop_name}")
                _safe_register_evidence(spec_module, prop_name, canonical, result)
            else:
                logger.error(f"  FAIL: {prop_name}: {result.error_message}")

            results.append(ProofObligationResult(
                property=prop_name,
                status=status,
                backend=canonical,
                iterations=result.iterations,
                proof_script=proof_script,
                error_message=result.error_message,
                duration=duration,
                details=result.metadata
            ))

        if args.perf_stats:
            stats = proof_skill.get_last_perf_stats()
            if stats and args.output_format != "json":
                _print_perf_stats(stats)

    if mc_obligations:
        logger.info(f"Running model checking for {len(mc_obligations)} obligation(s).")
        mc_dir = out_dir / "model_check"
        mc_dir.mkdir(exist_ok=True)

        # Use the already generated RTL/assertions if available, otherwise generate now
        if not rtl_file:
            rtl_dir = mc_dir / "rtl"
            rtl_dir.mkdir(exist_ok=True)
            try:
                rtl_container = koika_to_rtl_convert(spec_module, rtl_dir)
                rtl_file = rtl_dir / f"{design_name}.v"
                if not rtl_file.exists():
                    nested = rtl_dir / f"{design_name}.v" / f"{design_name}.v"
                    if nested.exists():
                        rtl_file = nested
                    else:
                        for candidate in sorted(rtl_dir.rglob("*.v")):
                            rtl_file = candidate
                            break
            except Exception as e:
                logger.error(f"RTL generation for model checking failed: {e}")
                for po in mc_obligations:
                    prop = po.get("property") if isinstance(po, dict) else getattr(po, "property", "?")
                    results.append(ProofObligationResult(
                        property=prop,
                        status=Status.ERROR,
                        backend="model_checking",
                        error_message=str(e)
                    ))
                return _finish_summary(results, args)

        if not rtl_file or not rtl_file.exists():
            logger.error("Could not locate generated Verilog file for model checking.")
            for po in mc_obligations:
                prop = po.get("property") if isinstance(po, dict) else getattr(po, "property", "?")
                results.append(ProofObligationResult(
                    property=prop,
                    status=Status.ERROR,
                    backend="model_checking",
                    error_message="Verilog file not found"
                ))
            return _finish_summary(results, args)

        if not assertions_file:
            assertions_dir = mc_dir / "assertions"
            assertions_dir.mkdir(exist_ok=True)
            try:
                assert_mod = spec_to_assert_convert(spec_module)
                mc_prop_names = {
                    po.get("property") if isinstance(po, dict) else getattr(po, "property", None)
                    for po in mc_obligations
                }
                assert_mod.always_checks = [
                    c for c in assert_mod.always_checks
                    if getattr(c, 'label', None) in mc_prop_names
                ]
                assert_mod.properties = [
                    p for p in assert_mod.properties
                    if getattr(p, 'label', None) in mc_prop_names
                ]
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
                sva_code = assert_to_sva_convert(assert_mod, signal_widths=signal_widths)
                assertions_file = assertions_dir / f"{design_name}_assertions.sv"
                assertions_file.write_text(sva_code, encoding="utf-8")
            except Exception as e:
                logger.error(f"Assertion generation failed: {e}")
                for po in mc_obligations:
                    prop = po.get("property") if isinstance(po, dict) else getattr(po, "property", "?")
                    results.append(ProofObligationResult(
                        property=prop,
                        status=Status.ERROR,
                        backend="model_checking",
                        error_message=str(e)
                    ))
                return _finish_summary(results, args)

        try:
            mc_result = run_model_check(
                rtl_path=rtl_file,
                assertions_path=assertions_file,
                top_module=design_name
            )
        except ModelCheckError as e:
            logger.error(f"Model checking error: {e}")
            for po in mc_obligations:
                prop = po.get("property") if isinstance(po, dict) else getattr(po, "property", "?")
                results.append(ProofObligationResult(
                    property=prop,
                    status=Status.ERROR,
                    backend="model_checking",
                    error_message=str(e)
                ))
            return _finish_summary(results, args)

        mc_status = Status.PASS if mc_result.get("success") else Status.FAIL
        for po in mc_obligations:
            prop = po.get("property") if isinstance(po, dict) else getattr(po, "property", "?")
            if mc_status == Status.PASS:
                logger.info(f"  PASS: {prop} (model checking)")
                _safe_register_mc_evidence(spec_module, prop, mc_result)
                results.append(ProofObligationResult(
                    property=prop,
                    status=Status.PASS,
                    backend="model_checking",
                    details={"engine": mc_result.get("details", {}).get("engine", "bmc")},
                    duration=mc_result.get("duration")
                ))
            else:
                logger.error(f"  FAIL: {prop} (model checking): {mc_result.get('error') or 'Counterexample found'}")
                results.append(ProofObligationResult(
                    property=prop,
                    status=Status.FAIL,
                    backend="model_checking",
                    error_message=mc_result.get("error"),
                    duration=mc_result.get("duration")
                ))

    return _finish_summary(results, args)


def _finish_summary(results: List[ProofObligationResult], args: argparse.Namespace) -> int:
    """Print summary, optionally showing proofs, and save report if requested."""
    report = VerificationReport(
        design_name="",
        backend="",
        obligations=results,
    )

    if hasattr(args, 'input'):
        report.design_name = Path(args.input).stem
    if args.backend:
        report.backend = _canonical_backend(args.backend) or "mixed"
    else:
        backends = set(o.backend for o in results)
        report.backend = ", ".join(sorted(backends)) if backends else "unknown"

    if args.output_format == "json":
        print(json.dumps(report.to_dict(), indent=2))
    else:
        _print_summary(report, show_proof=args.show_proof)

    if args.report:
        with open(args.report, "w") as f:
            json.dump(report.to_dict(), f, indent=2)
        logger.info(f"Report saved to {args.report}")

    all_passed = all(o.status == Status.PASS for o in results)
    return 0 if all_passed else 1


def _extract_acl2_statement(acl2_mod, prop_name: str) -> Optional[str]:
    """Try to retrieve the ACL2 formula for a given property name."""
    if acl2_mod is None:
        return None
    thm_name = f"{prop_name}_correct"
    for defthm in getattr(acl2_mod, "defthms", []):
        if defthm.thm_name == thm_name:
            return defthm.statement
    return None


def _safe_register_evidence(spec_module, prop_name: str, backend: str, result: ProofResult) -> None:
    """Register a successful theorem proof in the evidence database."""
    try:
        from specir.evidence.annotator import add_evidence_to_registry, create_evidence_ref
        evidence_type = "coq_theorem" if backend == "koika" else "acl2_theorem"
        ref_value = f"file://{result.proof_script}" if result.proof_script else f"local:{prop_name}"
        evidence = create_evidence_ref(
            evidence_type=evidence_type,
            ref_type="uri" if result.proof_script else "local_id",
            ref_value=ref_value,
            engine="theorem_proving",
            status="proved",
            property_name=prop_name
        )
        add_evidence_to_registry(evidence, property_name=prop_name)
        logger.info(f"Evidence registered for {prop_name}")
    except Exception as e:
        logger.warning(f"Failed to register evidence: {e}")


def _safe_register_mc_evidence(spec_module, prop_name: str, mc_result: Dict[str, Any]) -> None:
    """Register model‑checking evidence (proved or counterexample)."""
    try:
        from specir.evidence.annotator import add_evidence_to_registry, create_evidence_ref
        if mc_result["status"] == "proved":
            ev_type = "inductive_invariant"
            status = "proved"
            ref_value = f"local:{prop_name}"
        else:
            ev_type = "counterexample_trace"
            status = "counterexample"
            ref_value = str(mc_result.get("counterexample_trace") or f"local:{prop_name}")
        evidence = create_evidence_ref(
            evidence_type=ev_type,
            ref_type="uri" if mc_result.get("counterexample_trace") else "local_id",
            ref_value=ref_value,
            engine="model_checking",
            status=status,
            property_name=prop_name
        )
        add_evidence_to_registry(evidence, property_name=prop_name)
        logger.info(f"Model‑checking evidence registered for {prop_name}")
    except Exception as e:
        logger.warning(f"Failed to register model‑checking evidence: {e}")


def _generate_acl2_from_module(acl2_mod) -> str:
    """Generate a simple ACL2 Lisp file from an ACL2Module."""
    parts = [f";; Generated from SpecIR design {acl2_mod.name}"]
    for defun in acl2_mod.defuns:
        parts.append(str(defun))
    for defthm in acl2_mod.defthms:
        parts.append(str(defthm))
    return "\n".join(parts) + "\n"


def main() -> int:
    parser = _setup_arg_parser()
    args = parser.parse_args()
    return verify_spec(args)


if __name__ == "__main__":
    sys.exit(main())
