# tests/unit/test_proof.py
#
# Unit tests for the proof base classes:
# ProofResult and ProofSkill.

import pytest
from dataclasses import dataclass
from specir.verification.proof.proof import ProofResult, ProofSkill


class TestProofResult:
    def test_default_values(self):
        result = ProofResult(success=True)
        assert result.success is True
        assert result.proof_script is None
        assert result.error_message is None
        assert result.auxiliary_lemmas == []
        assert result.metadata == {}

    def test_with_values(self):
        result = ProofResult(
            success=False,
            proof_script="Proof. auto. Qed.",
            error_message="auto failed",
            auxiliary_lemmas=["lemma1"],
            metadata={"attempts": 3}
        )
        assert result.success is False
        assert result.proof_script == "Proof. auto. Qed."
        assert result.error_message == "auto failed"
        assert result.auxiliary_lemmas == ["lemma1"]
        assert result.metadata["attempts"] == 3

    def test_combine_all_success(self):
        results = [
            ProofResult(success=True),
            ProofResult(success=True),
            ProofResult(success=True)
        ]
        combined = ProofResult.combine(results)
        assert combined.success is True
        assert combined.metadata["total"] == 3
        assert combined.metadata["passed"] == 3
        assert combined.metadata["failed"] == 0

    def test_combine_some_failures(self):
        results = [
            ProofResult(success=True),
            ProofResult(success=False),
            ProofResult(success=True),
            ProofResult(success=False),
        ]
        combined = ProofResult.combine(results)
        assert combined.success is False
        assert combined.metadata["total"] == 4
        assert combined.metadata["passed"] == 2
        assert combined.metadata["failed"] == 2

    def test_combine_empty_list(self):
        combined = ProofResult.combine([])
        assert combined.success is True
        assert combined.metadata["total"] == 0
        assert combined.metadata["passed"] == 0
        assert combined.metadata["failed"] == 0


class TestProofSkill:
    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            ProofSkill()

    def test_concrete_subclass_instantiable(self):
        class DummySkill(ProofSkill):
            def prove(self, obligation, context):
                return ProofResult(success=True)

            def can_handle(self, obligation):
                return True

        skill = DummySkill()
        assert isinstance(skill, ProofSkill)
        assert skill.can_handle({}) is True

        result = skill.prove({}, {})
        assert result.success is True
