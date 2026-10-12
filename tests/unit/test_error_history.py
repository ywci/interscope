# tests/unit/test_error_history.py
#
# Unit tests for the PERF error-history tracker.

import pytest
from isir.verification.perf.error_history import ErrorHistory


class TestErrorHistoryConstruction:
    def test_default_max_entries(self):
        history = ErrorHistory()
        assert history._max_entries == 200
        assert len(history) == 0

    def test_max_entries_must_be_at_least_one(self):
        with pytest.raises(ValueError, match="max_entries must be >= 1"):
            ErrorHistory(max_entries=0)
        with pytest.raises(ValueError, match="max_entries must be >= 1"):
            ErrorHistory(max_entries=-5)


class TestErrorSignature:
    def test_empty_message(self):
        assert ErrorHistory._signature("") == ""

    def test_first_meaningful_line(self):
        sig = ErrorHistory._signature("Error: Unable to unify foo with bar\nmore details")
        assert sig == "Error: Unable to unify foo with bar"

    def test_skips_warnings_and_deprecations(self):
        msg = (
            "Warning: this is a deprecation notice\n"
            "Deprecated notation Nat.mod_add\n"
            "Error: the real problem"
        )
        assert ErrorHistory._signature(msg) == "Error: the real problem"

    def test_skips_deprecated_substring_line(self):
        msg = "Nat.mod_add is deprecated, use Div0.mod_add\nError: boom"
        assert ErrorHistory._signature(msg) == "Error: boom"

    def test_fallback_when_all_lines_are_warnings(self):
        msg = "Warning: only warnings here\nDeprecated notation"
        assert ErrorHistory._signature(msg) == msg[:200]

    def test_truncates_signature_to_200_chars(self):
        long_line = "E" * 300
        sig = ErrorHistory._signature(long_line)
        assert sig == long_line[:200]
        assert len(sig) == 200


class TestScriptFingerprint:
    def test_empty_script(self):
        assert ErrorHistory._script_fingerprint("") == ""
        assert ErrorHistory._script_fingerprint("   \n  ") == ""

    def test_collapses_whitespace(self):
        fp = ErrorHistory._script_fingerprint("intros   x.\n   reflexivity.")
        assert fp == "intros x. reflexivity."

    def test_strips_block_comments(self):
        fp = ErrorHistory._script_fingerprint("intros. (* a comment *) reflexivity.")
        assert fp == "intros. reflexivity."

    def test_strips_line_comments(self):
        fp = ErrorHistory._script_fingerprint("intros; simpl")
        assert fp == "intros"

    def test_truncates_to_500_chars(self):
        long_script = "x" * 1000
        fp = ErrorHistory._script_fingerprint(long_script)
        assert len(fp) == 500
        assert fp == "x" * 500


class TestRecordAndQuery:
    def test_record_and_has_similar_failure(self):
        history = ErrorHistory()
        assert not history.has_similar_failure("Proof. intros. reflexivity. Qed.", "Error: boom")
        history.record_failure("Proof. intros. reflexivity. Qed.", "Error: boom")
        assert history.has_similar_failure("Proof. intros. reflexivity. Qed.", "Error: boom")

    def test_identical_pair_is_deduplicated(self):
        history = ErrorHistory()
        history.record_failure("script", "Error: boom")
        history.record_failure("script", "Error: boom")
        assert len(history) == 1

    def test_different_fingerprint_is_not_similar(self):
        history = ErrorHistory()
        history.record_failure("Proof. auto. Qed.", "Error: boom")
        assert not history.has_similar_failure("Proof. intros. reflexivity. Qed.", "Error: boom")

    def test_different_signature_is_not_similar(self):
        history = ErrorHistory()
        history.record_failure("Proof. auto. Qed.", "Error: boom")
        assert not history.has_similar_failure("Proof. auto. Qed.", "Error: something else")

    def test_max_entries_eviction_is_fifo(self):
        history = ErrorHistory(max_entries=2)
        history.record_failure("s1", "e1")
        history.record_failure("s2", "e2")
        history.record_failure("s3", "e3")
        assert len(history) == 2
        assert not history.has_similar_failure("s1", "e1")
        assert history.has_similar_failure("s2", "e2")
        assert history.has_similar_failure("s3", "e3")

    def test_get_repeated_signatures_ordering(self):
        history = ErrorHistory()
        for i in range(3):
            history.record_failure(f"beta-script-{i}", "beta error")
        for i in range(2):
            history.record_failure(f"alpha-script-{i}", "alpha error")
        history.record_failure("gamma-script", "gamma error")

        assert history.get_repeated_signatures() == ["beta error", "alpha error"]

    def test_get_repeated_signatures_min_count(self):
        history = ErrorHistory()
        for i in range(3):
            history.record_failure(f"beta-script-{i}", "beta error")
        for i in range(2):
            history.record_failure(f"alpha-script-{i}", "alpha error")

        assert history.get_repeated_signatures(min_count=3) == ["beta error"]
        assert history.get_repeated_signatures(min_count=4) == []

    def test_clear(self):
        history = ErrorHistory()
        history.record_failure("s1", "e1")
        history.clear()
        assert len(history) == 0
        assert not history.has_similar_failure("s1", "e1")

    def test_len_contains_and_repr(self):
        history = ErrorHistory(max_entries=5)
        history.record_failure("s1", "e1")
        key = (ErrorHistory._signature("e1"), ErrorHistory._script_fingerprint("s1"))
        assert len(history) == 1
        assert key in history
        assert ("not", "there") not in history
        assert repr(history) == "ErrorHistory(entries=1, max_entries=5)"
