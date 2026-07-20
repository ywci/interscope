# tests/unit/test_rocq_client.py
#
# Unit tests for the rocq-mcp client.

import warnings
warnings.simplefilter("ignore", RuntimeWarning)

import json
import unittest
from queue import Empty
from unittest.mock import patch, MagicMock
from pathlib import Path

from specir.backends.rocq_client import RocqClient, RocqClientError


class TestLifecycle(unittest.TestCase):
    def setUp(self):
        self.client = RocqClient(rocq_mcp_path="rocq-mcp", timeout=30)

    @patch("threading.Thread")
    @patch("subprocess.Popen")
    def test_start_starts_process(self, mock_popen, mock_thread):
        mock_process = MagicMock()
        mock_process.stdin = MagicMock()
        mock_process.stdout = MagicMock()
        mock_process.stderr = MagicMock()
        mock_popen.return_value = mock_process

        # Prevent the initialisation request from blocking for 30 seconds
        with patch.object(self.client, "_send_request", return_value={"result": "ok"}):
            self.client.start()

        self.assertIsNotNone(self.client.process)
        mock_popen.assert_called_once()

    @patch("subprocess.Popen")
    def test_start_already_running(self, mock_popen):
        mock_process = MagicMock()
        self.client.process = mock_process
        self.client.start()
        mock_popen.assert_not_called()

    @patch("threading.Thread")
    @patch("subprocess.Popen")
    def test_stop_sends_shutdown_and_terminates(self, mock_popen, mock_thread):
        mock_process = MagicMock()
        mock_process.stdin = MagicMock()
        mock_process.stdout = MagicMock()
        mock_process.stderr = MagicMock()
        mock_popen.return_value = mock_process

        # Prevent the initialisation request from blocking
        with patch.object(self.client, "_send_request", return_value={"result": "ok"}):
            self.client.start()

        self.client.stop()
        self.assertIsNone(self.client.process)
        mock_process.terminate.assert_called_once()


class TestSendRequest(unittest.TestCase):
    def setUp(self):
        self.client = RocqClient(rocq_mcp_path="rocq-mcp", timeout=10)
        self.client.process = MagicMock()
        self.client.process.stdin = MagicMock()
        self.client.process.stdout = MagicMock()
        self.client.process.stderr = MagicMock()
        # Prevent real thread creation
        with patch("threading.Thread"):
            self.client._reader_thread = MagicMock()
            self.client._reader_thread.is_alive.return_value = True

    def test_send_request_success(self):
        response = {"data": "ok"}
        with patch("queue.Queue") as MockQueue:
            mock_q = MockQueue.return_value
            mock_q.get.return_value = {"result": response}
            result = self.client._send_request("test/method", {"arg": "val"})
        self.assertEqual(result, response)

    def test_send_request_error_response(self):
        error_response = {
            "error": {"code": -32000, "message": "Something went wrong"}
        }
        with patch("queue.Queue") as MockQueue:
            mock_q = MockQueue.return_value
            mock_q.get.return_value = error_response
            with self.assertRaises(RocqClientError) as cm:
                self.client._send_request("test/method", {})
            self.assertIn("Something went wrong", str(cm.exception))

    def test_send_request_timeout(self):
        with patch("queue.Queue") as MockQueue:
            mock_q = MockQueue.return_value
            mock_q.get.side_effect = Empty
            with self.assertRaises(RocqClientError) as cm:
                self.client._send_request("test/method", {})
            self.assertIn("Timeout", str(cm.exception))


class TestTools(unittest.TestCase):
    """Tool tests now mock _call_tool directly – no slow I/O or queues."""

    def setUp(self):
        self.client = RocqClient(rocq_mcp_path="rocq-mcp", timeout=10)

    def test_compile_file(self):
        with patch.object(self.client, "_call_tool") as mock_call:
            mock_call.return_value = {"success": True}
            result = self.client.compile_file(Path("test.v"))
            self.assertTrue(result["success"])

    def test_verify(self):
        with patch.object(self.client, "_call_tool") as mock_call:
            mock_call.return_value = {"verified": True}
            result = self.client.verify(Path("test.v"), "theorem")
            self.assertEqual(result, {"verified": True})

    def test_start_session(self):
        with patch.object(self.client, "_call_tool") as mock_call:
            mock_call.return_value = {
                "state_id": "1",
                "goals": "goal text"
            }
            state_id, goals = self.client.start_session(Path("test.v"), "theorem")
            self.assertEqual(state_id, "1")
            self.assertEqual(goals, ["goal text"])

    def test_check(self):
        with patch.object(self.client, "_call_tool") as mock_call:
            mock_call.return_value = {"new_state_id": "2", "goals": ["subgoal"]}
            result = self.client.check("1", "auto.")
            self.assertEqual(result["new_state_id"], "2")


class TestErrorExtraction(unittest.TestCase):
    def setUp(self):
        self.client = RocqClient(rocq_mcp_path="rocq-mcp")

    def test_extract_error_from_simple_error(self):
        resp = {"error": "something bad"}
        err = self.client._extract_error_from_response(resp)
        self.assertEqual(err, "something bad")

    def test_extract_error_from_isError(self):
        resp = {"isError": True, "error": "bad"}
        err = self.client._extract_error_from_response(resp)
        self.assertEqual(err, "bad")

    def test_extract_error_from_structured_content(self):
        resp = {
            "structuredContent": {
                "error": "structured error"
            }
        }
        err = self.client._extract_error_from_response(resp)
        self.assertEqual(err, "structured error")

    def test_extract_error_from_nested(self):
        resp = {
            "content": [
                {"type": "text", "text": json.dumps({"error": "deep error"})}
            ]
        }
        err = self.client._extract_error_from_response(resp)
        self.assertEqual(err, "deep error")

    def test_no_error(self):
        resp = {"result": "ok"}
        err = self.client._extract_error_from_response(resp)
        self.assertIsNone(err)


class TestPublicAPI(unittest.TestCase):
    def test_start_session_goals_not_list(self):
        """When rocq‑mcp returns a string for goals, it is normalized to a list."""
        client = RocqClient(rocq_mcp_path="rocq-mcp")
        with patch.object(client, "_call_tool") as mock_call:
            mock_call.return_value = {
                "state_id": "5",
                "goals": "single goal string"
            }
            state_id, goals = client.start_session(Path("test.v"), "theorem")
            self.assertEqual(state_id, "5")
            self.assertEqual(goals, ["single goal string"])

    def test_start_session_missing_state_id(self):
        client = RocqClient(rocq_mcp_path="rocq-mcp")
        with patch.object(client, "_call_tool") as mock_call:
            mock_call.return_value = {"goals": []}
            with self.assertRaises(RocqClientError):
                client.start_session(Path("test.v"), "theorem")


if __name__ == "__main__":
    unittest.main()
