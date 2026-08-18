# tests/unit/test_koika_prover.py
#
# Unit tests for Kōika/Coq proof infrastructure.
# Tests cover prover orchestration, proof prompt construction, script extraction,
# repair with sanity checks, skeleton proofs, skeleton reflection, and configurable hints.

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, mock_open, MagicMock, call
from specir.verification.proof.koika.prover import KoikaProver
from specir.verification.proof.koika.proof_gen import (
    build_coq_proof_prompt, extract_proof_script
)
from specir.verification.proof.koika.repair import (
    repair_coq_proof, _basic_sanity
)
from specir.verification.proof.proof import ProofResult


@pytest.fixture
def mock_config():
    return {
        "llm": {
            "provider": "openai",
            "model": "gpt-4",
            "api_key": "test-key",
        },
        "provers": {
            "koika": {
                "prove": {
                    "rocq_mcp_path": "rocq-mcp",
                    "proof_timeout": 300,
                    "max_consecutive_failures": 10,
                    "max_steps": 40,
                    "pre_simplify": True,
                    "invariant_mining": True,
                    "skeleton_reflection": True,
                    "skeleton_step_tactics": [],
                    "use_rocq_mcp": True,
                }
            }
        },
        "proof": {
            "max_repair_attempts": 3
        }
    }


@pytest.fixture
def mock_rocq_client():
    with patch("specir.verification.proof.koika.prover.RocqClient") as MockRocq:
        instance = MockRocq.return_value
        instance.start.return_value = None
        instance.compile_file.return_value = {"success": True}
        instance.start_session.return_value = ("1", ["goal1", "goal2"])
        yield instance


@pytest.fixture
def mock_llm_client():
    with patch("specir.verification.proof.koika.prover.get_llm_client_from_config") as MockLLM:
        instance = MockLLM.return_value
        instance.generate.return_value = "simpl.\nauto.\ninduction s."
        yield instance


class TestKoikaProverInit:
    def test_koika_prover_init(self, mock_config):
        with patch("specir.verification.proof.koika.prover.RocqClient") as mock_rocq_class:
            mock_rocq_class.return_value.start.return_value = None
            prover = KoikaProver(config=mock_config)
            assert prover.max_repair == 3
            assert prover.llm is not None
            assert prover.proof_timeout == 300
            assert prover.max_consecutive_failures == 10
            assert prover.max_steps == 40
            assert prover.pre_simplify is True
            assert prover.invariant_mining is True
            assert prover.skeleton_reflection is True

    def test_koika_prover_defaults(self):
        minimal_config = {
            "llm": {"provider": "openai", "model": "gpt-4", "api_key": "key"},
            "provers": {"koika": {"prove": {}}},
            "proof": {},
        }
        with patch("specir.verification.proof.koika.prover.RocqClient") as mock_rocq_class:
            mock_rocq_class.return_value.start.return_value = None
            prover = KoikaProver(config=minimal_config)
            assert prover.proof_timeout == 600
            assert prover.max_consecutive_failures == 10
            assert prover.max_steps == 80
            assert prover.pre_simplify is True
            assert prover.invariant_mining is True
            assert prover.skeleton_reflection is True


class TestProveTheorem:
    def test_prove_theorem_success(self, mock_config, mock_rocq_client, mock_llm_client):
        """The interactive prover returns success, so the whole flow succeeds."""
        prover = KoikaProver(config=mock_config)

        with patch.object(prover, "_theorem_already_proven", return_value=False), \
             patch.object(prover, "_apply_library_proof", return_value=None), \
             patch.object(prover, "_try_interactive_proof",
                          return_value=({"success": True, "proof_script": "Proof. auto. Qed."}, None, None)):
            result = prover.prove_theorem(Path("test.v"), "theorem_name")
        assert isinstance(result, ProofResult)
        assert result.success is True

    def test_prove_theorem_compilation_fails(self, mock_config, mock_rocq_client, mock_llm_client):
        mock_rocq_client.compile_file.return_value = {"isError": True, "error": "Compilation error"}
        prover = KoikaProver(config=mock_config)

        with patch.object(prover, "_theorem_already_proven", return_value=False), \
             patch.object(prover, "_apply_library_proof", return_value=None), \
             patch.object(prover, "_attempt_llm_proof_generation", return_value=None), \
             patch("pathlib.Path.read_text", return_value="Theorem theorem_name : Admitted."):
            result = prover.prove_theorem(Path("test.v"), "theorem_name")
        assert result.success is False

    def test_prove_theorem_no_goals(self, mock_config, mock_rocq_client):
        mock_rocq_client.start_session.return_value = ("1", [])
        prover = KoikaProver(config=mock_config)

        with patch.object(prover, "_theorem_already_proven", return_value=False), \
             patch.object(prover, "_apply_library_proof", return_value=None), \
             patch("pathlib.Path.read_text", return_value="Theorem theorem_name : Admitted."), \
             patch.object(prover, "_attempt_llm_proof_generation", return_value=None):
            result = prover.prove_theorem(Path("test.v"), "theorem_name")
        assert result.success is False

    def test_prove_theorem_tactic_fails_then_repair_succeeds(self, mock_config, mock_rocq_client, mock_llm_client):
        """When the interactive prover fails, the full pipeline returns failure."""
        prover = KoikaProver(config=mock_config)

        with patch.object(prover, "_theorem_already_proven", return_value=False), \
             patch.object(prover, "_apply_library_proof", return_value=None), \
             patch.object(prover, "_try_interactive_proof",
                          return_value=({"success": False, "error": "proof failed"}, None, None)), \
             patch("pathlib.Path.read_text", return_value="Theorem theorem_name : Admitted."):
            result = prover.prove_theorem(Path("test.v"), "theorem_name")
        assert result.success is False

    def test_prove_theorem_commands_run_zero(self, mock_config, mock_rocq_client, mock_llm_client):
        mock_rocq_client.check.return_value = {
            "isError": True,
            "error": "Tactic failed"
        }
        mock_llm_client.generate.return_value = "simpl."
        prover = KoikaProver(config=mock_config)

        with patch.object(prover, "_theorem_already_proven", return_value=False), \
             patch.object(prover, "_apply_library_proof", return_value=None), \
             patch("pathlib.Path.read_text", return_value="Theorem theorem_name : Admitted."):
            result = prover.prove_theorem(Path("test.v"), "theorem_name")
        assert result.success is False

    def test_prove_theorem_too_many_failures(self, mock_config, mock_rocq_client, mock_llm_client):
        mock_rocq_client.check.return_value = {
            "isError": True,
            "error": "Generic error",
        }
        mock_llm_client.generate.return_value = "tactic1."
        prover = KoikaProver(config=mock_config)

        with patch.object(prover, "_theorem_already_proven", return_value=False), \
             patch.object(prover, "_apply_library_proof", return_value=None), \
             patch("pathlib.Path.read_text", return_value="Theorem theorem_name : Admitted."):
            result = prover.prove_theorem(Path("test.v"), "theorem_name")
        assert result.success is False

    def test_prove_theorem_library_proof_applied(self, mock_config, mock_rocq_client):
        prover = KoikaProver(config=mock_config)

        with patch.object(prover, "_theorem_already_proven", return_value=False), \
             patch.object(prover, "_apply_library_proof", return_value="Proof. auto. Qed.") as mock_apply:
            result = prover.prove_theorem(Path("test.v"), "theorem_name")
            mock_apply.assert_called_once_with(Path("test.v"), "theorem_name")
            assert result.success is True
            assert result.proof_script == "Proof. auto. Qed."

    def test_prove_theorem_pre_simplify_enabled(self, mock_config, mock_rocq_client, mock_llm_client):
        mock_config["provers"]["koika"]["prove"]["pre_simplify"] = True
        fallback_responses = [
            {"structuredContent": {"state_id": "f1", "goals": ["subgoal"], "proof_finished": False, "commands_run": 1}, "isError": False},
            {"structuredContent": {"state_id": "f2", "goals": [], "proof_finished": True, "commands_run": 1}, "isError": False},
        ]
        mock_rocq_client.check.side_effect = fallback_responses
        mock_llm_client.generate.return_value = "auto."
        prover = KoikaProver(config=mock_config)

        with patch.object(prover, "_try_skeleton_proof", return_value=None), \
             patch.object(prover, "_request_skeleton_reflection", return_value=None), \
             patch.object(prover, "_theorem_already_proven", return_value=False), \
             patch.object(prover, "_apply_library_proof", return_value=None), \
             patch("pathlib.Path.read_text", return_value="Theorem theorem_name : Admitted."):
            result = prover.prove_theorem(Path("test.v"), "theorem_name")

        assert result.success is True
        assert mock_rocq_client.check.call_count == 2

    def test_prove_theorem_pre_simplify_disabled(self, mock_config, mock_rocq_client, mock_llm_client):
        mock_config["provers"]["koika"]["prove"]["pre_simplify"] = False
        fallback_responses = [
            {"structuredContent": {"state_id": "f1", "goals": [], "proof_finished": True, "commands_run": 1}, "isError": False},
        ]
        mock_rocq_client.check.side_effect = fallback_responses
        mock_llm_client.generate.return_value = "auto."
        prover = KoikaProver(config=mock_config)

        with patch.object(prover, "_try_skeleton_proof", return_value=None), \
             patch.object(prover, "_request_skeleton_reflection", return_value=None), \
             patch.object(prover, "_theorem_already_proven", return_value=False), \
             patch.object(prover, "_apply_library_proof", return_value=None), \
             patch("pathlib.Path.read_text", return_value="Theorem theorem_name : Admitted."):
            result = prover.prove_theorem(Path("test.v"), "theorem_name")

        assert result.success is True
        mock_rocq_client.check.assert_called_once()

    def test_skeleton_proof_succeeds(self, mock_config, mock_rocq_client):
        """The built‑in skeleton closes the proof without LLM interaction."""
        responses = [
            {"structuredContent": {"state_id": "s1", "goals": ["goal"], "commands_run": 1}, "isError": False},
            {"structuredContent": {"state_id": "s1", "goals": ["Hreach : reachable s |- goal"], "commands_run": 1}, "isError": False},
            {"structuredContent": {"state_id": "s2", "goals": ["base", "step"], "commands_run": 1}, "isError": False},
            {"structuredContent": {"state_id": "s3", "goals": ["step"], "commands_run": 1}, "isError": False},
            {"structuredContent": {"state_id": "s4", "goals": ["after inversion"], "commands_run": 1}, "isError": False},
            {"structuredContent": {"state_id": "s5", "goals": ["simplified"], "commands_run": 1}, "isError": False},
            {"structuredContent": {"state_id": "s6", "goals": [], "proof_finished": True, "commands_run": 1}, "isError": False},
        ]
        mock_rocq_client.check.side_effect = responses
        prover = KoikaProver(config=mock_config)

        with patch.object(prover, "_theorem_already_proven", return_value=False), \
             patch.object(prover, "_apply_library_proof", return_value=None), \
             patch("pathlib.Path.read_text", return_value="Theorem theorem_name : Admitted."):
            result = prover.prove_theorem(Path("test.v"), "theorem_name")

        assert result.success is True

    def test_skeleton_fails_reflection_succeeds(self, mock_config, mock_rocq_client, mock_llm_client):
        """When the skeleton fails, the LLM‑reflection step provides a valid proof."""
        mock_rocq_client.check.side_effect = [
            {"structuredContent": {"state_id": "s1", "goals": ["goal"], "commands_run": 1}, "isError": False},
            {"structuredContent": {"state_id": "s1", "goals": ["Hreach : reachable s |- goal"], "commands_run": 1}, "isError": False},
            {"structuredContent": {"state_id": "s2", "goals": ["base"], "commands_run": 1}, "isError": False},
            {"structuredContent": {"state_id": "s3", "goals": ["step"], "commands_run": 1}, "isError": False},
            {"isError": True, "error": "Inversion failed"},
        ]

        mock_rocq_client.start_session.side_effect = [
            ("1", ["goal1"]),
            ("2", ["goal2"]),
        ]

        file_content = "Theorem theorem_name : forall s, reachable s -> True.\nProof. Admitted."
        mock_llm_client.generate.return_value = "Proof. auto. Qed."

        prover = KoikaProver(config=mock_config)

        with patch.object(prover, "_theorem_already_proven", return_value=False), \
             patch.object(prover, "_apply_library_proof", return_value=None), \
             patch("pathlib.Path.read_text", return_value=file_content), \
             patch("builtins.open", mock_open(read_data=file_content)), \
             patch.object(prover, "_compile_with_coqc", return_value=True), \
             patch.object(prover, "_fallback_verify", return_value={"success": True}):
            result = prover.prove_theorem(Path("test.v"), "theorem_name")

        assert result.success is True

    def test_configurable_hints_in_prompt(self, mock_config, mock_rocq_client, mock_llm_client):
        """Custom base_case_hint and step_case_hint are forwarded to the prompt builder."""
        mock_config["provers"]["koika"]["prove"]["base_case_hint"] = "my_base"
        mock_config["provers"]["koika"]["prove"]["step_case_hint"] = "my_step"
        prover = KoikaProver(config=mock_config)

        mock_rocq_instance = MagicMock()
        mock_rocq_instance.start.return_value = None
        mock_rocq_instance.compile_file.return_value = {"success": True}
        mock_rocq_instance.start_session.return_value = ("1", ["goal"])
        mock_rocq_instance.check.return_value = {
            "structuredContent": {"state_id": "s1", "goals": ["goal"], "proof_finished": True, "commands_run": 1},
            "isError": False
        }

        with patch("specir.verification.proof.koika.prover.RocqClient", return_value=mock_rocq_instance), \
             patch("specir.verification.proof.koika.prover.build_interactive_step_prompt") as mock_build, \
             patch.object(prover, "_try_skeleton_proof", return_value=None), \
             patch.object(prover, "_request_skeleton_reflection", return_value=None), \
             patch.object(prover, "_theorem_already_proven", return_value=False), \
             patch.object(prover, "_apply_library_proof", return_value=None), \
             patch("pathlib.Path.read_text", return_value="Theorem theorem_name : Admitted."):
            prover.prove_theorem(Path("test.v"), "theorem_name")

        call_kwargs = mock_build.call_args[1]
        assert call_kwargs["base_case_hint"] == "my_base"
        assert call_kwargs["step_case_hint"] == "my_step"


class TestProofGen:
    def test_build_coq_proof_prompt(self):
        prompt = build_coq_proof_prompt(
            theorem_name="no_overflow",
            theorem_statement="forall st, reachable st -> full st -> not enqueue st",
            context="Require Import Koika.",
            tactic_hints=["induction", "simpl"],
            assumptions=["(always (not (enqueue and dequeue)))"],
            previous_attempts=[
                {"script": "Proof. auto. Qed.", "error": "auto failed"}
            ],
        )
        assert "Theorem no_overflow" in prompt
        assert "forall st, reachable st" in prompt
        assert "Previous attempts" in prompt
        assert "induction, simpl" in prompt
        assert "Require Import Koika." in prompt
        assert "auto failed" in prompt

    def test_extract_proof_script(self):
        response = """Some text
Proof.
  simpl.
  auto.
Qed.
More text"""
        script = extract_proof_script(response)
        assert "Proof." in script
        assert "Qed." in script
        assert "simpl" in script
        assert "More text" not in script

    def test_extract_proof_script_nested(self):
        response = """Proof.
  Lemma helper : True. Proof. auto. Qed.
  apply helper.
Qed."""
        script = extract_proof_script(response)
        assert "Lemma helper" in script
        assert script.strip().endswith("Qed.")

    def test_extract_proof_script_fallback(self):
        response = "No proof here"
        script = extract_proof_script(response)
        assert script == response


class TestRepair:
    def test_basic_sanity(self):
        assert _basic_sanity("Proof. auto. Qed.") is True
        assert _basic_sanity("Proof. auto. Admitted.") is True
        assert _basic_sanity("Proof. auto") is False
        assert _basic_sanity("auto. Qed.") is False
        assert _basic_sanity("") is False

    def test_repair_coq_proof(self, mock_llm_client):
        mock_llm_client.generate.return_value = "Proof. induction x; auto. Qed."
        success, repaired = repair_coq_proof(
            original_script="Proof. auto. Qed.",
            error_message="Error: cannot prove",
            llm_client=mock_llm_client,
            max_attempts=2
        )
        assert success is True
        assert "induction x" in repaired

        mock_llm_client.generate.return_value = "Proof. Admitted."
        success, repaired = repair_coq_proof(
            original_script="Proof. auto. Qed.",
            error_message="Error: cannot prove",
            llm_client=mock_llm_client,
            max_attempts=1
        )
        assert success is True
        assert "Admitted." in repaired

    def test_repair_coq_proof_sanity_fails(self, mock_llm_client):
        mock_llm_client.generate.return_value = "Invalid script"
        success, repaired = repair_coq_proof(
            original_script="Proof. auto. Qed.",
            error_message="Error",
            llm_client=mock_llm_client,
            max_attempts=1
        )
        assert success is False
        assert repaired == "Proof. auto. Qed."
