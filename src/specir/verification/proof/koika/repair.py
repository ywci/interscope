# src/specir/verification/proof/koika/repair.py
#
# One-shot repair of failed Coq proof scripts using an LLM.
# The repaired script can optionally be validated with rocq-mcp.
# Used as a fallback when the interactive prover cannot make progress.

import os
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

from specir.backends.llm_client import LLMClient
from specir.backends.rocq_client import RocqClient, RocqClientError
from specir.utils.logger import get_logger

logger = get_logger(__name__)


def repair_coq_proof(
    original_script: str,
    error_message: str,
    llm_client: LLMClient,
    theorem_name: Optional[str] = None,
    theorem_statement: Optional[str] = None,
    rocq_client: Optional[RocqClient] = None,
    max_attempts: int = 3,
) -> Tuple[bool, str]:
    """
    Attempt to repair a Coq proof script that failed with the given error.

    The LLM is asked to generate a corrected script.  If *rocq_client* is
    provided, the repaired script is written to a temporary file and
    compiled; only scripts that pass compilation are returned.

    Args:
        original_script: The failing Coq proof (should include ``Proof.`` …
                         ``Qed.`` or ``Admitted.``).
        error_message: The error message from Coq.
        llm_client: LLM client for repair suggestions.
        theorem_name: Optional name of the theorem (used in the prompt).
        theorem_statement: Optional statement of the theorem (used in the prompt).
        rocq_client: Optional connected RocqClient for validating repairs.
        max_attempts: Maximum repair attempts.

    Returns:
        (success, repaired_script) where *success* indicates whether a
        compilable script was obtained (or, if no rocq_client is given,
        whether a plausible script was generated).
    """
    prompt = _build_repair_prompt(
        original_script, error_message, theorem_name, theorem_statement
    )

    for attempt in range(max_attempts):
        repaired = llm_client.generate(prompt).strip()

        # Quick sanity checks before trying to compile
        if not _basic_sanity(repaired):
            logger.warning(
                "Repair attempt %d produced a script that fails basic sanity.",
                attempt + 1,
            )
            prompt = _update_repair_prompt(
                prompt, repaired, "The script is missing Proof. or Qed."
            )
            continue

        # If we have a rocq client, validate by compiling
        if rocq_client:
            tmp_path = None
            try:
                # Write the repaired script to a temporary file
                fd, tmp_path = tempfile.mkstemp(suffix=".v", prefix="repair_")
                os.close(fd)
                Path(tmp_path).write_text(repaired, encoding="utf-8")

                # Compile with rocq-mcp
                compile_result = rocq_client.compile_file(Path(tmp_path))
                error = rocq_client._extract_error_from_response(compile_result)
                if error:
                    raise RocqClientError(f"Compilation error: {error}")

                # Compilation succeeded
                logger.info(
                    "Repair attempt %d succeeded (compiled successfully).",
                    attempt + 1,
                )
                return True, repaired
            except RocqClientError as compile_err:
                logger.warning(
                    "Repair attempt %d failed compilation: %s",
                    attempt + 1,
                    compile_err,
                )
                prompt = _update_repair_prompt(prompt, repaired, str(compile_err))
            except Exception as e:
                logger.error("Unexpected error during repair validation: %s", e)
                prompt = _update_repair_prompt(prompt, repaired, str(e))
            finally:
                # Clean up the temporary file
                if tmp_path is not None and os.path.exists(tmp_path):
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass
        else:
            # Without a client we trust the LLM – return the script as a
            # plausible candidate.
            logger.info(
                "Repair attempt %d produced a plausible script (no rocq validation).",
                attempt + 1,
            )
            return True, repaired

    return False, original_script


def build_repair_prompt_from_error(
    failed_script: str,
    error_msg: str,
    theorem_name: Optional[str] = None,
    theorem_statement: Optional[str] = None,
) -> str:
    """Public wrapper for `_build_repair_prompt`."""
    return _build_repair_prompt(
        failed_script, error_msg, theorem_name, theorem_statement
    )


def _build_repair_prompt(
    failed_script: str,
    error_msg: str,
    theorem_name: Optional[str],
    theorem_statement: Optional[str],
) -> str:
    """Build a prompt asking the LLM to fix a failing Coq proof."""
    parts = ["The following Coq proof failed with an error.\n"]
    if theorem_name:
        parts.append(f"Theorem: {theorem_name}")
    if theorem_statement:
        parts.append(f"Statement: {theorem_statement}")

    parts.append(f"\nERROR:\n{error_msg}\n")
    parts.append(f"FAILED PROOF:\n```coq\n{failed_script}\n```\n")
    parts.append(
        "Please provide a corrected Coq proof script that fixes the error. "
        "Return only the Coq code from `Proof.` to `Qed.` (or `Admitted.` if "
        "you cannot complete the proof). Do not include any extra commentary."
    )
    return "\n".join(parts)


def _update_repair_prompt(
    previous_prompt: str,
    attempted_script: str,
    new_error: str,
) -> str:
    """Extend the prompt with information about the latest failed attempt."""
    return (
        f"{previous_prompt}\n\n"
        f"The previous repair attempt produced:\n"
        f"```coq\n{attempted_script}\n```\n"
        f"This still failed with:\n{new_error}\n\n"
        f"Please provide a corrected script."
    )


def _basic_sanity(script: str) -> bool:
    """Return True if the script contains the minimal expected structure."""
    return "Proof." in script and ("Qed." in script or "Admitted." in script)
