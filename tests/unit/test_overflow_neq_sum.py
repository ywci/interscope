# tests/unit/test_overflow_neq_sum.py
#
# Unit tests for the corrected built‑in proof of
# `overflow_implies_result_neq_sum`.
#
# These tests verify that the built‑in proof script used by KoikaProver
# for the ALU overflow property no longer contains the anti‑patterns that
# caused failures in earlier runs.  They do NOT require a Coq installation
# or an LLM; they inspect the proof string directly.

import pytest
from unittest.mock import patch

from specir.verification.proof.koika.prover import KoikaProver
from specir.verification.proof.koika.auto_patcher import (
    auto_patch,
)


@pytest.fixture
def prover():
    """Create a KoikaProver with a minimal dummy config (no LLM, no rocq)."""
    config = {
        "llm": {"provider": "ollama", "model": "dummy"},
        "provers": {
            "koika": {
                "prove": {
                    "use_rocq_mcp": False,
                    "rocq_mcp_path": "rocq-mcp",
                    "proof_timeout": 60,
                    "max_consecutive_failures": 3,
                    "max_steps": 10,
                    "pre_simplify": True,
                    "invariant_mining": False,
                    "skeleton_reflection": False,
                    "skeleton_step_tactics": [],
                }
            }
        },
        "proof": {"max_repair_attempts": 1},
    }
    with patch("specir.verification.proof.koika.prover.get_llm_client_from_config") as mock_llm:
        mock_llm.return_value = object()
        return KoikaProver(config=config)


def test_overflow_proof_has_no_bad_patterns(prover):
    """The built‑in overflow proof must not contain the known bad patterns."""
    proof = prover._overflow_sum_proof()

    # 1. No deprecated Nat.mod_add
    assert "Nat.mod_add" not in proof

    # 2. No `discriminate Hop` on boolean equality
    assert "discriminate Hop." not in proof

    # 3. Proper handling of boolean equality is present
    assert ("inversion Hop" in proof) or ("rewrite Nat.eqb_eq in Hop" in proof)

    # 4. The legitimate base-case `discriminate Hvalid` remains
    assert "discriminate Hvalid" in proof

    # 5. No orphan bullets (lines that are only a bullet)
    for line in proof.splitlines():
        stripped = line.strip()
        assert stripped not in ("-", "+", "*"), f"Orphan bullet found: {stripped}"

    # 6. Explicit braces are used for the inner step‑case sub‑goals
    assert "{" in proof and "}" in proof

    # 7. Proof is well‑formed
    assert proof.strip().startswith("Proof.")
    assert "Qed." in proof


def test_overflow_proof_is_idempotent_under_auto_patch(prover):
    """The built‑in proof should not be changed by auto_patch."""
    proof = prover._overflow_sum_proof()
    patched = auto_patch(proof)
    assert patched == proof


def test_auto_patcher_fixes_deprecated_notation_and_bool_discriminate():
    """The patcher should convert Nat.mod_add and fix boolean discriminate."""
    bad_script = """Proof.
  intros.
  rewrite <- (Nat.mod_add x 1 4).
  discriminate Hop.
Qed."""
    patched = auto_patch(
        bad_script,
        error_msg="Error: Not a discriminable equality."
    )
    assert "Nat.mod_add" not in patched
    assert "Div0.mod_add" in patched
    assert "discriminate Hop." not in patched
    assert "inversion Hop." in patched


def test_auto_patcher_does_not_alter_correct_bullet_usage():
    """Correct bullet usage (with content) is preserved when no focus error."""
    good_script = """Proof.
  intros s inputs Hreach.
  induction Hreach as [| s' s'' inputs' Hreach' IH Hstep].
  - simpl. auto.
  - inversion Hstep; subst; simpl; auto.
Qed."""
    patched = auto_patch(good_script)
    assert patched == good_script
