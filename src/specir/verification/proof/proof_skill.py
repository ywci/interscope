# src/specir/verification/proof/proof_skill.py
#
# LLM-driven proof orchestrator that delegates to specialized
# provers (KoikaProver, ACL2Prover, ModelCheckProver) and
# respects per-obligation metadata for proof tuning.

from typing import Dict, Any, Optional, List
from pathlib import Path

from specir.backends.llm_client import get_llm_client_from_config
from specir.verification.proof.proof import ProofSkill, ProofResult
from specir.verification.proof.koika.prover import KoikaProver
from specir.verification.proof.acl2.prover import ACL2Prover
from specir.verification.model_checker import run_model_check, ModelCheckError
from specir.utils.logger import get_logger
from specir.utils.config_loader import get_config

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
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Run the model checker and return a result dictionary."""
        try:
            result = run_model_check(
                rtl_path=rtl_path,
                assertions_path=assertions_path,
                top_module=top_module,
                engine=engine,
                depth=depth,
                timeout=timeout,
            )
            return result
        except ModelCheckError as e:
            return {
                "success": False,
                "status": "error",
                "error": str(e),
                "output": "",
                "counterexample_trace": None,
            }


class LLMProofSkill(ProofSkill):
    """
    Proof skill that uses an LLM together with dedicated interactive provers
    (KoikaProver for Coq, ACL2Prover for ACL2, ModelCheckProver for model
    checking) and manages the repair loop.

    Per‑obligation metadata can override global configuration for settings
    such as `max_consecutive_failures`, `max_steps`, `pre_simplify`, and
    `invariant_mining`.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        if config is None:
            config = get_config()
        self.config = config
        self.llm = get_llm_client_from_config(config)
        self._koika_prover: Optional[KoikaProver] = None
        self._acl2_prover: Optional[ACL2Prover] = None
        self._mc_prover: Optional[ModelCheckProver] = None

        # Global defaults from configuration
        proof_cfg = config.get("proof", {})
        prove_cfg = config.get("provers", {}).get("koika", {}).get("prove", {})

        self.max_repair_attempts = proof_cfg.get("max_repair_attempts", 5)
        self.max_consecutive_failures = prove_cfg.get("max_consecutive_failures", 10)
        self.max_steps = prove_cfg.get("max_steps", 80)
        self.pre_simplify = prove_cfg.get("pre_simplify", True)
        self.invariant_mining = prove_cfg.get("invariant_mining", True)

    def can_handle(self, proof_obligation: Dict[str, Any]) -> bool:
        engine = (proof_obligation.get("engine") or "").lower()
        if engine == "model_checking":
            return True

        backend = (proof_obligation.get("backend") or "").lower()
        normalised = backend.replace("ō", "o")
        if normalised.startswith("koi"):
            return True
        if normalised in ("acl2",):
            return True
        return False

    def prove(
        self,
        proof_obligation: Dict[str, Any],
        context: Dict[str, Any],
    ) -> ProofResult:
        engine = (proof_obligation.get("engine") or "").lower()
        if engine == "model_checking":
            return self._prove_model_check(proof_obligation, context)

        backend = (proof_obligation.get("backend") or "").lower()
        normalised = backend.replace("ō", "o")
        if normalised.startswith("koi"):
            return self._prove_koika(proof_obligation, context)
        elif normalised in ("acl2",):
            return self._prove_acl2(proof_obligation, context)
        else:
            return ProofResult(
                success=False,
                error_message=f"Unsupported backend: {backend}",
            )

    def _prove_model_check(
        self,
        obligation: Dict[str, Any],
        context: Dict[str, Any],
    ) -> ProofResult:
        rtl_path = context.get("rtl_file_path")
        assertions_path = context.get("assertions_file_path")
        if not rtl_path or not assertions_path:
            return ProofResult(
                success=False,
                error_message="Missing 'rtl_file_path' or 'assertions_file_path' in context",
            )

        top_module = context.get("top_module")
        if not top_module:
            top_module = context.get("spec_module").name if context.get("spec_module") else "top"

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
            timeout=timeout,
        )

        if result.get("success"):
            return ProofResult(
                success=True,
                proof_script="Model checking succeeded",
                metadata={"backend": "model_checking", "engine": engine},
            )
        else:
            return ProofResult(
                success=False,
                error_message=result.get("error") or "Model checking failed",
                metadata={"backend": "model_checking", "engine": engine},
            )

    def _prove_koika(
        self,
        obligation: Dict[str, Any],
        context: Dict[str, Any],
    ) -> ProofResult:
        coq_path = context.get("coq_file_path")
        if not coq_path:
            return ProofResult(
                success=False,
                error_message="Missing 'coq_file_path' in context",
            )

        theorem_name = context.get("theorem_name")
        if not theorem_name:
            theorem_name = obligation.get("property", "")
        if not theorem_name:
            return ProofResult(
                success=False,
                error_message="Missing property name in obligation",
            )

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

        try:
            result = prover.prove_theorem(
                coq_file=Path(coq_path),
                theorem_name=theorem_name,
                tactic_hints=tactic_hints if tactic_hints else None,
            )
        except Exception as e:
            logger.exception("Koika prover raised an exception")
            return ProofResult(
                success=False,
                error_message=f"Koika prover error: {e}",
            )
        finally:
            if has_overrides and prover is not self._koika_prover:
                prover.close()

        if result.get("success"):
            return ProofResult(
                success=True,
                proof_script=result.get("proof_script", ""),
                metadata={"backend": "koika"},
            )
        else:
            return ProofResult(
                success=False,
                error_message=result.get("error", "Unknown Koika proof failure"),
                metadata={"backend": "koika"},
            )

    def _prove_acl2(
        self,
        obligation: Dict[str, Any],
        context: Dict[str, Any],
    ) -> ProofResult:
        acl2_file = context.get("acl2_file_path")
        if not acl2_file:
            return ProofResult(
                success=False,
                error_message="Missing 'acl2_file_path' in context",
            )

        theorem_name = context.get("theorem_name")
        if not theorem_name:
            theorem_name = obligation.get("property", "")
        if not theorem_name:
            return ProofResult(
                success=False,
                error_message="Missing property name in obligation",
            )

        if self._acl2_prover is None:
            self._acl2_prover = ACL2Prover(config=self.config)

        statement = context.get("theorem_statement")
        hints = (
            obligation.get("metadata", {}).get("acl2_hints", [])
            if isinstance(obligation, dict)
            else []
        )

        try:
            result = self._acl2_prover.prove_theorem(
                theorem_name=theorem_name,
                statement=statement,
                hints=hints if hints else None,
            )
        except Exception as e:
            logger.exception("ACL2 prover raised an exception")
            return ProofResult(
                success=False,
                error_message=f"ACL2 prover error: {e}",
            )

        if result.get("success"):
            return ProofResult(
                success=True,
                proof_script=result.get("proof_script", ""),
                metadata={"backend": "acl2"},
            )
        else:
            return ProofResult(
                success=False,
                error_message=result.get("error", "Unknown ACL2 proof failure"),
                metadata={"backend": "acl2"},
            )

    def close(self) -> None:
        if self._koika_prover:
            self._koika_prover.close()
        if self._acl2_prover:
            self._acl2_prover.stop()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
