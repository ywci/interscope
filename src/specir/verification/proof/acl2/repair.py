# src/specir/verification/proof/acl2/repair.py
#
# Iterative repair of ACL2 proofs using LLM.
# Supports both full proof script repair and hint-only repair,
# with optional validation using the ACL2 subprocess client.

import re
from typing import List, Optional, Tuple

from specir.backends.llm_client import LLMClient
from specir.backends.acl2_client import ACL2Client, ACL2ClientError
from specir.verification.proof.acl2.proof_gen import (
    build_acl2_hint_prompt,
    parse_hints_from_response
)
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
    max_attempts: int = 3
) -> Tuple[bool, str, Optional[List[str]]]:
    """
    Repair the hints for a failed ACL2 theorem.

    Args:
        theorem_name: Name of the theorem.
        statement: ACL2 formula.
        error_message: The error output from ACL2.
        llm_client: LLM client for hint generation.
        acl2_client: Connected ACL2 client (used to validate new hints).
        previous_hints: Hints that were previously attempted.
        context: Additional ACL2 definitions or environment info.
        max_attempts: Maximum repair attempts.

    Returns:
        Tuple of (success, proof_script, final_hints).
        * success: Whether a valid proof was obtained.
        * proof_script: The complete defthm form if success, else empty string.
        * final_hints: The hints that succeeded, or None if failed.
    """
    prompt = _build_hint_repair_prompt(
        statement, error_message, previous_hints, context
    )
    for attempt in range(max_attempts):
        logger.info(f"ACL2 hint repair attempt {attempt+1}/{max_attempts}")
        new_hints = _generate_hints_from_llm(llm_client, prompt)
        if not new_hints:
            logger.warning("LLM returned no usable hints")
            prompt = _append_failure_to_prompt(prompt, None, "No valid hints generated.")
            continue

        # Test the new hints
        result = acl2_client.defthm(theorem_name, statement, new_hints)
        if result["success"]:
            proof_script = _build_defthm_string(theorem_name, statement, new_hints)
            logger.info(f"Hint repair succeeded on attempt {attempt+1}")
            return True, proof_script, new_hints

        new_error = result.get("output", "ACL2 proof failed")
        logger.debug(f"Hint attempt failed: {new_error[:200]}")
        prompt = _append_failure_to_prompt(prompt, new_hints, new_error)

    logger.warning("ACL2 hint repair failed after all attempts")
    return False, "", None


def repair_acl2_defun(
    func_name: str,
    args: List[str],
    body: str,
    error_message: str,
    llm_client: LLMClient,
    acl2_client: ACL2Client,
    guard: Optional[str] = None,
    max_attempts: int = 2
) -> Tuple[bool, str]:
    """
    Repair a failed ACL2 function definition (defun).

    Args:
        func_name: Function name.
        args: List of argument names (each may be a plain symbol or a nested
              list for destructuring).
        body: Current (failing) function body.
        error_message: ACL2 error message.
        llm_client: LLM client.
        acl2_client: ACL2 client for validation.
        guard: Optional guard expression.
        max_attempts: Maximum repair attempts.

    Returns:
        Tuple of (success, repaired_defun_string).
    """
    prompt = _build_defun_repair_prompt(func_name, args, body, guard, error_message)
    for attempt in range(max_attempts):
        logger.info(f"ACL2 defun repair attempt {attempt+1}/{max_attempts}")
        repaired_body = llm_client.generate(prompt).strip()
        # Extract just the body if the response is a full defun form
        repaired_body = _extract_defun_body(repaired_body)
        if not repaired_body:
            continue

        result = acl2_client.defun(func_name, args, repaired_body, guard)
        if result["success"]:
            return True, _build_defun_string(func_name, args, repaired_body, guard)

        new_error = result.get("output", "defun failed")
        prompt = _append_defun_failure_to_prompt(prompt, repaired_body, new_error)

    return False, ""


def _build_hint_repair_prompt(
    statement: str,
    error_message: str,
    previous_hints: Optional[List[str]],
    context: Optional[str]
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
    """Extend the prompt with information about a failed attempt."""
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
    response = llm_client.generate(prompt).strip()
    return parse_hints_from_response(response)


def _extract_defun_body(response: str) -> Optional[str]:
    """
    Extract the function body from an LLM response.
    The response might be a full defun form or just the body.
    Uses a simple token‑based approach that correctly handles nested
    argument lists (e.g., ``(defun f ((x y) z) body)``).
    """
    response = response.strip()
    # Remove markdown fences
    if response.startswith("```"):
        lines = response.splitlines()
        if len(lines) >= 3:
            response = "\n".join(lines[1:-1]).strip()

    # If it looks like a full defun, extract the body.
    if response.startswith("(defun"):
        # Find the end of the argument list by tracking parenthesis depth.
        # The structure is: (defun name (args ...) body)
        # We need to skip past the function name and the argument list.
        idx = len("(defun")  # skip "(defun"
        # skip whitespace and function name (a single token)
        while idx < len(response) and response[idx].isspace():
            idx += 1
        # skip the function name token
        while idx < len(response) and not response[idx].isspace() and response[idx] != '(':
            idx += 1
        # now skip whitespace until the argument list '('
        while idx < len(response) and response[idx] != '(':
            idx += 1
        if idx >= len(response) or response[idx] != '(':
            return None  # malformed
        # count depth for the argument list
        depth = 1
        arg_end = idx + 1
        while arg_end < len(response) and depth > 0:
            ch = response[arg_end]
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
            arg_end += 1
        # arg_end is one past the closing paren of the argument list
        # The body starts after that, skipping whitespace
        body_start = arg_end
        while body_start < len(response) and response[body_start].isspace():
            body_start += 1
        if body_start >= len(response):
            return None
        # The body ends at the last character before the final closing paren
        # of the defun, so trim trailing whitespace and the final ')'
        body = response[body_start:].rstrip()
        if body.endswith(')'):
            body = body[:-1].rstrip()
        return body if body else None

    # Otherwise assume the whole response is the body
    return response if response else None


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
