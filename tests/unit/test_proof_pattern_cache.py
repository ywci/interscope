# tests/unit/test_proof_pattern_cache.py
#
# Unit tests for the persistent proof pattern cache in
# `isir.verification.proof.proof_pattern_cache`.  Tests use `tmp_path`
# for the JSON cache file and cover store/get, persistence across
# instances, missing/corrupt cache handling, and reusable-tactic
# extraction.

import json
import pytest
from isir.verification.proof.proof_pattern_cache import (
    ProofPatternCache,
    _common_prefix_len,
)


@pytest.fixture
def cache_path(tmp_path):
    return tmp_path / "patterns.json"


class TestStoreAndGet:
    def test_store_and_get_roundtrip(self, cache_path):
        c = ProofPatternCache(cache_path)
        c.store_successful_proof("alu", "zero_flag_correct", "Proof. auto. Qed.")
        assert c.get_successful_proof("alu", "zero_flag_correct") == "Proof. auto. Qed."

    def test_get_missing_property_returns_none(self, cache_path):
        c = ProofPatternCache(cache_path)
        assert c.get_successful_proof("alu", "unknown") is None

    def test_get_missing_design_returns_none(self, cache_path):
        c = ProofPatternCache(cache_path)
        c.store_successful_proof("alu", "p", "Proof.")
        assert c.get_successful_proof("other", "p") is None

    def test_len_counts_proofs(self, cache_path):
        c = ProofPatternCache(cache_path)
        assert len(c) == 0
        c.store_successful_proof("alu", "a", "Proof. a.")
        c.store_successful_proof("alu", "b", "Proof. b.")
        c.store_successful_proof("mem", "a", "Proof. c.")
        assert len(c) == 3

    def test_empty_fields_are_noops(self, cache_path):
        c = ProofPatternCache(cache_path)
        c.store_successful_proof("", "p", "Proof.")
        c.store_successful_proof("d", "", "Proof.")
        c.store_successful_proof("d", "p", "")
        assert len(c) == 0

    def test_storing_duplicate_is_idempotent(self, cache_path):
        c = ProofPatternCache(cache_path)
        c.store_successful_proof("alu", "p", "Proof. auto. Qed.")
        c.store_successful_proof("alu", "p", "Proof. auto. Qed.")
        assert len(c) == 1

    def test_overwrite_replaces_previous_script(self, cache_path):
        c = ProofPatternCache(cache_path)
        c.store_successful_proof("alu", "p", "Proof. auto. Qed.")
        c.store_successful_proof("alu", "p", "Proof. lia. Qed.")
        assert c.get_successful_proof("alu", "p") == "Proof. lia. Qed."
        assert len(c) == 1


class TestPersistence:
    def test_cache_persists_across_instances(self, cache_path):
        c1 = ProofPatternCache(cache_path)
        c1.store_successful_proof("alu", "p", "Proof. auto. Qed.")

        c2 = ProofPatternCache(cache_path)
        assert c2.get_successful_proof("alu", "p") == "Proof. auto. Qed."

    def test_cache_file_created_on_save(self, cache_path):
        c = ProofPatternCache(cache_path)
        assert not cache_path.exists()
        c.store_successful_proof("alu", "p", "Proof.")
        assert cache_path.exists()

    def test_missing_cache_starts_empty(self, cache_path):
        c = ProofPatternCache(cache_path)
        assert len(c) == 0
        assert not cache_path.exists()

    def test_parent_directory_is_created(self, tmp_path):
        deep_path = tmp_path / "nested" / "dir" / "patterns.json"
        c = ProofPatternCache(deep_path)
        c.store_successful_proof("alu", "p", "Proof.")
        assert deep_path.exists()


class TestClear:
    def test_clear_removes_entries_and_file(self, cache_path):
        c = ProofPatternCache(cache_path)
        c.store_successful_proof("alu", "p", "Proof.")
        assert cache_path.exists()
        c.clear()
        assert len(c) == 0
        assert not cache_path.exists()

    def test_clear_on_empty_cache_is_safe(self, cache_path):
        c = ProofPatternCache(cache_path)
        c.clear()
        assert len(c) == 0


class TestCorruptCache:
    def test_invalid_json_starts_empty(self, cache_path):
        cache_path.write_text("{not valid json", encoding="utf-8")
        c = ProofPatternCache(cache_path)
        assert len(c) == 0

    def test_non_dict_json_starts_empty(self, cache_path):
        cache_path.write_text('["a", "b"]', encoding="utf-8")
        c = ProofPatternCache(cache_path)
        assert len(c) == 0

    def test_dict_with_non_string_values_coerced(self, cache_path):
        cache_path.write_text(json.dumps({"alu": {"p": 123}}), encoding="utf-8")
        c = ProofPatternCache(cache_path)
        # Non-string proof values are dropped during coercion.
        assert c.get_successful_proof("alu", "p") is None


class TestReusablePatterns:
    def test_extract_reusable_tactics(self):
        proof = (
            "Proof.\n"
            "  induction Hreach as [| s' s'' inputs' Hreach' IH Hstep].\n"
            "  inversion Hstep; subst; clear Hstep; simpl.\n"
            "  destruct (op_reg s' =? 0) eqn:Hop0.\n"
            "  simpl.\n"
            "  auto.\n"
            "Qed."
        )
        tactics = ProofPatternCache.extract_reusable_tactics(proof)
        assert "induction Hreach as [| s' s'' inputs' Hreach' IH Hstep]." in tactics
        assert "inversion Hstep; subst; clear Hstep; simpl." in tactics
        assert "destruct (op_reg s' =? 0) eqn:Hop0." in tactics
        assert "simpl." in tactics
        assert "auto." not in tactics  # not a reusable pattern

    def test_extract_reusable_tactics_dedupes(self):
        proof = "simpl.\nsimpl.\nsimpl."
        assert ProofPatternCache.extract_reusable_tactics(proof) == ["simpl."]

    def test_extract_empty_proof(self):
        assert ProofPatternCache.extract_reusable_tactics("") == []
        assert ProofPatternCache.extract_reusable_tactics(None) == []

    def test_get_reusable_patterns_exact_match(self, cache_path):
        c = ProofPatternCache(cache_path)
        c.store_successful_proof(
            "alu", "overflow_implies", "Proof.\n  intros H.\n  simpl.\nQed."
        )
        pats = c.get_reusable_patterns("overflow_implies", design_name="alu")
        assert "intros H." in pats
        assert "simpl." in pats

    def test_get_reusable_patterns_similar_prefix(self, cache_path):
        c = ProofPatternCache(cache_path)
        c.store_successful_proof("alu", "zero_flag_correct", "Proof.\n  simpl.\nQed.")
        pats = c.get_reusable_patterns("zero_flag_other", design_name="alu")
        assert "simpl." in pats

    def test_get_reusable_patterns_design_filter(self, cache_path):
        c = ProofPatternCache(cache_path)
        c.store_successful_proof("alu", "p", "Proof.\n  simpl.\nQed.")
        c.store_successful_proof("mem", "p", "Proof.\n  intros H.\nQed.")
        assert "simpl." in c.get_reusable_patterns("p", design_name="alu")
        assert "intros H." in c.get_reusable_patterns("p", design_name="mem")

    def test_get_reusable_patterns_none_found(self, cache_path):
        c = ProofPatternCache(cache_path)
        assert c.get_reusable_patterns("unknown") == []

    def test_get_reusable_patterns_no_design_searches_all(self, cache_path):
        c = ProofPatternCache(cache_path)
        c.store_successful_proof("mem", "p", "Proof.\n  simpl.\nQed.")
        assert "simpl." in c.get_reusable_patterns("p")


def test_common_prefix_len():
    assert _common_prefix_len("abc", "abd") == 2
    assert _common_prefix_len("abc", "xyz") == 0
    assert _common_prefix_len("", "abc") == 0
    assert _common_prefix_len("abc", "") == 0
    assert _common_prefix_len("abc", "abc") == 3
