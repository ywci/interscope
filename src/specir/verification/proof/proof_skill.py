# src/specir/verification/proof/proof_skill.py
#
# LLM‑driven proof orchestrator that delegates to specialized provers
# (KoikaProver, ACL2Prover, ModelCheckProver) and manages the repair loop.

from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path

from specir.backends.llm_client import get_llm_client_from_config
from specir.verification.proof.proof import ProofSkill, ProofResult
from specir.verification.proof.koika.prover import KoikaProver
from specir.verification.proof.acl2.prover import ACL2Prover
from specir.verification.model_checker import run_model_check, ModelCheckError
from specir.utils.logger import get_logger
from specir.utils.config_loader import get_config
from specir.verification.perf.perf_config import PERFConfig, validate_perf_against_config
from specir.verification.perf.perf_stats import PERFStats
from specir.verification.perf.perf_traversal import PERFTraversal
from specir.verification.perf.perf_analyzer import PERFAnalyzer, ObligationAnalysis
from specir.verification.proof.structural_validator import validate_structure
from specir.verification.proof.tactic_modernizer import modernize_tactics
from specir.verification.proof.koika.proof_gen import adapt_proof
from specir.verification.proof.proof_pattern_cache import get_proof_pattern_cache

logger = get_logger(__name__)


class ModelCheckProver:
    """Prover that wraps an external model checker (SymbiYosys / sby)."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        if config is None:
            config = get_config()
        self.config = config

    def prove(
        self,
        rtl_path: Path,
        assertions_path: Path,
        top_module: str,
        engine: str = "bmc",
        depth: Optional[int] = None,
        timeout: Optional[int] = None
    ) -> Dict[str, Any]:
        try:
            result = run_model_check(
                rtl_path=rtl_path,
                assertions_path=assertions_path,
                top_module=top_module,
                engine=engine,
                depth=depth,
                timeout=timeout
            )
            return result
        except ModelCheckError as e:
            return {
                "success": False,
                "status": "error",
                "error": str(e),
                "output": "",
                "counterexample_trace": None
            }


class LLMProofSkill(ProofSkill):
    """Proof skill that combines PERF, linear provers, and model checking."""

    # Track which designs have already had their model checking pre‑run
    _mc_prepared: Dict[str, bool] = {}

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        if config is None:
            config = get_config()
        self.config = config
        self.llm = get_llm_client_from_config(config)
        self._koika_prover: Optional[KoikaProver] = None
        self._acl2_prover: Optional[ACL2Prover] = None
        self._mc_prover: Optional[ModelCheckProver] = None

        proof_cfg = config.get("proof", {})
        prove_cfg = config.get("provers", {}).get("koika", {}).get("prove", {})

        self.max_repair_attempts = proof_cfg.get("max_repair_attempts", 5)
        self.max_consecutive_failures = prove_cfg.get("max_consecutive_failures", 10)
        self.max_steps = prove_cfg.get("max_steps", 80)
        self.pre_simplify = prove_cfg.get("pre_simplify", True)
        self.invariant_mining = prove_cfg.get("invariant_mining", True)

        self.use_stronger_llm = prove_cfg.get("use_stronger_llm", True)
        self.max_stronger_attempts = prove_cfg.get("max_stronger_attempts", 3)

        self.perf_global_config = PERFConfig.from_global_config(self.config)
        self._last_perf_stats: Optional[PERFStats] = None

        self._analysis: Optional[ObligationAnalysis] = None
        self._analyzer = PERFAnalyzer()

        # In‑memory cache of successful proofs (fast path).
        self._successful_proofs: Dict[str, str] = {}

        # Persistent proof pattern cache.
        try:
            self._proof_cache = get_proof_pattern_cache(self.config)
        except Exception as e:
            logger.warning("Failed to initialize proof pattern cache: %s", e)
            self._proof_cache = None

        try:
            validate_perf_against_config(self.config)
        except ValueError as e:
            logger.warning("PERF configuration validation: %s", e)

        logger.info(
            "LLMProofSkill initialized: PERF enabled=%s",
            self.perf_global_config.enabled,
        )

    def _store_successful_proof(self, design_name: str, prop_name: str, script: str) -> None:
        """Store a successful proof in both in‑memory and persistent caches."""
        if not design_name or not prop_name or not script:
            return
        self._successful_proofs[prop_name] = script
        if self._proof_cache:
            try:
                self._proof_cache.store_successful_proof(design_name, prop_name, script)
            except Exception as e:
                logger.warning("Failed to store proof in pattern cache: %s", e)

    def _get_cached_proof(self, design_name: str, prop_name: str) -> Optional[str]:
        """Retrieve a cached proof for a design/property, if available."""
        if not design_name or not prop_name:
            return None
        if prop_name in self._successful_proofs:
            return self._successful_proofs[prop_name]
        if self._proof_cache:
            try:
                cached = self._proof_cache.get_successful_proof(design_name, prop_name)
                if cached:
                    self._successful_proofs[prop_name] = cached
                    return cached
            except Exception as e:
                logger.warning("Failed to read proof pattern cache: %s", e)
        return None

    def can_handle(self, proof_obligation: Dict[str, Any]) -> bool:
        engine = (proof_obligation.get("engine") or "").lower()
        if engine == "model_checking":
            return True
        backend = (proof_obligation.get("backend") or "").lower()
        normalised = backend.replace("ō", "o")
        return normalised.startswith("koi") or normalised == "acl2"

    def prove(
        self,
        proof_obligation: Dict[str, Any],
        context: Dict[str, Any]
    ) -> ProofResult:
        engine = (proof_obligation.get("engine") or "").lower()

        if (engine != "model_checking"
                and self.config.get("provers", {}).get("koika", {}).get("use_mc_lemmas", False)):
            backend = (proof_obligation.get("backend") or "").lower().replace("ō", "o")
            if backend.startswith("koi"):
                self._prepare_model_check_lemmas(context)

        if engine == "model_checking":
            return self._prove_model_check(proof_obligation, context)

        backend = (proof_obligation.get("backend") or "").lower().replace("ō", "o")

        perf_config = PERFConfig.from_obligation_metadata(
            self.perf_global_config,
            proof_obligation.get("metadata", {}),
        )

        self._analysis = None
        if backend.startswith("koi"):
            coq_file = context.get("coq_file_path")
            theorem_name = context.get("theorem_name")
            if coq_file and theorem_name:
                self._analysis = self._analyzer.analyze(Path(coq_file), theorem_name)
                if self._analysis.suggests_rule_splitting:
                    logger.warning(
                        "Obligation analysis suggests rule splitting would help. "
                        "Consider adding the 'split' attribute to monolithic rules."
                    )

        if perf_config.is_enabled_for_obligation(proof_obligation):
            logger.info(
                "PERF enabled for obligation '%s' (backend=%s)",
                proof_obligation.get("property", "unknown"),
                backend,
            )
            return self._prove_with_perf(proof_obligation, context, perf_config)

        return self._prove_linear(proof_obligation, context, backend)

    def _prepare_model_check_lemmas(self, context: Dict[str, Any]) -> None:
        spec_module = context.get("spec_module")
        if not spec_module:
            return

        design_name = spec_module.name
        if design_name in self._mc_prepared:
            return

        mc_obligations = [
            po for po in spec_module.proof_obligations
            if (isinstance(po, dict) and po.get("engine") == "model_checking")
            or (hasattr(po, "engine") and po.engine == "model_checking")
        ]
        if not mc_obligations:
            self._mc_prepared[design_name] = True
            return

        rtl_path = context.get("rtl_file_path")
        assertions_path = context.get("assertions_file_path")
        if not rtl_path or not assertions_path:
            logger.warning(
                "Cannot run model checking pre‑pass: missing RTL or assertions path."
            )
            return

        logger.info(
            "Pre‑running %d model‑checking obligation(s) for design '%s' to "
            "populate MC lemmas.",
            len(mc_obligations),
            design_name,
        )

        for po in mc_obligations:
            try:
                result = self._prove_model_check(po, context)
                if not result.success:
                    logger.warning(
                        "Model‑checking pre‑run for '%s' failed: %s",
                        po.get("property") if isinstance(po, dict) else getattr(po, "property", "?"),
                        result.error_message,
                    )
            except Exception as e:
                logger.error("Model‑checking pre‑run exception: %s", e)

        self._mc_prepared[design_name] = True

    def _prove_linear(
        self,
        obligation: Dict[str, Any],
        context: Dict[str, Any],
        backend: str,
        initial_script: Optional[str] = None,
    ) -> ProofResult:
        if initial_script is not None:
            initial_script = self._prepare_initial_script(initial_script)

        if backend.startswith("koi"):
            result = self._prove_koika(obligation, context, initial_script=initial_script)
        elif backend == "acl2":
            result = self._prove_acl2(obligation, context, initial_script=initial_script)
        else:
            result = ProofResult(
                success=False,
                error_message=f"Unsupported backend: {backend}"
            )

        if result.success and result.proof_script:
            prop_name = obligation.get("property", "")
            design_name = context.get("design_name")
            if not design_name and context.get("spec_module"):
                design_name = getattr(context["spec_module"], "name", None)
            if prop_name and design_name:
                self._store_successful_proof(design_name, prop_name, result.proof_script)

        return result

    def _prepare_initial_script(self, script: str) -> str:
        """Validate and modernise an initial proof script."""
        if not script:
            return script

        modernized = modernize_tactics(script)
        issues = validate_structure(modernized)
        if issues:
            logger.warning(
                "Structural issues in initial script:\n  %s",
                "\n  ".join(issues),
            )

        return modernized

    def _prove_koika(
        self,
        obligation: Dict[str, Any],
        context: Dict[str, Any],
        initial_script: Optional[str] = None,
    ) -> ProofResult:
        coq_path = context.get("coq_file_path")
        if not coq_path:
            return ProofResult(success=False, error_message="Missing 'coq_file_path'")
        theorem_name = context.get("theorem_name") or obligation.get("property", "")
        if not theorem_name:
            return ProofResult(success=False, error_message="Missing property name")

        metadata = obligation.get("metadata", {}) if isinstance(obligation, dict) else {}
        tactic_hints = metadata.get("coq_tactic_hints", [])
        has_overrides = any(
            metadata.get(k) is not None
            for k in ("max_consecutive_failures", "max_steps", "pre_simplify", "invariant_mining")
        )

        if has_overrides:
            custom_cfg = self.config.copy()
            prove_cfg = custom_cfg.setdefault("provers", {}).setdefault("koika", {}).setdefault("prove", {})
            if metadata.get("max_consecutive_failures") is not None:
                prove_cfg["max_consecutive_failures"] = metadata["max_consecutive_failures"]
            if metadata.get("max_steps") is not None:
                prove_cfg["max_steps"] = metadata["max_steps"]
            if metadata.get("pre_simplify") is not None:
                prove_cfg["pre_simplify"] = metadata["pre_simplify"]
            if metadata.get("invariant_mining") is not None:
                prove_cfg["invariant_mining"] = metadata["invariant_mining"]
            prover = KoikaProver(config=custom_cfg)
        else:
            if self._koika_prover is None:
                self._koika_prover = KoikaProver(config=self.config)
            prover = self._koika_prover

        if self._analysis:
            hints_str = self._build_structural_hints_string()
            if hints_str:
                prover.set_structural_hints(hints_str)

        if context.get("spec_module"):
            prover.spec_module = context["spec_module"]

        try:
            result: ProofResult = prover.prove_theorem(
                coq_file=Path(coq_path),
                theorem_name=theorem_name,
                tactic_hints=tactic_hints if tactic_hints else None,
                initial_script=initial_script,
            )
        except Exception as e:
            logger.exception("Koika prover raised an exception")
            return ProofResult(success=False, error_message=f"Koika prover error: {e}")
        finally:
            if has_overrides and prover is not self._koika_prover:
                prover.close()

        if result.success:
            return ProofResult(
                success=True,
                proof_script=result.proof_script or "",
                metadata={"backend": "koika"}
            )
        return ProofResult(
            success=False,
            error_message=result.error_message or "Unknown Koika proof failure",
            metadata={"backend": "koika"}
        )

    def _prove_acl2(
        self,
        obligation: Dict[str, Any],
        context: Dict[str, Any],
        initial_script: Optional[str] = None,
    ) -> ProofResult:
        acl2_file = context.get("acl2_file_path")
        if not acl2_file:
            return ProofResult(success=False, error_message="Missing 'acl2_file_path'")
        theorem_name = context.get("theorem_name") or obligation.get("property", "")
        if not theorem_name:
            return ProofResult(success=False, error_message="Missing property name")

        if self._acl2_prover is None:
            self._acl2_prover = ACL2Prover(config=self.config)

        statement = context.get("theorem_statement")
        hints = (
            obligation.get("metadata", {}).get("acl2_hints", [])
            if isinstance(obligation, dict)
            else []
        )

        try:
            result: ProofResult = self._acl2_prover.prove_theorem(
                theorem_name=theorem_name,
                statement=statement,
                hints=hints if hints else None,
                initial_script=initial_script,
            )
        except Exception as e:
            logger.exception("ACL2 prover raised an exception")
            return ProofResult(success=False, error_message=f"ACL2 prover error: {e}")

        if result.success:
            return ProofResult(
                success=True,
                proof_script=result.proof_script or "",
                metadata={"backend": "acl2"}
            )
        return ProofResult(
            success=False,
            error_message=result.error_message or "Unknown ACL2 proof failure",
            metadata={"backend": "acl2"}
        )

    def _prove_model_check(self, obligation: Dict[str, Any], context: Dict[str, Any]) -> ProofResult:
        rtl_path = context.get("rtl_file_path")
        assertions_path = context.get("assertions_file_path")
        if not rtl_path or not assertions_path:
            return ProofResult(
                success=False,
                error_message="Missing 'rtl_file_path' or 'assertions_file_path' in context"
            )
        top_module = context.get("top_module") or (
            context.get("spec_module").name if context.get("spec_module") else "top"
        )
        metadata = obligation.get("metadata", {}) if isinstance(obligation, dict) else {}
        engine = metadata.get("mc_engine", "bmc")
        depth = metadata.get("depth")
        timeout = metadata.get("timeout")

        if self._mc_prover is None:
            self._mc_prover = ModelCheckProver(config=self.config)

        result = self._mc_prover.prove(
            rtl_path=Path(rtl_path),
            assertions_path=Path(assertions_path),
            top_module=top_module,
            engine=engine,
            depth=depth,
            timeout=timeout
        )

        prop_name = obligation.get("property") if isinstance(obligation, dict) else getattr(obligation, "property", "?")
        try:
            from specir.evidence.annotator import create_evidence_ref, add_evidence_to_registry
            if result.get("success"):
                evidence = create_evidence_ref(
                    evidence_type="inductive_invariant",
                    ref_type="local_id",
                    ref_value=f"local:{prop_name}",
                    engine="BMC" if engine == "bmc" else "IC3",
                    status="proved",
                    property_name=prop_name,
                )
                add_evidence_to_registry(evidence, property_name=prop_name)
                logger.info("Registered model‑checking evidence for '%s'.", prop_name)
            else:
                cex_trace = result.get("counterexample_trace")
                ref_val = str(cex_trace) if cex_trace else f"local:{prop_name}"
                evidence = create_evidence_ref(
                    evidence_type="counterexample_trace",
                    ref_type="uri" if cex_trace else "local_id",
                    ref_value=ref_val,
                    engine="BMC" if engine == "bmc" else "IC3",
                    status="counterexample",
                    property_name=prop_name,
                )
                add_evidence_to_registry(evidence, property_name=prop_name)
                logger.info("Registered counterexample evidence for '%s'.", prop_name)
        except Exception as e:
            logger.warning("Failed to register model‑checking evidence: %s", e)

        if result.get("success"):
            return ProofResult(
                success=True,
                proof_script="Model checking succeeded",
                metadata={"backend": "model_checking", "engine": engine}
            )
        return ProofResult(
            success=False,
            error_message=result.get("error") or "Model checking failed",
            metadata={"backend": "model_checking", "engine": engine}
        )

    def _prove_with_perf(
        self,
        obligation: Dict[str, Any],
        context: Dict[str, Any],
        perf_config: PERFConfig
    ) -> ProofResult:
        logger.info(
            "Starting PERF traversal for '%s' (beam=%d, depth=%d, branches=%d)",
            obligation.get("property", "unknown"),
            perf_config.beam_size,
            perf_config.depth_limit,
            perf_config.branches_per_node
        )

        backend = obligation.get("backend", "koika").lower().replace("ō", "o")

        # Fast skeleton proof attempt (optional, before PERF)
        if perf_config.try_skeleton_first and backend.startswith("koi"):
            coq_file = context.get("coq_file_path")
            theorem_name = context.get("theorem_name")
            if coq_file and theorem_name:
                logger.info("Attempting fast skeleton proof before PERF...")

                temp_prover = KoikaProver(config=self.config)
                temp_prover._prelude = ""
                temp_prover._prelude_validated = True

                if self._analysis:
                    hints_str = self._build_structural_hints_string()
                    if hints_str:
                        temp_prover.set_structural_hints(hints_str)
                if context.get("spec_module"):
                    temp_prover.spec_module = context["spec_module"]

                skeleton_result = temp_prover.prove_with_skeleton_only(
                    Path(coq_file), theorem_name
                )
                temp_prover.close()

                if skeleton_result and skeleton_result.get("success"):
                    logger.info("Skeleton proof succeeded – PERF skipped.")
                    self._last_perf_stats = PERFStats()
                    prop_name = obligation.get("property", "")
                    design_name = context.get("design_name")
                    if not design_name and context.get("spec_module"):
                        design_name = getattr(context["spec_module"], "name", None)
                    if prop_name and design_name:
                        self._store_successful_proof(design_name, prop_name, skeleton_result["proof_script"])
                    return ProofResult(
                        success=True,
                        proof_script=skeleton_result["proof_script"],
                        metadata={"backend": "koika", "skeleton": True}
                    )

        # Proof‑pattern reuse from cache / successful proofs
        initial_script = None
        prop_name = obligation.get("property", "")
        design_name = context.get("design_name")
        if not design_name and context.get("spec_module"):
            design_name = getattr(context["spec_module"], "name", None)

        # 1) Try proof library (if allowed)
        use_library_allowed = self.config.get("provers", {}).get("koika", {}).get(
            "use_proof_library", False
        )
        if use_library_allowed and backend.startswith("koi"):
            from lib.koika.assist import PROOF_LIBRARY
            lib_key = context.get("theorem_name", "")
            if lib_key in PROOF_LIBRARY:
                logger.info("Using library proof as PERF initial script.")
                initial_script = PROOF_LIBRARY[lib_key]
                initial_script = self._prepare_initial_script(initial_script)

        # 2) Try cached proof for this exact property
        if initial_script is None and design_name and prop_name:
            cached = self._get_cached_proof(design_name, prop_name)
            if cached:
                logger.info("Using cached proof for '%s/%s' as PERF initial script.", design_name, prop_name)
                initial_script = self._prepare_initial_script(cached)

        # 3) Try adapting a previously proven similar property
        if initial_script is None and self._successful_proofs:
            similar_proof = self._find_and_adapt_similar_proof(prop_name, obligation, context)
            if similar_proof:
                logger.info(
                    "Using adapted proof from a previously proven obligation as PERF initial script."
                )
                initial_script = self._prepare_initial_script(similar_proof)

        if initial_script:
            context["initial_script"] = initial_script

        perf_context = self._build_perf_context(obligation, context, perf_config)

        # Model‑checking counterexample trace extraction (only if enabled)
        if self.perf_global_config.mc_guided_prompt_enabled:
            mc_trace_info = self._extract_mc_trace_info(obligation, context)
            if mc_trace_info:
                perf_context["mc_trace_info"] = mc_trace_info
                logger.info("MC counterexample trace information added to PERF context.")

        try:
            traversal = PERFTraversal(
                config=perf_config,
                llm_client=self.llm,
                context=perf_context
            )
            proof_script, stats = traversal.traverse()
            self._last_perf_stats = stats

            if proof_script is not None and stats.successful_depth is not None:
                logger.info(
                    "PERF found a proof for '%s' at depth %d",
                    prop_name,
                    stats.successful_depth
                )
                if prop_name and design_name:
                    self._store_successful_proof(design_name, prop_name, proof_script)
                return ProofResult(
                    success=True,
                    proof_script=proof_script,
                    metadata={
                        "backend": obligation.get("backend", "unknown"),
                        "perf_stats": stats.to_dict(),
                        "perf_successful_depth": stats.successful_depth
                    }
                )

            if initial_script and stats.total_nodes == 0:
                logger.info("Library/adapted proof verified by PERF; returning success.")
                if prop_name and design_name:
                    self._store_successful_proof(design_name, prop_name, initial_script)
                return ProofResult(
                    success=True,
                    proof_script=initial_script,
                    metadata={
                        "backend": obligation.get("backend", "unknown"),
                        "perf_stats": stats.to_dict(),
                        "library": True
                    }
                )

            # PERF did not find a proof. Try to salvage the best candidate.
            best_candidate = self._get_best_candidate_from_perf(traversal)
            if best_candidate:
                best_candidate = self._prepare_initial_script(best_candidate)
                logger.info(
                    "PERF exhausted for '%s', but a best candidate was found. "
                    "Passing it to linear prover as initial_script for focused repair.",
                    prop_name
                )
                result = self._prove_linear(
                    obligation,
                    context,
                    backend,
                    initial_script=best_candidate,
                )
                if result.success:
                    logger.info("Linear prover succeeded using PERF's best candidate.")
                    result.metadata["perf_stats"] = stats.to_dict()
                    result.metadata["perf_used_best_candidate"] = True
                    if prop_name and design_name:
                        self._store_successful_proof(design_name, prop_name, result.proof_script or "")
                    return result
                else:
                    logger.info(
                        "Linear prover could not prove using PERF best candidate; "
                        "falling back to normal linear prover from scratch."
                    )

            # Fallback to normal linear prover (without initial script).
            logger.warning(
                "PERF exhausted for '%s' (max_depth=%d, nodes=%d). "
                "Falling back to linear prover from scratch.",
                prop_name,
                stats.max_depth,
                stats.total_nodes
            )
            result = self._prove_linear(obligation, context, backend)

            # Stronger LLM fallback after linear prover fails
            if not result.success and self.use_stronger_llm and backend.startswith("koi"):
                logger.info(
                    "Linear prover failed for '%s'. Attempting stronger LLM fallback.",
                    prop_name
                )
                stronger_result = self._prove_with_stronger_llm(obligation, context, backend)
                if stronger_result.success:
                    stronger_result.metadata["perf_stats"] = stats.to_dict()
                    stronger_result.metadata["stronger_llm_fallback"] = True
                    if prop_name and design_name:
                        self._store_successful_proof(design_name, prop_name, stronger_result.proof_script or "")
                    return stronger_result

            return result

        except Exception as e:
            logger.exception("PERF traversal raised an exception; falling back to linear prover.")
            return self._prove_linear(obligation, context, backend)

    def _get_best_candidate_from_perf(self, traversal: PERFTraversal) -> Optional[str]:
        """Extract the highest‑scored proof script from the PERF traversal."""
        best = getattr(traversal, "best_candidate_script", None)
        if best:
            return best

        getter = getattr(traversal, "get_best_candidate", None)
        if callable(getter):
            try:
                best = getter()
                if best:
                    return best
            except Exception:
                pass

        last_frontier = getattr(traversal, "last_frontier", None)
        if last_frontier:
            best_node = max(
                last_frontier,
                key=lambda n: n.score.get(self.perf_global_config.primary_dimension, 0.0)
                if n.score else 0.0
            )
            return best_node.script
        return None

    def _find_and_adapt_similar_proof(
        self,
        current_prop: str,
        obligation: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Optional[str]:
        """Look for a previously proven property with a similar name and try to adapt its proof."""
        if not current_prop:
            return None

        best_match = None
        best_score = 0
        for prop_name, proof in self._successful_proofs.items():
            if prop_name == current_prop:
                continue
            i = 0
            for a, b in zip(prop_name, current_prop):
                if a == b:
                    i += 1
                else:
                    break
            if i > best_score:
                best_score = i
                best_match = (prop_name, proof)

        if best_match is None or best_score < 5:
            return None

        prop_name, proof = best_match
        theorem_name = context.get("theorem_name", current_prop)
        theorem_stmt = context.get("theorem_statement", "")

        if obligation.get("backend", "").lower().startswith("koi"):
            condition_subst = {}
            operation_subst = {}
            if "overflow_implies_result_neq_sum" in prop_name and "overflow_implies_result_neq_diff" in current_prop:
                condition_subst["op_reg s =? 0"] = "op_reg s =? 1"
                operation_subst["a_reg s + b_reg s"] = "a_reg s - b_reg s"
            elif "overflow_implies_result_neq_diff" in prop_name and "overflow_implies_result_neq_sum" in current_prop:
                condition_subst["op_reg s =? 1"] = "op_reg s =? 0"
                operation_subst["a_reg s - b_reg s"] = "a_reg s + b_reg s"

            if condition_subst or operation_subst:
                adapted = adapt_proof(
                    proof, theorem_name, theorem_stmt,
                    condition_subst=condition_subst,
                    operation_subst=operation_subst,
                )
                if adapted:
                    return adapted

        return proof

    def _extract_mc_trace_info(
        self,
        obligation: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Optional[str]:
        """Extract a concise string describing the model‑checking counterexample."""
        mc_trace = context.get("mc_trace")
        if mc_trace is None:
            return None

        prop_name = obligation.get("property", "")

        if hasattr(mc_trace, "extract_failing_trace"):
            try:
                failing = mc_trace.extract_failing_trace(prop_name, window=3)
                if failing and failing.get("failing_cycle") is not None:
                    cycle = failing["failing_cycle"]
                    lines = [f"Counterexample found at cycle {cycle}."]
                    window = failing.get("window", [])
                    if window:
                        lines.append("Relevant signal values:")
                        for w in window:
                            cyc = w["cycle"]
                            values = w.get("values", {})
                            sig_str = ", ".join(f"{k}={v}" for k, v in list(values.items())[:10])
                            lines.append(f"  cycle {cyc}: {sig_str}")
                    return "\n".join(lines)
            except Exception as e:
                logger.debug("Failed to extract from TraceModule: %s", e)

        if isinstance(mc_trace, str):
            return mc_trace[:2000]

        if isinstance(mc_trace, dict):
            try:
                import json
                return json.dumps(mc_trace, indent=2, default=str)[:2000]
            except Exception:
                return str(mc_trace)[:2000]

        return None

    def _prove_with_stronger_llm(
        self,
        obligation: Dict[str, Any],
        context: Dict[str, Any],
        backend: str,
    ) -> ProofResult:
        if not backend.startswith("koi"):
            return ProofResult(success=False, error_message="Stronger LLM only supported for Koika")

        logger.info("Attempting proof with stronger LLM settings for '%s'",
                    obligation.get("property", "unknown"))

        stronger_cfg = self.config.copy()
        proof_cfg = stronger_cfg.setdefault("proof", {})
        prove_cfg = stronger_cfg.setdefault("provers", {}).setdefault("koika", {}).setdefault("prove", {})

        proof_cfg["max_repair_attempts"] = self.max_stronger_attempts
        prove_cfg["use_rocq_mcp"] = False

        stronger_llm_cfg = self.config.get("llm_strong", None)
        if stronger_llm_cfg:
            stronger_cfg["llm"] = stronger_llm_cfg

        prover = KoikaProver(config=stronger_cfg)
        try:
            if self._analysis:
                hints_str = self._build_structural_hints_string()
                if hints_str:
                    prover.set_structural_hints(hints_str)
            if context.get("spec_module"):
                prover.spec_module = context["spec_module"]

            coq_path = context.get("coq_file_path")
            theorem_name = context.get("theorem_name") or obligation.get("property", "")

            result = prover.prove_theorem(
                coq_file=Path(coq_path) if coq_path else None,
                theorem_name=theorem_name,
                tactic_hints=(
                    obligation.get("metadata", {}).get("coq_tactic_hints", [])
                    if isinstance(obligation, dict) else []
                ),
                initial_script=None,
            )
            return result
        except Exception as e:
            logger.exception("Stronger LLM proof attempt raised an exception")
            return ProofResult(success=False, error_message=f"Stronger LLM error: {e}")
        finally:
            prover.close()

    def _build_perf_context(self, obligation: Dict[str, Any], context: Dict[str, Any],
                            perf_config: PERFConfig) -> Dict[str, Any]:
        backend = obligation.get("backend", "koika")
        perf_ctx = {
            "obligation": obligation,
            "backend": backend,
            "config": self.config,
            "llm": self.llm,
            "perf_config": perf_config
        }
        if backend == "koika" or backend.startswith("koi"):
            perf_ctx["coq_file_path"] = context.get("coq_file_path")
            perf_ctx["theorem_name"] = context.get("theorem_name")
            perf_ctx["workspace"] = context.get("workspace")
            perf_ctx["rocq_path"] = (
                self.config.get("provers", {})
                .get("koika", {})
                .get("prove", {})
                .get("rocq_mcp_path", "rocq-mcp")
            )
            if not context.get("theorem_statement") and context.get("coq_file_path"):
                perf_ctx["theorem_statement"] = self._extract_coq_statement(
                    Path(context["coq_file_path"]), context.get("theorem_name", "")
                )
        elif backend == "acl2":
            perf_ctx["acl2_file_path"] = context.get("acl2_file_path")
            perf_ctx["theorem_name"] = context.get("theorem_name")
            perf_ctx["theorem_statement"] = context.get("theorem_statement")
            perf_ctx["workspace"] = context.get("workspace")
            perf_ctx["acl2_mcp_path"] = (
                self.config.get("provers", {})
                .get("acl2", {})
                .get("mcp_path", "acl2-mcp")
            )
        if context.get("mc_trace"):
            perf_ctx["mc_trace"] = context["mc_trace"]
        if context.get("initial_script"):
            perf_ctx["initial_script"] = context["initial_script"]
        if context.get("spec_module"):
            perf_ctx["spec_module"] = context["spec_module"]
        return perf_ctx

    def _extract_coq_statement(self, coq_file: Path, theorem_name: str) -> str:
        import re
        try:
            content = coq_file.read_text()
            if theorem_name:
                pattern = re.compile(
                    rf"Theorem\s+{re.escape(theorem_name)}\s*:\s*([^.]*)\.", re.DOTALL
                )
                match = pattern.search(content)
                if match:
                    return match.group(1).strip()
            pattern = re.compile(r"Theorem\s+\w+\s*:\s*([^.]*)\.", re.DOTALL)
            match = pattern.search(content)
            if match:
                return match.group(1).strip()
        except Exception:
            pass
        return ""

    def _build_structural_hints_string(self) -> Optional[str]:
        if not self._analysis:
            return None

        hints = []

        if self._analysis.num_step_constructors == 1 and self._analysis.max_ite_depth >= 3:
            hints.append(
                "The step constructor contains a deeply nested if-then-else chain "
                f"(depth {self._analysis.max_ite_depth}). "
                "Consider using 'destruct' on the condition variables to split into cases."
            )
        if self._analysis.suggests_lemma_introduction and self._analysis.duplicated_subexpressions:
            hints.append(
                "Duplicated subexpressions detected: "
                + "; ".join(self._analysis.duplicated_subexpressions)
                + ". A helper lemma could simplify the proof."
            )

        if self._analysis.num_step_constructors == 2 and self._analysis.step_constructor_names:
            names = self._analysis.step_constructor_names
            hints.append(
                f"The step relation has exactly {len(names)} constructors: "
                f"{' and '.join(names)}.\n"
                "After induction on the reachability hypothesis, perform "
                "`inversion Hstep; subst; clear Hstep` to split into two sub‑goals.\n"
                f"- For `{names[0]}`, the induction hypothesis (IH) can be applied directly.\n"
                f"- For `{names[1]}`, the goal simplifies trivially with `simpl` "
                "and can be closed by `reflexivity` (the property is definitionally true)."
            )
        elif self._analysis.num_step_constructors == 2:
            hints.append(
                "The step relation has exactly two constructors. "
                "After induction on reachability, use `inversion Hstep; subst; clear Hstep` "
                "to split into two sub‑goals.  The first sub‑goal can be handled by the "
                "induction hypothesis; the second likely simplifies to reflexivity."
            )

        return "\n".join(hints) if hints else None

    def get_last_perf_stats(self) -> Optional[PERFStats]:
        return self._last_perf_stats

    def close(self) -> None:
        if self._koika_prover:
            self._koika_prover.close()
        if self._acl2_prover:
            self._acl2_prover.stop()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
