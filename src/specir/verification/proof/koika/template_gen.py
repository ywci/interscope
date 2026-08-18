# src/specir/verification/proof/koika/template_gen.py
#
# Template‑based Coq proof variant generator.
# Produces a set of alternative proof scripts without an LLM,
# using pre‑defined tactic patterns that match typical Koika
# safety properties.  Intended as a fallback when no LLM is
# available or as a complement in PERF's beam search.

from typing import List, Optional
from specir.utils.logger import get_logger
from specir.verification.proof.structural_validator import validate_structure

logger = get_logger(__name__)

try:
    from specir.verification.perf.perf_analyzer import ObligationAnalysis
except ImportError:
    ObligationAnalysis = None


def _template_is_structurally_valid(script: str) -> bool:
    """Return True if the script has no critical structural issues."""
    issues = validate_structure(script)
    for issue in issues:
        if ("Unbalanced braces" in issue or
            "Unbalanced parentheses" in issue or
            "Unbalanced square brackets" in issue or
            "Unclosed proof" in issue or
            "orphan bullet" in issue):
            return False
    return True


def _contains_deprecated_notations(script: str) -> bool:
    """Return True if the script contains deprecated notations that we want to avoid."""
    deprecated = [
        "Nat.mod_add",
        "Nat.mod_mul",
        "Nat.mod_mod",
        "Nat.mod_same",
        "Nat.mod_1_l",
        "Nat.mod_1_r",
        "Nat.mod_0_l",
        "Nat.mod_0_r",
        "Nat.div_add",
        "Nat.div_mul",
        "Nat.div_div",
        "Nat.div_same",
        "Nat.div_1_r",
        "Nat.div_1_l",
    ]
    for old in deprecated:
        if old in script:
            return True
    return False


def generate_coq_proof_variants_template(
    theorem_name: str,
    theorem_statement: str,
    num_variants: int = 4,
    context: Optional[str] = None,
    tactic_hints: Optional[List[str]] = None,
    assumptions: Optional[List[str]] = None,
    temperature: float = 0.4,
    max_tokens: int = 2048,
    analysis: Optional[ObligationAnalysis] = None
) -> List[str]:
    """
    Return a list of Coq proof scripts generated from built‑in templates.

    If *analysis* (an ``ObligationAnalysis``) is provided and certain
    structural conditions are met, specialised templates are emitted
    first, making the search more targeted.  After those, generic
    templates fill the remaining requested variants.

    **All returned templates are structurally validated**: any script
    with unbalanced braces, unclosed proof blocks, orphan bullets, or
    deprecated notations is discarded.  This ensures fallback candidates
    do not cause focus/nested‑proof errors or Coq deprecation warnings
    downstream.

    Args:
        theorem_name:   Name of the theorem (used to select specific templates).
        theorem_statement: The Coq statement (ignored; templates are generic).
        num_variants:   Number of distinct proof scripts to generate.
        context:        Ignored (provided for API compatibility).
        tactic_hints:   Ignored.
        assumptions:    Ignored.
        temperature:    Ignored.
        max_tokens:     Ignored.
        analysis:       Optional structural analysis result from
                        ``PERFAnalyzer``.  Used to adapt templates.

    Returns:
        List of Coq proof scripts (``Proof. … Qed.``), one per variant.
    """
    variants: List[str] = []

    # Helper to decide if the theorem is overflow-like (needs arithmetic).
    is_overflow_like = ("overflow" in theorem_name.lower() or
                        "neq" in theorem_name.lower() or
                        "result_neq" in theorem_name.lower())

    def _brace_destruct_chain(op_var: str, num_branches: int = 4) -> str:
        """
        Return a Coq tactic string that destructs op_var =? 0,1,2,...
        using explicit braces.  The final branch is a catch‑all.
        """
        if num_branches <= 1:
            return f"destruct ({op_var} =? 0) eqn:Hop0.\n{{ simpl. reflexivity. }}"

        lines = []
        for i in range(num_branches - 1):
            eq = f"({op_var} =? {i})"
            if i == 0:
                lines.append(f"destruct {eq} eqn:Hop{i}.")
                lines.append("{ simpl. reflexivity. }")
                lines.append("{")
            else:
                lines.append(f"  destruct {eq} eqn:Hop{i}.")
                lines.append("  { simpl. reflexivity. }")
                lines.append("  {")
        # last branch: after false of last explicit condition, we are in
        # the innermost else. We just close all braces and add final tactic.
        lines.append("    simpl. reflexivity.")
        for _ in range(num_branches - 1):
            lines.append("  }")
        return "\n".join(lines)

    if analysis is not None:
        if analysis.num_step_constructors == 2 and analysis.step_constructor_names:
            # Template using explicit single braces throughout.
            template_two_ctors = (
                "Proof.\n"
                "  intros s inputs Hreach.\n"
                "  induction Hreach as [| s' s'' inputs' Hreach' IH Hstep].\n"
                "  { simpl. intros Hvalid. discriminate Hvalid. }\n"
                "  { inversion Hstep; subst; clear Hstep; simpl.\n"
                "    { intros Hvalid. apply IH. assumption. }\n"
                "    { intros Hvalid.\n"
                "      destruct (op_reg s' =? 0) eqn:Hop0.\n"
                "      { simpl. reflexivity. }\n"
                "      { destruct (op_reg s' =? 1) eqn:Hop1.\n"
                "        { simpl. reflexivity. }\n"
                "        { destruct (op_reg s' =? 2) eqn:Hop2.\n"
                "          { simpl. reflexivity. }\n"
                "          { simpl. reflexivity. } } } } }\n"
                "Qed."
            )
            variants.append(template_two_ctors)

            # Variant using `auto` in execute branch.
            template_two_ctors_auto = (
                "Proof.\n"
                "  intros s inputs Hreach.\n"
                "  induction Hreach as [| s' s'' inputs' Hreach' IH Hstep].\n"
                "  { simpl. intros Hvalid. discriminate Hvalid. }\n"
                "  { inversion Hstep; subst; clear Hstep; simpl.\n"
                "    { apply IH; auto. }\n"
                "    { intros Hvalid; destruct (op_reg s' =? 0) eqn:Hop0;\n"
                "      destruct (op_reg s' =? 1) eqn:Hop1;\n"
                "      destruct (op_reg s' =? 2) eqn:Hop2; simpl; auto. }\n"
                "  }\n"
                "Qed."
            )
            variants.append(template_two_ctors_auto)

            # Overflow-specific template: use lia in execute, handle load_inputs
            # by destructing the boolean equality, not by rewriting Nat.eqb_eq.
            if is_overflow_like:
                template_overflow = (
                    "Proof.\n"
                    "  intros s inputs Hreach.\n"
                    "  induction Hreach as [| s' s'' inputs' Hreach' IH Hstep].\n"
                    "  { simpl. intros Hcond. destruct Hcond as [Hvalid [Hop Hoverflow]].\n"
                    "    discriminate Hvalid. }\n"
                    "  { inversion Hstep; subst; clear Hstep; simpl.\n"
                    "    { intros Hcond. destruct Hcond as [Hvalid [Hop Hoverflow]].\n"
                    "      simpl in Hop. inversion Hop. }\n"
                    "    { intros Hcond. destruct Hcond as [Hvalid [Hop Hoverflow]].\n"
                    "      destruct (op_reg s' =? 0) eqn:Hop0.\n"
                    "      { simpl in *. lia. }\n"
                    "      { destruct (op_reg s' =? 1) eqn:Hop1.\n"
                    "        { simpl in *. lia. }\n"
                    "        { destruct (op_reg s' =? 2) eqn:Hop2.\n"
                    "          { simpl in *. lia. }\n"
                    "          { simpl in *. lia. } } } } }\n"
                    "Qed."
                )
                variants.append(template_overflow)

        if analysis.has_nested_ite and analysis.max_ite_depth >= 3:
            destruct_chain = _brace_destruct_chain("op_reg s'", 4)

            template_nested_ite = (
                "Proof.\n"
                "  intros s inputs Hreach.\n"
                "  induction Hreach as [| s' s'' inputs' Hreach' IH Hstep].\n"
                "  { simpl. intros Hvalid. discriminate Hvalid. }\n"
                "  { inversion Hstep; subst; clear Hstep; simpl.\n"
                f"    {destruct_chain}\n"
                "  }\n"
                "Qed."
            )
            # Insert only if we don't already have two-constructor variants.
            if not (analysis.num_step_constructors == 2 and analysis.step_constructor_names):
                variants.insert(0, template_nested_ite)
            else:
                variants.append(template_nested_ite)

        elif analysis.has_nested_ite and analysis.max_ite_depth <= 2:
            template_nested_ite_simple = (
                "Proof.\n"
                "  intros s inputs Hreach.\n"
                "  induction Hreach as [| s' s'' inputs' Hreach' IH Hstep].\n"
                "  { simpl. auto. }\n"
                "  { inversion Hstep; subst; clear Hstep; simpl.\n"
                "    repeat (match goal with\n"
                "            | [ |- context[if ?b then _ else _] ] => destruct b eqn:?\n"
                "            | [ H : context[if ?b then _ else _] |- _ ] => destruct b eqn:? in H\n"
                "            end).\n"
                "    auto; try lia; try nia. }\n"
                "Qed."
            )
            variants.append(template_nested_ite_simple)

    template_pool = [
        # 0 – Simple induction + auto
        """Proof.
  intros s inputs Hreach.
  induction Hreach as [| s' s'' inputs' Hreach' IH Hstep].
  { simpl. auto. }
  { inversion Hstep; subst; simpl; auto. }
Qed.""",

        # 1 – Induction + destruct on if‑then‑else + auto
        """Proof.
  intros s inputs Hreach.
  induction Hreach as [| s' s'' inputs' Hreach' IH Hstep].
  { simpl. auto. }
  { inversion Hstep; subst; simpl.
    repeat (match goal with [ |- context[if ?b then _ else _] ] => destruct b eqn:? end).
    auto. }
Qed.""",

        # 2 – Induction + lia for arithmetic goals
        """Proof.
  intros s inputs Hreach.
  induction Hreach as [| s' s'' inputs' Hreach' IH Hstep].
  { simpl. lia. }
  { inversion Hstep; subst; simpl. lia. }
Qed.""",

        # 3 – Induction + rewriting with slice_low2
        """Proof.
  intros s inputs Hreach.
  induction Hreach as [| s' s'' inputs' Hreach' IH Hstep].
  { simpl. auto. }
  { inversion Hstep; subst; simpl.
    try rewrite slice_low2.
    auto. }
Qed.""",

        # 4 – Induction + apply induction hypothesis explicitly
        """Proof.
  intros s inputs Hreach.
  induction Hreach as [| s' s'' inputs' Hreach' IH Hstep].
  { simpl. auto. }
  { inversion Hstep; subst; simpl.
    try apply IH.
    auto. }
Qed.""",

        # 5 – Induction + eauto with a larger search depth
        """Proof.
  intros s inputs Hreach.
  induction Hreach as [| s' s'' inputs' Hreach' IH Hstep].
  { simpl. eauto. }
  { inversion Hstep; subst; simpl; eauto 6. }
Qed.""",

        # 6 – Induction + nia (non‑linear integer arithmetic)
        """Proof.
  intros s inputs Hreach.
  induction Hreach as [| s' s'' inputs' Hreach' IH Hstep].
  { simpl. nia. }
  { inversion Hstep; subst; simpl. nia. }
Qed.""",

        # 7 – General skeleton: intros, induction, inversion, subst, simpl, auto with *
        """Proof.
  intros s inputs Hreach.
  induction Hreach as [| s' s'' inputs' Hreach' IH Hstep].
  { simpl. auto with *. }
  { inversion Hstep; subst; simpl. auto with *. }
Qed.""",
    ]

    needed = num_variants - len(variants)
    if needed > 0:
        for i in range(needed):
            template = template_pool[i % len(template_pool)]
            if i >= len(template_pool):
                template = template.replace(
                    "Qed.",
                    f"  (* variant {len(variants)+1} *) Qed."
                )
            variants.append(template)

    valid_variants = [
        v for v in variants
        if _template_is_structurally_valid(v) and not _contains_deprecated_notations(v)
    ]

    if len(valid_variants) < num_variants:
        logger.debug(
            "Filtered out %d structurally invalid or deprecated template(s).",
            len(variants) - len(valid_variants),
        )
        # Fill any remaining slots with known-valid generic templates.
        for template in template_pool:
            if len(valid_variants) >= num_variants:
                break
            if _template_is_structurally_valid(template) and not _contains_deprecated_notations(template):
                valid_variants.append(template)

    # Ensure we return exactly num_variants if possible.
    if len(valid_variants) < num_variants:
        logger.warning(
            "Could only produce %d valid template variants out of %d requested.",
            len(valid_variants), num_variants,
        )
        return valid_variants

    logger.debug(
        "Generated %d template proof variants for theorem '%s' (analysis=%s, overflow_like=%s).",
        len(valid_variants),
        theorem_name,
        analysis is not None,
        is_overflow_like,
    )

    return valid_variants[:num_variants]
