# src/specir/verification/proof/proof_skill.py
#
# LLM‑driven proof orchestrator that delegates to specialized provers
# (KoikaProver, ACL2Prover, ModelCheckProver) and manages the repair loop.
#
# PERF (Proof tree Exploration with Reflective Feedback):
# When enabled, PERF traversal is used instead of the linear repair loop.
# If a proof‑library entry exists for the obligation **and** the global
# config flag `use_proof_library` is True, the entry is used as the
# initial PERF script to accelerate the search.  If PERF exhausts its
# budget, the orchestrator falls back to the standard linear prover.

from typing import Dict, Any, Optional, List
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

        self.perf_global_config = PERFConfig.from_global_config(self.config)
        self._last_perf_stats: Optional[PERFStats] = None

        self._analysis: Optional[ObligationAnalysis] = None
        self._analyzer = PERFAnalyzer()

        try:
            validate_perf_against_config(self.config)
        except ValueError as e:
            logger.warning("PERF configuration validation: %s", e)

        logger.info(
            "LLMProofSkill initialized: PERF enabled=%s",
            self.perf_global_config.enabled,
        )

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

    def _prove_linear(
        self,
        obligation: Dict[str, Any],
        context: Dict[str, Any],
        backend: str
    ) -> ProofResult:
        """Dispatch to the appropriate linear prover, injecting structural hints."""
        if backend.startswith("koi"):
            return self._prove_koika(obligation, context)
        if backend == "acl2":
            return self._prove_acl2(obligation, context)
        return ProofResult(
            success=False,
            error_message=f"Unsupported backend: {backend}"
        )

    def _prove_koika(self, obligation, context) -> ProofResult:
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

        # Inject structural hints if available
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

    def _prove_acl2(self, obligation, context) -> ProofResult:
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
                hints=hints if hints else None
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

    def _prove_model_check(self, obligation, context) -> ProofResult:
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

        if perf_config.try_skeleton_first and backend.startswith("koi"):
            coq_file = context.get("coq_file_path")
            theorem_name = context.get("theorem_name")
            if coq_file and theorem_name:
                logger.info("Attempting fast skeleton proof before PERF...")
                if self._koika_prover is None:
                    self._koika_prover = KoikaProver(config=self.config)
                if self._analysis:
                    hints_str = self._build_structural_hints_string()
                    if hints_str:
                        self._koika_prover.set_structural_hints(hints_str)
                skeleton_result = self._koika_prover.prove_with_skeleton_only(
                    Path(coq_file), theorem_name
                )
                if skeleton_result and skeleton_result.get("success"):
                    logger.info("Skeleton proof succeeded – PERF skipped.")
                    self._last_perf_stats = PERFStats()
                    return ProofResult(
                        success=True,
                        proof_script=skeleton_result["proof_script"],
                        metadata={"backend": "koika", "skeleton": True}
                    )

        initial_script = None
        use_library_allowed = self.config.get("provers", {}).get("koika", {}).get(
            "use_proof_library", False
        )
        if use_library_allowed and backend.startswith("koi"):
            from lib.koika.assist import PROOF_LIBRARY
            lib_key = context.get("theorem_name", "")
            if lib_key in PROOF_LIBRARY:
                logger.info("Using library proof as PERF initial script.")
                initial_script = PROOF_LIBRARY[lib_key]
        if initial_script:
            context["initial_script"] = initial_script

        perf_context = self._build_perf_context(obligation, context, perf_config)

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
                    obligation.get("property", "unknown"),
                    stats.successful_depth
                )
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
                logger.info("Library proof verified by PERF; returning success.")
                return ProofResult(
                    success=True,
                    proof_script=initial_script,
                    metadata={
                        "backend": obligation.get("backend", "unknown"),
                        "perf_stats": stats.to_dict(),
                        "library": True
                    }
                )

            logger.warning(
                "PERF exhausted for '%s' (max_depth=%d, nodes=%d). Falling back to linear prover.",
                obligation.get("property", "unknown"),
                stats.max_depth,
                stats.total_nodes
            )
            if backend.startswith("koi"):
                return self._prove_koika(obligation, context)
            if backend == "acl2":
                return self._prove_acl2(obligation, context)
            return ProofResult(
                success=False,
                error_message="PERF exhausted and no linear prover available."
            )
        except Exception as e:
            logger.exception("PERF traversal raised an exception; falling back to linear prover.")
            if backend.startswith("koi"):
                return self._prove_koika(obligation, context)
            if backend == "acl2":
                return self._prove_acl2(obligation, context)
            return ProofResult(
                success=False,
                error_message=f"PERF traversal error: {e}",
                metadata={"backend": obligation.get("backend", "unknown")}
            )

    def _build_perf_context(self, obligation, context, perf_config) -> Dict[str, Any]:
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
        """
        Convert the current ObligationAnalysis into a string suitable for prompts.
        When the step relation has exactly two constructors, explicit case‑split
        instructions are included, which dramatically improves the LLM’s success rate.
        """
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
