# tests/unit/test_verify.py
#
# Unit tests for the `specir verify` CLI command.
# Covers theorem proving (Koika/ACL2) and model-checking obligations.

import json
import sys
import argparse
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, call

from specir.cli.verify import (
    verify_spec,
    _setup_arg_parser,
    _canonical_backend,
    _finish_summary,
    _extract_acl2_statement,
    _safe_register_evidence,
    _safe_register_mc_evidence,
    _generate_acl2_from_module
)
from specir.verification.proof.proof import ProofResult
from specir.verification.proof.proof_skill import LLMProofSkill
from specir.verification.model_checker import ModelCheckError


def _make_minimal_spec_module(name="test"):
    from specir.dialects.spec_ir import SpecModule, SpecStateOp, SpecRuleOp, SpecPropertyOp
    mod = SpecModule(name=name)
    mod.state_ops.append(SpecStateOp(state_name="x", kind="register", data_type="bits<8>", initial=0))
    mod.rule_ops.append(SpecRuleOp(rule_name="nop", condition="true", actions=[]))
    mod.property_ops.append(SpecPropertyOp(
        prop_name="simple_prop",
        kind="safety",
        expression={"kind": "always", "operand": "(eq (read x) 0)"}
    ))
    return mod


class TestCanonicalBackend:
    def test_koika_variants(self):
        assert _canonical_backend("koika") == "koika"
        assert _canonical_backend("kōika") == "koika"
        assert _canonical_backend("KOIKA") == "koika"
        assert _canonical_backend("koik") == "koika"

    def test_acl2(self):
        assert _canonical_backend("acl2") == "acl2"
        assert _canonical_backend("ACL2") == "acl2"

    def test_model_checking(self):
        assert _canonical_backend("model_checking") == "model_checking"
        assert _canonical_backend("modelchecking") == "model_checking"
        assert _canonical_backend("mc") == "model_checking"

    def test_none(self):
        assert _canonical_backend(None) is None
        assert _canonical_backend("unknown") is None


class TestVerifyTheoremProving:
    @patch("specir.cli.verify.LLMProofSkill")
    @patch("specir.cli.verify.convert_ast_to_spec_module")
    @patch("specir.cli.verify.parse_specir")
    @patch("specir.cli.verify.validate_specir_file")
    @patch("specir.cli.verify.load_config", return_value={"directories": {"build": "build"}, "provers": {"koika": {"prove": {}}}})
    def test_koika_proof_passes(self, mock_cfg, mock_val, mock_parse, mock_conv, mock_skill, tmp_path):
        # Setup
        mod = _make_minimal_spec_module()
        mod.proof_obligations = [{"property": "simple_prop", "engine": "theorem_proving", "backend": "koika"}]
        mock_conv.return_value = mod
        mock_ast = MagicMock()
        mock_ast.module = MagicMock()
        mock_parse.return_value = mock_ast

        mock_skill_instance = MagicMock()
        mock_skill.return_value = mock_skill_instance
        mock_skill_instance.prove.return_value = ProofResult(success=True, proof_script="Proof. trivial. Qed.")

        with patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.read_text", return_value="dummy"):
            args = argparse.Namespace(
                input=str(tmp_path / "test.specir"),
                backend=None, out_dir=str(tmp_path), max_attempts=None,
                report=None, no_llm=False, show_proof=False, debug=False
            )
            ret = verify_spec(args)

        assert ret == 0
        mock_skill_instance.prove.assert_called_once()

    @patch("specir.cli.verify.LLMProofSkill")
    @patch("specir.cli.verify.convert_ast_to_spec_module")
    @patch("specir.cli.verify.parse_specir")
    @patch("specir.cli.verify.validate_specir_file")
    @patch("specir.cli.verify.load_config", return_value={"directories": {"build": "build"}, "provers": {"koika": {"prove": {}}}})
    def test_koika_proof_fails(self, mock_cfg, mock_val, mock_parse, mock_conv, mock_skill, tmp_path):
        mod = _make_minimal_spec_module()
        mod.proof_obligations = [{"property": "simple_prop", "engine": "theorem_proving", "backend": "koika"}]
        mock_conv.return_value = mod
        mock_parse.return_value = MagicMock(module=MagicMock())

        mock_skill_instance = MagicMock()
        mock_skill.return_value = mock_skill_instance
        mock_skill_instance.prove.return_value = ProofResult(success=False, error_message="proof failed")

        with patch("pathlib.Path.exists", return_value=True):
            args = argparse.Namespace(
                input=str(tmp_path / "test.specir"), backend=None, out_dir=str(tmp_path),
                max_attempts=None, report=None, no_llm=False, show_proof=False, debug=False
            )
            ret = verify_spec(args)

        assert ret == 1

    @patch("specir.cli.verify.LLMProofSkill")
    @patch("specir.cli.verify.convert_ast_to_spec_module")
    @patch("specir.cli.verify.parse_specir")
    @patch("specir.cli.verify.validate_specir_file")
    @patch("specir.cli.verify.load_config", return_value={"directories": {"build": "build"}, "provers": {"koika": {"prove": {}}}})
    def test_backend_filtering(self, mock_cfg, mock_val, mock_parse, mock_conv, mock_skill, tmp_path):
        mod = _make_minimal_spec_module()
        mod.proof_obligations = [
            {"property": "prop_a", "engine": "theorem_proving", "backend": "koika"},
            {"property": "prop_b", "engine": "theorem_proving", "backend": "acl2"}
        ]
        mock_conv.return_value = mod
        mock_parse.return_value = MagicMock(module=MagicMock())

        mock_skill_instance = MagicMock()
        mock_skill.return_value = mock_skill_instance
        mock_skill_instance.prove.return_value = ProofResult(success=True)

        with patch("pathlib.Path.exists", return_value=True):
            args = argparse.Namespace(
                input=str(tmp_path / "test.specir"), backend="koika", out_dir=str(tmp_path),
                max_attempts=None, report=None, no_llm=False, show_proof=False, debug=False
            )
            verify_spec(args)

        # Should only call prove once (for the koika obligation)
        assert mock_skill_instance.prove.call_count == 1
        called_prop = mock_skill_instance.prove.call_args[0][0]["property"]
        assert called_prop == "prop_a"


class TestVerifyModelChecking:
    @patch("specir.cli.verify.run_model_check")
    @patch("specir.cli.verify.koika_to_rtl_convert")
    @patch("specir.cli.verify.convert_ast_to_spec_module")
    @patch("specir.cli.verify.parse_specir")
    @patch("specir.cli.verify.validate_specir_file")
    @patch("specir.cli.verify.load_config", return_value={"directories": {"build": "build"}, "verification": {"bmc_max_depth": 100}})
    def test_mc_passes(self, mock_cfg, mock_val, mock_parse, mock_conv, mock_rtl, mock_mc, tmp_path):
        mod = _make_minimal_spec_module()
        # Obligation engine is model_checking, backend not set (irrelevant)
        mod.proof_obligations = [{"property": "simple_prop", "engine": "model_checking", "backend": None}]
        mock_conv.return_value = mod
        mock_parse.return_value = MagicMock(module=MagicMock())

        # RTL generation produces a dummy Verilog file
        rtl_file = tmp_path / "rtl" / "test.v"
        rtl_file.parent.mkdir(parents=True)
        rtl_file.write_text("// dummy")
        mock_rtl.return_value = MagicMock()
        # simulate that koika_to_rtl_convert writes rtl_file
        with patch("pathlib.Path.exists", side_effect=lambda: True), \
             patch("pathlib.Path.read_text", return_value="// dummy"), \
             patch("shutil.which", return_value="/usr/bin/sby"):
            mock_mc.return_value = {"success": True, "status": "proved", "counterexample_trace": None, "output": "", "error": None}

            args = argparse.Namespace(
                input=str(tmp_path / "test.specir"), backend="model_checking",
                out_dir=str(tmp_path), max_attempts=None, report=None,
                no_llm=False, show_proof=False, debug=False
            )
            ret = verify_spec(args)

        assert ret == 0
        mock_mc.assert_called_once()

    @patch("specir.cli.verify.run_model_check")
    @patch("specir.cli.verify.koika_to_rtl_convert")
    @patch("specir.cli.verify.convert_ast_to_spec_module")
    @patch("specir.cli.verify.parse_specir")
    @patch("specir.cli.verify.validate_specir_file")
    @patch("specir.cli.verify.load_config", return_value={"directories": {"build": "build"}, "verification": {"bmc_max_depth": 100}})
    def test_mc_counterexample(self, mock_cfg, mock_val, mock_parse, mock_conv, mock_rtl, mock_mc, tmp_path):
        mod = _make_minimal_spec_module()
        mod.proof_obligations = [{"property": "simple_prop", "engine": "model_checking", "backend": None}]
        mock_conv.return_value = mod
        mock_parse.return_value = MagicMock(module=MagicMock())

        trace_path = tmp_path / "trace.vcd"
        trace_path.write_text("dummy trace")
        mock_mc.return_value = {"success": False, "status": "disproved", "counterexample_trace": trace_path, "output": "", "error": None}

        with patch("pathlib.Path.exists", side_effect=lambda: True), \
             patch("pathlib.Path.read_text", return_value="// dummy"):
            args = argparse.Namespace(
                input=str(tmp_path / "test.specir"), backend="model_checking",
                out_dir=str(tmp_path), max_attempts=None, report=None,
                no_llm=False, show_proof=False, debug=False
            )
            ret = verify_spec(args)

        assert ret == 1  # failure because property disproved

    @patch("specir.cli.verify.run_model_check", side_effect=ModelCheckError("tool not found"))
    @patch("specir.cli.verify.koika_to_rtl_convert")
    @patch("specir.cli.verify.convert_ast_to_spec_module")
    @patch("specir.cli.verify.parse_specir")
    @patch("specir.cli.verify.validate_specir_file")
    @patch("specir.cli.verify.load_config", return_value={"directories": {"build": "build"}})
    def test_mc_tool_error(self, mock_cfg, mock_val, mock_parse, mock_conv, mock_rtl, mock_mc, tmp_path):
        mod = _make_minimal_spec_module()
        mod.proof_obligations = [{"property": "simple_prop", "engine": "model_checking", "backend": None}]
        mock_conv.return_value = mod
        mock_parse.return_value = MagicMock(module=MagicMock())

        with patch("pathlib.Path.exists", side_effect=lambda: True), \
             patch("pathlib.Path.read_text", return_value="// dummy"):
            args = argparse.Namespace(
                input=str(tmp_path / "test.specir"), backend="model_checking",
                out_dir=str(tmp_path), max_attempts=None, report=None,
                no_llm=False, show_proof=False, debug=False
            )
            ret = verify_spec(args)

        assert ret == 1  # error counts as failure

    @patch("specir.cli.verify.LLMProofSkill")
    @patch("specir.cli.verify.run_model_check")
    @patch("specir.cli.verify.koika_to_rtl_convert")
    @patch("specir.cli.verify.spec_to_koika_convert")          # new mock for Coq generation
    @patch("specir.cli.verify.convert_ast_to_spec_module")
    @patch("specir.cli.verify.parse_specir")
    @patch("specir.cli.verify.validate_specir_file")
    @patch("specir.cli.verify.load_config", return_value={"directories": {"build": "build"}, "verification": {"bmc_max_depth": 100}})
    def test_mixed_theorem_and_mc(self, mock_cfg, mock_val, mock_parse, mock_conv,
                                  mock_koika_conv, mock_rtl, mock_mc, mock_skill, tmp_path):
        mod = _make_minimal_spec_module()
        mod.proof_obligations = [
            {"property": "simple_prop", "engine": "theorem_proving", "backend": "koika"},
            {"property": "simple_prop", "engine": "model_checking", "backend": None}
        ]
        mock_conv.return_value = mod
        mock_parse.return_value = MagicMock(module=MagicMock())
        mock_koika_conv.return_value = MagicMock()    # prevent real Coq conversion

        # Theorem proving mock
        mock_skill_instance = MagicMock()
        mock_skill.return_value = mock_skill_instance
        mock_skill_instance.prove.return_value = ProofResult(success=True, proof_script="dummy")

        # Model checking mock
        mock_mc.return_value = {"success": True, "status": "proved", "counterexample_trace": None, "output": "", "error": None}

        with patch("pathlib.Path.exists", side_effect=lambda: True), \
             patch("pathlib.Path.read_text", return_value="// dummy"), \
             patch("shutil.which", return_value="/usr/bin/sby"):
            args = argparse.Namespace(
                input=str(tmp_path / "test.specir"), backend=None,  # no filtering – run both
                out_dir=str(tmp_path), max_attempts=None, report=None,
                no_llm=False, show_proof=False, debug=False
            )
            ret = verify_spec(args)

        assert ret == 0
        assert mock_skill_instance.prove.call_count == 1
        assert mock_mc.call_count == 1


class TestReport:
    def test_report_file_written(self, tmp_path):
        results = [{"property": "p", "status": "passed", "detail": "", "backend": "koika"}]
        report_path = tmp_path / "report.json"
        args = argparse.Namespace(report=str(report_path), debug=False)
        _finish_summary(results, args)
        assert report_path.exists()
        data = json.loads(report_path.read_text())
        assert len(data["results"]) == 1
        assert data["results"][0]["status"] == "passed"

    def test_summary_output(self, capsys):
        results = [
            {"property": "a", "status": "passed", "detail": "", "backend": "koika"},
            {"property": "b", "status": "failed", "detail": "error msg", "backend": "acl2"}
        ]
        args = argparse.Namespace(report=None, debug=False)
        ret = _finish_summary(results, args)
        captured = capsys.readouterr()
        assert "PASS: a (koika)" in captured.out
        assert "FAIL: b (acl2)" in captured.out
        assert ret == 1
