# tests/unit/test_structural_validator.py
#
# Unit tests for structural validation of Coq proof scripts in
# `isir.verification.proof.structural_validator`.  These tests exercise
# the deterministic checks (balanced delimiters, proof closure,
# deprecated notations, focus/bullet heuristics, and missing imports)
# without requiring a Coq installation.

import pytest
from isir.verification.proof.structural_validator import (
    validate_structure,
    DEPRECATED_NOTATIONS,
    COMMON_DEPENDENCIES,
)


class TestValidateStructure:
    def test_empty_script_returns_error(self):
        assert validate_structure("") == ["Empty proof script"]

    def test_none_script_treated_as_empty(self):
        assert validate_structure(None) == ["Empty proof script"]

    def test_whitespace_only_script_has_no_issues(self):
        assert validate_structure("   \n\t  ") == []

    def test_valid_script_has_no_issues(self):
        script = "Proof.\n  intros H.\n  auto.\nQed."
        assert validate_structure(script) == []

    def test_admitted_closes_proof(self):
        assert validate_structure("Proof. intros. Admitted.") == []

    def test_unbalanced_braces_missing_close(self):
        issues = validate_structure("Proof. { intros H. Qed.")
        assert any(
            "Unbalanced braces" in i and "missing 1 closing '}'" in i for i in issues
        )

    def test_unbalanced_braces_unexpected_close(self):
        issues = validate_structure("Proof. } intros. Qed.")
        assert any(
            "Unbalanced braces" in i and "unexpected '}'" in i for i in issues
        )

    def test_unbalanced_parentheses(self):
        issues = validate_structure("Proof. intros (H. Qed.")
        assert any("Unbalanced parentheses" in i for i in issues)

    def test_unbalanced_square_brackets(self):
        issues = validate_structure("Proof. intros [H. Qed.")
        assert any("Unbalanced square brackets" in i for i in issues)

    def test_unclosed_proof(self):
        issues = validate_structure("Proof. intros H. auto.")
        assert any("Unclosed proof block(s)" in i for i in issues)

    def test_qed_without_proof(self):
        issues = validate_structure("intros H. Qed.")
        assert any("without open 'Proof.'" in i for i in issues)

    def test_multiple_unclosed_proofs_reported(self):
        issues = validate_structure("Proof. intros.\nProof. auto.")
        assert any("Unclosed proof block(s): 2" in i for i in issues)

    def test_deprecated_notation_flagged(self):
        issues = validate_structure("Proof. rewrite Nat.mod_add. Qed.")
        assert any("[HARD ERROR] Deprecated notation 'Nat.mod_add'" in i for i in issues)

    def test_multiple_deprecated_notations(self):
        script = "Proof. rewrite Nat.mod_add. rewrite Nat.div_same. Qed."
        issues = validate_structure(script)
        assert any("Nat.mod_add" in i for i in issues)
        assert any("Nat.div_same" in i for i in issues)

    def test_modern_div0_not_flagged(self):
        assert validate_structure("Proof. rewrite Div0.mod_add. Qed.") == []

    def test_substring_of_deprecated_not_flagged(self):
        assert validate_structure("Proof. rewrite Nat.mod_add_extra. Qed.") == []

    def test_boolean_discriminate_flagged(self):
        script = "Hop : (op_reg s =? 0) = true.\ndiscriminate Hop."
        issues = validate_structure(script)
        assert any("discriminate Hop" in i and "boolean equality" in i for i in issues)

    def test_discriminate_on_constructor_not_flagged(self):
        script = "Hn : S n = 0.\ndiscriminate Hn."
        assert validate_structure(script) == []

    def test_orphan_bullet_flagged(self):
        script = "Proof.\n-\nintros.\nQed."
        issues = validate_structure(script)
        assert any("orphan bullet" in i for i in issues)

    def test_mixed_bullets_braces_flagged(self):
        script = "Proof.\n- intros H.\n{ auto. }\nQed."
        issues = validate_structure(script)
        assert any("Mixed bullet and brace usage" in i for i in issues)

    def test_bullet_before_closing_brace_flagged(self):
        script = "Proof.\n- }\nQed."
        issues = validate_structure(script)
        assert any("Bullet followed by closing brace" in i for i in issues)

    def test_consecutive_same_bullets_flagged(self):
        script = "Proof.\n- intros.\n- auto.\nQed."
        issues = validate_structure(script)
        assert any("consecutive bullets of same type" in i for i in issues)

    def test_missing_import_lia(self):
        issues = validate_structure(
            "Proof. lia. Qed.", context="Require Import Bool."
        )
        assert any("Missing import 'Require Import Lia.'" in i for i in issues)

    def test_missing_import_nat_eqb_eq(self):
        issues = validate_structure(
            "Proof. rewrite Nat.eqb_eq. Qed.", context="Require Import Lia."
        )
        assert any(
            "Missing import 'Require Import Arith.PeanoNat.'" in i for i in issues
        )

    def test_missing_import_satisfied(self):
        issues = validate_structure("Proof. lia. Qed.", context="Require Import Lia.")
        assert issues == []

    def test_no_context_skips_import_check(self):
        assert validate_structure("Proof. lia. Qed.") == []

    def test_comment_with_unbalanced_brace_ignored(self):
        script = "Proof.\n  intros.\n  (* unbalanced { in a comment *)\n  auto.\nQed."
        assert validate_structure(script) == []

    def test_string_with_paren_ignored(self):
        script = 'Definition s := ")".'
        assert validate_structure(script) == []


def test_deprecated_notations_map_has_expected_keys():
    assert "Nat.mod_add" in DEPRECATED_NOTATIONS
    assert DEPRECATED_NOTATIONS["Nat.mod_add"] == "Div0.mod_add"
    assert "Nat.div_same" in DEPRECATED_NOTATIONS


def test_common_dependencies_has_lia():
    assert "lia" in COMMON_DEPENDENCIES
    assert "Require Import Lia." in COMMON_DEPENDENCIES["lia"]
    assert "Nat.eqb_eq" in COMMON_DEPENDENCIES
