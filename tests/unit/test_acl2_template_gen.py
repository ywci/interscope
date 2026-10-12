# tests/unit/test_acl2_template_gen.py
#
# Unit tests for the template-based (LLM-free) ACL2 proof variant generator.

from isir.verification.perf.perf_analyzer import ObligationAnalysis
from isir.verification.proof.acl2.template_gen import (
    generate_acl2_proof_variants_template,
)


def test_generates_requested_number_of_variants():
    variants = generate_acl2_proof_variants_template(
        theorem_name="no-overflow",
        theorem_statement="(implies (full st) (not (enqueue st)))",
        num_variants=4,
    )
    assert len(variants) == 4
    assert all(v.startswith("(defthm no-overflow") for v in variants)
    assert all("(implies (full st) (not (enqueue st)))" in v for v in variants)


def test_first_template_is_simple_induction():
    variants = generate_acl2_proof_variants_template(
        theorem_name="t", theorem_statement="stmt", num_variants=1
    )
    assert variants[0] == (
        "(defthm t\n  stmt\n  :hints ((\"Goal\" :induct t)))"
    )


def test_second_template_is_step_induction():
    variants = generate_acl2_proof_variants_template(
        theorem_name="t", theorem_statement="stmt", num_variants=2
    )
    assert ":induct (step st inputs)" in variants[1]


def test_zero_variants_returns_empty_list():
    assert generate_acl2_proof_variants_template(
        theorem_name="t", theorem_statement="stmt", num_variants=0
    ) == []


def test_more_variants_than_templates_repeats_with_comment():
    variants = generate_acl2_proof_variants_template(
        theorem_name="t", theorem_statement="stmt", num_variants=10
    )
    assert len(variants) == 10
    assert any(";; variant" in v for v in variants)


def test_analysis_with_two_step_constructors_emits_expand_hints_first():
    analysis = ObligationAnalysis(
        num_step_constructors=2,
        step_constructor_names=["step_a", "step_b"],
    )
    variants = generate_acl2_proof_variants_template(
        theorem_name="t", theorem_statement="stmt", num_variants=2, analysis=analysis
    )
    assert "(step_a st) (step_b st)" in variants[0]
    assert ":induct t :expand" in variants[1]


def test_analysis_with_nested_ite_emits_step_expand_hints():
    analysis = ObligationAnalysis(has_nested_ite=True, max_ite_depth=3)
    variants = generate_acl2_proof_variants_template(
        theorem_name="t", theorem_statement="stmt", num_variants=2, analysis=analysis
    )
    assert ':hints (("Goal" :expand ((step st inputs))))' in variants[0]
    assert ":induct (step st inputs) :expand" in variants[1]


def test_analysis_that_does_not_match_conditions_uses_generic_templates():
    analysis = ObligationAnalysis(num_step_constructors=2, step_constructor_names=[])
    variants = generate_acl2_proof_variants_template(
        theorem_name="t", theorem_statement="stmt", num_variants=1, analysis=analysis
    )
    assert variants[0] == "(defthm t\n  stmt\n  :hints ((\"Goal\" :induct t)))"


def test_llm_client_and_other_args_are_ignored():
    variants = generate_acl2_proof_variants_template(
        llm_client=object(),
        theorem_name="t",
        theorem_statement="stmt",
        num_variants=1,
        context="ignored",
        hint_classes=["ignored"],
        assumptions=["ignored"],
        temperature=99.0,
        max_tokens=1,
    )
    assert len(variants) == 1
    assert variants[0].startswith("(defthm t")
