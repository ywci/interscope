# tests/unit/test_acl2_repair.py
#
# Unit tests for ACL2 repair loops (hint repair and defun repair).  The LLM
# and ACL2 clients are both mocked; no real LLM or ACL2 process is used.

from unittest.mock import MagicMock
from isir.backends.acl2_client import ACL2ClientError
from isir.verification.proof.proof import ProofResult
from isir.verification.proof.acl2.repair import (
    repair_acl2_hints,
    repair_acl2_defun,
    _build_hint_repair_prompt,
    _build_defun_repair_prompt,
    _extract_defun_body,
    _build_defthm_string,
    _build_defun_string,
    _format_hints,
)


class FakeLLMClient:
    """LLM client returning a fixed script / body."""

    def __init__(self, response="", responses=None):
        self._default = response
        self._queue = list(responses) if responses is not None else None
        self.calls = []

    def generate(self, prompt, **kwargs):
        self.calls.append(prompt)
        if self._queue is not None:
            return self._queue.pop(0) if self._queue else self._default
        return self._default


def _make_acl2_client():
    client = MagicMock()
    client.save_checkpoint.return_value = {"success": True}
    client.restore_checkpoint.return_value = {"success": True}
    return client


HINT_RESPONSE = '(("Goal" :induct t))'


def test_repair_hints_succeeds_on_first_attempt():
    llm = FakeLLMClient(response=HINT_RESPONSE)
    acl2 = _make_acl2_client()
    acl2.defthm.return_value = {"success": True, "output": "Q.E.D."}

    result = repair_acl2_hints(
        "my-thm", "(implies (full st) (not (enqueue st)))", "boom",
        llm, acl2,
    )

    assert isinstance(result, ProofResult)
    assert result.success is True
    assert result.iterations == 1
    assert result.backend == "acl2"
    assert "defthm my-thm" in result.proof_script
    assert result.metadata["hints"] == ['(("Goal" :induct t))']

    acl2.defthm.assert_called_once_with(
        "my-thm", "(implies (full st) (not (enqueue st)))", ['(("Goal" :induct t))']
    )
    acl2.save_checkpoint.assert_called_once()
    assert acl2.save_checkpoint.call_args[0][0].startswith("repair_my-thm_")
    acl2.restore_checkpoint.assert_not_called()


def test_repair_hints_succeeds_after_failure():
    llm = FakeLLMClient(response=HINT_RESPONSE)
    acl2 = _make_acl2_client()
    acl2.defthm.side_effect = [
        {"success": False, "output": "failed"},
        {"success": True, "output": "Q.E.D."},
    ]

    result = repair_acl2_hints(
        "my-thm", "stmt", "boom", llm, acl2, max_attempts=3,
    )

    assert result.success is True
    assert result.iterations == 2
    assert acl2.defthm.call_count == 2
    acl2.save_checkpoint.assert_called_once()
    acl2.restore_checkpoint.assert_called_once()


def test_repair_hints_exhausts_attempts():
    llm = FakeLLMClient(response=HINT_RESPONSE)
    acl2 = _make_acl2_client()
    acl2.defthm.return_value = {"success": False, "output": "no"}

    result = repair_acl2_hints("my-thm", "stmt", "boom", llm, acl2, max_attempts=3)

    assert result.success is False
    assert result.iterations == 3
    assert "Hint repair exhausted after 3 attempts" in result.error_message
    assert acl2.defthm.call_count == 3


def test_repair_hints_llm_returns_no_usable_hints():
    llm = FakeLLMClient(response="garbage without hints")
    acl2 = _make_acl2_client()

    result = repair_acl2_hints("my-thm", "stmt", "boom", llm, acl2, max_attempts=2)

    assert result.success is False
    assert acl2.defthm.call_count == 0


def test_repair_hints_handles_acl2_client_error():
    llm = FakeLLMClient(response=HINT_RESPONSE)
    acl2 = _make_acl2_client()
    acl2.defthm.side_effect = ACL2ClientError("connection lost")

    result = repair_acl2_hints("my-thm", "stmt", "boom", llm, acl2, max_attempts=2)

    assert result.success is False
    assert acl2.defthm.call_count == 2


def test_repair_hints_without_checkpoints():
    llm = FakeLLMClient(response=HINT_RESPONSE)
    acl2 = _make_acl2_client()
    acl2.defthm.return_value = {"success": True, "output": "Q.E.D."}

    result = repair_acl2_hints(
        "my-thm", "stmt", "boom", llm, acl2, use_checkpoints=False,
    )

    assert result.success is True
    acl2.save_checkpoint.assert_not_called()
    acl2.restore_checkpoint.assert_not_called()


def test_repair_defun_succeeds_with_plain_body():
    llm = FakeLLMClient(response="(+ x 1)")
    acl2 = _make_acl2_client()
    acl2.defun.return_value = {"success": True, "output": "ok"}

    result = repair_acl2_defun("foo", ["x"], "(+ x 0)", "err", llm, acl2)

    assert result.success is True
    assert result.iterations == 1
    assert "defun foo" in result.proof_script
    acl2.defun.assert_called_once_with("foo", ["x"], "(+ x 1)", None)


def test_repair_defun_extracts_body_from_full_defun():
    llm = FakeLLMClient(response="(defun foo (x) (+ x 1))")
    acl2 = _make_acl2_client()
    acl2.defun.return_value = {"success": True, "output": "ok"}

    result = repair_acl2_defun("foo", ["x"], "(+ x 0)", "err", llm, acl2)

    assert result.success is True
    acl2.defun.assert_called_once_with("foo", ["x"], "(+ x 1)", None)


def test_repair_defun_with_guard():
    llm = FakeLLMClient(response="(+ x 1)")
    acl2 = _make_acl2_client()
    acl2.defun.return_value = {"success": True, "output": "ok"}

    result = repair_acl2_defun(
        "foo", ["x"], "(+ x 0)", "err", llm, acl2, guard="(natp x)"
    )

    assert result.success is True
    assert "xargs :guard (natp x)" in result.proof_script
    acl2.defun.assert_called_once_with("foo", ["x"], "(+ x 1)", "(natp x)")


def test_repair_defun_exhausts_when_llm_empty():
    llm = FakeLLMClient(response="")
    acl2 = _make_acl2_client()

    result = repair_acl2_defun("foo", ["x"], "(+ x 0)", "err", llm, acl2)

    assert result.success is False
    assert acl2.defun.call_count == 0


def test_repair_defun_handles_llm_exception():
    llm = MagicMock()
    llm.generate.side_effect = RuntimeError("llm down")
    acl2 = _make_acl2_client()

    result = repair_acl2_defun("foo", ["x"], "(+ x 0)", "err", llm, acl2)

    assert result.success is False
    assert acl2.defun.call_count == 0


def test_repair_defun_handles_acl2_client_error():
    llm = FakeLLMClient(response="(+ x 1)")
    acl2 = _make_acl2_client()
    acl2.defun.side_effect = ACL2ClientError("boom")

    result = repair_acl2_defun("foo", ["x"], "(+ x 0)", "err", llm, acl2)

    assert result.success is False
    assert acl2.defun.call_count == 2


def test_build_hint_repair_prompt_delegates():
    prompt = _build_hint_repair_prompt("stmt", "err", ['("Goal" :induct t)'], "ctx")
    assert "stmt" in prompt
    assert "err" in prompt
    assert '("Goal" :induct t)' in prompt
    assert "ctx" in prompt


def test_build_defun_repair_prompt_without_guard():
    prompt = _build_defun_repair_prompt("foo", ["x"], "(+ x 1)", None, "err")
    assert "FUNCTION: foo" in prompt
    assert "ARGUMENTS: (x)" in prompt
    assert "(+ x 1)" in prompt
    assert "err" in prompt
    assert "GUARD:" not in prompt


def test_build_defun_repair_prompt_with_guard():
    prompt = _build_defun_repair_prompt("foo", ["x"], "(+ x 1)", "(natp x)", "err")
    assert "GUARD: (natp x)" in prompt


def test_extract_defun_body_plain_body():
    assert _extract_defun_body("(+ x 1)") == "(+ x 1)"


def test_extract_defun_body_from_full_defun():
    assert _extract_defun_body("(defun foo (x) (+ x 1))") == "(+ x 1)"


def test_extract_defun_body_nested_args():
    assert _extract_defun_body("(defun foo ((x y)) (+ x y))") == "(+ x y)"


def test_extract_defun_body_empty_returns_none():
    assert _extract_defun_body("") is None
    assert _extract_defun_body("   ") is None


def test_build_defthm_string_with_and_without_hints():
    assert _build_defthm_string("t", "stmt", ['("Goal" :induct t)']) == (
        '(defthm t\n  stmt\n  :hints (("Goal" :induct t)))'
    )
    assert _build_defthm_string("t", "stmt", []) == "(defthm t\n  stmt)"


def test_build_defun_string_with_and_without_guard():
    assert _build_defun_string("foo", ["x"], "(+ x 1)") == (
        "(defun foo (x)\n  (+ x 1))"
    )
    assert _build_defun_string("foo", ["x"], "(+ x 1)", "(natp x)") == (
        "(defun foo (x)\n  (declare (xargs :guard (natp x)))\n  (+ x 1))"
    )


def test_format_hints():
    assert _format_hints([]) == "none"
    assert _format_hints(["a"]) == "a"
    assert _format_hints(["a", "b"]) == "a b"
