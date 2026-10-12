# tests/unit/test_acl2_client.py
#
# Unit tests for the ACL2 MCP client.  The underlying stdio transport and
# ClientSession are mocked so that no real ACL2 MCP process is started.
# Sync methods are exercised with mocked internals, and the async helpers
# are driven directly with asyncio.run against a mocked session.

import pytest
import asyncio
import json
import warnings

warnings.simplefilter("ignore", RuntimeWarning)

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from isir.backends.acl2_client import (
    ACL2Client,
    ACL2ClientError,
    get_acl2_client_from_config,
)

pytestmark = pytest.mark.filterwarnings("ignore::RuntimeWarning")


def _make_tool_result(text):
    result = MagicMock()
    result.content = [MagicMock()]
    result.content[0].text = text
    return result

def test_contains_error_detects_indicators():
    assert ACL2Client._contains_error("Error: something") is True
    assert ACL2Client._contains_error("ACL2 Error in foo") is True
    assert ACL2Client._contains_error("*** boom ***") is True


def test_contains_error_clean_output():
    assert ACL2Client._contains_error("ok") is False
    assert ACL2Client._contains_error("Q.E.D.") is False


def test_contains_error_empty():
    assert ACL2Client._contains_error("") is False
    assert ACL2Client._contains_error(None) is False


def test_send_requires_start():
    client = ACL2Client()
    with pytest.raises(ACL2ClientError):
        client.send("(foo)")


def test_load_file_requires_start():
    client = ACL2Client()
    with pytest.raises(ACL2ClientError):
        client.load_file("/tmp/x.lisp")


def test_defthm_requires_start():
    client = ACL2Client()
    with pytest.raises(ACL2ClientError):
        client.defthm("t", "stmt", [])


def test_save_checkpoint_requires_start():
    client = ACL2Client()
    with pytest.raises(ACL2ClientError):
        client.save_checkpoint("cp")


def test_restore_checkpoint_requires_start():
    client = ACL2Client()
    with pytest.raises(ACL2ClientError):
        client.restore_checkpoint("cp")


def test_run_async_requires_running_loop():
    client = ACL2Client()
    client._loop = None
    with pytest.raises(ACL2ClientError):
        client._run_async(MagicMock())


def test_send_returns_result():
    client = ACL2Client()
    client._started = True
    with patch.object(client, "_send_async", new=Mock(return_value="payload")), \
            patch.object(client, "_run_async", return_value="out") as mock_run:
        assert client.send("(foo)") == "out"
    mock_run.assert_called_once_with("payload")


def test_load_file_success():
    client = ACL2Client()
    client._started = True
    with patch.object(client, "send", return_value="loaded ok") as mock_send:
        result = client.load_file("/tmp/x.lisp")
    assert result == {"success": True, "output": "loaded ok"}
    mock_send.assert_called_once_with('(ld "/tmp/x.lisp")')


def test_load_file_accepts_path():
    client = ACL2Client()
    client._started = True
    with patch.object(client, "send", return_value="ok") as mock_send:
        client.load_file(Path("/tmp/y.lisp"))
    mock_send.assert_called_once_with('(ld "/tmp/y.lisp")')


def test_load_file_detects_error():
    client = ACL2Client()
    client._started = True
    with patch.object(client, "send", return_value="ACL2 Error: no file") as mock_send:
        result = client.load_file("/tmp/x.lisp")
    assert result["success"] is False
    assert result["output"] == "ACL2 Error: no file"


def test_load_file_propagates_exception_into_error():
    client = ACL2Client()
    client._started = True
    with patch.object(client, "send", side_effect=RuntimeError("boom")):
        result = client.load_file("/tmp/x.lisp")
    assert result == {"success": False, "output": "", "error": "boom"}


def test_defun_builds_form_and_detects_success():
    client = ACL2Client()
    with patch.object(client, "send", return_value="ok") as mock_send:
        result = client.defun("f", ["x"], "(+ x 1)")
    assert result["success"] is True
    mock_send.assert_called_once_with("(defun f (x)\n  (+ x 1))")


def test_defun_with_guard_and_mode():
    client = ACL2Client()
    with patch.object(client, "send", return_value="ok") as mock_send:
        client.defun(
            "f", ["x"], "(+ x 1)",
            guard="(natp x)", mode=":program", verify_guards=False,
        )
    form = mock_send.call_args[0][0]
    assert ":guard (natp x)" in form
    assert ":verify-guards nil" in form
    assert ":mode :program" in form


def test_defun_detects_error():
    client = ACL2Client()
    with patch.object(client, "send", return_value="Error: bad"):
        result = client.defun("f", ["x"], "(+ x 1)")
    assert result["success"] is False


def test_defthm_returns_run_async_result():
    client = ACL2Client()
    client._started = True
    with patch.object(client, "_defthm_async", new=Mock(return_value="coro")) as mock_defthm, \
            patch.object(
                client, "_run_async",
                return_value={"success": True, "output": "Q.E.D."},
            ) as mock_run:
        result = client.defthm("t", "stmt", ['("Goal" :induct t)'])
    assert result == {"success": True, "output": "Q.E.D."}
    mock_defthm.assert_called_once_with("t", "stmt", ['("Goal" :induct t)'])
    mock_run.assert_called_once_with("coro")


def test_save_checkpoint_returns_result():
    client = ACL2Client()
    client._started = True
    with patch.object(client, "_save_checkpoint_async", new=Mock(return_value="coro")) as mock_save, \
            patch.object(client, "_run_async", return_value={"success": True}) as mock_run:
        assert client.save_checkpoint("cp") == {"success": True}
    mock_save.assert_called_once_with("cp")
    mock_run.assert_called_once_with("coro")


def test_restore_checkpoint_returns_result():
    client = ACL2Client()
    client._started = True
    with patch.object(client, "_restore_checkpoint_async", new=Mock(return_value="coro")) as mock_restore, \
            patch.object(client, "_run_async", return_value={"success": True}) as mock_run:
        assert client.restore_checkpoint("cp") == {"success": True}
    mock_restore.assert_called_once_with("cp")
    mock_run.assert_called_once_with("coro")


def test_undo():
    client = ACL2Client()
    with patch.object(client, "send", return_value="ok") as mock_send:
        result = client.undo()
    assert result["success"] is True
    mock_send.assert_called_once_with(":u")


def test_undo_back_to():
    client = ACL2Client()
    with patch.object(client, "send", return_value="ok") as mock_send:
        client.undo_back_to("foo")
    mock_send.assert_called_once_with("(ubt! 'foo)")


def test_include_book():
    client = ACL2Client()
    with patch.object(client, "send", return_value="ok") as mock_send:
        client.include_book("mylib")
    mock_send.assert_called_once_with('(include-book "mylib")')


def test_certify_book():
    client = ACL2Client()
    with patch.object(client, "send", return_value="ok") as mock_send:
        client.certify_book("mylib")
    mock_send.assert_called_once_with('(certify-book "mylib")')


def test_send_async_returns_text():
    client = ACL2Client()
    session = AsyncMock()
    session.call_tool = AsyncMock(return_value=_make_tool_result("hello"))
    client.session = session

    out = asyncio.run(client._send_async("(foo)"))

    assert out == "hello"
    session.call_tool.assert_awaited_once_with(
        "evaluate", arguments={"form": "(foo)"}
    )


def test_send_async_wraps_exception():
    client = ACL2Client()
    session = AsyncMock()
    session.call_tool = AsyncMock(side_effect=RuntimeError("boom"))
    client.session = session

    with pytest.raises(ACL2ClientError) as exc:
        asyncio.run(client._send_async("(foo)"))

    assert "ACL2 evaluate failed" in str(exc.value)
    assert "boom" in str(exc.value)


def test_call_tool_parses_json():
    client = ACL2Client()
    session = AsyncMock()
    session.call_tool = AsyncMock(return_value=_make_tool_result(
        json.dumps({"success": True, "output": "done", "error": None})
    ))
    client.session = session

    result = asyncio.run(client._call_tool("prove", {"a": 1}))

    assert result == {"success": True, "output": "done", "error": None}
    session.call_tool.assert_awaited_once_with("prove", arguments={"a": 1})


def test_call_tool_non_json_error():
    client = ACL2Client()
    session = AsyncMock()
    session.call_tool = AsyncMock(return_value=_make_tool_result("ACL2 Error: xyz"))
    client.session = session

    result = asyncio.run(client._call_tool("prove", {}))

    assert result["success"] is False
    assert result["output"] == "ACL2 Error: xyz"
    assert result["error"] == "ACL2 Error: xyz"


def test_call_tool_non_json_clean_output():
    client = ACL2Client()
    session = AsyncMock()
    session.call_tool = AsyncMock(return_value=_make_tool_result("Q.E.D."))
    client.session = session

    result = asyncio.run(client._call_tool("prove", {}))

    assert result == {"success": True, "output": "Q.E.D.", "error": None}


def test_call_tool_empty_content():
    client = ACL2Client()
    session = AsyncMock()
    empty = MagicMock()
    empty.content = []
    session.call_tool = AsyncMock(return_value=empty)
    client.session = session

    result = asyncio.run(client._call_tool("prove", {}))

    assert result == {
        "success": False,
        "output": "",
        "error": "Empty response from MCP tool",
    }


def test_call_tool_swallows_exception():
    client = ACL2Client()
    session = AsyncMock()
    session.call_tool = AsyncMock(side_effect=Exception("boom"))
    client.session = session

    result = asyncio.run(client._call_tool("prove", {}))

    assert result == {"success": False, "output": "", "error": "boom"}


def test_defthm_async_success_via_prove_tool():
    client = ACL2Client()
    with patch.object(
        client, "_call_tool",
        new=AsyncMock(return_value={"success": True, "output": "Q.E.D."}),
    ) as mock_call:
        result = asyncio.run(
            client._defthm_async("t", "(equal 1 1)", ['("Goal" :induct t)'])
        )

    assert result == {"success": True, "output": "Q.E.D."}
    mock_call.assert_awaited_once_with(
        "prove",
        {"theorem": "(equal 1 1)", "name": "t", "hints": ['("Goal" :induct t)']},
    )


def test_defthm_async_omits_hints_when_none():
    client = ACL2Client()
    with patch.object(
        client, "_call_tool",
        new=AsyncMock(return_value={"success": True, "output": "Q.E.D."}),
    ) as mock_call:
        asyncio.run(client._defthm_async("t", "(equal 1 1)", None))

    assert mock_call.await_args_list[0].args[1] == {
        "theorem": "(equal 1 1)", "name": "t",
    }


def test_defthm_async_falls_back_to_evaluate_on_failure():
    client = ACL2Client()
    with patch.object(
        client, "_call_tool",
        new=AsyncMock(side_effect=[
            {"success": False, "output": "", "error": "prove failed"},
            {"success": True, "output": "Q.E.D.", "error": None},
        ]),
    ) as mock_call:
        result = asyncio.run(client._defthm_async("t", "(equal 1 1)", None))

    assert result["success"] is True
    assert result["output"] == "Q.E.D."
    assert mock_call.await_count == 2
    assert mock_call.await_args_list[0].args[0] == "prove"
    assert mock_call.await_args_list[1].args[0] == "evaluate"


def test_save_checkpoint_async():
    client = ACL2Client()
    with patch.object(
        client, "_call_tool", new=AsyncMock(return_value={"success": True})
    ) as mock_call:
        result = asyncio.run(client._save_checkpoint_async("cp"))

    assert result == {"success": True}
    mock_call.assert_awaited_once_with("save_checkpoint", {"name": "cp"})


def test_restore_checkpoint_async():
    client = ACL2Client()
    with patch.object(
        client, "_call_tool", new=AsyncMock(return_value={"success": True})
    ) as mock_call:
        result = asyncio.run(client._restore_checkpoint_async("cp"))

    assert result == {"success": True}
    mock_call.assert_awaited_once_with("restore_checkpoint", {"name": "cp"})


def test_start_and_stop_with_mocked_transport():
    client = ACL2Client(mcp_path="fake-acl2", init_commands=["(set-ignore-ok t)"])

    session = AsyncMock()
    session.initialize = AsyncMock()
    session.call_tool = AsyncMock(return_value=MagicMock())

    with patch("isir.backends.acl2_client.stdio_client") as mock_stdio, \
            patch("isir.backends.acl2_client.ClientSession") as mock_session_cls:
        read, write = MagicMock(), MagicMock()
        stdio_ctx = mock_stdio.return_value
        stdio_ctx.__aenter__ = AsyncMock(return_value=(read, write))
        stdio_ctx.__aexit__ = AsyncMock(return_value=None)

        session_ctx = mock_session_cls.return_value
        session_ctx.__aenter__ = AsyncMock(return_value=session)
        session_ctx.__aexit__ = AsyncMock(return_value=None)

        client.start()
        try:
            assert client._started is True
            assert client.session is session
            session.initialize.assert_awaited_once()
            session.call_tool.assert_awaited_once_with(
                "evaluate", arguments={"form": "(set-ignore-ok t)"}
            )
        finally:
            client.stop()

    assert client._started is False
    assert client.session is None


def test_start_is_idempotent():
    client = ACL2Client()
    with patch("isir.backends.acl2_client.stdio_client") as mock_stdio, \
            patch("isir.backends.acl2_client.ClientSession") as mock_session_cls:
        read, write = MagicMock(), MagicMock()
        mock_stdio.return_value.__aenter__ = AsyncMock(return_value=(read, write))
        mock_stdio.return_value.__aexit__ = AsyncMock(return_value=None)

        session = AsyncMock()
        session.initialize = AsyncMock()
        session.call_tool = AsyncMock(return_value=MagicMock())
        mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=session)
        mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        client.start()
        try:
            first_thread = client._thread
            client.start()
            assert client._thread is first_thread
        finally:
            client.stop()


def test_get_acl2_client_from_config_explicit():
    config = {
        "provers": {
            "acl2": {
                "mcp_path": "my-acl2",
                "mcp_timeout": 12,
                "init_commands": ["(in-package \"ACL2\")"],
            }
        }
    }
    client = get_acl2_client_from_config(config)
    assert client.mcp_path == "my-acl2"
    assert client.timeout == 12
    assert client.init_commands == ['(in-package "ACL2")']


def test_get_acl2_client_from_config_defaults():
    client = get_acl2_client_from_config({"provers": {}})
    assert client.mcp_path == "acl2-mcp"
    assert client.timeout == 30
    assert client.init_commands == []


def test_get_acl2_client_from_config_none_uses_global_config():
    with patch("isir.backends.acl2_client.get_config", return_value={
        "provers": {"acl2": {"mcp_path": "global-acl2", "mcp_timeout": 5}}
    }):
        client = get_acl2_client_from_config(None)
    assert client.mcp_path == "global-acl2"
    assert client.timeout == 5
