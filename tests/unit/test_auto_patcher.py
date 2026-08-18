# tests/unit/test_auto_patcher.py
#
# Unit tests for the deterministic Coq proof auto‑patcher.

import pytest
from specir.verification.proof.koika.auto_patcher import (
    patch_deprecated_notations,
    patch_discriminate_on_bool,
    patch_bullets_to_braces,
    auto_patch,
)


def test_patch_deprecated_notations_replaces_nat_mod_add():
    script = "rewrite <- (Nat.mod_add x 1 4)."
    patched = patch_deprecated_notations(script)
    assert patched == "rewrite <- (Div0.mod_add x 1 4)."


def test_patch_deprecated_notations_replaces_multiple():
    script = "Nat.mod_add x y = Nat.mod_mul x y z"
    patched = patch_deprecated_notations(script)
    assert patched == "Div0.mod_add x y = Div0.mod_mul x y z"


def test_patch_deprecated_notations_does_not_touch_unrelated_words():
    script = "x = Nat.mod_add_extra"
    patched = patch_deprecated_notations(script)
    assert patched == "x = Nat.mod_add_extra"


def test_patch_deprecated_notations_handles_word_boundaries():
    script = "Nat.mod_add x = Nat.mod_add"
    patched = patch_deprecated_notations(script)
    assert patched == "Div0.mod_add x = Div0.mod_add"


def test_patch_discriminate_on_bool_with_error_message():
    script = """Proof.
  intros H.
  discriminate Hop.
Qed."""
    error_msg = 'File "test.v", line 3, characters 2-17:\nError: Not a discriminable equality.'
    patched = patch_discriminate_on_bool(script, error_msg)
    assert "discriminate Hop." not in patched
    assert "inversion Hop." in patched


def test_patch_discriminate_on_bool_with_boolean_hypothesis():
    script = """Proof.
  intros H.
  (* Hop : (op_reg s =? 0) = true *)
  discriminate Hop.
Qed."""
    patched = patch_discriminate_on_bool(script)
    assert "discriminate Hop." not in patched
    assert "inversion Hop." in patched


def test_patch_discriminate_on_bool_does_not_touch_valid_discriminate():
    script = """Proof.
  intros H.
  discriminate Hvalid.
Qed."""
    patched = patch_discriminate_on_bool(script)
    assert "discriminate Hvalid." in patched
    assert "inversion Hvalid." not in patched


def test_patch_discriminate_on_bool_handles_multiple():
    script = """Proof.
  intros.
  discriminate H1.
  (* H2 : (op_reg s =? 1) = true *)
  discriminate H2.
  discriminate H3.
Qed."""
    patched = patch_discriminate_on_bool(script)
    assert "discriminate H1." in patched
    assert "discriminate H2." not in patched
    assert "inversion H2." in patched
    assert "discriminate H3." in patched


def test_patch_bullets_to_braces_removes_orphan_bullets():
    script = """Proof.
  intros.
  +
  auto.
  +
  lia.
Qed."""
    patched = patch_bullets_to_braces(script)
    # Orphan bullet lines are replaced with harmless comments.
    assert "(* orphan bullet removed by auto‑patcher *)" in patched
    assert patched.count("(* orphan bullet removed by auto‑patcher *)") == 2
    # No braces are introduced.
    assert "{" not in patched
    assert "}" not in patched
    # Non‑bullet lines remain.
    assert "auto." in patched
    assert "lia." in patched


def test_patch_bullets_to_braces_does_not_alter_bullets_with_content():
    script = """Proof.
  intros.
  + auto.
  + (* first *) simpl; auto.
  + (* second *) reflexivity.
Qed."""
    patched = patch_bullets_to_braces(script)
    # The script is unchanged because these bullets have content.
    assert patched == script


def test_patch_bullets_to_braces_no_bullets():
    script = """Proof.
  intros.
  simpl.
Qed."""
    patched = patch_bullets_to_braces(script)
    assert patched == script


def test_auto_patch_applies_all_patches():
    script = """Proof.
  intros s inputs Hreach.
  induction Hreach as [| s' s'' inputs' Hreach' IH Hstep].
  - simpl. intros Hcond. destruct Hcond as [Hvalid [Hop Hoverflow]].
    discriminate Hvalid.
  - inversion Hstep; subst; clear Hstep; simpl.
    + intros Hcond. destruct Hcond as [Hvalid [Hop Hoverflow]].
      simpl in Hop.
      rewrite <- (Nat.mod_add (op_reg s') 1 4).
      discriminate Hop.
Qed."""
    error_msg = 'File "test.v", line 10, characters 8-16:\nError: Not a discriminable equality.'

    patched = auto_patch(script, error_msg)

    # Deprecated notation fixed
    assert "Nat.mod_add" not in patched
    assert "Div0.mod_add" in patched

    # discriminate on boolean equality fixed
    assert "discriminate Hop." not in patched
    assert "inversion Hop." in patched

    # Bullets with content are NOT converted (the error is not a focus error)
    assert "+ intros Hcond." in patched
    assert "- simpl. intros Hcond." in patched


def test_auto_patch_with_focus_error_removes_orphan_bullets_only():
    script = """Proof.
  intros.
  +
  auto.
  +
  lia.
Qed."""
    error_msg = 'File "test.v", line 3:\nError: [Focus] Wrong bullet +.'
    patched = auto_patch(script, error_msg)

    # Orphan bullets removed
    assert "(* orphan bullet removed by auto‑patcher *)" in patched
    assert "+ auto." not in patched   # the bullet alone is removed
    assert "+ lia." not in patched
    assert "auto." in patched
    assert "lia." in patched
    # No braces introduced
    assert "{" not in patched
    assert "}" not in patched


def test_auto_patch_idempotent():
    script = "rewrite <- (Nat.mod_add x 1 4)."
    patched_once = auto_patch(script)
    patched_twice = auto_patch(patched_once)
    assert patched_once == patched_twice


def test_auto_patch_does_not_alter_clean_script():
    clean_script = """Proof.
  intros s inputs Hreach.
  induction Hreach as [| s' s'' inputs' Hreach' IH Hstep].
  - simpl. auto.
  - inversion Hstep; subst; simpl; auto.
Qed."""
    patched = auto_patch(clean_script)
    assert patched == clean_script
