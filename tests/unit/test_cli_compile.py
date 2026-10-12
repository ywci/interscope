# tests/unit/test_cli_compile.py
#
# Unit tests for the `isir compile` CLI subcommand.

import argparse
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from isir.cli.compile import _setup_arg_parser, compile_spec
from isir.utils.result_types import BackendResult, CompilationReport


def _make_args(tmp_path, backend="koika", output_format="text",
               no_rtl=False, simulate=False):
    (tmp_path / "design.isir").write_text("dummy", encoding="utf-8")
    return argparse.Namespace(
        input=str(tmp_path / "design.isir"),
        out_dir=None,
        backend=backend,
        assert_lang="sva",
        no_rtl=no_rtl,
        simulate=simulate,
        cycles=None,
        verilator_path=None,
        koika_path=None,
        output_format=output_format,
        debug=False,
    )


def _make_spec_module(name="my_design"):
    spec = MagicMock()
    spec.name = name
    return spec


def _make_ast():
    ast = MagicMock()
    ast.module = MagicMock()
    return ast


class TestArgumentParser:
    def test_requires_input(self):
        with pytest.raises(SystemExit):
            _setup_arg_parser().parse_args([])

    def test_defaults(self):
        args = _setup_arg_parser().parse_args(["in.isir"])
        assert args.input == "in.isir"
        assert args.backend == "koika"
        assert args.assert_lang == "sva"
        assert args.out_dir is None
        assert args.no_rtl is False
        assert args.simulate is False
        assert args.cycles is None
        assert args.output_format == "text"
        assert args.debug is False

    def test_backend_choices(self):
        args = _setup_arg_parser().parse_args(["in.isir", "--backend", "acl2"])
        assert args.backend == "acl2"
        with pytest.raises(SystemExit):
            _setup_arg_parser().parse_args(["in.isir", "--backend", "bogus"])

    def test_assert_lang_choices(self):
        args = _setup_arg_parser().parse_args(
            ["in.isir", "--backend", "assert", "--assert-lang", "vhdl"]
        )
        assert args.assert_lang == "vhdl"
        with pytest.raises(SystemExit):
            _setup_arg_parser().parse_args(
                ["in.isir", "--backend", "assert", "--assert-lang", "bogus"]
            )

    def test_all_optional_arguments(self):
        args = _setup_arg_parser().parse_args([
            "in.isir", "-o", "/tmp/out", "--backend", "assert",
            "--assert-lang", "vhdl", "--no-rtl", "--simulate",
            "--cycles", "10", "--output-format", "json", "--debug",
        ])
        assert args.out_dir == "/tmp/out"
        assert args.assert_lang == "vhdl"
        assert args.no_rtl is True
        assert args.simulate is True
        assert args.cycles == 10
        assert args.output_format == "json"
        assert args.debug is True


class TestCompileSpec:
    def test_file_not_found(self, tmp_path):
        args = _make_args(tmp_path)
        args.input = str(tmp_path / "missing.isir")
        with patch("isir.cli.compile.load_config", return_value={}):
            assert compile_spec(args) == 1

    def test_schema_validation_failure(self, tmp_path):
        args = _make_args(tmp_path)
        with patch("isir.cli.compile.load_config", return_value={}), \
             patch("isir.cli.compile.validate_isir_file",
                   side_effect=Exception("schema error")):
            assert compile_spec(args) == 1

    def test_parse_failure(self, tmp_path):
        args = _make_args(tmp_path)
        with patch("isir.cli.compile.load_config", return_value={}), \
             patch("isir.cli.compile.validate_isir_file"), \
             patch("isir.cli.compile.parse_isir",
                   side_effect=Exception("parse error")):
            assert compile_spec(args) == 1

    def test_conversion_failure(self, tmp_path):
        args = _make_args(tmp_path)
        with patch("isir.cli.compile.load_config", return_value={}), \
             patch("isir.cli.compile.validate_isir_file"), \
             patch("isir.cli.compile.parse_isir", return_value=_make_ast()), \
             patch("isir.cli.compile.convert_ast_to_isir_module",
                   side_effect=Exception("conversion error")):
            assert compile_spec(args) == 1

    def test_koika_compile_produces_report(self, tmp_path, capsys):
        args = _make_args(tmp_path, backend="koika", output_format="json")
        spec = _make_spec_module("my_design")
        results = [
            BackendResult(backend="koika", success=True, output_file="my_design.v"),
            BackendResult(backend="rtl", success=True, output_file="my_design_rtl.v"),
        ]
        with patch("isir.cli.compile.load_config", return_value={"verification": {}}), \
             patch("isir.cli.compile.validate_isir_file"), \
             patch("isir.cli.compile.parse_isir", return_value=_make_ast()), \
             patch("isir.cli.compile.convert_ast_to_isir_module", return_value=spec), \
             patch("isir.cli.compile._compile_koika", return_value=results) as mock_koika:
            ret = compile_spec(args)
        captured = json.loads(capsys.readouterr().out)
        assert ret == 0
        assert captured["design_name"] == "my_design"
        assert captured["overall_success"] is True
        assert len(captured["results"]) == 2
        mock_koika.assert_called_once()

    def test_koika_compile_failure_returns_1(self, tmp_path):
        args = _make_args(tmp_path, backend="koika")
        spec = _make_spec_module("my_design")
        results = [BackendResult(backend="koika", success=False, error_message="boom")]
        with patch("isir.cli.compile.load_config", return_value={"verification": {}}), \
             patch("isir.cli.compile.validate_isir_file"), \
             patch("isir.cli.compile.parse_isir", return_value=_make_ast()), \
             patch("isir.cli.compile.convert_ast_to_isir_module", return_value=spec), \
             patch("isir.cli.compile._compile_koika", return_value=results):
            assert compile_spec(args) == 1

    def test_acl2_backend_routed(self, tmp_path):
        args = _make_args(tmp_path, backend="acl2", output_format="json")
        spec = _make_spec_module("my_design")
        results = [BackendResult(backend="acl2", success=True, output_file="my_design.lisp")]
        with patch("isir.cli.compile.load_config", return_value={"verification": {}}), \
             patch("isir.cli.compile.validate_isir_file"), \
             patch("isir.cli.compile.parse_isir", return_value=_make_ast()), \
             patch("isir.cli.compile.convert_ast_to_isir_module", return_value=spec), \
             patch("isir.cli.compile._compile_acl2", return_value=results) as mock_acl2, \
             patch("isir.cli.compile._compile_koika") as mock_koika:
            ret = compile_spec(args)
        assert ret == 0
        mock_acl2.assert_called_once()
        mock_koika.assert_not_called()

    def test_assert_backend_routed(self, tmp_path):
        args = _make_args(tmp_path, backend="assert", output_format="json")
        spec = _make_spec_module("my_design")
        results = [BackendResult(backend="sva", success=True, output_file="my_design.sv")]
        with patch("isir.cli.compile.load_config", return_value={"verification": {}}), \
             patch("isir.cli.compile.validate_isir_file"), \
             patch("isir.cli.compile.parse_isir", return_value=_make_ast()), \
             patch("isir.cli.compile.convert_ast_to_isir_module", return_value=spec), \
             patch("isir.cli.compile._compile_assert", return_value=results) as mock_assert:
            ret = compile_spec(args)
        assert ret == 0
        mock_assert.assert_called_once()

    def test_unsupported_backend(self, tmp_path):
        args = _make_args(tmp_path, backend="unknown")
        spec = _make_spec_module("my_design")
        with patch("isir.cli.compile.load_config", return_value={"verification": {}}), \
             patch("isir.cli.compile.validate_isir_file"), \
             patch("isir.cli.compile.parse_isir", return_value=_make_ast()), \
             patch("isir.cli.compile.convert_ast_to_isir_module", return_value=spec):
            assert compile_spec(args) == 1

    def test_backend_not_implemented(self, tmp_path):
        args = _make_args(tmp_path, backend="koika")
        spec = _make_spec_module("my_design")
        with patch("isir.cli.compile.load_config", return_value={"verification": {}}), \
             patch("isir.cli.compile.validate_isir_file"), \
             patch("isir.cli.compile.parse_isir", return_value=_make_ast()), \
             patch("isir.cli.compile.convert_ast_to_isir_module", return_value=spec), \
             patch("isir.cli.compile._compile_koika",
                   side_effect=NotImplementedError("nope")):
            assert compile_spec(args) == 1

    def test_split_rules_enabled(self, tmp_path):
        args = _make_args(tmp_path, backend="koika", no_rtl=True)
        spec = _make_spec_module("my_design")
        results = [BackendResult(backend="koika", success=True, output_file="x.v")]
        with patch("isir.cli.compile.load_config",
                   return_value={"verification": {"split_monolithic_rules": True}}), \
             patch("isir.cli.compile.validate_isir_file"), \
             patch("isir.cli.compile.parse_isir", return_value=_make_ast()), \
             patch("isir.cli.compile.convert_ast_to_isir_module", return_value=spec), \
             patch("isir.cli.compile.split_rules", return_value=spec) as mock_split, \
             patch("isir.cli.compile._compile_koika", return_value=results):
            assert compile_spec(args) == 0
        mock_split.assert_called_once_with(spec)

    def test_simulate_triggers_simulation(self, tmp_path):
        args = _make_args(tmp_path, backend="koika", simulate=True)
        spec = _make_spec_module("my_design")
        results = [BackendResult(backend="koika", success=True, output_file="x.v")]
        with patch("isir.cli.compile.load_config", return_value={"verification": {}}), \
             patch("isir.cli.compile.validate_isir_file"), \
             patch("isir.cli.compile.parse_isir", return_value=_make_ast()), \
             patch("isir.cli.compile.convert_ast_to_isir_module", return_value=spec), \
             patch("isir.cli.compile._compile_koika", return_value=results), \
             patch("isir.cli.compile._run_simulation") as mock_sim:
            assert compile_spec(args) == 0
        mock_sim.assert_called_once()

    def test_compile_returns_a_report_type(self, tmp_path):
        """The function itself returns an int; the internal report is a CompilationReport."""
        report = CompilationReport(
            design_name="d", input_file="d.isir",
            results=[BackendResult(backend="koika", success=True)],
        )
        assert report.overall_success() is True
        assert isinstance(report, CompilationReport)
