# src/specir/verification/proof/acl2/template_gen.py
#
# Template‑based ACL2 proof variant generator.
# Produces a set of alternative defthm forms without an LLM,
# using pre‑defined hint patterns suitable for safety properties
# of typical hardware designs.  Intended as a fallback when no
# LLM is available or as a complement in PERF's beam search.

from typing import List, Optional, Dict, Any

try:
    from specir.verification.perf.perf_analyzer import ObligationAnalysis
except ImportError:
    ObligationAnalysis = None


def generate_acl2_proof_variants_template(
    llm_client: Any = None,
    theorem_name: str = "",
    theorem_statement: str = "",
    num_variants: int = 4,
    context: Optional[str] = None,
    hint_classes: Optional[List[str]] = None,
    assumptions: Optional[List[str]] = None,
    temperature: float = 0.4,
    max_tokens: int = 2048,
    analysis: Optional[ObligationAnalysis] = None,
) -> List[str]:
    """
    Return a list of ACL2 defthm forms generated from built‑in templates.

    The templates use standard hint patterns (induction, rewriting, linear
    arithmetic, etc.) and do **not** require an LLM.

    If *analysis* (an ``ObligationAnalysis``) is provided and certain
    structural conditions are met, specialised templates are emitted
    first, making the search more targeted.  After those, generic
    templates fill the remaining requested variants.

    Args:
        llm_client:       Ignored (provided for API compatibility).
        theorem_name:     Name of the theorem (used in each defthm).
        theorem_statement: ACL2 formula for the theorem.
        num_variants:     Number of distinct defthm forms to generate.
        context:          Ignored.
        hint_classes:     Ignored.
        assumptions:      Ignored.
        temperature:      Ignored.
        max_tokens:       Ignored.
        analysis:         Optional structural analysis result from
                          ``PERFAnalyzer``.  Used to adapt templates.

    Returns:
        List of complete defthm strings, one per variant.
    """
    variants: List[str] = []

    if analysis is not None:
        if analysis.num_step_constructors == 2 and analysis.step_constructor_names:
            names = analysis.step_constructor_names
            expand_hint = f':hints (("Goal" :expand ({" ".join(f"({n} st)" for n in names)})))'
            script = (
                f"(defthm {theorem_name}\n"
                f"  {theorem_statement}\n"
                f"  {expand_hint})"
            )
            variants.append(script)

            expand_induct_hint = (
                f':hints (("Goal" :induct t :expand ({" ".join(f"({n} st)" for n in names)})))'
            )
            script2 = (
                f"(defthm {theorem_name}\n"
                f"  {theorem_statement}\n"
                f"  {expand_induct_hint})"
            )
            variants.append(script2)

        if analysis.has_nested_ite and analysis.max_ite_depth >= 3:
            step_expand_hint = ':hints (("Goal" :expand ((step st inputs))))'
            script = (
                f"(defthm {theorem_name}\n"
                f"  {theorem_statement}\n"
                f"  {step_expand_hint})"
            )
            variants.append(script)

            step_expand_induct_hint = ':hints (("Goal" :induct (step st inputs) :expand ((step st inputs))))'
            script2 = (
                f"(defthm {theorem_name}\n"
                f"  {theorem_statement}\n"
                f"  {step_expand_induct_hint})"
            )
            variants.append(script2)

    hint_templates = [
        # Simple induction on the top‑level goal
        ':hints (("Goal" :induct t))',

        # Induction on a specific step function (if the context uses it)
        ':hints (("Goal" :induct (step st inputs)))',

        # Expand definitions and rewrite
        ':hints (("Goal" :do-not-induct t :expand ((full st) (empty st)) :in-theory (enable*)))',

        # Use linear arithmetic
        ':hints (("Goal" :do-not-induct t :use (:instance linear-lemma)))',

        # Combination: induction with rewriting
        ':hints (("Goal" :induct (step st inputs) :in-theory (enable*)))',

        # Case splitting on a critical condition
        ':hints (("Goal" :cases ((enqueue st) (not (enqueue st))) :in-theory (enable*)))',

        # Use a lemma about the invariant (fixed balanced parentheses)
        ':hints (("Goal" :use (:instance invariant-lemma) :in-theory (disable invariant-lemma)))',

        # No hints – let ACL2's heuristics try
        "",
    ]

    needed = num_variants - len(variants)
    if needed > 0:
        for i in range(needed):
            hint = hint_templates[i % len(hint_templates)]
            if hint:
                script = f"(defthm {theorem_name}\n  {theorem_statement}\n  {hint})"
            else:
                script = f"(defthm {theorem_name}\n  {theorem_statement})"
            # Add a distinguishing comment for repeated templates
            if i >= len(hint_templates):
                script = script.rstrip(")") + f"  ;; variant {len(variants)+1}\n)"
            variants.append(script)

    return variants[:num_variants]
