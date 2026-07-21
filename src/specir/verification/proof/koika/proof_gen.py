# src/specir/verification/proof/koika/proof_gen.py
#
# Coq proof generation using LLM.
# Builds prompts for one‑shot proof scripts and for interactive
# step‑by‑step tactic generation, and parses LLM responses to
# extract proof scripts or tactic lists.
#
# All prompts are design‑agnostic.  The interactive prompt now
# receives the actual list of available auto‑generated lemmas
# so the LLM can use them by name.  Base‑ and step‑case hints
# are configurable via the prover's configuration.

import re
from typing import List, Optional, Dict, Any

from specir.backends.llm_client import LLMClient
from specir.utils.logger import get_logger

logger = get_logger(__name__)


def build_coq_proof_prompt(
    theorem_name: str,
    theorem_statement: str,
    context: Optional[str] = None,
    tactic_hints: Optional[List[str]] = None,
    assumptions: Optional[List[str]] = None,
    previous_attempts: Optional[List[Dict[str, str]]] = None
) -> str:
    """Build a prompt for an LLM to generate a complete Coq proof script."""
    hints_str = ", ".join(tactic_hints) if tactic_hints else "induction, simpl, auto, rewrite, inversion"
    assumes_str = "\n".join(f"Assumption: {a}" for a in assumptions) if assumptions else ""
    context_str = context if context else ""

    parts = [
        "You are an expert in Coq and hardware verification.",
        "",
        "Theorem to prove:",
        f"```coq",
        f"Theorem {theorem_name} : {theorem_statement}.",
        f"```",
        ""
    ]
    if context_str:
        parts.append(f"Available definitions and lemmas:\n{context_str}\n")
    if assumes_str:
        parts.append(f"Assumptions:\n{assumes_str}\n")
    parts.append(f"Suggested tactics: {hints_str}")
    parts.append("")
    parts.append(
        "Generate a complete Coq proof script that proves the theorem. "
        "The script must include the `Proof.` and `Qed.` lines. "
        "If you cannot complete the proof, end with `Admitted.` instead of `Qed.`. "
        "Return only the Coq code without any extra commentary."
    )

    if previous_attempts:
        recent = previous_attempts[-3:]
        parts.append("\nPrevious attempts failed with the following errors:\n")
        for i, att in enumerate(recent, 1):
            script = att.get("script", "")
            error = att.get("error", "Unknown error")
            parts.append(f"Attempt {i} script:\n```coq\n{script}\n```")
            parts.append(f"Error:\n{error}\n")
        parts.append("Please provide a corrected proof that addresses these errors.")

    return "\n".join(parts)


def generate_coq_proof(
    llm_client: LLMClient,
    theorem_name: str,
    theorem_statement: str,
    context: Optional[str] = None,
    tactic_hints: Optional[List[str]] = None,
    assumptions: Optional[List[str]] = None,
    previous_attempts: Optional[List[Dict[str, str]]] = None,
    max_tokens: int = 2048
) -> str:
    """Generate a Coq proof script using an LLM."""
    prompt = build_coq_proof_prompt(
        theorem_name=theorem_name,
        theorem_statement=theorem_statement,
        context=context,
        tactic_hints=tactic_hints,
        assumptions=assumptions,
        previous_attempts=previous_attempts
    )
    logger.debug("One‑shot proof prompt (%d chars):\n%s", len(prompt), prompt)

    original_max = llm_client.max_tokens
    llm_client.max_tokens = max_tokens
    try:
        response = llm_client.generate(prompt)
    finally:
        llm_client.max_tokens = original_max

    logger.debug("One‑shot proof response (%d chars): %s", len(response), response[:500])
    return response.strip()


def extract_proof_script(response: str) -> str:
    """Extract a Coq proof script from an LLM response."""
    lines = response.splitlines()
    proof_lines = []
    in_proof = False
    proof_depth = 0
    for line in lines:
        stripped = line.strip()
        if not in_proof and stripped.startswith("Proof."):
            in_proof = True
            proof_lines.append(line)
            continue
        if in_proof:
            proof_lines.append(line)
            if stripped == "Proof.":
                proof_depth += 1
            elif stripped == "Qed.":
                if proof_depth == 0:
                    break
                proof_depth -= 1
            elif stripped == "Admitted.":
                if proof_depth == 0:
                    break
    if proof_lines:
        return "\n".join(proof_lines)
    return response


def build_interactive_step_prompt(
    theorem_name: str,
    goals: List[str],
    tactic_hints: Optional[List[str]],
    applied_tactics: List[str],
    recent_errors: List[str],
    base_case_hint: str = "simpl; auto with *; try lia; try nia.",
    step_case_hint: str = "invert the step hypothesis, substitute, simpl, then try to apply the induction hypothesis or use available lemmas; finish with auto/lia/nia.",
    available_lemmas: Optional[List[str]] = None
) -> str:
    """
    Build a prompt for the next tactic in an interactive Coq proof.

    Args:
        theorem_name: Name of the theorem being proved.
        goals: List of current goal strings (as returned by rocq‑mcp).
        tactic_hints: Suggested tactic names for this theorem.
        applied_tactics: List of recently applied tactics (for context).
        recent_errors: Recent error messages from failed tactics.
        base_case_hint: A short description / tactic for the base case of an induction.
        step_case_hint: A short description / tactic for the step case.
        available_lemmas: Optional list of lemma names that are already proved and may be used.
    """
    goals_str = "\n".join(goals) if goals else "No goals"
    hints_str = ", ".join(tactic_hints) if tactic_hints else (
        "induction, simpl, auto, eauto, rewrite, inversion, subst, destruct, split, lia, nia"
    )
    recent_history = applied_tactics[-8:] if applied_tactics else []
    history_str = "\n".join(f"  {t}" for t in recent_history) if recent_history else "(none)"

    # Error feedback
    error_str = ""
    if recent_errors:
        last_error = recent_errors[-1]
        error_str = (
            f"\n**CRITICAL: The LAST tactic you suggested FAILED with this error:**\n"
            f"  {last_error}\n\n"
            f"**DO NOT repeat the same tactic. You MUST change your approach.**\n"
        )
        if len(recent_errors) > 1:
            error_str += "\nEarlier errors:\n"
            for e in recent_errors[-4:-1]:
                error_str += f"  {e}\n"

    # Extract hypotheses from the goal text
    hyp_lines = []
    for line in goals_str.splitlines():
        line = line.strip()
        if ":" in line and not line.startswith("|-"):
            hyp_lines.append(line)
    hypotheses_str = "\n".join(hyp_lines) if hyp_lines else "No hypotheses visible"

    lemmas_str = ""
    if available_lemmas:
        lemmas_str = (
            f"\n**Available lemmas** (you can rewrite with them): "
            f"{', '.join(available_lemmas)}\n"
        )

    return (
        f"You are an expert in Coq and hardware verification.\n\n"
        f"Theorem: {theorem_name}\n\n"
        f"**CURRENT GOAL** (this is what you need to prove NOW):\n"
        f"```\n{goals_str}\n```\n\n"
        f"**VISIBLE HYPOTHESES:**\n"
        f"```\n{hypotheses_str}\n```\n\n"
        f"Recently applied tactics:\n```\n{history_str}\n```\n"
        f"{error_str}"
        f"{lemmas_str}"
        f"Suggested approach: {hints_str}\n\n"
        "**CRITICAL RULES:**\n"
        "- Look at the goal above. It shows ALL hypotheses and the conclusion.\n"
        "- If a variable already appears in the hypotheses, "
        "do NOT try to 'intros' it again.\n"
        "- After `induction` on the reachability hypothesis, you will have one "
        "subgoal per constructor of `reachable` and `step`.\n"
        f"- For the base case: `{base_case_hint}`\n"
        f"- For the step case: `{step_case_hint}`\n"
        "- Use the induction hypothesis (often named `IH`) when it helps.\n"
        "- If the goal contains `if ... then ... else`, use `destruct` on the "
        "condition to split into two subgoals.\n"
        "- Return ONLY one complete tactic ending with a dot.\n"
        "- If your previous tactic failed, you MUST try something different."
    )


def extract_tactics_from_response(response: str) -> List[str]:
    """Parse an LLM response that should contain one or more Coq tactics."""
    logger.debug("Raw LLM response for tactic extraction (%d chars): %s", len(response), response)

    cleaned = re.sub(r'```(?:coq)?\s*', '', response)
    cleaned = re.sub(r'`', '', cleaned)

    lines = cleaned.splitlines()
    tactics: List[str] = []
    current = ""
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped[0].isdigit() and len(stripped) > 1 and stripped[1] in ('.', ')', ':'):
            stripped = stripped[2:].strip()
        elif stripped.startswith('- '):
            stripped = stripped[2:].strip()

        current = (current + " " + stripped) if current else stripped
        if current.rstrip().endswith('.'):
            tactics.append(current.strip())
            current = ""

    if current.strip():
        logger.warning("Discarded incomplete tactic: %s", current.strip())

    seen = set()
    unique = []
    for t in tactics:
        if t not in seen:
            seen.add(t)
            unique.append(t)
    return unique[:10]


def build_skeleton_script(goals: List[str]) -> Optional[str]:
    """Construct a static induction proof script for simple safety properties."""
    if not goals:
        return None

    reachable_hyp = None
    for g in goals:
        for line in g.splitlines():
            line = line.strip()
            if "reachable" in line and ":" in line:
                parts = line.split(":", 1)
                if len(parts) == 2 and "reachable" in parts[1]:
                    reachable_hyp = parts[0].strip()
                    break
        if reachable_hyp:
            break

    if not reachable_hyp:
        return None

    goal_str = goals[0] if goals else ""
    is_slice_goal = "slice" in goal_str and "1 0" in goal_str and "= 0" in goal_str
    is_mod_goal = "mod 4" in goal_str and "= 0" in goal_str

    if not is_slice_goal and not is_mod_goal:
        return None

    if is_slice_goal:
        step_tactic = (
            "match goal with H : step _ _ _ |- _ => inversion H; subst; clear H end; "
            "simpl; "
            "repeat (match goal with "
            "| [ |- context[slice (?x + 4) 1 0] ] => rewrite (slice_low2 (?x + 4)) "
            "| [ H : context[slice ?x 1 0] |- _ ] => rewrite (slice_low2 x) in H "
            "end); "
            "try (rewrite Nat.add_mod; rewrite (Nat.mod_same 4) by lia; "
            "     rewrite Nat.add_0_r; assumption); "
            "auto; try lia; try nia."
        )
    else:
        step_tactic = (
            "match goal with H : step _ _ _ |- _ => inversion H; subst; clear H end; "
            "simpl; "
            "rewrite Nat.add_mod; rewrite (Nat.mod_same 4) by lia; "
            "rewrite Nat.add_0_r; assumption; "
            "auto; try lia; try nia."
        )

    script = (
        "Proof.\n"
        "  intros.\n"
        f"  induction {reachable_hyp}.\n"
        "  - simpl; auto; try lia; try nia.\n"
        f"  - {step_tactic}\n"
        "Qed."
    )
    return script


def build_slice_alignment_prompt(
    theorem_name: str,
    theorem_statement: str,
    context: str
) -> str:
    """Specialised prompt for slice‑low‑2 alignment invariants (not used by generic pipeline)."""
    return (
        "You are an expert in Coq and hardware verification.\n"
        f"The theorem `{theorem_name}` states an alignment invariant:\n"
        f"```coq\n{theorem_statement}\n```\n\n"
        "The lemma `slice_low2` is available: `Lemma slice_low2 (x : nat) : slice x 1 0 = x mod 4.`\n\n"
        "Please provide a proof script that follows this structure:\n"
        "```coq\n"
        "Proof.\n"
        "  intros s inputs Hreach.\n"
        "  induction Hreach as [| s' s'' inputs' Hreach' IH Hstep].\n"
        "  - unfold slice; simpl; reflexivity.\n"
        "  - inversion Hstep; subst; simpl.\n"
        "    rewrite slice_low2.\n"
        "    rewrite slice_low2 in IH.\n"
        "    rewrite Nat.add_mod.\n"
        "    rewrite (Nat.mod_same 4) by lia.\n"
        "    rewrite Nat.add_0_r.\n"
        "    rewrite IH; reflexivity.\n"
        "Qed.\n"
        "```\n\n"
        f"Environment (the Coq definitions and lemmas above the theorem):\n```coq\n{context}\n```\n\n"
        "Return ONLY the Coq code from \"Proof.\" to \"Qed.\" (inclusive). Do NOT use Admitted."
    )


def build_skeleton_reflection_prompt(
    theorem_name: str,
    theorem_statement: str,
    context: str,
    goals: List[str],
    available_lemmas: List[str]
) -> str:
    """Prompt for LLM‑driven generation of a tailored proof skeleton."""
    goals_str = "\n".join(goals) if goals else "No goals"
    lemmas_str = ", ".join(available_lemmas) if available_lemmas else "none"

    return (
        "You are an expert in Coq and hardware verification.\n\n"
        f"We need to prove the theorem `{theorem_name}`:\n"
        f"```coq\n{theorem_statement}\n```\n\n"
        "The built‑in proof skeletons (induction on reachability + inversion + "
        "rewriting) have already been tried and failed.  We need a custom proof "
        "script that handles the specific structure of this design.\n\n"
        f"**Current goal** (after `intros`):\n```\n{goals_str}\n```\n\n"
        f"**Available lemmas**: {lemmas_str}\n\n"
        f"**Environment** (the Coq code above the theorem):\n```coq\n{context}\n```\n\n"
        "Please provide a complete Coq proof script starting with `Proof.` and ending "
        "with `Qed.` (use `Admitted.` only if absolutely impossible).  The script should:\n"
        "- Use induction on the reachability hypothesis if it exists.\n"
        "- Case‑split on the step constructors with `inversion`.\n"
        "- Make use of the available lemmas and the induction hypothesis.\n"
        "- Handle `if` conditions by `destruct`-ing them.\n"
        "Return **only** the Coq proof script, without any extra commentary."
    )
