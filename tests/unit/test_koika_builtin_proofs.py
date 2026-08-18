# tests/unit/test_koika_builtin_proofs.py
#
# Unit tests for the corrected built‑in Coq proof scripts in
# `KoikaProver`.  These tests verify that the proofs no longer contain
# the specific anti‑patterns that caused failures in the ALU
# verification (deprecated notations, `discriminate` on boolean
# equalities, bullet misuse).  They do not require a working Coq
# installation and can be run in any environment.

import pytest
from unittest.mock import patch
from specir.verification.proof.koika.prover import KoikaProver


def _get_builtin_proof(prover: KoikaProver, theorem_name: str) -> str:
    """Retrieve a built‑in proof script by theorem name."""
    if theorem_name == "zero_flag_correct_proved":
        return prover._zero_flag_proof()
    elif theorem_name == "overflow_implies_result_neq_sum_proved":
        return prover._overflow_sum_proof()
    elif theorem_name == "sub_overflow_implies_result_neq_diff_proved":
        return prover._overflow_diff_proof()
    else:
        raise ValueError(f"Unknown built‑in theorem: {theorem_name}")


@pytest.fixture
def prover() -> KoikaProver:
    """Create a KoikaProver with a minimal configuration.

    The LLM client is not actually used for built‑in proofs, so we mock
    its creation to avoid external dependencies.
    """
    config = {
        "llm": {"provider": "ollama", "model": "dummy"},
        "provers": {"koika": {"prove": {"use_rocq_mcp": False}}},
        "proof": {},
    }
    with patch("specir.verification.proof.koika.prover.get_llm_client_from_config") as mock_llm:
        mock_llm.return_value = object()  # dummy LLM client
        return KoikaProver(config=config)


def test_builtin_proofs_do_not_contain_deprecated_notations(prover: KoikaProver):
    """Ensure no deprecated `Nat.mod_add` remains."""
    for thm in [
        "zero_flag_correct_proved",
        "overflow_implies_result_neq_sum_proved",
        "sub_overflow_implies_result_neq_diff_proved",
    ]:
        proof = _get_builtin_proof(prover, thm)
        assert "Nat.mod_add" not in proof, (
            f"{thm} contains deprecated `Nat.mod_add`; use `Div0.mod_add` instead."
        )


def test_overflow_proofs_do_not_use_bad_discriminate(prover: KoikaProver):
    """Overflow proofs must not use `discriminate Hop` on a boolean equality.

    The corrected proofs should instead use `inversion Hop` or
    `rewrite Nat.eqb_eq in Hop`.
    """
    for thm in [
        "overflow_implies_result_neq_sum_proved",
        "sub_overflow_implies_result_neq_diff_proved",
    ]:
        proof = _get_builtin_proof(prover, thm)
        # The exact bad pattern "discriminate Hop." should be absent.
        assert "discriminate Hop." not in proof, (
            f"{thm} still contains the faulty `discriminate Hop.`; "
            "use `inversion Hop` or `rewrite Nat.eqb_eq` instead."
        )
        # The legitimate base-case `discriminate Hvalid` (valid is false
        # initially) should still be present.
        assert "discriminate Hvalid" in proof, (
            f"{thm} is missing the base‑case `discriminate Hvalid`."
        )
        # One of the corrected handling patterns should be present.
        assert ("inversion Hop" in proof or "rewrite Nat.eqb_eq in Hop" in proof), (
            f"{thm} lacks a proper handling of the boolean equality `Hop`."
        )


def test_zero_flag_proof_uses_braces_not_bullets(prover: KoikaProver):
    """The zero‑flag proof should separate subgoals with braces, not bullets."""
    proof = prover._zero_flag_proof()
    # Check that explicit braces are used.
    assert "{" in proof and "}" in proof, (
        "Zero‑flag proof should use `{ ... }` for subgoal separation."
    )
    # Ensure no line consists solely of a bullet character (a common cause
    # of `Wrong bullet` / `Focus` errors).
    for line in proof.splitlines():
        stripped = line.strip()
        assert stripped not in ("-", "+", "*"), (
            f"Orphan bullet found in proof:\n{proof}"
        )


def test_all_builtin_proofs_are_non_empty_and_well_formed(prover: KoikaProver):
    """All built‑in proofs must contain the mandatory Proof/Qed markers."""
    for thm in [
        "zero_flag_correct_proved",
        "overflow_implies_result_neq_sum_proved",
        "sub_overflow_implies_result_neq_diff_proved",
    ]:
        proof = _get_builtin_proof(prover, thm)
        assert proof.strip().startswith("Proof."), f"{thm} does not start with Proof."
        assert "Qed." in proof, f"{thm} does not end with Qed."
