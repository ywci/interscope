# src/specir/verification/proof/koika/proof_gen.py
#
# Coq proof generation using LLM.
# Extended with destruct‑template injection, mandatory‑avoid lists,
# stronger skeleton proofs that handle nested ite chains, and
# automatic Coq‑error correction (sanitization) plus proof‑adaptation
# for similar properties.

import re
from typing import List, Optional, Dict, Any
from specir.backends.llm_client import LLMClient
from specir.utils.logger import get_logger

logger = get_logger(__name__)

try:
    from specir.verification.perf.perf_analyzer import ObligationAnalysis
except ImportError:
    ObligationAnalysis = None


def sanitize_coq_script(script: str,
                        context_hypotheses: Optional[List[str]] = None) -> str:
    """
    Apply a series of simple, safe rewrites to a generated Coq proof
    script to eliminate the most common syntactic mistakes and deprecated
    notations.
    """
    if not script:
        return script

    original = script

    # 1. Rename conflicting "intros H" when H is already in the context.
    if context_hypotheses and any("H" in h for h in context_hypotheses):
        script = re.sub(r'\bintros\s+H\b\.', 'intros H0.', script)
        script = re.sub(r'\bintros\s+H\b\s*;', 'intros H0;', script)
        script = re.sub(r'\bintros\s+H\b\s*\n', 'intros H0\n', script)

    # 2. Remove orphan bullet lines (harmless but clean).
    lines = script.splitlines()
    cleaned_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped in ('-', '+', '*') and not stripped.startswith('(*'):
            cleaned_lines.append('  (* bullet removed by sanitizer *)')
        else:
            cleaned_lines.append(line)
    script = '\n'.join(cleaned_lines)

    # 3. Replace deprecated Nat.mod_add with Div0.mod_add.
    script = script.replace('Nat.mod_add', 'Div0.mod_add')

    # 4. Replace obvious boolean‑equality `discriminate` patterns.
    if re.search(r'discriminate\s+(\w+)\.', script):
        script = re.sub(r'discriminate\s+(\w+)\.', r'inversion \1.', script)

    if script != original:
        logger.debug("Sanitization applied to proof script.")
    return script


def adapt_proof(original_proof: str,
                theorem_name: str,
                theorem_statement: str,
                condition_subst: Optional[Dict[str, str]] = None,
                operation_subst: Optional[Dict[str, str]] = None) -> Optional[str]:
    """
    Adapt an existing successful proof script to a new theorem by
    substituting condition expressions and operation names.
    """
    if not original_proof or not original_proof.startswith("Proof."):
        return None

    script = original_proof

    if condition_subst:
        for old, new in condition_subst.items():
            script = script.replace(f"destruct ({old})", f"destruct ({new})")
            script = script.replace(old, new)

    if operation_subst:
        for old, new in operation_subst.items():
            script = script.replace(old, new)

    if script.startswith("Proof."):
        script = f"Theorem {theorem_name} : {theorem_statement}.\n{script}"
    else:
        lines = script.splitlines()
        new_lines = []
        replaced = False
        for line in lines:
            if line.strip().startswith("Theorem ") and not replaced:
                new_lines.append(f"Theorem {theorem_name} : {theorem_statement}.")
                replaced = True
            else:
                new_lines.append(line)
        script = "\n".join(new_lines)

    logger.info("Adapted proof for theorem '%s' using substitutions.", theorem_name)
    return script


def build_destruct_pattern(condition_var: str, num_branches: int) -> str:
    """
    Create a Coq destruct chain for a nested if‑then‑else on *condition_var*.

    The generated chain uses **explicit braces** for each case, avoiding
    bullet/focus issues.
    """
    if num_branches <= 1:
        return f"destruct ({condition_var} =? 0) eqn:Hop0.\n{{ simpl. reflexivity. }}"

    lines = []
    for i in range(num_branches - 1):
        eq = f"({condition_var} =? {i})"
        if i == 0:
            lines.append(f"destruct {eq} eqn:Hop{i}.")
            lines.append("{ simpl. reflexivity. }")
            lines.append("{")
        else:
            lines.append(f"  destruct {eq} eqn:Hop{i}.")
            lines.append("  { simpl. reflexivity. }")
            lines.append("  {")
    # last branch
    lines.append("    simpl. reflexivity.")
    # close nested braces
    for _ in range(num_branches - 1):
        lines.append("  }")
    return "\n".join(lines)


def _default_destruct_example() -> str:
    """
    Return a complete proof skeleton suitable as a few‑shot example for
    designs with a `load_inputs` rule and an `execute` rule containing a
    nested opcode `ite`.

    Uses explicit braces only.
    """
    return """Proof.
  intros s inputs Hreach.
  induction Hreach as [| s' s'' inputs' Hreach' IH Hstep].
  { simpl. intros Hvalid. discriminate Hvalid. }
  { inversion Hstep; subst; clear Hstep; simpl.
    { intros Hvalid. apply IH. assumption. }
    { intros Hvalid.
      destruct (op_reg s' =? 0) eqn:Hop0.
      { simpl. reflexivity. }
      { destruct (op_reg s' =? 1) eqn:Hop1.
        { simpl. reflexivity. }
        { destruct (op_reg s' =? 2) eqn:Hop2.
          { simpl. reflexivity. }
          { simpl. reflexivity. } } } } }
Qed."""


def _overflow_example() -> str:
    """
    Example for overflow‑style properties.  Uses `lia` after destructing
    the opcode and avoids `discriminate` on boolean equalities.
    Uses explicit braces only.
    """
    return """Proof.
  intros s inputs Hreach.
  induction Hreach as [| s' s'' inputs' Hreach' IH Hstep].
  { simpl. intros Hcond. destruct Hcond as [Hvalid [Hop Hoverflow]].
    discriminate Hvalid. }
  { inversion Hstep; subst; clear Hstep; simpl.
    { intros Hcond. destruct Hcond as [Hvalid [Hop Hoverflow]].
      simpl in Hop.
      inversion Hop. }
    { intros Hcond. destruct Hcond as [Hvalid [Hop Hoverflow]].
      destruct (op_reg s' =? 0) eqn:Hop0.
      { simpl in *. lia. }
      { destruct (op_reg s' =? 1) eqn:Hop1.
        { simpl in *. lia. }
        { destruct (op_reg s' =? 2) eqn:Hop2.
          { simpl in *. lia. }
          { simpl in *. lia. } } } } }
Qed."""


def build_coq_proof_prompt(
    theorem_name: str,
    theorem_statement: str,
    context: Optional[str] = None,
    tactic_hints: Optional[List[str]] = None,
    assumptions: Optional[List[str]] = None,
    previous_attempts: Optional[List[Dict[str, str]]] = None,
    structural_hints: Optional[str] = None,
    strategy_hint: Optional[str] = None,
    available_lemmas: Optional[List[str]] = None,
    mandatory_avoid: Optional[List[str]] = None,
    positive_example: Optional[str] = None,
    positive_examples: Optional[List[str]] = None,
    analysis: Optional[ObligationAnalysis] = None,
    failure_prompt_snippet: Optional[str] = None,
    mc_trace_info: Optional[str] = None,
) -> str:
    """Build a prompt for an LLM to generate a complete Coq proof script."""
    hints_str = ", ".join(tactic_hints) if tactic_hints else "induction, simpl, auto, rewrite, inversion, destruct, lia"
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
    if available_lemmas:
        lemmas_str = ", ".join(available_lemmas)
        parts.append(f"**Proved lemmas** (you may rewrite with them): {lemmas_str}\n")
    if assumes_str:
        parts.append(f"Assumptions:\n{assumes_str}\n")
    if structural_hints:
        parts.append(f"**Structural analysis of the goal:**\n{structural_hints}\n")
    if strategy_hint:
        parts.append(f"**Proof strategy to use:** {strategy_hint}\n")
    parts.append(f"Suggested tactics: {hints_str}")
    parts.append("")
    parts.append(
        "Generate a complete Coq proof script that proves the theorem. "
        "The script must include the `Proof.` and `Qed.` lines. "
        "If you cannot complete the proof, end with `Admitted.` instead of `Qed.`. "
        "Return only the Coq code without any extra commentary."
    )

    # Static forbidden patterns
    avoid_list = [
        "Do NOT use `intros H` – use fresh names such as `intros Hcond`.",
        "Do NOT use `discriminate` on boolean equalities; use `inversion` or `destruct`.",
        "Use explicit braces `{ ... }` for subgoals.  Do NOT use bullets `-`, `+`, `*`.",
        "Do NOT apply the induction hypothesis before destructing the opcode condition.",
        "After `inversion Hstep; subst; clear Hstep`, run `simpl` before `apply IH` or `destruct`.",
        "Always destruct `op_reg s =? 0`, `op_reg s =? 1`, etc. before applying the induction hypothesis.",
        "Use `reflexivity` ONLY when both sides are syntactically identical.",
        "Do NOT use `rewrite Nat.eqb_refl` unless the goal contains `x =? x`.",
        "If the induction hypothesis has a conjunctive antecedent, destruct it before applying `IH`.",
        "The step relation may have two constructors `step_load_inputs` and `step_execute`.",
        "In the `step_load_inputs` subgoal, do NOT apply IH; close by contradiction/vacuity.",
        "In the `step_execute` subgoal, destruct the opcode and use `simpl; reflexivity` or `simpl; lia`.",
        "If you have a hypothesis `Hop : (op_reg s =? 0) = true`, use `destruct (op_reg s =? 0) eqn:Hop0` or `inversion Hop` after `simpl`, not `discriminate`.",
    ]
    if mandatory_avoid:
        avoid_list = mandatory_avoid + avoid_list

    if analysis is not None and analysis.has_nested_ite and analysis.max_ite_depth >= 3:
        avoid_list.append(
            "The step constructor contains a deeply nested if‑then‑else chain. "
            "After inversion, destruct each condition before applying the induction hypothesis."
        )

    if failure_prompt_snippet:
        avoid_list.append(
            "**Recent repeated failures (do NOT repeat these mistakes):**\n" +
            failure_prompt_snippet
        )

    parts.append(
        "\n**CRITICAL RULES (do NOT break these):**\n" +
        "\n".join(f"- {item}" for item in avoid_list) + "\n"
    )

    # Positive examples
    examples = [_default_destruct_example()]
    if "overflow" in theorem_name.lower() or "neq" in theorem_name.lower():
        examples.append(_overflow_example())
    if positive_example:
        examples.append(positive_example)
    if positive_examples:
        examples.extend(positive_examples)

    # De‑duplicate
    seen = set()
    unique_examples = []
    for ex in examples:
        if ex not in seen:
            seen.add(ex)
            unique_examples.append(ex)
    examples = unique_examples

    if examples:
        for i, example in enumerate(examples, 1):
            parts.append(
                f"\n**Example {i} of a successful proof for a similar property:**\n"
                f"```coq\n{example}\n```\n"
            )
        parts.append(
            "Use the structure shown above as a template. Replace condition and "
            "operation names as needed for the current theorem."
        )

    if mc_trace_info:
        parts.append(
            "\n**Model‑checking counterexample trace information:**\n" +
            mc_trace_info +
            "\nUse this information to guide arithmetic reasoning."
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
    max_tokens: int = 2048,
    structural_hints: Optional[str] = None,
    available_lemmas: Optional[List[str]] = None,
    mandatory_avoid: Optional[List[str]] = None,
    positive_example: Optional[str] = None,
    positive_examples: Optional[List[str]] = None,
    analysis: Optional[ObligationAnalysis] = None,
    failure_prompt_snippet: Optional[str] = None,
    mc_trace_info: Optional[str] = None,
) -> str:
    prompt = build_coq_proof_prompt(
        theorem_name=theorem_name,
        theorem_statement=theorem_statement,
        context=context,
        tactic_hints=tactic_hints,
        assumptions=assumptions,
        previous_attempts=previous_attempts,
        structural_hints=structural_hints,
        available_lemmas=available_lemmas,
        mandatory_avoid=mandatory_avoid,
        positive_example=positive_example,
        positive_examples=positive_examples,
        analysis=analysis,
        failure_prompt_snippet=failure_prompt_snippet,
        mc_trace_info=mc_trace_info,
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
    step_case_hint: str = (
        "1.  Name the step hypothesis `Hstep` in the induction scheme.\n"
        "2.  `inversion Hstep; subst; clear Hstep.`\n"
        "3.  If the goal now contains `if op_reg s =? …`, destruct each comparison.\n"
        "4.  In each sub‑goal, `simpl` and apply the induction hypothesis `IH`.\n"
        "5.  Finish with `auto; try lia; try nia`."
    ),
    available_lemmas: Optional[List[str]] = None,
    structural_hints: Optional[str] = None,
) -> str:
    goals_str = "\n".join(goals) if goals else "No goals"
    hints_str = ", ".join(tactic_hints) if tactic_hints else (
        "induction, simpl, auto, eauto, rewrite, inversion, subst, destruct, split, lia, nia"
    )
    recent_history = applied_tactics[-8:] if applied_tactics else []
    history_str = "\n".join(f"  {t}" for t in recent_history) if recent_history else "(none)"

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

    structural_str = ""
    if structural_hints:
        structural_str = f"\n**Structural notes:** {structural_hints}\n"

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
        f"{structural_str}"
        f"Suggested approach: {hints_str}\n\n"
        "**CRITICAL RULES:**\n"
        "- Use explicit braces `{ ... }` for subgoals, not bullets.\n"
        "- If a variable already appears in the hypotheses, do NOT `intros` it again.\n"
        "- After `induction` on the reachability hypothesis, there will be one subgoal per constructor.\n"
        f"- For the base case: `{base_case_hint}`\n"
        f"- For the step case: `{step_case_hint}`\n"
        "- Use the induction hypothesis (often named `IH`) when it helps.\n"
        "- If the goal contains `if ... then ... else`, use `destruct` on the condition.\n"
        "- Return ONLY one complete tactic ending with a dot.\n"
        "- If your previous tactic failed, you MUST try something different."
    )


def extract_tactics_from_response(response: str) -> List[str]:
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


def build_skeleton_script(
    goals: List[str],
    theorem_statement: str = "",
    condition_var: Optional[str] = None,
    num_branches: int = 0,
) -> Optional[str]:
    if not goals:
        return None

    reachable_hyp = None
    goal_str = goals[0] if goals else ""

    for line in goal_str.splitlines():
        line = line.strip()
        if "reachable" in line and ":" in line:
            parts = line.split(":", 1)
            if len(parts) == 2 and "reachable" in parts[1]:
                reachable_hyp = parts[0].strip()
                break

    if not reachable_hyp:
        return None

    has_valid_implication = bool(
        re.search(r"\(?valid\s+\w+\s*\)?\s*=\s*true\s*->", goal_str)
    )

    if has_valid_implication:
        base_tactic = "simpl; intros Hvalid; discriminate Hvalid."
        if condition_var and num_branches > 1:
            destruct_tactic = build_destruct_pattern(condition_var, num_branches)
            step_tactic = (
                "inversion Hstep; subst; simpl in *.\n"
                f"  {destruct_tactic}\n"
                "  all: try (simpl; reflexivity); try (apply IH; auto)."
            )
        else:
            step_tactic = (
                "inversion Hstep; subst; simpl in *; "
                "auto; try lia; try nia."
            )
        # Use braces for the two induction subgoals.
        script = (
            "Proof.\n"
            "  intros s inputs Hreach.\n"
            f"  induction Hreach as [| s' s'' inputs' Hreach' IH Hstep].\n"
            f"  {{ {base_tactic} }}\n"
            f"  {{ {step_tactic} }}\n"
            "Qed."
        )
        return script

    return None


def build_slice_alignment_prompt(
    theorem_name: str,
    theorem_statement: str,
    context: str
) -> str:
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
        "  { unfold slice; simpl; reflexivity. }\n"
        "  { inversion Hstep; subst; simpl.\n"
        "    rewrite slice_low2.\n"
        "    rewrite slice_low2 in IH.\n"
        "    rewrite Nat.add_mod.\n"
        "    rewrite (Nat.mod_same 4) by lia.\n"
        "    rewrite Nat.add_0_r.\n"
        "    rewrite IH; reflexivity. }\n"
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
    available_lemmas: List[str],
    structural_hints: Optional[str] = None,
) -> str:
    goals_str = "\n".join(goals) if goals else "No goals"
    lemmas_str = ", ".join(available_lemmas) if available_lemmas else "none"

    structural_part = ""
    if structural_hints:
        structural_part = f"\n**Structural insights:** {structural_hints}\n"

    return (
        "You are an expert in Coq and hardware verification.\n\n"
        f"We need to prove the theorem `{theorem_name}`:\n"
        f"```coq\n{theorem_statement}\n```\n\n"
        "The built‑in proof skeletons have already been tried and failed. "
        "We need a custom proof script that handles the specific structure "
        "of this design.\n\n"
        f"**Current goal** (after `intros`):\n```\n{goals_str}\n```\n\n"
        f"**Available lemmas**: {lemmas_str}\n"
        f"{structural_part}"
        f"**Environment** (the Coq code above the theorem):\n```coq\n{context}\n```\n\n"
        "Please provide a complete Coq proof script starting with `Proof.` and ending "
        "with `Qed.`.  Use explicit braces `{ ... }` for subgoals, not bullets.\n"
        "Return **only** the Coq proof script, without any extra commentary."
    )


def generate_coq_proof_variants(
    llm_client: LLMClient,
    theorem_name: str,
    theorem_statement: str,
    num_variants: int = 4,
    context: Optional[str] = None,
    tactic_hints: Optional[List[str]] = None,
    assumptions: Optional[List[str]] = None,
    temperature: float = 0.4,
    max_tokens: int = 2048,
    previous_attempts: Optional[List[Dict[str, str]]] = None,
    structural_hints: Optional[str] = None,
    diversity_tags: Optional[List[str]] = None,
    repair_mode: bool = False,
    available_lemmas: Optional[List[str]] = None,
    mandatory_avoid: Optional[List[str]] = None,
    positive_example: Optional[str] = None,
    positive_examples: Optional[List[str]] = None,
    analysis: Optional[ObligationAnalysis] = None,
    failure_prompt_snippet: Optional[str] = None,
    mc_trace_info: Optional[str] = None,
) -> List[str]:
    if repair_mode and not previous_attempts:
        repair_mode = False

    if repair_mode:
        return _generate_with_repair(
            llm_client, theorem_name, theorem_statement, num_variants,
            context, tactic_hints, assumptions, temperature, max_tokens,
            previous_attempts, structural_hints, diversity_tags,
            available_lemmas, mandatory_avoid, positive_example,
            positive_examples, analysis, failure_prompt_snippet, mc_trace_info,
        )

    variants = []
    original_temp = llm_client.temperature
    gen_temp = temperature if temperature > 0 else original_temp

    base_prompt = build_coq_proof_prompt(
        theorem_name=theorem_name,
        theorem_statement=theorem_statement,
        context=context,
        tactic_hints=tactic_hints,
        assumptions=assumptions,
        previous_attempts=previous_attempts,
        structural_hints=structural_hints,
        available_lemmas=available_lemmas,
        mandatory_avoid=mandatory_avoid,
        positive_example=positive_example,
        positive_examples=positive_examples,
        analysis=analysis,
        failure_prompt_snippet=failure_prompt_snippet,
        mc_trace_info=mc_trace_info,
    )

    for i in range(num_variants):
        prompt = base_prompt
        if diversity_tags and i < len(diversity_tags):
            prompt += f"\n\n**Strategy hint for this variant:** {diversity_tags[i]}"
        if i > 0:
            prompt += (
                f"\n\nTry a fundamentally different proof approach than previous attempts. "
                f"Use different tactics or a different induction scheme. "
                f"This is variant {i+1} of {num_variants}."
            )
        llm_client.temperature = max(0.1, gen_temp + (i - num_variants/2) * 0.05) if i > 0 else gen_temp

        try:
            response = llm_client.generate(prompt, max_tokens=max_tokens)
            script = extract_proof_script(response)
            if script and "Proof." in script and ("Qed." in script or "Admitted." in script):
                variants.append(script)
            else:
                fallback = build_coq_proof_prompt(
                    theorem_name=theorem_name,
                    theorem_statement=theorem_statement,
                    context=context,
                    tactic_hints=["induction", "simpl", "auto", "discriminate", "destruct", "lia"],
                    assumptions=assumptions,
                    available_lemmas=available_lemmas,
                    mandatory_avoid=mandatory_avoid,
                    positive_example=positive_example,
                    positive_examples=positive_examples,
                    analysis=analysis,
                    failure_prompt_snippet=failure_prompt_snippet,
                    mc_trace_info=mc_trace_info,
                )
                if diversity_tags and i < len(diversity_tags):
                    fallback += f"\n\n**Strategy hint:** {diversity_tags[i]}"
                response2 = llm_client.generate(fallback, max_tokens=max_tokens)
                script2 = extract_proof_script(response2)
                if script2 and "Proof." in script2:
                    variants.append(script2)
                else:
                    variants.append("Proof. Admitted.")
        except Exception as e:
            logger.warning("Variant %d generation failed: %s", i, e)
            variants.append("Proof. Admitted.")

    llm_client.temperature = original_temp
    while len(variants) < num_variants:
        variants.append("Proof. Admitted.")
    return variants[:num_variants]


def _generate_with_repair(
    llm_client: LLMClient,
    theorem_name: str,
    theorem_statement: str,
    num_variants: int,
    context: Optional[str],
    tactic_hints: Optional[List[str]],
    assumptions: Optional[List[str]],
    temperature: float,
    max_tokens: int,
    previous_attempts: Optional[List[Dict[str, str]]],
    structural_hints: Optional[str],
    diversity_tags: Optional[List[str]],
    available_lemmas: Optional[List[str]],
    mandatory_avoid: Optional[List[str]],
    positive_example: Optional[str],
    positive_examples: Optional[List[str]],
    analysis: Optional[ObligationAnalysis] = None,
    failure_prompt_snippet: Optional[str] = None,
    mc_trace_info: Optional[str] = None,
) -> List[str]:
    prompt = build_coq_proof_prompt(
        theorem_name=theorem_name,
        theorem_statement=theorem_statement,
        context=context,
        tactic_hints=tactic_hints,
        assumptions=assumptions,
        previous_attempts=previous_attempts,
        structural_hints=structural_hints,
        available_lemmas=available_lemmas,
        mandatory_avoid=mandatory_avoid,
        positive_example=positive_example,
        positive_examples=positive_examples,
        analysis=analysis,
        failure_prompt_snippet=failure_prompt_snippet,
        mc_trace_info=mc_trace_info,
    )

    n_extra = max(1, num_variants - 1)
    prompt += (
        "\n\n"
        "Your response must contain **one repaired proof** that fixes the error, "
        f"followed by **{n_extra} additional, meaningfully different proof attempts**.\n\n"
        "Format your reply exactly like this:\n\n"
        "### REPAIR\n"
        "Proof.\n"
        "...\n"
        "Qed.\n\n"
        f"### VARIANT 1\n"
        "Proof.\n"
        "...\n"
        "Qed.\n\n"
        f"... up to VARIANT {n_extra}\n\n"
        "Return ONLY the sections described above, without any extra commentary."
    )

    if diversity_tags and n_extra > 0:
        tags = []
        for i in range(n_extra):
            tag = diversity_tags[i % len(diversity_tags)]
            tags.append(f"VARIANT {i+1} strategy: {tag}")
        prompt += "\n" + "\n".join(tags)

    original_temp = llm_client.temperature
    llm_client.temperature = max(0.3, temperature)
    try:
        response = llm_client.generate(prompt, max_tokens=max_tokens)
    except Exception as e:
        logger.warning("Repair+variants generation failed: %s", e)
        llm_client.temperature = original_temp
        return ["Proof. Admitted."] * num_variants
    finally:
        llm_client.temperature = original_temp

    scripts = _parse_repair_variants_response(response, num_variants)
    while len(scripts) < num_variants:
        scripts.append("Proof. Admitted.")
    return scripts[:num_variants]


def _parse_repair_variants_response(response: str, expected_total: int) -> List[str]:
    response = response.replace("\r\n", "\n").replace("\r", "\n")

    pattern = re.compile(r"^###\s*(REPAIR|VARIANT\s+\d+)", re.MULTILINE)
    parts = pattern.split(response)

    repair_found = False
    variant_scripts = {}

    for i in range(1, len(parts), 2):
        header = parts[i].strip()
        content = parts[i + 1] if i + 1 < len(parts) else ""
        script = _extract_coq_block(content)
        if header == "REPAIR":
            variant_scripts[-1] = script
            repair_found = True
        else:
            match = re.match(r"VARIANT\s+(\d+)", header)
            if match:
                num = int(match.group(1))
                variant_scripts[num] = script

    result = []
    if repair_found and -1 in variant_scripts:
        result.append(variant_scripts[-1])
    else:
        result.append("Proof. Admitted.")

    for vnum in range(1, expected_total):
        result.append(variant_scripts.get(vnum, "Proof. Admitted."))

    return result


def _extract_coq_block(text: str) -> str:
    text = text.strip()
    if "Proof." in text:
        return extract_proof_script(text)
    return text if text else "Proof. Admitted."
