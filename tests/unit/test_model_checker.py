# tests/unit/test_model_checker.py
#
# Unit tests for the model-checking wrapper (model_checker.py).
# Covers SymbiYosys script generation, output parsing, and end-to-end execution.

import subprocess
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from specir.verification.model_checker import (
    run_model_check,
    ModelCheckError,
    _write_sby_file,
    _parse_sby_output,
)


class TestSBYScript:
    def test_bmc_script(self, tmp_path):
        """BMC mode produces 'mode bmc' and correct depth."""
        sby = tmp_path / "test.sby"
        _write_sby_file(
            sby,
            Path("/rtl/test.v"),
            Path("/rtl/test_assert.sv"),
            "top",
            "bmc",
            42,
            timeout=100,
        )
        content = sby.read_text()
        assert "mode bmc" in content
        assert "depth 42" in content
        assert "timeout 100" in content
        assert "read -formal" in content
        assert "read -sv" in content
        assert "prep -top top" in content
        assert "smtbmc z3" in content

    def test_induction_script(self, tmp_path):
        """Induction mode produces 'mode prove'."""
        sby = tmp_path / "test.sby"
        _write_sby_file(
            sby,
            Path("/rtl/test.v"),
            Path("/rtl/test_assert.sv"),
            "top",
            "induction",
            1000,
            timeout=200,
        )
        content = sby.read_text()
        assert "mode prove" in content
        assert "depth 1000" in content
        assert "timeout 200" in content

    def test_files_listed(self, tmp_path):
        """The [files] section contains both RTL and assertions paths."""
        sby = tmp_path / "test.sby"
        _write_sby_file(
            sby,
            Path("/rtl/test.v"),
            Path("/rtl/test_assert.sv"),
            "top",
            "bmc",
            10,
            timeout=50,
        )
        content = sby.read_text()
        assert "/rtl/test.v" in content
        assert "/rtl/test_assert.sv" in content


class TestParseOutput:
    def test_pass(self):
        out = "some log\nDONE (PASS, rc=0)\nmore log"
        status, trace = _parse_sby_output(out, Path("/tmp"))
        assert status == "proved"
        assert trace is None

    def test_fail_with_trace(self, tmp_path):
        """When a counterexample trace exists, it is returned."""
        trace_dir = tmp_path / "design" / "engine_0"
        trace_dir.mkdir(parents=True)
        trace_file = trace_dir / "trace.vcd"
        trace_file.write_text("dummy")
        out = "DONE (FAIL, rc=1)"
        status, trace = _parse_sby_output(out, tmp_path)
        assert status == "disproved"
        assert trace is not None
        assert trace.name == "trace.vcd"

    def test_fail_no_trace(self):
        """No trace file → still disproved but trace is None."""
        out = "DONE (FAIL, rc=1)"
        status, trace = _parse_sby_output(out, Path("/tmp/nonexistent"))
        assert status == "disproved"
        assert trace is None

    def test_unknown(self):
        out = "DONE (UNKNOWN, rc=2)"
        status, _ = _parse_sby_output(out, Path("/tmp"))
        assert status == "inconclusive"

    def test_no_summary_line(self):
        """If there is no 'DONE' line, status should be 'error'."""
        out = "random log without summary"
        status, _ = _parse_sby_output(out, Path("/tmp"))
        assert status == "error"


class TestRunModelCheck:
    @patch("subprocess.run")
    @patch("shutil.which", return_value="/usr/bin/sby")
    def test_success(self, mock_which, mock_run, tmp_path):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="DONE (PASS, rc=0)", stderr=""
        )
        result = run_model_check(
            rtl_path=tmp_path / "test.v",
            assertions_path=tmp_path / "test.sv",
            top_module="top",
            engine="bmc",
            depth=10,
        )
        assert result["success"] is True
        assert result["status"] == "proved"
        assert result["error"] is None

    @patch("subprocess.run")
    @patch("shutil.which", return_value="/usr/bin/sby")
    def test_failure(self, mock_which, mock_run, tmp_path):
        mock_run.return_value = MagicMock(
            returncode=1, stdout="DONE (FAIL, rc=1)", stderr=""
        )
        result = run_model_check(
            rtl_path=tmp_path / "test.v",
            assertions_path=tmp_path / "test.sv",
            top_module="top",
            engine="bmc",
            depth=10,
        )
        assert result["success"] is False
        assert result["status"] == "disproved"

    @patch("subprocess.run")
    @patch("shutil.which", return_value="/usr/bin/sby")
    def test_timeout(self, mock_which, mock_run, tmp_path):
        mock_run.side_effect = subprocess.TimeoutExpired("sby", 330)
        result = run_model_check(
            rtl_path=tmp_path / "test.v",
            assertions_path=tmp_path / "test.sv",
            top_module="top",
            engine="bmc",
            depth=10,
        )
        assert result["success"] is False
        assert result["status"] == "inconclusive"
        assert "timed out" in result["error"].lower()

    def test_missing_tool(self):
        with patch("shutil.which", return_value=None):
            with pytest.raises(ModelCheckError, match="SymbiYosys"):
                run_model_check(
                    rtl_path=Path("/tmp/test.v"),
                    assertions_path=Path("/tmp/test.sv"),
                    top_module="top",
                )

    @patch("subprocess.run")
    @patch("shutil.which", return_value="/usr/bin/sby")
    def test_extra_args(self, mock_which, mock_run, tmp_path):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="DONE (PASS, rc=0)", stderr=""
        )
        run_model_check(
            rtl_path=tmp_path / "test.v",
            assertions_path=tmp_path / "test.sv",
            top_module="top",
            extra_args=["--smtc", "z3"],
        )
        call_args = mock_run.call_args[0][0]
        assert "--smtc" in call_args
        assert "z3" in call_args
