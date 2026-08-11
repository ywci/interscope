# tests/unit/test_proof_skill.py
#
# Complete unit tests for LLMProofSkill: ACL2, Koika, and model-checking paths.
# Updated to mock prove_theorem return values as ProofResult dataclasses.

import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path
from specir.verification.proof.proof_skill import (
    LLMProofSkill,
    ModelCheckProver
)
from specir.verification.proof.proof import ProofResult
from specir.verification.model_checker import ModelCheckError


class TestProofSkillACL2(unittest.TestCase):
    """Test suite for ACL2 path in LLMProofSkill."""

    def setUp(self):
        """Create a proof skill instance with mocked dependencies."""
        patcher_prover = patch("specir.verification.proof.proof_skill.ACL2Prover")
        patcher_llm = patch("specir.verification.proof.proof_skill.get_llm_client_from_config")
        self.mock_prover_cls = patcher_prover.start()
        self.mock_get_llm = patcher_llm.start()
        self.addCleanup(patcher_prover.stop)
        self.addCleanup(patcher_llm.stop)

        self.config = {"proof": {"max_repair_attempts": 3}}
        self.skill = LLMProofSkill(config=self.config)
        self.mock_prover = MagicMock()
        self.mock_prover_cls.return_value = self.mock_prover

    def test_can_handle_acl2_backend(self):
        obligation = {"backend": "acl2"}
        self.assertTrue(self.skill.can_handle(obligation))

    def test_can_handle_koika_backend(self):
        obligation = {"backend": "koika"}
        self.assertTrue(self.skill.can_handle(obligation))

    def test_can_handle_model_checking_engine(self):
        obligation = {"engine": "model_checking"}
        self.assertTrue(self.skill.can_handle(obligation))

    def test_can_handle_unsupported_backend(self):
        obligation = {"backend": "unsupported"}
        self.assertFalse(self.skill.can_handle(obligation))

    def test_prove_dispatches_to_acl2(self):
        obligation = {"backend": "acl2"}
        context = {"acl2_file_path": "/path/file.lisp", "theorem_name": "test"}
        with patch.object(self.skill, "_prove_acl2") as mock_prove:
            self.skill.prove(obligation, context)
            mock_prove.assert_called_once_with(obligation, context)

    def test_prove_dispatches_to_koika(self):
        obligation = {"backend": "koika"}
        context = {"coq_file_path": "/path/file.v"}
        with patch.object(self.skill, "_prove_koika") as mock_prove:
            self.skill.prove(obligation, context)
            mock_prove.assert_called_once_with(obligation, context)

    def test_prove_dispatches_to_model_check(self):
        obligation = {"engine": "model_checking"}
        context = {"rtl_file_path": "/rtl/test.v", "assertions_file_path": "/assert/test.sv"}
        with patch.object(self.skill, "_prove_model_check") as mock_mc:
            self.skill.prove(obligation, context)
            mock_mc.assert_called_once_with(obligation, context)

    def test_prove_unsupported_backend(self):
        obligation = {"backend": "unsupported"}
        result = self.skill.prove(obligation, {})
        self.assertFalse(result.success)
        self.assertIn("Unsupported backend", result.error_message)

    def test_prove_acl2_success(self):
        obligation = {"property": "no_overflow", "metadata": {"acl2_hints": ["((" "Goal" ":induct t))"]}}
        context = {"acl2_file_path": "/path/file.lisp", "theorem_name": "no_overflow_correct", "theorem_statement": "(implies (full st) (not (enqueue st)))"}
        self.mock_prover.prove_theorem.return_value = ProofResult(success=True, proof_script="(defthm no_overflow_correct ...)")
        result = self.skill._prove_acl2(obligation, context)
        self.assertTrue(result.success)
        self.assertEqual(result.proof_script, "(defthm no_overflow_correct ...)")

    def test_prove_acl2_without_statement(self):
        obligation = {"property": "no_overflow"}
        context = {"acl2_file_path": "/path/file.lisp", "theorem_name": "no_overflow_correct"}
        self.mock_prover.prove_theorem.return_value = ProofResult(success=True, proof_script="...")
        result = self.skill._prove_acl2(obligation, context)
        self.assertTrue(result.success)

    def test_prove_acl2_missing_file_path(self):
        obligation = {"property": "no_overflow"}
        context = {}
        result = self.skill._prove_acl2(obligation, context)
        self.assertFalse(result.success)
        self.assertIn("Missing 'acl2_file_path'", result.error_message)

    def test_prove_acl2_missing_theorem_name(self):
        obligation = {"property": ""}
        context = {"acl2_file_path": "/path/file.lisp"}
        result = self.skill._prove_acl2(obligation, context)
        self.assertFalse(result.success)
        self.assertIn("Missing property name", result.error_message)

    def test_prove_acl2_prover_failure(self):
        obligation = {"property": "no_overflow"}
        context = {"acl2_file_path": "/path/file.lisp", "theorem_name": "no_overflow_correct"}
        self.mock_prover.prove_theorem.return_value = ProofResult(success=False, error_message="induction error")
        result = self.skill._prove_acl2(obligation, context)
        self.assertFalse(result.success)
        self.assertIn("induction error", result.error_message)

    def test_prove_acl2_prover_exception(self):
        obligation = {"property": "no_overflow"}
        context = {"acl2_file_path": "/path/file.lisp", "theorem_name": "no_overflow_correct"}
        self.mock_prover.prove_theorem.side_effect = Exception("Connection refused")
        result = self.skill._prove_acl2(obligation, context)
        self.assertFalse(result.success)
        self.assertIn("ACL2 prover error: Connection refused", result.error_message)


class TestProofSkillKoika(unittest.TestCase):
    """Test suite for the Kōika/Coq path in LLMProofSkill."""

    def setUp(self):
        patcher_prover = patch("specir.verification.proof.proof_skill.KoikaProver")
        patcher_llm = patch("specir.verification.proof.proof_skill.get_llm_client_from_config")
        self.mock_prover_cls = patcher_prover.start()
        self.mock_get_llm = patcher_llm.start()
        self.addCleanup(patcher_prover.stop)
        self.addCleanup(patcher_llm.stop)

        self.config = {"proof": {"max_repair_attempts": 3}}
        self.skill = LLMProofSkill(config=self.config)
        self.mock_prover = MagicMock()
        self.mock_prover_cls.return_value = self.mock_prover

    def test_can_handle_koika_backend(self):
        obligation = {"backend": "koika"}
        self.assertTrue(self.skill.can_handle(obligation))

    def test_prove_koika_success(self):
        obligation = {"property": "my_prop"}
        context = {"coq_file_path": "/path/file.v", "theorem_name": "my_prop_proved"}
        self.mock_prover.prove_theorem.return_value = ProofResult(success=True, proof_script="Proof. trivial. Qed.")
        result = self.skill._prove_koika(obligation, context)
        self.assertTrue(result.success)
        self.assertEqual(result.metadata["backend"], "koika")

    def test_prove_koika_missing_coq_file(self):
        obligation = {"property": "my_prop"}
        context = {}
        result = self.skill._prove_koika(obligation, context)
        self.assertFalse(result.success)
        self.assertIn("Missing 'coq_file_path'", result.error_message)

    def test_prove_koika_prover_exception(self):
        obligation = {"property": "my_prop"}
        context = {"coq_file_path": "/path/file.v", "theorem_name": "my_prop_proved"}
        self.mock_prover.prove_theorem.side_effect = Exception("Coq crashed")
        result = self.skill._prove_koika(obligation, context)
        self.assertFalse(result.success)
        self.assertIn("Koika prover error: Coq crashed", result.error_message)

    def test_prove_koika_lazy_initialization(self):
        obligation = {"property": "my_prop"}
        context = {"coq_file_path": "/path/file.v", "theorem_name": "my_prop_proved"}
        self.mock_prover.prove_theorem.return_value = ProofResult(success=True, proof_script="")
        self.skill._prove_koika(obligation, context)
        self.mock_prover_cls.assert_called_once()
        self.mock_prover_cls.reset_mock()
        self.skill._prove_koika(obligation, context)
        self.mock_prover_cls.assert_not_called()


class TestModelCheckProver(unittest.TestCase):
    """Tests for ModelCheckProver that wraps run_model_check."""

    def setUp(self):
        self.mock_run = patch("specir.verification.proof.proof_skill.run_model_check").start()
        self.addCleanup(patch.stopall)

    def test_success(self):
        prover = ModelCheckProver(config={})
        self.mock_run.return_value = {"success": True, "status": "proved"}
        result = prover.prove(Path("/rtl.v"), Path("/assert.sv"), "top")
        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "proved")

    def test_failure(self):
        prover = ModelCheckProver()
        self.mock_run.return_value = {"success": False, "status": "disproved", "counterexample_trace": Path("/trace.vcd")}
        result = prover.prove(Path("/rtl.v"), Path("/assert.sv"), "top")
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "disproved")

    def test_tool_error_caught(self):
        prover = ModelCheckProver()
        self.mock_run.side_effect = ModelCheckError("tool not found")
        result = prover.prove(Path("/rtl.v"), Path("/assert.sv"), "top")
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "error")
        self.assertIn("tool not found", result["error"])


class TestProofSkillModelCheck(unittest.TestCase):
    """Tests for model‑checking path in LLMProofSkill."""

    def setUp(self):
        patcher_llm = patch("specir.verification.proof.proof_skill.get_llm_client_from_config")
        self.mock_llm = patcher_llm.start()
        self.addCleanup(patcher_llm.stop)

        self.config = {"proof": {"max_repair_attempts": 3}}
        self.skill = LLMProofSkill(config=self.config)

    def test_prove_model_check_success(self):
        obligation = {"engine": "model_checking", "property": "test_prop"}
        context = {"rtl_file_path": "/rtl/test.v", "assertions_file_path": "/assert/test.sv", "top_module": "top"}
        with patch.object(ModelCheckProver, "prove") as mock_mc:
            mock_mc.return_value = {"success": True, "status": "proved"}
            result = self.skill._prove_model_check(obligation, context)
            self.assertTrue(result.success)
            self.assertEqual(result.metadata["backend"], "model_checking")

    def test_prove_model_check_failure(self):
        obligation = {"engine": "model_checking", "property": "test_prop"}
        context = {"rtl_file_path": "/rtl/test.v", "assertions_file_path": "/assert/test.sv"}
        with patch.object(ModelCheckProver, "prove") as mock_mc:
            mock_mc.return_value = {"success": False, "status": "disproved", "error": "assertion violated"}
            result = self.skill._prove_model_check(obligation, context)
            self.assertFalse(result.success)
            self.assertIn("assertion violated", result.error_message)

    def test_prove_model_check_missing_rtl_path(self):
        obligation = {"engine": "model_checking"}
        context = {"assertions_file_path": "/assert/test.sv"}
        result = self.skill._prove_model_check(obligation, context)
        self.assertFalse(result.success)
        self.assertIn("Missing 'rtl_file_path'", result.error_message)

    def test_prove_model_check_missing_assertions_path(self):
        obligation = {"engine": "model_checking"}
        context = {"rtl_file_path": "/rtl/test.v"}
        result = self.skill._prove_model_check(obligation, context)
        self.assertFalse(result.success)
        self.assertIn("Missing 'rtl_file_path'", result.error_message)
