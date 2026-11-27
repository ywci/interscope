# src/isir/cli/verify.py
#
# CLI subcommand `verify` – runs proof obligations on a ISIR design
# using the selected backend (Kōika/Coq, ACL2, or model checking).
# For model checking, RTL and assertions are generated and verified
# with an external model checker (SymbiYosys / sby).
# If enabled in config, automatically splits monolithic ite‑rules
# before verification (see `split_monolithic_rules` in config.yaml).

import argparse
import copy
import sys
import json
import re
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
from isir.parser.parser import parse_isir
from isir.parser.validator import validate_isir_file
from isir.lowering.ast_to_isir import convert_ast_to_isir_module
from isir.lowering.split_rules import split_rules
from isir.lowering.isir_to_koika import convert as isir_to_koika_convert
from isir.lowering.isir_to_acl2 import convert as isir_to_acl2_convert
from isir.lowering.isir_to_assert import convert as isir_to_assert_convert
from isir.lowering.assert_to_sva import convert as assert_to_sva_convert
from isir.lowering.assert_to_sva import convert_inline as assert_to_sva_convert_inline
from isir.lowering.koika_to_rtl import convert as koika_to_rtl_convert
from isir.verification.model_checker import run_model_check, ModelCheckError
from isir.utils.logger import setup_logging, get_logger
from isir.utils.config_loader import load_config, get_project_root, _validate_config
from isir.verification.proof.proof_skill import LLMProofSkill, ProofResult
from isir.verification.perf.perf_config import PERFConfig, validate_perf_against_config
from isir.verification.perf.perf_stats import PERFStats
from isir.verification.perf.perf_diagnostics import print_diagnostics  # NEW
from isir.utils.result_types import (
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
    if b in ("koika_acl2", "koika-acl2", "cowork", "co-work"):
        return "koika_acl2"
    if b.startswith("koi"):
        return "koika"
    if b == "acl2":
        return "acl2"
    if b in ("model_checking", "modelchecking", "mc"):
        return "model_checking"
    return None


def _effective_backend(canonical: Optional[str], no_cowork: bool, acl2_only: bool = False) -> Optional[str]:
    """Apply the single-backend ablation: downgrade koika_acl2 to Koika or ACL2."""
    if no_cowork and canonical == "koika_acl2":
        return "koika"
    if acl2_only and canonical == "koika_acl2":
        return "acl2"
    return canonical


def _property_kind(spec_module, prop_name: str) -> Optional[str]:
    """Return the property's temporal-expression kind (e.g. 'always'), or None."""
    for prop in getattr(spec_module, "property_ops", []):
        if getattr(prop, "prop_name", "") == prop_name:
            expr = getattr(prop, "expression", {})
            return expr.get("kind") if isinstance(expr, dict) else None
    return None


def _setup_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="isir verify",
        description=(
            "Prove proof obligations in a ISIR design using theorem provers, "
            "model checking, or PERF (Proof tree Exploration with Reflective Feedback)."
)
)
    parser.add_argument("input", type=str, help="Path to the .isir file")
    parser.add_argument(
        "--backend", "-b", choices=["koika", "acl2", "model_checking", "koika_acl2"], default=None,
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
    parser.add_argument("--search", choices=["linear", "perf", "mcts"], default=None,
                        help="Search strategy: linear (greedy), perf (PERF beam, default), mcts (MCTS)")
    parser.add_argument("--perf-stats", action="store_true",
                        help="Print PERF traversal statistics (nodes, depth, tokens, diagnostics)")
    parser.add_argument("--no-pareto", action="store_true",
                        help="Disable Pareto pruning (for ablation experiments)")
    parser.add_argument("--no-trace-alignment", action="store_true",
                        help="Disable trace alignment dimension (for ablation)")
    parser.add_argument("--no-reflection", action="store_true",
                        help="Disable reflection feedback (for ablation)")
    parser.add_argument("--no-skeleton", action="store_true",
                        help="Disable the recursive proof skeleton (for raw-LLM baselines)")
    parser.add_argument("--no-coqc-fallback", action="store_true",
                        help="Disable the deterministic coqc fallback (for pure-LLM baselines symmetric with MCTS)")
    parser.add_argument("--mc-lemmas", action="store_true",
                        help="Enable MC lemma injection (model-checking gating) for Koika (ablation)")
    parser.add_argument("--no-mc-lemmas", action="store_true",
                        help="Disable MC lemma injection (ablation)")
    parser.add_argument("--mc-engine", choices=["bmc", "induction"], default=None,
                        help="Model-checking engine for MC-gating: bmc (bounded, unsound for invariants) or induction (IC3/k-induction, sound)")
    parser.add_argument("--no-cowork", action="store_true",
                        help="Disable the koika_acl2 co-work dispatch: downgrade to single-backend Koika (ablation)")
    parser.add_argument("--sat-gate", action="store_true",
                        help="Short-circuit inductive (always) obligations via the SAT gate before the ITP")
    parser.add_argument("--acl2-only", action="store_true",
                        help="Downgrade koika_acl2 to single-backend ACL2 (ablation); inductive (always) obligations are skipped")
    parser.add_argument("--dry-run", action="store_true",
                        help="Parse and validate only (no execution)")

    parser.add_argument("--candidate-rtl", type=str, default=None,
                        help="Path to a Candidate RTL (.v) for RTL Conformance checking (Mode B)")
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


def _rtl_signal_map(spec_module) -> tuple:
    """Derive the ISIR → RTL signal-name mapping used by the SVA ``bind``.

    The Kōika/cuttlec backend renames signals from the ISIR names: registers
    (including internalized inputs/outputs) become the ``reg_t`` constructors
    ``Reg_<Capitalized>`` (see ``koika_to_rtl._reg_ctor``), and the reset
    becomes ``rst_n`` (active‑low).  Returns ``(signal_map, reset_inverted)``.
    """
    from isir.lowering.koika_to_rtl import _reg_ctor

    signal_map: Dict[str, str] = {}
    reset_inverted = False
    for s in getattr(spec_module, "state_ops", []):
        if getattr(s, "kind", "") == "register" and getattr(s, "state_name", ""):
            signal_map[s.state_name] = _reg_ctor(s.state_name)
    for inp in getattr(spec_module, "inputs", []):
        if getattr(inp, "name", ""):
            # Inputs are exposed as top-level `Inp_<name>` ports (injected by
            # the long-path post-processing), driven onto the internalized
            # register wires.
            signal_map[inp.name] = f"Inp_{inp.name}"
    for rst in getattr(spec_module, "resets", []):
        if isinstance(rst, dict) and rst.get("name"):
            rst_name = rst["name"]
            signal_map[rst_name] = f"{rst_name}_n"
            if rst.get("polarity") == "active_high":
                reset_inverted = True
    return signal_map, reset_inverted


def _drive_inputs(assert_mod, spec_module) -> None:
    """Add SVA ``assume`` constraints forcing each free input high, so the
    model checker explores the state transitions instead of leaving an
    input-gated rule dormant (which would make every invariant vacuously true).
    """
    from isir.dialects.asserts import AssertAssumeOp
    for inp in getattr(spec_module, "inputs", []):
        if getattr(inp, "name", ""):
            assert_mod.assumptions.append(
                AssertAssumeOp(condition=inp.name, label=f"drive_{inp.name}")
)


def _force_inputs_rtl_str(content: str, spec_module) -> str:
    """Return RTL with the free inputs forced high (string version)."""
    drivers = []
    for inp in getattr(spec_module, "inputs", []):
        name = getattr(inp, "name", "")
        if not name:
            continue
        w = _extract_width(inp.data_type) or 1
        rtl_name = f"Inp_{name}"
        content = re.sub(rf"input\s*(?:\[[^\]]*\]\s*)?{rtl_name}\s*,", "", content)
        drivers.append(f"  wire [{w-1}:0] {rtl_name} = {w}'b{'1' * w};")
    if drivers:
        m = re.search(r"\)\s*;", content)
        if m:
            content = content[:m.end()] + "\n" + "\n".join(drivers) + content[m.end():]
    return content


def _inject_inline_assertions_str(content: str, assert_mod, signal_widths,
                                  signal_map, reset_inverted: bool) -> str:
    """Return RTL with the inline SVA assertions appended (string version)."""
    inline_code = assert_to_sva_convert_inline(
        assert_mod,
        signal_widths=signal_widths,
        signal_map=signal_map,
        reset_inverted=reset_inverted
)
    idx = content.rfind("endmodule")
    if idx == -1:
        raise ValueError("No 'endmodule' found in RTL")
    return content[:idx] + inline_code + "\n" + content[idx:]


def _force_inputs_in_rtl(rtl_file: Path, spec_module) -> None:
    """Force the free inputs high in the generated RTL so the model checker
    explores the state transitions (an input-gated rule that never fires makes
    every invariant vacuously true).  The input ports are turned into driven
    constant wires inside the module, keeping the DUT as the top so the SVA
    ``bind`` still applies."""
    rtl_file.write_text(_force_inputs_rtl_str(rtl_file.read_text(), spec_module), encoding="utf-8")


def _inject_inline_assertions(rtl_file: Path, assert_mod, signal_widths,
                              signal_map, reset_inverted: bool) -> None:
    """Append inline SVA assertions inside the RTL module (before ``endmodule``).

    Yosys/SymbiYosys does not apply SystemVerilog ``bind``, so the assertions
    must live inside the design module itself, referencing the real RTL signal
    names."""
    content = _inject_inline_assertions_str(
        rtl_file.read_text(), assert_mod, signal_widths, signal_map, reset_inverted
)
    rtl_file.write_text(content, encoding="utf-8")


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
    skipped = sum(1 for o in report.obligations if o.status == Status.SKIPPED)
    gated = sum(1 for o in report.obligations if o.status == Status.SAT_GATED)
    failed = len(report.obligations) - passed - skipped - gated
    parts = [f"{passed} passed", f"{failed} failed"]
    if gated:
        parts.append(f"{gated} sat-gated")
    if skipped:
        parts.append(f"{skipped} skipped")
    print(f"\n===== Verification Summary: {', '.join(parts)} =====\n")
    for obl in report.obligations:
        status_label = {Status.PASS: "PASS", Status.SKIPPED: "SKIPPED",
                        Status.SAT_GATED: "SAT-GATED"}.get(obl.status, "FAIL")
        print(f"{status_label}: {obl.property} ({obl.backend})")
        if obl.status not in (Status.PASS, Status.SKIPPED, Status.SAT_GATED) and obl.error_message:
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

    if getattr(args, "no_cowork", False) and getattr(args, "acl2_only", False):
        logger.error("--no-cowork and --acl2-only are mutually exclusive")
        return 2

    if args.perf:
        config['proof']['perf']['enabled'] = True
        config['provers']['koika']['use_proof_library'] = False
        logger.info("PERF enabled via --perf flag")
    elif args.no_perf:
        config['proof']['perf']['enabled'] = False
        logger.info("PERF disabled via --no-perf flag")

    if getattr(args, "search", None):
        config.setdefault("proof", {})["search_strategy"] = args.search
        if args.search == "mcts":
            # Keep MCTS symmetric with the linear path: no proof-library head-start.
            config['provers']['koika']['use_proof_library'] = False
            logger.info("MCTS search: proof library disabled for symmetric baseline")
        logger.info("Search strategy set to '%s' via --search flag", args.search)

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

    if getattr(args, "no_skeleton", False):
        config.setdefault("provers", {}).setdefault("koika", {}).setdefault("prove", {})["skeleton_enabled"] = False
        config.setdefault("proof", {}).setdefault("perf", {})["try_skeleton_first"] = False
        logger.info("Recursive proof skeleton disabled via --no-skeleton flag (linear + PERF skeleton-first)")

    if getattr(args, "no_coqc_fallback", False):
        config.setdefault("provers", {}).setdefault("koika", {}).setdefault("prove", {})["coqc_fallback"] = False
        logger.info("Deterministic coqc fallback disabled via --no-coqc-fallback flag (pure-LLM baseline)")

    if getattr(args, 'mc_lemmas', False):
        config.setdefault("provers", {}).setdefault("koika", {})["use_mc_lemmas"] = True
        logger.info("Ablation: MC lemma injection enabled")
    elif getattr(args, 'no_mc_lemmas', False):
        config.setdefault("provers", {}).setdefault("koika", {})["use_mc_lemmas"] = False
        logger.info("Ablation: MC lemma injection disabled")

    if getattr(args, 'mc_engine', None):
        config.setdefault("verification", {})["mc_engine"] = args.mc_engine
        logger.info("MC-gating engine set to '%s' via --mc-engine", args.mc_engine)

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
            validate_isir_file(input_path)
            ast_doc = parse_isir(input_path)
            if not hasattr(ast_doc, "module") or not ast_doc.module:
                logger.error("Parsed spec does not contain a module")
                return 1
            spec_module = convert_ast_to_isir_module(ast_doc.module)
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
        validate_isir_file(input_path)
    except Exception as e:
        logger.error(f"Schema validation failed: {e}")
        return 1

    try:
        ast_doc = parse_isir(input_path)
    except Exception as e:
        logger.error(f"Parsing failed: {e}")
        return 1

    if not hasattr(ast_doc, "module") or not ast_doc.module:
        logger.error("Parsed spec does not contain a module")
        return 1

    try:
        spec_module = convert_ast_to_isir_module(ast_doc.module)
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

    # RTL Conformance (Mode B): check an externally provided Candidate RTL.
    if getattr(args, "candidate_rtl", None):
        from isir.lowering.verify_candidate import verify_candidate_rtl
        try:
            result = verify_candidate_rtl(spec_module, args.candidate_rtl)
        except Exception as e:  # noqa: BLE001
            logger.error("Candidate RTL conformance check failed: %s", e)
            return 1
        if args.output_format == "json":
            import json as _json
            print(_json.dumps(result.to_dict(), indent=2))
        else:
            print(f"design: {result.design}")
            print(f"status: {result.status}")
            for rec in result.records:
                print(f"  divergent: {rec.primary_spec_item_id} (counterexample @ {rec.counterexample})")
            if result.message:
                print(f"message: {result.message}")
        return 0 if result.status != "error" else 1

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
                po_canon = _canonical_backend(po_backend)
                # A single-backend request covers the corresponding side of
                # co-work (`koika_acl2`) obligations too: `--backend koika`
                # proves their Kōika side, `--backend acl2` their ACL2 side.
                if po_canon == target_backend or (
                        target_backend in ("koika", "acl2") and po_canon == "koika_acl2"):
                    filtered.append(po)
        if not filtered:
            logger.warning(f"No proof obligations match backend '{args.backend}'.")
            print(f"SKIPPED: no proof obligations match backend '{args.backend}'.")
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

    # Lemma-share: prove transition step-identities BEFORE always inductions so
    # the ACL2-proved lemmas are available to the induction.  Stable sort keeps
    # the original relative order within each kind.
    def _obligation_rank(po) -> int:
        prop = po.get("property") if isinstance(po, dict) else getattr(po, "property", "")
        kind = _property_kind(spec_module, prop)
        if kind == "transition":
            return 0
        if kind == "always":
            return 1
        return 2
    theorem_obligations = sorted(theorem_obligations, key=_obligation_rank)

    rtl_dir = None
    assertions_dir = None
    rtl_file = None
    assertions_file = None
    koika_needs_mc_prep = False

    use_mc_lemmas = config.get("provers", {}).get("koika", {}).get("use_mc_lemmas", False)
    if use_mc_lemmas:
        # Check if any theorem obligation uses the Koika backend (including the
        # co-work koika_acl2, whose `always` obligations are proved on the Koika
        # side and so can consume the MC-proved invariant lemmas).
        for po in theorem_obligations:
            backend = po.get("backend") if isinstance(po, dict) else getattr(po, "backend", "")
            if _canonical_backend(backend) in ("koika", "koika_acl2"):
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
                assert_mod = isir_to_assert_convert(spec_module)
                _drive_inputs(assert_mod, spec_module)
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
                signal_map, reset_inverted = _rtl_signal_map(spec_module)
                _inject_inline_assertions(rtl_file, assert_mod, signal_widths, signal_map, reset_inverted)
                _force_inputs_in_rtl(rtl_file, spec_module)
                assertions_file = None  # assertions are inline in the RTL
            except Exception as e:
                logger.error("Inline assertion injection for MC prep failed: %s", e)
                koika_needs_mc_prep = False
                assertions_file = None

    # Build context for proof skill
    context: Dict[str, Any] = {
        "spec_module": spec_module,
        "config": config,
    }
    if koika_needs_mc_prep and rtl_file:
        context["rtl_file_path"] = str(rtl_file)
        logger.info("Provided inline-asserted RTL path for automatic MC lemma injection.")

    results: List[ProofObligationResult] = []

    if theorem_obligations:
        backend_files: Dict[str, str] = {}
        backends_needed: set = set()

        for po in theorem_obligations:
            backend = po.get("backend") if isinstance(po, dict) else getattr(po, "backend", "koika")
            canonical = _canonical_backend(backend)
            downgrade_cowork = getattr(args, 'no_cowork', False) or _canonical_backend(args.backend) == "koika"
            acl2_only = getattr(args, 'acl2_only', False) or _canonical_backend(args.backend) == "acl2"
            canonical = _effective_backend(canonical, downgrade_cowork, acl2_only)
            if canonical == "koika":
                backends_needed.add("koika")
            elif canonical == "acl2":
                backends_needed.add("acl2")
            elif canonical == "koika_acl2":
                backends_needed.add("koika")
                backends_needed.add("acl2")

        if "koika" in backends_needed:
            coq_dir = out_dir / "coq"
            coq_dir.mkdir(exist_ok=True)
            coq_file = coq_dir / f"{design_name}.v"
            try:
                koika_mod = isir_to_koika_convert(spec_module)
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
                acl2_mod = isir_to_acl2_convert(spec_module)
                acl2_code = acl2_mod.to_acl2_code() if hasattr(acl2_mod, "to_acl2_code") else _generate_acl2_from_module(acl2_mod)
                acl2_file.write_text(acl2_code, encoding="utf-8")
                backend_files["acl2"] = str(acl2_file)
                logger.info(f"ACL2 file written to {acl2_file}")
            except Exception as e:
                logger.error(f"Failed to generate ACL2 file: {e}")
                return 1

        try:
            if args.max_attempts is not None:
                # Propagate to the provers' LLM repair loops (Koika and ACL2),
                # which read config["proof"]["max_repair_attempts"] — the skill
                # attribute `max_repair_attempts` is never read.
                config.setdefault("proof", {})["max_repair_attempts"] = args.max_attempts
            proof_skill = LLMProofSkill(config=config)
            if args.no_llm:
                logger.warning("--no-llm flag is experimental; LLM may still be used for repair.")
        except Exception as e:
            logger.error(f"Failed to initialize proof skill: {e}")
            return 1

        # SAT gate pre-filter: short-circuit inductive (always) obligations whose
        # BASE_ENTAIL + IND_STEP pair is UNSAT (T3-certified induction).  The
        # gate is a pre-filter only; anything it does not resolve falls through
        # to the ITP below.
        sat_gate_results: Dict[str, Any] = {}
        if getattr(args, "sat_gate", False):
            from isir.verification.sat_gate.gate_runner import run_gate
            from isir.verification.sat_gate.policy import EvidenceAction
            try:
                _gate_rows, _gate_metrics = run_gate(spec_module)
                for _gr in _gate_rows:
                    sat_gate_results[_gr.property] = _gr
                gated = sum(1 for _gr in _gate_rows
                            if _gr.evidence_action is EvidenceAction.PROVE_STEP)
                logger.info(
                    "SAT gate: %d always obligation(s), %d gated (inductive pair), "
                    "coverage %.2f",
                    _gate_metrics.eligible_pre, gated, _gate_metrics.coverage(),
)
            except Exception as e:  # noqa: BLE001
                logger.warning("SAT gate pre-filter failed; falling through to the ITP: %s", e)

        # Lemma-share arm: transition step-identities proved by ACL2 are collected
        # here (as their Coq theorem names) and shared into later `always`
        # inductions, which may consume them via `Hint Resolve`.
        shared_step_lemmas: List[str] = []

        for po in theorem_obligations:
            prop_name = po.get("property") if isinstance(po, dict) else getattr(po, "property", "unknown")
            backend_raw = po.get("backend") if isinstance(po, dict) else getattr(po, "backend", "koika")
            canonical = _canonical_backend(backend_raw) or "koika"
            downgrade_cowork = getattr(args, 'no_cowork', False) or _canonical_backend(args.backend) == "koika"
            acl2_only = getattr(args, 'acl2_only', False) or _canonical_backend(args.backend) == "acl2"
            canonical = _effective_backend(canonical, downgrade_cowork, acl2_only)
            if getattr(args, "sat_gate", False) and prop_name in sat_gate_results:
                _gr = sat_gate_results[prop_name]
                if _gr.evidence_action is not None and _gr.evidence_action.value == "prove_step":
                    logger.info(
                        "SAT-gated '%s' (inductive pair UNSAT, T3): skipping ITP", prop_name,
)
                    results.append(ProofObligationResult(
                        property=prop_name,
                        status=Status.SAT_GATED,
                        backend="sat_gate",
                        error_message=None,
))
                    continue
            logger.info(f"Proving '{prop_name}' with backend {canonical}")

            start_time = time.time()
            po_context = dict(context)  # copy
            po_context["obligation"] = po

            cowork_result = None
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
            elif canonical == "acl2":
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
                # Inductive (always) obligations need induction; ACL2 can only
                # skip-proof them, so under single-backend ACL2 they are skipped
                # (mirrors the co-work "ACL2 cannot prove induction" gating).
                if _property_kind(spec_module, prop_name) == "always":
                    logger.info(
                        "Skipping inductive obligation '%s' (kind=always): "
                        "ACL2 cannot prove induction", prop_name,
)
                    results.append(ProofObligationResult(
                        property=prop_name,
                        status=Status.SKIPPED,
                        backend=canonical,
                        error_message="ACL2 cannot prove induction (skipped under single-backend ACL2)",
))
                    continue
            else:  # koika_acl2 co-work
                if "koika" not in backend_files or "acl2" not in backend_files:
                    logger.error("Coq/ACL2 files not generated; cannot co-work.")
                    results.append(ProofObligationResult(
                        property=prop_name,
                        status=Status.ERROR,
                        backend=canonical,
                        error_message="Coq/ACL2 files missing"
))
                    continue
                po_context["coq_file_path"] = backend_files["koika"]
                po_context["acl2_file_path"] = backend_files["acl2"]
                po_context["theorem_statement"] = _extract_acl2_statement(acl2_mod, prop_name)
                logger.info("Co-work (koika_acl2): dispatching both provers concurrently for '%s'", prop_name)
                from isir.verification.cowork import run_cowork
                koika_ctx = dict(po_context)
                koika_ctx["theorem_name"] = f"{prop_name}_proved"
                koika_ctx.pop("acl2_file_path", None)
                koika_ctx.pop("theorem_statement", None)
                acl2_ctx = dict(po_context)
                acl2_ctx["theorem_name"] = f"{prop_name}_correct"
                acl2_ctx.pop("coq_file_path", None)
                prop_kind = _property_kind(spec_module, prop_name)
                if prop_kind == "always":
                    # Inductive safety/invariant properties need induction; ACL2 can
                    # only skip-proof them, so its half of the co-work is wasted
                    # work.  Prove with Koika alone.
                    logger.info(
                        "Inductive property '%s' (kind=%s): proving with Koika only "
                        "(ACL2 cannot prove induction)", prop_name, prop_kind,
)
                    # Share the ACL2-proved transition step-identities into this
                    # induction so Koika can `Hint Resolve` them.
                    koika_ctx["shared_lemmas"] = list(shared_step_lemmas)
                    cowork_result = proof_skill.prove({**po, "backend": "koika"}, koika_ctx)
                else:
                    # Bound each side so a slow loser can't hold resources forever;
                    # run_cowork returns on the FIRST success (first-wins).
                    # For combinational/transition (step-identity) kinds, ACL2's
                    # fast path is the combinational hint (no generalization),
                    # not the :induct t skeleton + full PERF traversal.
                    def _acl2_side() -> ProofResult:
                        if prop_kind == "transition":
                            # Step-identity: ACL2's :induct t skeleton closes it fast.
                            # Skip the (slow) PERF traversal and go straight to the
                            # linear prover.
                            return proof_skill._prove_linear(
                                {**po, "backend": "acl2"}, acl2_ctx, "acl2")
                        return proof_skill.prove({**po, "backend": "acl2"}, acl2_ctx)
                    cw = run_cowork(
                        lambda: proof_skill.prove({**po, "backend": "koika"}, koika_ctx),
                        _acl2_side,
                        timeout=60,
)
                    cowork_result = ProofResult(
                        success=cw.success,
                        proof_script=cw.proof_script,
                        error_message=cw.error_message,
                        auxiliary_lemmas=cw.auxiliary_lemmas,
                        metadata=cw.metadata,
                        duration=time.time() - start_time,
                        backend="koika_acl2",
)
                    if not cw.success:
                        # Both backends failed on the same sub-goal: reflect (LLM
                        # proposes a complete Coq script) then re-dispatch + re-prove.
                        from isir.verification.cowork import cowork_retry
                        retry = cowork_retry(
                            cw, proof_skill.llm,
                            lambda s: proof_skill._prove_linear(
                                {**po, "backend": "koika"}, koika_ctx, "koika",
                                initial_script=s,
),
)
                        if retry is not None:
                            retry.metadata["cross_backend_reflection"] = retry.proof_script or ""
                            cowork_result = retry
                            logger.info(
                                "Co-work reflection proved '%s' (neither backend alone could)",
                                prop_name,
)

                    # Lemma-share: a proved transition step-identity is a reusable
                    # combinational lemma for later `always` inductions.
                    if prop_kind == "transition" and cowork_result.success:
                        shared_step_lemmas.append(f"{prop_name}_proved")
                        logger.info(
                            "Shared step-identity '%s_proved' for later inductions",
                            prop_name,
)

            if cowork_result is not None:
                result = cowork_result
            else:
                try:
                    result: ProofResult = proof_skill.prove({**po, "backend": canonical}, po_context)
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

        # Build the base assertion module + signal info once, then run the
        # model checker once per obligation so each property gets its own
        # PASS/FAIL verdict.
        assert_mod_full = isir_to_assert_convert(spec_module)
        _drive_inputs(assert_mod_full, spec_module)
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
        signal_map, reset_inverted = _rtl_signal_map(spec_module)
        base_rtl_content = rtl_file.read_text()

        for po in mc_obligations:
            prop = po.get("property") if isinstance(po, dict) else getattr(po, "property", "?")
            assert_mod = copy.copy(assert_mod_full)
            assert_mod.always_checks = [
                c for c in assert_mod_full.always_checks
                if getattr(c, 'label', None) == prop
            ]
            assert_mod.properties = [
                p for p in assert_mod_full.properties
                if getattr(p, 'label', None) == prop
            ]
            try:
                rtl_str = _inject_inline_assertions_str(
                    base_rtl_content, assert_mod, signal_widths, signal_map, reset_inverted
)
                rtl_str = _force_inputs_rtl_str(rtl_str, spec_module)
                prop_rtl = mc_dir / "rtl" / f"{design_name}_{prop}.v"
                prop_rtl.write_text(rtl_str, encoding="utf-8")
                mc_result = run_model_check(
                    rtl_path=prop_rtl,
                    assertions_path=None,
                    top_module=design_name
)
            except Exception as e:
                logger.error(f"Model checking failed for {prop}: {e}")
                results.append(ProofObligationResult(
                    property=prop,
                    status=Status.ERROR,
                    backend="model_checking",
                    error_message=str(e)
))
                continue

            if mc_result.get("success"):
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

    all_passed = all(o.status in (Status.PASS, Status.SKIPPED, Status.SAT_GATED)
                     for o in results)
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
        from isir.evidence.annotator import add_evidence_to_registry, create_evidence_ref
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
        from isir.evidence.annotator import add_evidence_to_registry, create_evidence_ref
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
    parts = [f";; Generated from ISIR design {acl2_mod.name}"]
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
