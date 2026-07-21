# src/specir/verification/proof/acl2/proof_gen.py
#
# ACL2 proof generation using LLM.
# Builds prompts from theorem statements and ACL2 context,
# parses LLM responses to extract complete defthm forms or
# just the :hints section. Used for both one-shot proof
# attempts and for hint generation during repair.
# Also provides a reflection-prompt builder for asking the
# LLM for a fundamentally new proof strategy after repeated
# hint failures.

import re
from typing import List, Optional, Dict, Union

from specir.backends.llm_client import LLMClient
from specir.utils.logger import get_logger

logger = get_logger(__name__)


def get_skeleton_hint() -> List[str]:
    """
    Return the canonical skeleton hint for a trivial induction proof.

    This hint instructs ACL2 to perform induction on the top‑level goal,
    which suffices for many safety properties of the form
    ``(implies (and (reachable st) ...) <property>)`` where the step
    function has a straightforward recursive structure.

    Returns:
        A list containing a single hint string ``("Goal" :induct t)``.
    """
    return ['("Goal" :induct t)']


def build_acl2_proof_prompt(
    theorem_name: str,
    theorem_statement: str,
    context: Optional[str] = None,
    hint_classes: Optional[List[str]] = None,
    assumptions: Optional[List[str]] = None,
    previous_attempts: Optional[List[Dict[str, str]]] = None
) -> str:
    """
    Build a prompt for an LLM to generate a complete ACL2 proof (defthm with hints).

    Args:
        theorem_name: Name of the theorem (e.g., "no-overflow").
        theorem_statement: ACL2 formula (e.g., "(implies (full st) (not (enqueue st)))").
        context: Optional extra ACL2 definitions or helpful lemmas.
        hint_classes: Suggested hint classes (e.g., ["rewrite", "linear", "induct"]).
        assumptions: List of assumptions (environment constraints).
        previous_attempts: List of previous failed attempts, each as a dict with
                           keys "script" and "error", for repair feedback.

    Returns:
        A string prompt suitable for an LLM.
    """
    hints_str = ", ".join(hint_classes) if hint_classes else "rewrite, linear, induct"
    assumes_str = "\n".join(f"Assumption: {a}" for a in assumptions) if assumptions else ""
    context_str = context if context else ""

    parts = [
        "You are an expert in ACL2 and hardware verification.",
        "",
        f"Theorem to prove:",
        f"```lisp",
        f"(defthm {theorem_name}",
        f"  {theorem_statement})",
        f"```",
        ""
    ]
    if context_str:
        parts.append(f"Available definitions / lemmas:\n{context_str}\n")
    if assumes_str:
        parts.append(f"Assumptions:\n{assumes_str}\n")
    parts.append(f"Suggested hint classes: {hints_str}")
    parts.append(
        "Generate a complete ACL2 defthm form that includes an appropriate "
        ":hints section.  The hints should be a proper ACL2 hint list, e.g.\n"
        '  :hints (("Goal" :induct t) ("Subgoal *1/2" :expand ((foo x))))\n'
        "Return ONLY the defthm form without any additional text or commentary."
    )

    if previous_attempts:
        recent = previous_attempts[-3:]
        parts.append("\nPrevious attempts failed with the following errors:\n")
        for i, att in enumerate(recent, 1):
            script = att.get("script", "")
            error = att.get("error", "Unknown error")
            parts.append(f"Attempt {i} script:\n```lisp\n{script}\n```")
            parts.append(f"Error:\n{error}\n")
        parts.append("Please correct the proof and provide the fixed defthm.")

    return "\n".join(parts)


def build_acl2_hint_prompt(
    theorem_statement: str,
    error_message: str,
    old_hints: Optional[List[str]] = None,
    context: Optional[str] = None
) -> str:
    """
    Build a prompt specifically for generating improved :hints.

    Args:
        theorem_statement: The ACL2 formula.
        error_message: The error output from ACL2.
        old_hints: The hints that were previously attempted (as strings).
        context: Optional definitions or lemmas.

    Returns:
        A prompt asking the LLM to return only the new :hints list.
    """
    old_hints_str = " ".join(old_hints) if old_hints else "none"
    return (
        "You are an expert in ACL2.\n\n"
        f"The following theorem proof failed:\n\n"
        f"Theorem statement:\n{theorem_statement}\n\n"
        f"Previous hints: {old_hints_str}\n\n"
        f"Error message:\n{error_message}\n\n"
        f"{context if context else ''}"
        "Suggest a new set of :hints for ACL2.  The hints must be a proper ACL2 "
        "hint list, for example:\n"
        '  (("Goal" :induct t) ("Subgoal *1/2" :expand ((foo x))))\n\n'
        "Return ONLY the hint list as a single s-expression, without any "
        "extra text."
    )


def build_acl2_reflection_prompt(
    theorem_name: str,
    theorem_statement: str,
    current_hints: List[str],
    last_error: str,
    previous_attempts: Optional[List[Dict[str, str]]] = None
) -> str:
    """
    Build a prompt asking the LLM for a fundamentally new proof strategy
    after repeated hint‑repair failures.

    Args:
        theorem_name: Name of the theorem.
        theorem_statement: ACL2 formula.
        current_hints: The hints that have already been attempted without success.
        last_error: The most recent ACL2 error message.
        previous_attempts: Optional list of dicts with keys "script" and "error"
                           for additional context.

    Returns:
        A prompt string asking for new hints.
    """
    attempts_str = ""
    if previous_attempts:
        recent = previous_attempts[-3:]
        attempts_str = "\n".join(
            f"Attempt {i+1}: hints={att.get('script', '?')} error={att.get('error', '?')}"
            for i, att in enumerate(recent)
        )

    return (
        "You are an expert in ACL2 hardware verification.\n\n"
        f"We have been trying to prove theorem `{theorem_name}`:\n"
        f"```lisp\n{theorem_statement}\n```\n\n"
        f"The hints we have already tried are:\n{current_hints}\n\n"
        f"The latest error message is:\n{last_error}\n\n"
        + (f"Previous attempts:\n{attempts_str}\n\n" if attempts_str else "") +
        "We are stuck and need a fundamentally different approach.  "
        "Suggest a completely new set of :hints that attempts a different "
        "proof strategy (e.g. use a different induction scheme, a new lemma, "
        "or a different set of rewrite rules).  The hints must be a proper "
        "ACL2 hint list, for example:\n"
        '  (("Goal" :induct t) ("Subgoal *1/2" :expand ((foo x))))\n\n'
        "Return ONLY the hint list as a single s-expression, without any "
        "extra text."
    )


def generate_acl2_proof(
    llm_client: LLMClient,
    theorem_name: str,
    theorem_statement: str,
    context: Optional[str] = None,
    hint_classes: Optional[List[str]] = None,
    assumptions: Optional[List[str]] = None,
    previous_attempts: Optional[List[Dict[str, str]]] = None,
    max_tokens: int = 2048
) -> str:
    """
    Generate a complete ACL2 defthm form using an LLM.

    Args:
        llm_client: Configured LLM client.
        theorem_name, theorem_statement, context, hint_classes, assumptions,
        previous_attempts: Passed to `build_acl2_proof_prompt`.
        max_tokens: Maximum tokens for the LLM response.

    Returns:
        The raw LLM response (may contain extra text; use `extract_acl2_proof`
        to isolate the defthm).
    """
    prompt = build_acl2_proof_prompt(
        theorem_name=theorem_name,
        theorem_statement=theorem_statement,
        context=context,
        hint_classes=hint_classes,
        assumptions=assumptions,
        previous_attempts=previous_attempts
    )
    original_max = llm_client.max_tokens
    llm_client.max_tokens = max_tokens
    try:
        response = llm_client.generate(prompt)
    finally:
        llm_client.max_tokens = original_max
    return response.strip()


def generate_acl2_hints(
    llm_client: LLMClient,
    theorem_statement: str,
    error_message: str,
    old_hints: Optional[List[str]] = None,
    context: Optional[str] = None,
    max_tokens: int = 1024
) -> Optional[List[str]]:
    """
    Generate improved ACL2 hints for a failed proof.

    Args:
        llm_client: Configured LLM client.
        theorem_statement: The ACL2 formula that failed.
        error_message: The error message from ACL2.
        old_hints: Previous hints that were attempted.
        context: Optional extra definitions.
        max_tokens: Maximum tokens for the LLM response.

    Returns:
        A list of hint strings (each a complete hint s-expression), or None
        if the LLM response could not be parsed.
    """
    prompt = build_acl2_hint_prompt(
        theorem_statement=theorem_statement,
        error_message=error_message,
        old_hints=old_hints,
        context=context
    )
    original_max = llm_client.max_tokens
    llm_client.max_tokens = max_tokens
    try:
        response = llm_client.generate(prompt)
    finally:
        llm_client.max_tokens = original_max
    return parse_hints_from_response(response.strip())


def extract_acl2_proof(response: str) -> str:
    """
    Extract the ACL2 defthm form from an LLM response.

    The function tracks balanced parentheses starting from the first
    ``(defthm`` line and returns the entire s-expression.

    Args:
        response: Raw LLM output.

    Returns:
        The defthm form, or the whole response if no defthm block is found.
    """
    lines = response.splitlines()
    in_defthm = False
    paren_depth = 0
    defthm_lines = []

    for line in lines:
        stripped = line.strip()
        if not in_defthm and stripped.startswith("(defthm"):
            in_defthm = True
        if in_defthm:
            defthm_lines.append(line.rstrip())
            paren_depth += line.count("(") - line.count(")")
            if paren_depth == 0:
                break

    if defthm_lines:
        return "\n".join(defthm_lines)
    # Fallback: return everything
    return response


def parse_hints_from_response(response: str) -> Optional[List[str]]:
    """
    Parse an LLM response that should contain an ACL2 hint list.

    Attempts to locate an s-expression that starts with a parenthesis and
    contains ``:induct``, ``:expand``, or similar hint keywords.

    Args:
        response: The raw text from the LLM.

    Returns:
        A list of one element containing the full hint s-expression, or None.
    """
    response = response.strip()
    # Remove markdown fences if present
    if response.startswith("```"):
        lines = response.splitlines()
        if len(lines) >= 3:
            response = "\n".join(lines[1:-1]).strip()

    # If the whole response looks like an s-expression (starts with '(' and
    # ends with ')'), treat it as a single hint list.
    if response.startswith("(") and response.endswith(")"):
        # Quick sanity: must contain at least one hint indicator
        if any(kw in response for kw in (":induct", ":expand", ":rewrite",
                                          ":use", ":cases", ":in-theory")):
            return [response]

    # Try to extract a parenthesised block containing hint keywords
    match = re.search(r"\(\(.*\)\)", response, re.DOTALL)
    if match:
        block = match.group(0)
        if any(kw in block for kw in (":induct", ":expand", ":rewrite")):
            return [block]

    return None
