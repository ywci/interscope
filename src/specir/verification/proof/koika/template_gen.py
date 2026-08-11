# src/specir/verification/proof/koika/template_gen.py
#
# Template‑based Coq proof variant generator.
# Produces a set of alternative proof scripts without an LLM,
# using pre‑defined tactic patterns that match typical Koika
# safety properties.  Intended as a fallback when no LLM is
# available or as a complement in PERF's beam search.

from typing import List, Optional
from specir.utils.logger import get_logger

logger = get_logger(__name__)

try:
    from specir.verification.perf.perf_analyzer import ObligationAnalysis
except ImportError:
    ObligationAnalysis = None


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

    The templates are simple structural induction patterns combined with
    common tactics (auto, lia, inversion, destruct) and are intended for
    reachability‑based safety properties.  They do **not** use an LLM.

    If *analysis* (an ``ObligationAnalysis``) is provided and certain
    structural conditions are met, specialised templates are emitted
    first, making the search more targeted.  After those, generic
    templates fill the remaining requested variants.

    Args:
        theorem_name:   Name of the theorem (used only for a comment).
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

    if analysis is not None:
        if analysis.num_step_constructors == 2 and analysis.step_constructor_names:
            names = analysis.step_constructor_names
            template_two_ctors = (
                "Proof.\n"
                "  intros s inputs Hreach.\n"
                "  induction Hreach as [| s' s'' inputs' Hreach' IH Hstep].\n"
                "  - simpl. auto.\n"
                "  - inversion Hstep; subst; clear Hstep.\n"
                f"    + (* {names[0]} *) apply IH; auto.\n"
                f"    + (* {names[1]} *) simpl; reflexivity.\n"
                "Qed."
            )
            variants.append(template_two_ctors)

            template_two_ctors_destruct = (
                "Proof.\n"
                "  intros s inputs Hreach.\n"
                "  induction Hreach as [| s' s'' inputs' Hreach' IH Hstep].\n"
                "  - simpl. auto.\n"
                "  - inversion Hstep; subst; clear Hstep.\n"
                "    repeat (match goal with [ |- context[if ?b then _ else _] ] => destruct b eqn:? end).\n"
                f"    + apply IH; auto.\n"
                f"    + simpl; reflexivity.\n"
                "Qed."
            )
            variants.append(template_two_ctors_destruct)

        if analysis.has_nested_ite and analysis.max_ite_depth >= 3:
            # Template with repeated destruct on conditionals
            template_nested_ite = (
                "Proof.\n"
                "  intros s inputs Hreach.\n"
                "  induction Hreach as [| s' s'' inputs' Hreach' IH Hstep].\n"
                "  - simpl. auto.\n"
                "  - inversion Hstep; subst; clear Hstep; simpl.\n"
                "    repeat (match goal with\n"
                "            | [ |- context[if ?b then _ else _] ] => destruct b eqn:?\n"
                "            | [ H : context[if ?b then _ else _] |- _ ] => destruct b eqn:? in H\n"
                "            end).\n"
                "    auto; try lia; try nia.\n"
                "Qed."
            )
            variants.append(template_nested_ite)

            # Alternative: case analysis with multiple destruct + auto
            template_nested_ite2 = (
                "Proof.\n"
                "  intros s inputs Hreach.\n"
                "  induction Hreach as [| s' s'' inputs' Hreach' IH Hstep].\n"
                "  - simpl. auto.\n"
                "  - inversion Hstep; subst; clear Hstep; simpl.\n"
                "    repeat destruct_ifs; auto; try lia; try nia.\n"
                "Qed."
            )
            variants.append(template_nested_ite2)

    template_pool = [
        # 0 – Simple induction + auto
        """Proof.
  intros s inputs Hreach.
  induction Hreach as [| s' s'' inputs' Hreach' IH Hstep].
  - simpl. auto.
  - inversion Hstep; subst; simpl; auto.
Qed.""",

        # 1 – Induction + destruct on if‑then‑else + auto
        """Proof.
  intros s inputs Hreach.
  induction Hreach as [| s' s'' inputs' Hreach' IH Hstep].
  - simpl. auto.
  - inversion Hstep; subst; simpl.
    repeat (match goal with [ |- context[if ?b then _ else _] ] => destruct b eqn:? end).
    auto.
Qed.""",

        # 2 – Induction + lia for arithmetic goals
        """Proof.
  intros s inputs Hreach.
  induction Hreach as [| s' s'' inputs' Hreach' IH Hstep].
  - simpl. lia.
  - inversion Hstep; subst; simpl. lia.
Qed.""",

        # 3 – Induction + rewriting with slice_low2 (common helper lemma)
        """Proof.
  intros s inputs Hreach.
  induction Hreach as [| s' s'' inputs' Hreach' IH Hstep].
  - simpl. auto.
  - inversion Hstep; subst; simpl.
    try rewrite slice_low2.
    auto.
Qed.""",

        # 4 – Induction + apply induction hypothesis explicitly
        """Proof.
  intros s inputs Hreach.
  induction Hreach as [| s' s'' inputs' Hreach' IH Hstep].
  - simpl. auto.
  - inversion Hstep; subst; simpl.
    try apply IH.
    auto.
Qed.""",

        # 5 – Induction + eauto with a larger search depth
        """Proof.
  intros s inputs Hreach.
  induction Hreach as [| s' s'' inputs' Hreach' IH Hstep].
  - simpl. eauto.
  - inversion Hstep; subst; simpl; eauto 6.
Qed.""",

        # 6 – Induction + nia (non‑linear integer arithmetic)
        """Proof.
  intros s inputs Hreach.
  induction Hreach as [| s' s'' inputs' Hreach' IH Hstep].
  - simpl. nia.
  - inversion Hstep; subst; simpl. nia.
Qed.""",

        # 7 – General skeleton: intros, induction, inversion, subst, simpl, auto with *
        """Proof.
  intros s inputs Hreach.
  induction Hreach as [| s' s'' inputs' Hreach' IH Hstep].
  - simpl. auto with *.
  - inversion Hstep; subst; simpl. auto with *.
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

    return variants[:num_variants]
