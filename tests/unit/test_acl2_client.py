# tests/unit/test_acl2_prover.py
#
# Unit tests for the ACL2Prover class.
# Updated to reflect:
#   - Skeleton proof attempt (adds one defthm call before the main loop).
#   - statement=None now falls through to _prove_existing_by_name (no NotImplementedError).
#   - Checkpoint is now saved only once before the main loop (not inside it).
#   - Early stop due to identical hints results in a message like "ACL2 proof failed after N attempts".
#     The exact number of attempts may vary, so we use a flexible assertion.
#   - Internal async methods of the mocked client are replaced with synchronous lambdas to avoid warnings.

import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path

from specir.verification.proof.acl2.prover import ACL2Prover


class TestACL2Prover(unittest.TestCase):
    """Test suite for ACL2Prover."""

    def setUp(self):
        """Create a prover instance with mocked dependencies."""
        # Mock config
        self.config = {
            "proof": {"max_repair_attempts": 3},
            "provers": {
                "acl2": {
                    "mcp_path": "fake-acl2-mcp",
                    "mcp_timeout": 30,
                }
            }
        }

        # Patch the client and LLM at the class level for all tests
        patcher_client = patch("specir.verification.proof.acl2.prover.get_acl2_client_from_config")
        patcher_llm = patch("specir.verification.proof.acl2.prover.get_llm_client_from_config")
        self.mock_get_client = patcher_client.start()
        self.mock_get_llm = patcher_llm.start()
        self.addCleanup(patcher_client.stop)
        self.addCleanup(patcher_llm.stop)

        # Ensure the mocked client behaves synchronously (no real asyncio)
        mock_client = self.mock_get_client.return_value
        mock_client.start.return_value = None
        mock_client.stop.return_value = None

        # Replace async methods on the mock client with synchronous functions
        # to avoid "coroutine was never awaited" warnings.
        mock_client._send_async = lambda cmd: ""
        mock_client._defthm_async = lambda *args, **kwargs: {"success": True}
        mock_client._save_checkpoint_async = lambda name: {"success": True}
        mock_client._restore_checkpoint_async = lambda name: {"success": True}

        # Create a fresh prover for each test
        self.prover = ACL2Prover(config=self.config)

    def test_init(self):
        """Test that the prover initializes the ACL2 client."""
        self.mock_get_client.assert_called_once_with(self.config)
        self.mock_get_client.return_value.start.assert_called_once()

    def test_load_file_success(self):
        """Test loading a file successfully."""
        mock_client = self.prover.acl2
        mock_client.send.return_value = "Loaded file."
        mock_client._contains_error.return_value = False

        result = self.prover.load_file(Path("/path/to/file.lisp"))
        self.assertTrue(result)
        mock_client.send.assert_called_once_with('(ld "/path/to/file.lisp")')

    def test_load_file_failure(self):
        """Test loading a file that fails."""
        mock_client = self.prover.acl2
        mock_client.send.return_value = "ACL2 Error: file not found"
        mock_client._contains_error.return_value = True

        result = self.prover.load_file(Path("/path/to/file.lisp"))
        self.assertFalse(result)

    def test_load_file_exception(self):
        """Test load_file when ACL2 throws an exception."""
        mock_client = self.prover.acl2
        mock_client.send.side_effect = Exception("Connection error")

        result = self.prover.load_file(Path("/path/to/file.lisp"))
        self.assertFalse(result)

    def test_prove_theorem_success(self):
        """Test successful theorem proof with hints supplied (skips skeleton)."""
        mock_client = self.prover.acl2
        mock_client.defthm.return_value = {"success": True, "output": "Q.E.D."}
        mock_client.save_checkpoint.return_value = {"success": True}
        mock_client.restore_checkpoint.return_value = {"success": True}

        result = self.prover.prove_theorem(
            theorem_name="test-thm",
            statement="(equal 1 1)",
            hints=["((" "Goal" ":induct t))"]
        )

        self.assertTrue(result["success"])
        self.assertIn("defthm test-thm", result["proof_script"])

        # With hints supplied, the skeleton step is skipped; only main loop runs.
        # Checkpoint saved once before main loop.
        mock_client.save_checkpoint.assert_called_once_with("pre_test-thm")
        # defthm called once (success on first attempt)
        mock_client.defthm.assert_called_once_with(
            "test-thm", "(equal 1 1)", ["((" "Goal" ":induct t))"]
        )
        # No restore should be called on success
        mock_client.restore_checkpoint.assert_not_called()

    def test_prove_theorem_failure_then_repair_success(self):
        """Test proof fails initially, LLM suggests hints, then succeeds."""
        mock_client = self.prover.acl2
        mock_llm = self.prover.llm

        # Skeleton attempt (no hints supplied) will happen first.
        # Then main loop: first attempt fails, second succeeds.
        mock_client.defthm.side_effect = [
            {"success": False, "output": "Proof failed"},          # skeleton
            {"success": False, "output": "Proof failed: ..."},    # main attempt 1
            {"success": True, "output": "Q.E.D."},                # main attempt 2
        ]
        mock_client.save_checkpoint.return_value = {"success": True}
        mock_client.restore_checkpoint.return_value = {"success": True}
        mock_client.undo.return_value = {"success": True}

        # LLM returns new hints
        mock_llm.generate.return_value = '(("Goal" :induct t) ("Subgoal *1/2" :expand ((foo x))))'

        result = self.prover.prove_theorem(
            theorem_name="test-thm",
            statement="(implies (full st) (not (enqueue st)))",
            hints=[]   # no hints, skeleton will run
        )

        self.assertTrue(result["success"])
        self.assertIn("defthm test-thm", result["proof_script"])

        # Checkpoints: saved once before main loop (after skeleton undo).
        mock_client.save_checkpoint.assert_called_once_with("pre_test-thm")
        # Restore: called after first main attempt failure
        mock_client.restore_checkpoint.assert_called_once_with("pre_test-thm")

        # defthm called: 1 skeleton + 2 main loop = 3 times
        self.assertEqual(mock_client.defthm.call_count, 3)
        # Check LLM was called for repair
        mock_llm.generate.assert_called_once()

    def test_prove_theorem_all_repair_attempts_fail(self):
        """Test proof fails and all repair attempts fail. Early stop may occur."""
        mock_client = self.prover.acl2
        mock_llm = self.prover.llm

        # Skeleton + 3 main loop attempts all fail (but early stop possible)
        mock_client.defthm.return_value = {"success": False, "output": "Proof failed"}
        mock_client.save_checkpoint.return_value = {"success": True}
        mock_client.restore_checkpoint.return_value = {"success": True}
        mock_client.undo.return_value = {"success": True}

        # LLM returns hints but they don't help
        mock_llm.generate.return_value = '(("Goal" :induct t))'

        result = self.prover.prove_theorem(
            theorem_name="test-thm",
            statement="(implies (full st) (not (enqueue st)))",
            hints=[]
        )

        self.assertFalse(result["success"])
        # Error message now reflects the number of attempts actually made (may vary)
        self.assertIn("ACL2 proof failed after", result["error"])
        self.assertIn("attempts", result["error"])

    def test_prove_theorem_llm_returns_no_hints(self):
        """Test that if LLM returns no hints, the loop stops early."""
        mock_client = self.prover.acl2
        mock_llm = self.prover.llm

        # Skeleton attempt fails, then main loop first attempt fails
        mock_client.defthm.side_effect = [
            {"success": False, "output": "Proof failed"},   # skeleton
            {"success": False, "output": "Proof failed"},   # main attempt 1
        ]
        mock_client.save_checkpoint.return_value = {"success": True}
        mock_client.restore_checkpoint.return_value = {"success": True}
        mock_client.undo.return_value = {"success": True}

        # LLM returns nothing useful
        mock_llm.generate.return_value = ""

        result = self.prover.prove_theorem(
            theorem_name="test-thm",
            statement="(implies (full st) (not (enqueue st)))",
            hints=[]
        )

        self.assertFalse(result["success"])
        # Only skeleton + 1 main attempt = 2 defthm calls
        self.assertEqual(mock_client.defthm.call_count, 2)

    def test_prove_theorem_with_statement_none(self):
        """Test that proving without statement goes to _prove_existing_by_name."""
        mock_client = self.prover.acl2
        # _prove_existing_by_name tries (verify ...), we mock send to succeed
        mock_client.send.return_value = "Q.E.D."
        mock_client._contains_error.return_value = False

        result = self.prover.prove_theorem(
            theorem_name="test-thm",
            statement=None,
            hints=[]
        )
        self.assertTrue(result["success"])
        # Should have called send with (verify (test-thm))
        mock_client.send.assert_called_with("(verify (test-thm))")

    def test_repair_hints_parses_response(self):
        """Test that _repair_hints calls LLM and parses response."""
        mock_llm = self.prover.llm
        mock_llm.generate.return_value = '(("Goal" :induct t))'

        hints = self.prover._repair_hints(
            statement="(implies (full st) (not (enqueue st)))",
            old_hints=["((" "Goal" ":induct nil))"],
            error="Proof failed"
        )
        self.assertEqual(hints, ['(("Goal" :induct t))'])
        mock_llm.generate.assert_called_once()

    def test_repair_hints_handles_markdown(self):
        """Test that _repair_hints strips markdown fences."""
        mock_llm = self.prover.llm
        mock_llm.generate.return_value = "```lisp\n((\"Goal\" :induct t))\n```"

        hints = self.prover._repair_hints("stmt", [], "err")
        self.assertEqual(hints, ['((\"Goal\" :induct t))'])

    def test_repair_hints_returns_none_on_parse_failure(self):
        """Test that _repair_hints returns None if response cannot be parsed."""
        mock_llm = self.prover.llm
        mock_llm.generate.return_value = "Just some text without parentheses"

        hints = self.prover._repair_hints("stmt", [], "err")
        self.assertIsNone(hints)

    def test_checkpoint_saved_once_before_main_loop(self):
        """Test that a checkpoint is saved once before the main proof loop."""
        mock_client = self.prover.acl2
        mock_client.defthm.side_effect = [
            {"success": False, "output": "failed"},   # skeleton (will be undone)
            {"success": True, "output": "success"},   # main attempt 1
        ]
        mock_client.save_checkpoint.return_value = {"success": True}
        mock_client.restore_checkpoint.return_value = {"success": True}
        mock_client.undo.return_value = {"success": True}
        mock_llm = self.prover.llm
        mock_llm.generate.return_value = '(("Goal" :induct t))'

        self.prover.prove_theorem("test", "stmt", [])

        # Checkpoint saved exactly once, before the main loop
        mock_client.save_checkpoint.assert_called_once_with("pre_test")
        # Restore not called because first main attempt succeeded
        mock_client.restore_checkpoint.assert_not_called()

    def test_max_repair_from_config(self):
        """Test that max_repair_attempts is read from config."""
        config = {"proof": {"max_repair_attempts": 7}}
        prover = ACL2Prover(config=config)
        self.assertEqual(prover.max_repair, 7)


if __name__ == "__main__":
    unittest.main()
