# src/specir/verification/proof/acl2/prover.py
#
# High-level ACL2 prover using acl2-mcp (MCP client) with LLM-assisted repair.
# Uses checkpoints for safe iterative proof attempts.

import re
from pathlib import Path
from typing import Dict, Any, List, Optional

from specir.backends.acl2_client import ACL2Client, get_acl2_client_from_config
from specir.backends.llm_client import LLMClient, get_llm_client_from_config
from specir.verification.proof.acl2.proof_gen import (
    build_acl2_hint_prompt,
    parse_hints_from_response
)
from specir.utils.logger import get_logger
from specir.utils.config_loader import get_config

logger = get_logger(__name__)


class ACL2Prover:
    """Prover for ACL2 theorems using acl2‑mcp and LLM‑assisted repair."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Args:
            config: Override configuration (defaults to global config).
        """
        if config is None:
            config = get_config()
        self.config = config

        # LLM client
        self.llm = get_llm_client_from_config(config)

        # ACL2 client (MCP‑based)
        self.acl2 = get_acl2_client_from_config(config)
        self.acl2.start()

        self.max_repair = config.get("proof", {}).get("max_repair_attempts", 5)
        logger.info("ACL2 prover ready – max repair attempts: %d", self.max_repair)

    def start(self) -> None:
        """Start the ACL2 session (already done in __init__)."""
        pass

    def stop(self) -> None:
        """Stop the ACL2 session."""
        self.acl2.stop()

    def load_file(self, file_path: Path) -> bool:
        """
        Load a Lisp file containing ACL2 definitions (defun, defstobj, etc.)
        into the current session.

        Returns True if the file was loaded without errors.
        """
        logger.info("Loading ACL2 file: %s", file_path)
        try:
            result = self.acl2.send(f'(ld "{file_path}")')
            if self.acl2._contains_error(result):
                logger.error("Failed to load ACL2 file %s: %s", file_path, result)
                return False
            logger.info("ACL2 file loaded successfully.")
            return True
        except Exception as e:
            logger.error("Failed to load ACL2 file %s: %s", file_path, e)
            return False

    def prove_theorem(
        self,
        theorem_name: str,
        statement: Optional[str] = None,
        hints: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Prove an ACL2 theorem using the current session (which must already
        contain all required function definitions). Uses checkpoint/rollback
        for safe iterative repair.

        If *statement* is None, the theorem is assumed to already exist in the
        session (e.g., loaded from a file) and we attempt to re‑verify it by
        name.

        Args:
            theorem_name: Name of the theorem (e.g., "no-overflow").
            statement: ACL2 formula (e.g., "(implies (full st) (not (enqueue st)))").
                       If None, the theorem must already be present in the session.
            hints: Optional list of hint strings.  Each entry is a complete
                   ACL2 hint expression, e.g. ``("Goal" :induct t)``.

        Returns:
            Dictionary with keys:
            - success (bool)
            - proof_script (str) if successful
            - error (str) if failed
        """
        if statement is None:
            return self._prove_existing_by_name(theorem_name)

        if not hints:
            skeleton_hint = ['("Goal" :induct t)']
            logger.info("Trying skeleton induction hint for '%s'", theorem_name)
            result = self.acl2.defthm(theorem_name, statement, skeleton_hint)
            if result["success"]:
                proof_script = self._build_defthm_string(
                    theorem_name, statement, skeleton_hint
                )
                logger.info("Skeleton proof succeeded for '%s'.", theorem_name)
                return {"success": True, "proof_script": proof_script}
            else:
                logger.info(
                    "Skeleton proof failed for '%s': %s",
                    theorem_name, result.get("output", "")[:200]
                )
                self.acl2.undo()

        # Save a checkpoint *once* before the first repair attempt
        checkpoint_name = f"pre_{theorem_name}"
        self.acl2.save_checkpoint(checkpoint_name)

        attempt = 0
        current_hints = hints or []
        last_error = None
        prev_hints_list: List[List[str]] = []   # for dead‑end detection
        same_error_count = 0

        logger.info("Starting main proof attempt loop for '%s' (max %d attempts).",
                    theorem_name, self.max_repair)

        while attempt < self.max_repair:
            logger.info("Proof attempt %d/%d", attempt + 1, self.max_repair)

            # Restore clean checkpoint before each attempt (except first)
            if attempt > 0:
                self.acl2.restore_checkpoint(checkpoint_name)
                logger.debug("Restored checkpoint '%s'", checkpoint_name)

            result = self.acl2.defthm(theorem_name, statement, current_hints)
            if result["success"]:
                proof_script = self._build_defthm_string(
                    theorem_name, statement, current_hints
                )
                logger.info("ACL2 proof succeeded for '%s'.", theorem_name)
                return {"success": True, "proof_script": proof_script}

            last_error = result.get("output", "ACL2 proof failed")
            logger.warning(
                "ACL2 proof attempt %d for %s failed: %s",
                attempt + 1, theorem_name, last_error[:200]
            )

            prev_hints_list.append(current_hints[:])
            if len(prev_hints_list) >= 2:
                if prev_hints_list[-1] == prev_hints_list[-2]:
                    logger.warning("LLM returned identical hints twice; stopping repair.")
                    break
            # Detect if the same error is occurring repeatedly
            error_key = last_error[:80]  # simple fingerprint
            if attempt > 0 and error_key in (err[:80] for err in [last_error]):  # crude
                same_error_count += 1
                if same_error_count >= 3:
                    logger.warning("The same error has occurred %d times; stopping repair.",
                                   same_error_count)
                    break

            if attempt + 1 == self.max_repair // 2:
                logger.info("Triggering strategy reflection after %d failed attempts.",
                            attempt + 1)
                new_approach = self._request_strategy_reflection(
                    theorem_name, statement, current_hints, last_error
                )
                if new_approach:
                    # Reset with the new hints
                    current_hints = new_approach
                    prev_hints_list.clear()
                    same_error_count = 0
                    logger.info("Reflection yielded new hints; resetting failure history.")
                    attempt += 1
                    continue

            logger.info("Requesting repair hints from LLM...")
            new_hints = self._repair_hints(statement, current_hints, last_error)
            if new_hints:
                logger.info("LLM returned %d new hint(s): %s", len(new_hints), new_hints)
                current_hints = new_hints
            else:
                logger.warning("LLM did not return usable hints; stopping repair.")
                break

            attempt += 1

        logger.error("ACL2 proof failed after %d attempts", attempt)
        return {
            "success": False,
            "error": f"ACL2 proof failed after {attempt} attempts: {last_error}"
        }

    def _prove_existing_by_name(self, theorem_name: str) -> Dict[str, Any]:
        """Attempt to re‑verify an existing theorem by name."""
        logger.info("Attempting to verify existing theorem '%s'", theorem_name)
        for name_variant in (theorem_name, f"acl2::{theorem_name}"):
            cmd = f"(verify ({name_variant}))"
            try:
                result = self.acl2.send(cmd)
                if not self.acl2._contains_error(result):
                    return {
                        "success": True,
                        "proof_script": f";; Theorem {theorem_name} already verified in session"
                    }
            except Exception as e:
                logger.debug("Verification attempt with '%s' raised: %s", name_variant, e)
                continue

        last_result = self.acl2.send(f"(verify ({theorem_name}))")
        return {
            "success": False,
            "error": f"Verification of '{theorem_name}' failed: {last_result}"
        }

    def _repair_hints(
        self,
        statement: str,
        old_hints: Optional[List[str]],
        error: str
    ) -> Optional[List[str]]:
        """Ask the LLM for a new set of hints given the failure."""
        prompt = build_acl2_hint_prompt(
            theorem_statement=statement,
            error_message=error,
            old_hints=old_hints,
            context=None
        )
        logger.debug("Hint repair prompt:\n%s", prompt)
        response = self.llm.generate(prompt)
        logger.debug("LLM hint response: %s", response[:200])
        parsed = parse_hints_from_response(response)
        if parsed:
            logger.debug("LLM hint response parsed: %s", parsed)
        else:
            logger.warning("Could not parse hint response: %s", response[:200])
        return parsed

    def _request_strategy_reflection(
        self,
        theorem_name: str,
        statement: str,
        current_hints: List[str],
        last_error: str
    ) -> Optional[List[str]]:
        """
        Ask the LLM for a completely new proof approach after repeated failures.

        Returns a new list of hints (or None if no useful response).
        """
        prompt = (
            "You are an expert in ACL2 hardware verification.\n\n"
            f"We have been trying to prove theorem `{theorem_name}`:\n"
            f"```lisp\n{statement}\n```\n\n"
            f"The current hints we have attempted are:\n{current_hints}\n"
            f"The latest error message is:\n{last_error}\n\n"
            "We are stuck and need a fundamentally different approach. "
            "Provide a completely new set of :hints for ACL2 that attempts a different "
            "proof strategy (e.g. use a different induction scheme, a new lemma, or "
            "rewrite rules).  The hints must be a proper ACL2 hint list, for example:\n"
            '  (("Goal" :induct t) ("Subgoal *1/2" :expand ((foo x))))\n\n'
            "Return ONLY the hint list as a single s-expression, without any extra text."
        )
        logger.debug("Reflection prompt: %s", prompt)
        response = self.llm.generate(prompt)
        logger.debug("Reflection response: %s", response[:200])
        return parse_hints_from_response(response.strip())

    def _build_defthm_string(
        self,
        theorem_name: str,
        statement: str,
        hints: List[str]
    ) -> str:
        """Create a human‑readable defthm form (for registration)."""
        hints_str = " ".join(hints) if hints else ""
        if hints_str:
            return f"(defthm {theorem_name}\n  {statement}\n  :hints ({hints_str}))"
        else:
            return f"(defthm {theorem_name}\n  {statement})"
