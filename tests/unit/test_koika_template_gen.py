# tests/unit/test_koika_template_gen.py
#
# Unit tests for the template-based Coq proof variant generator in
# `isir.verification.proof.koika.template_gen`.  These tests assert that
# the generator returns the requested number of well-formed `Proof. …
# Qed.` variants, emits specialised templates when analysis is supplied,
# and never returns deprecated notations.

import pytest
from isir.verification.proof.koika.template_gen import (
    generate_coq_proof_variants_template,
)
from isir.verification.proof.structural_validator import validate_structure
from isir.verification.perf.perf_analyzer import ObligationAnalysis


class TestGenerateVariants:
    def test_default_returns_requested_count(self):
        variants = generate_coq_proof_variants_template("foo_correct", "Theorem foo : True.")
        assert len(variants) == 4

    def test_custom_num_variants(self):
        variants = generate_coq_proof_variants_template(
            "foo", "Theorem foo : True.", num_variants=7
        )
        assert len(variants) == 7

    def test_zero_variants_returns_empty(self):
        assert (
            generate_coq_proof_variants_template("foo", "T", num_variants=0) == []
        )

    def test_all_variants_have_proof_and_qed(self):
        variants = generate_coq_proof_variants_template(
            "foo", "Theorem foo : True.", num_variants=8
        )
        for v in variants:
            assert v.strip().startswith("Proof.")
            assert "Qed." in v

    def test_all_variants_structurally_valid(self):
        variants = generate_coq_proof_variants_template(
            "foo", "Theorem foo : True.", num_variants=8
        )
        for v in variants:
            assert validate_structure(v) == [], f"variant failed validation:\n{v}"

    def test_no_deprecated_notations(self):
        variants = generate_coq_proof_variants_template(
            "foo", "Theorem foo : True.", num_variants=8
        )
        for v in variants:
            assert "Nat.mod_add" not in v
            assert "Nat.div_same" not in v

    def test_variants_are_distinct(self):
        variants = generate_coq_proof_variants_template(
            "foo", "Theorem foo : True.", num_variants=4
        )
        assert len(set(variants)) == 4

    def test_variants_are_strings(self):
        variants = generate_coq_proof_variants_template("foo", "T", num_variants=4)
        assert all(isinstance(v, str) for v in variants)


class TestWithAnalysis:
    def test_two_ctor_analysis_emits_specialized_first(self):
        a = ObligationAnalysis(
            num_step_constructors=2,
            step_constructor_names=["step_load_inputs", "step_execute"],
        )
        variants = generate_coq_proof_variants_template("foo", "T", num_variants=4, analysis=a)
        assert "discriminate Hvalid" in variants[0]

    def test_overflow_analysis_adds_lia(self):
        a = ObligationAnalysis(
            num_step_constructors=2,
            step_constructor_names=["step_load_inputs", "step_execute"],
        )
        variants = generate_coq_proof_variants_template(
            "overflow_x", "T", num_variants=4, analysis=a
        )
        assert any("lia" in v for v in variants)

    def test_nested_ite_deep_uses_destruct_chain(self):
        a = ObligationAnalysis(num_step_constructors=1, has_nested_ite=True, max_ite_depth=3)
        variants = generate_coq_proof_variants_template("foo", "T", num_variants=4, analysis=a)
        assert any("Hop0" in v for v in variants)

    def test_nested_ite_shallow_uses_match_goal(self):
        a = ObligationAnalysis(num_step_constructors=1, has_nested_ite=True, max_ite_depth=2)
        variants = generate_coq_proof_variants_template("foo", "T", num_variants=4, analysis=a)
        assert any("match goal" in v for v in variants)

    def test_analysis_variants_structurally_valid(self):
        a = ObligationAnalysis(
            num_step_constructors=2,
            step_constructor_names=["step_load_inputs", "step_execute"],
        )
        variants = generate_coq_proof_variants_template(
            "overflow_x", "T", num_variants=6, analysis=a
        )
        for v in variants:
            assert validate_structure(v) == [], f"variant failed validation:\n{v}"
