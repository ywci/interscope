# tests/unit/test_domain_tactics.py
#
# Unit tests for domain-specific tactic/lemma helpers in
# `isir.verification.proof.domain_tactics`.  These tests exercise the
# property-name dispatch for Coq tactic patterns, ACL2 hints, lemma
# hints, and the bad-`discriminate` substitution, without any external
# tools.

import pytest
from isir.verification.proof.domain_tactics import (
    get_koika_tactic_pattern,
    get_acl2_hints,
    get_lemma_hints,
    apply_domain_tactics,
    KOIKA_OVERFLOW_TEMPLATE,
    KOIKA_COMMON_LEMMAS,
    ACL2_COMMON_LEMMAS,
    ACL2_OVERFLOW_HINTS,
    ACL2_INDUCT_HINT,
    ACL2_INDUCT_STEP_HINT,
)


class _FakeAnalysis:
    def __init__(self, num_step_constructors=0):
        self.num_step_constructors = num_step_constructors


class TestGetKoikaTacticPattern:
    def test_overflow_property_returns_full_template(self):
        pat = get_koika_tactic_pattern("overflow_implies_result_neq_sum")
        assert pat is not None
        assert pat.startswith("Proof.")
        assert "Qed." in pat

    def test_neq_property_returns_template(self):
        assert get_koika_tactic_pattern("result_neq_something") is not None

    def test_zero_flag_property_returns_none_when_template_invalid(self):
        pat = get_koika_tactic_pattern("zero_flag_correct")
        assert pat is None

    def test_unknown_property_returns_none(self):
        assert get_koika_tactic_pattern("totally_unknown") is None

    def test_two_constructor_analysis_returns_overflow_template(self):
        pat = get_koika_tactic_pattern("some_property", analysis=_FakeAnalysis(2))
        assert pat == KOIKA_OVERFLOW_TEMPLATE

    def test_non_two_constructor_analysis_returns_none(self):
        assert get_koika_tactic_pattern("some_property", analysis=_FakeAnalysis(1)) is None

    def test_property_name_case_insensitive(self):
        assert get_koika_tactic_pattern("OVERFLOW_PROPERTY") is not None


class TestGetAcl2Hints:
    def test_overflow_returns_overflow_hints(self):
        assert get_acl2_hints("overflow_x") == ACL2_OVERFLOW_HINTS

    def test_neq_returns_overflow_hints(self):
        assert get_acl2_hints("something_neq_something") == ACL2_OVERFLOW_HINTS

    def test_zero_flag_returns_step_hint(self):
        assert get_acl2_hints("zero_flag_correct") == ACL2_INDUCT_STEP_HINT

    def test_valid_returns_step_hint(self):
        assert get_acl2_hints("valid_property") == ACL2_INDUCT_STEP_HINT

    def test_default_returns_induct_hint(self):
        assert get_acl2_hints("random") == ACL2_INDUCT_HINT

    def test_overflow_hints_are_non_empty(self):
        hints = get_acl2_hints("overflow_x")
        assert len(hints) == 2
        assert all(isinstance(h, str) and h for h in hints)


class TestGetLemmaHints:
    def test_koika_base_lemmas(self):
        assert get_lemma_hints("koika", "something") == KOIKA_COMMON_LEMMAS

    def test_koika_overflow_extends_lemmas(self):
        lemmas = get_lemma_hints("koika", "overflow_x")
        assert lemmas[: len(KOIKA_COMMON_LEMMAS)] == KOIKA_COMMON_LEMMAS
        assert "Nat.add_comm" in lemmas
        assert "Nat.add_assoc" in lemmas
        assert "Nat.sub_0_r" in lemmas

    def test_acl2_base_lemmas(self):
        assert get_lemma_hints("acl2", "something") == ACL2_COMMON_LEMMAS

    def test_acl2_overflow_extends_lemmas(self):
        lemmas = get_lemma_hints("acl2", "overflow_x")
        assert lemmas[: len(ACL2_COMMON_LEMMAS)] == ACL2_COMMON_LEMMAS
        assert len(lemmas) == len(ACL2_COMMON_LEMMAS) + 1

    def test_unknown_backend_returns_empty(self):
        assert get_lemma_hints("lean", "overflow_x") == []

    def test_backend_case_insensitive(self):
        assert get_lemma_hints("KOIKA", "overflow_x") == get_lemma_hints(
            "koika", "overflow_x"
        )

    def test_returns_new_list_each_call(self):
        a = get_lemma_hints("koika", "overflow_x")
        b = get_lemma_hints("koika", "overflow_x")
        assert a == b
        a.append("mutated")
        assert "mutated" not in get_lemma_hints("koika", "overflow_x")


class TestApplyDomainTactics:
    def test_replaces_bad_discriminate_hop(self):
        script = "Hop : (op_reg s =? 0) = true.\ndiscriminate Hop.\nrest."
        out = apply_domain_tactics(script, "overflow_x", "koika")
        assert "simpl in Hop. inversion Hop." in out
        assert "discriminate Hop." not in out

    def test_requires_bool_eq_context(self):
        script = "discriminate Hop."
        assert apply_domain_tactics(script, "overflow_x", "koika") == script

    def test_acl2_backend_unchanged(self):
        script = "Hop : (op_reg s =? 0) = true.\ndiscriminate Hop."
        assert apply_domain_tactics(script, "overflow_x", "acl2") == script

    def test_koika_no_bad_pattern_unchanged(self):
        script = "Proof. auto. Qed."
        assert apply_domain_tactics(script, "overflow_x", "koika") == script
