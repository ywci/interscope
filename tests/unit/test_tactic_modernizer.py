# tests/unit/test_tactic_modernizer.py
#
# Unit tests for Coq tactic modernisation in
# `isir.verification.proof.tactic_modernizer`.  These tests feed sample
# scripts and assert that deprecated tactics/imports are replaced and
# that boolean-equality `discriminate` commands are corrected.

import pytest
from isir.verification.proof.tactic_modernizer import (
    modernize_tactics,
)


class TestModernizeTactics:
    def test_empty_script_unchanged(self):
        assert modernize_tactics("") == ""

    def test_omega_replaced_with_lia(self):
        assert modernize_tactics("omega.") == "lia."

    def test_romega_replaced_with_lia(self):
        assert modernize_tactics("romega.") == "lia."

    def test_omega_in_compound_tactic(self):
        assert modernize_tactics("intros; omega.") == "intros; lia."

    def test_omega_not_replaced_as_substring(self):
        script = "omega_lemma.\nmyomega.\nomega'."
        # All three are part of a larger identifier and must be preserved.
        assert modernize_tactics(script) == script

    def test_require_import_omega(self):
        assert modernize_tactics("Require Import Omega.") == "Require Import Lia."

    def test_require_export_omega(self):
        assert modernize_tactics("Require Export Omega.") == "Require Export Lia."

    def test_nat_mod_left_unchanged_by_default(self):
        script = "rewrite Nat.mod_add."
        assert modernize_tactics(script) == script

    def test_nat_mod_replaced_when_enabled(self):
        assert (
            modernize_tactics("rewrite Nat.mod_add.", replace_nat_mod_add=True)
            == "rewrite Div0.mod_add."
        )

    def test_nat_add_mod_replaced_when_enabled(self):
        assert (
            modernize_tactics("rewrite Nat.add_mod.", replace_nat_mod_add=True)
            == "rewrite Div0.add_mod."
        )

    def test_nat_div_replaced_when_enabled(self):
        assert (
            modernize_tactics("apply Nat.div_same.", replace_nat_mod_add=True)
            == "apply Div0.div_same."
        )

    def test_nat_mod_word_boundary_when_enabled(self):
        assert (
            modernize_tactics("apply Nat.mod_add_extra.", replace_nat_mod_add=True)
            == "apply Nat.mod_add_extra."
        )

    def test_boolean_discriminate_modernized(self):
        script = "Hop : (op_reg s =? 0) = true.\ndiscriminate Hop."
        out = modernize_tactics(script)
        assert "inversion Hop." in out
        assert "discriminate Hop." not in out

    def test_boolean_discriminate_nat_eqb_modernized(self):
        script = "Hop : Nat.eqb a b = true.\ndiscriminate Hop."
        out = modernize_tactics(script)
        assert "inversion Hop." in out
        assert "discriminate Hop." not in out

    def test_non_boolean_discriminate_unchanged(self):
        script = "Hn : S n = 0.\ndiscriminate Hn."
        assert modernize_tactics(script) == script

    def test_unchanged_script_is_identical(self):
        script = "Proof. intros. auto. Qed."
        assert modernize_tactics(script) == script

    def test_none_script_unchanged(self):
        assert modernize_tactics(None) is None
