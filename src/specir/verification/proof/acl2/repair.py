# src/specir/verification/proof/acl2/repair.py
#
# Iterative repair of ACL2 proofs and function definitions using an LLM.
#
# This module provides standalone repair loops that can be used by the
# ACL2Prover or directly from PERF evaluation.  The functions assume
# the caller provides an already‑connected ``ACL2Client``.  Checkpoint
# management is optional – when enabled, the client’s checkpoint /
# restore facilities are used to isolate each repair attempt, preventing
# re‑definition errors and keeping the session clean.
#
# All public functions return a ``ProofResult`` for consistency with
# the rest of the InterScope verification pipeline.

import re
from typing import List, Optional, Tuple, Dict, Any
from specir.backends.llm_client import LLMClient
from specir.backends.acl2_client import ACL2Client, ACL2ClientError
from specir.verification.proof.acl2.proof_gen import (
    build_acl2_hint_prompt,
    parse_hints_from_response
)
from specir.verification.proof.proof import ProofResult
from specir.utils.logger import get_logger

logger = get_logger(__name__)


def repair_acl2_hints(
    theorem_name: str,
    statement: str,
    error_message: str,
    llm_client: LLMClient,
    acl2_client: ACL2Client,
    previous_hints: Optional[List[str]] = None,
    context: Optional[str] = None,
    max_attempts: int = 3,
    use_checkpoints: bool = True
) -> ProofResult:
    """
    Repair the hints for a failed ACL2 theorem.

    The function repeatedly asks an LLM for a new set of ``:hints`` and
    tries them via ``acl2_client.defthm``.  By default it uses ACL2
    checkpoints to isolate each attempt, so that a failed attempt does
    not pollute the session.

    Args:
        theorem_name: Name of the theorem.
        statement: The ACL2 formula (the body of the ``defthm``).
        error_message: The error output from the previous failure.
        llm_client: LLM client used for hint generation.
        acl2_client: **Connected** ACL2 client.  The session state will
            be modified unless *use_checkpoints* is False.
        previous_hints: Hints that were previously attempted (may be
            passed as context to the LLM).
        context: Additional ACL2 definitions or environment information.
        max_attempts: Maximum number of repair attempts (default 3).
        use_checkpoints: If True (default), save a checkpoint before the
            first attempt and restore it before each subsequent attempt.
            This keeps the session clean and prevents re‑definition errors.

    Returns:
        ``ProofResult`` with ``success=True`` and the proof script on
        success, or ``success=False`` with an error message.
    """
    prompt = _build_hint_repair_prompt(
        statement, error_message, previous_hints, context
    )

    checkpoint_name = None
    if use_checkpoints:
        checkpoint_name = f"repair_{theorem_name}_{id(prompt)}"
        acl2_client.save_checkpoint(checkpoint_name)

    for attempt in range(max_attempts):
        # Restore checkpoint before every attempt after the first.
        if use_checkpoints and attempt > 0:
            acl2_client.restore_checkpoint(checkpoint_name)

        logger.info("ACL2 hint repair attempt %d/%d", attempt + 1, max_attempts)

        # 1. Generate new hints
        new_hints = _generate_hints_from_llm(llm_client, prompt)
        if not new_hints:
            logger.warning("LLM returned no usable hints")
            prompt = _append_failure_to_prompt(
                prompt, None, "No valid hints generated."
            )
            continue

        # 2. Try the new hints
        try:
            result = acl2_client.defthm(theorem_name, statement, new_hints)
        except ACL2ClientError as e:
            logger.error("defthm raised exception: %s", e)
            new_error = f"ACL2 client error: {e}"
            prompt = _append_failure_to_prompt(prompt, new_hints, new_error)
            continue

        if result["success"]:
            proof_script = _build_defthm_string(theorem_name, statement, new_hints)
            logger.info("Hint repair succeeded on attempt %d", attempt + 1)
            return ProofResult(
                success=True,
                proof_script=proof_script,
                backend="acl2",
                iterations=attempt + 1,
                metadata={"automation": "llm_repair", "hints": new_hints}
            )

        # 3. Failure – capture error and feed back to LLM
        new_error = result.get("output", "ACL2 proof failed")
        logger.debug("Hint attempt failed: %s", new_error[:200])
        prompt = _append_failure_to_prompt(prompt, new_hints, new_error)

    logger.warning("ACL2 hint repair failed after %d attempts", max_attempts)
    return ProofResult(
        success=False,
        error_message=f"Hint repair exhausted after {max_attempts} attempts",
        backend="acl2",
        iterations=max_attempts,
        metadata={"automation": "llm_repair_exhausted"}
    )


def repair_acl2_defun(
    func_name: str,
    args: List[str],
    body: str,
    error_message: str,
    llm_client: LLMClient,
    acl2_client: ACL2Client,
    guard: Optional[str] = None,
    max_attempts: int = 2,
    use_checkpoints: bool = True
) -> ProofResult:
    """
    Repair a failed ACL2 function definition (``defun``).

    The LLM is asked to provide a corrected function body.  Each attempt
    is validated by submitting the complete ``defun`` to the ACL2 client.

    Args:
        func_name: Name of the function.
        args: List of argument names (symbols or nested destructuring lists).
        body: The failing function body (as a string).
        error_message: The error output from ACL2.
        llm_client: LLM client.
        acl2_client: **Connected** ACL2 client.
        guard: Optional guard expression.
        max_attempts: Maximum repair attempts (default 2).
        use_checkpoints: If True, isolate attempts with checkpoints.

    Returns:
        ``ProofResult`` with ``success=True`` and the repaired ``defun``
        string in ``proof_script``, or ``success=False``.
    """
    prompt = _build_defun_repair_prompt(
        func_name, args, body, guard, error_message
    )

    checkpoint_name = None
    if use_checkpoints:
        checkpoint_name = f"repair_defun_{func_name}_{id(prompt)}"
        acl2_client.save_checkpoint(checkpoint_name)

    for attempt in range(max_attempts):
        if use_checkpoints and attempt > 0:
            acl2_client.restore_checkpoint(checkpoint_name)

        logger.info(
            "ACL2 defun repair attempt %d/%d for '%s'",
            attempt + 1, max_attempts, func_name
        )

        # 1. Get repaired body from LLM
        try:
            raw_response = llm_client.generate(prompt).strip()
        except Exception as e:
            logger.error("LLM call failed during defun repair: %s", e)
            prompt = _append_defun_failure_to_prompt(
                prompt, "<LLM call failed>", str(e)
            )
            continue

        repaired_body = _extract_defun_body(raw_response)
        if repaired_body is None:
            logger.warning("Could not extract a valid body from LLM response")
            prompt = _append_defun_failure_to_prompt(
                prompt, raw_response, "No valid body extracted."
            )
            continue

        # 2. Validate with ACL2
        try:
            result = acl2_client.defun(func_name, args, repaired_body, guard)
        except ACL2ClientError as e:
            logger.error("defun validation raised exception: %s", e)
            new_error = f"ACL2 client error: {e}"
            prompt = _append_defun_failure_to_prompt(prompt, repaired_body, new_error)
            continue

        if result["success"]:
            defun_string = _build_defun_string(func_name, args, repaired_body, guard)
            logger.info("Defun repair succeeded on attempt %d", attempt + 1)
            return ProofResult(
                success=True,
                proof_script=defun_string,
                backend="acl2",
                iterations=attempt + 1,
                metadata={"automation": "llm_repair_defun"},
            )

        new_error = result.get("output", "defun failed")
        logger.debug("Defun attempt failed: %s", new_error[:200])
        prompt = _append_defun_failure_to_prompt(prompt, repaired_body, new_error)

    logger.warning("ACL2 defun repair failed after %d attempts", max_attempts)
    return ProofResult(
        success=False,
        error_message=f"Defun repair exhausted after {max_attempts} attempts",
        backend="acl2",
        iterations=max_attempts,
        metadata={"automation": "llm_repair_exhausted"}
    )


def _build_hint_repair_prompt(
    statement: str,
    error_message: str,
    previous_hints: Optional[List[str]],
    context: Optional[str],
) -> str:
    """Build an LLM prompt to repair ACL2 hints (delegates to shared builder)."""
    return build_acl2_hint_prompt(
        theorem_statement=statement,
        error_message=error_message,
        old_hints=previous_hints,
        context=context
    )


def _build_defun_repair_prompt(
    func_name: str,
    args: List[str],
    body: str,
    guard: Optional[str],
    error_message: str
) -> str:
    """Build a prompt to repair an ACL2 function body."""
    args_str = " ".join(args)
    guard_str = f"\nGUARD: {guard}" if guard else ""
    return (
        "You are an expert in ACL2.\n\n"
        f"The following function definition failed:\n\n"
        f"FUNCTION: {func_name}\n"
        f"ARGUMENTS: ({args_str})\n"
        f"BODY:\n{body}{guard_str}\n\n"
        f"ERROR:\n{error_message}\n\n"
        "Provide a corrected function body. Return ONLY the body expression."
    )


def _append_failure_to_prompt(
    prompt: str,
    tried_hints: Optional[List[str]],
    new_error: str
) -> str:
    """Extend the prompt with information about a failed hint attempt."""
    hints_str = _format_hints(tried_hints) if tried_hints else "none"
    return (
        f"{prompt}\n\n"
        f"The attempt with hints:\n{hints_str}\n"
        f"Failed with error:\n{new_error}\n"
        f"Please provide a different set of hints."
    )


def _append_defun_failure_to_prompt(
    prompt: str,
    attempted_body: str,
    new_error: str,
) -> str:
    """Extend the defun repair prompt with a new failure."""
    return (
        f"{prompt}\n\n"
        f"The attempt with body:\n{attempted_body}\n"
        f"Failed with error:\n{new_error}\n"
        f"Please provide a corrected body."
    )


def _generate_hints_from_llm(
    llm_client: LLMClient, prompt: str
) -> Optional[List[str]]:
    """Call the LLM and parse the response into a list of hint strings."""
    try:
        response = llm_client.generate(prompt).strip()
    except Exception as e:
        logger.error("LLM call for hints failed: %s", e)
        return None
    return parse_hints_from_response(response)


def _extract_defun_body(response: str) -> Optional[str]:
    """
    Extract the function body from an LLM response.

    The response might be a full ``(defun name (args...) body)`` form or
    just the body itself.  The parser handles nested argument lists and
    gracefully falls back to returning the whole response if parsing fails.
    """
    response = response.strip()
    # Remove markdown fences
    if response.startswith("```"):
        lines = response.splitlines()
        if len(lines) >= 3:
            response = "\n".join(lines[1:-1]).strip()

    # If it does not look like a defun, treat the entire response as the body.
    if not response.startswith("(defun"):
        return response if response else None

    # skip "(defun"
    idx = len("(defun")

    # skip whitespace + function name
    while idx < len(response) and response[idx].isspace():
        idx += 1
    while idx < len(response) and not response[idx].isspace() and response[idx] != '(':
        idx += 1
    # skip whitespace until the argument list '('
    while idx < len(response) and response[idx] != '(':
        idx += 1

    if idx >= len(response) or response[idx] != '(':
        logger.warning("Malformed defun: could not find argument list. Using whole response as fallback.")
        return response

    # Find the end of the argument list
    depth = 1
    arg_end = idx + 1
    while arg_end < len(response) and depth > 0:
        ch = response[arg_end]
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
        arg_end += 1

    if depth != 0:
        logger.warning("Unbalanced parentheses in argument list. Using whole response as fallback.")
        return response

    # arg_end is one past the closing paren of the argument list.
    body_start = arg_end
    # skip whitespace
    while body_start < len(response) and response[body_start].isspace():
        body_start += 1

    if body_start >= len(response):
        logger.warning("Empty body after argument list. Using whole response.")
        return response

    # The body ends at the last character before the final ')', so strip it.
    body = response[body_start:].rstrip()
    if body.endswith(')'):
        # Remove the final closing parenthesis of the defun
        body = body[:-1].rstrip()
    else:
        logger.warning("defun missing closing parenthesis; returning extracted portion as body.")

    return body if body else response  # if body empty, fallback to whole response


def _format_hints(hints: List[str]) -> str:
    """Format a list of hint strings for display."""
    if not hints:
        return "none"
    if len(hints) == 1:
        return hints[0]
    return " ".join(hints)


def _build_defthm_string(
    theorem_name: str, statement: str, hints: List[str]
) -> str:
    """Build a complete defthm string for registration."""
    hints_str = " ".join(hints) if hints else ""
    if hints_str:
        return (
            f"(defthm {theorem_name}\n"
            f"  {statement}\n"
            f"  :hints ({hints_str}))"
        )
    return f"(defthm {theorem_name}\n  {statement})"


def _build_defun_string(
    func_name: str, args: List[str], body: str, guard: Optional[str] = None
) -> str:
    """Build a complete defun string."""
    args_str = " ".join(args)
    if guard:
        return (
            f"(defun {func_name} ({args_str})\n"
            f"  (declare (xargs :guard {guard}))\n"
            f"  {body})"
        )
    return f"(defun {func_name} ({args_str})\n  {body})"
