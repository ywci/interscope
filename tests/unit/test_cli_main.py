# tests/unit/test_cli_main.py
#
# Unit tests for the global CLI entry point (isir.cli.main).
# Focus on global option parsing, sub-command routing, and batch dispatch
# without executing real work.

import argparse
import sys
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from isir.cli.main import (
    _parse_global_options,
    _setup_config,
    _run_single,
    _run_batch
)
from isir.utils.result_types import CompilationReport, BackendResult


def _global_namespace(remaining=None, output_format="text", config=None,
                      report_file=None, batch=None, debug=False):
    return argparse.Namespace(
        batch=batch,
        output_format=output_format,
        report_file=report_file,
        config=config,
        debug=debug,
        remaining=remaining or []
    )


class TestParseGlobalOptions:
    def test_no_args(self):
        args = _parse_global_options([])
        assert args.batch is None
        assert args.output_format == "text"
        assert args.report_file is None
        assert args.config is None
        assert args.debug is False
        assert args.remaining == []

    def test_batch_default_dir(self):
        args = _parse_global_options(["--batch"])
        assert args.batch == "."

    def test_batch_with_dir(self):
        args = _parse_global_options(["--batch", "benchmarks"])
        assert args.batch == "benchmarks"

    def test_output_format_choices(self):
        assert _parse_global_options(["--output-format", "json"]).output_format == "json"
        with pytest.raises(SystemExit):
            _parse_global_options(["--output-format", "xml"])

    def test_remaining_captures_subcommand(self):
        args = _parse_global_options(["compile", "design.isir", "--backend", "koika"])
        assert args.remaining == ["compile", "design.isir", "--backend", "koika"]

    def test_all_global_flags(self):
        args = _parse_global_options([
            "--batch", "bench", "--output-format", "json",
            "--report-file", "r.json", "--config", "c.yaml", "--debug",
            "verify", "d.isir"
        ])
        assert args.batch == "bench"
        assert args.output_format == "json"
        assert args.report_file == "r.json"
        assert args.config == "c.yaml"
        assert args.debug is True
        assert args.remaining == ["verify", "d.isir"]


class TestSetupConfig:
    def test_missing_external_config_exits(self):
        args = _global_namespace(config="/nonexistent/config.yaml")
        with pytest.raises(SystemExit):
            _setup_config(args)

    def test_no_config_calls_load_config_with_none_external(self):
        args = _global_namespace(config=None)
        with patch("isir.cli.main.load_config") as mock_load:
            _setup_config(args)
        mock_load.assert_called_once_with(
            force_reload=True, external_config_path=None
        )


class TestRunSingle:
    def test_no_command(self):
        assert _run_single(_global_namespace()) == 1

    def test_unknown_command(self):
        assert _run_single(_global_namespace(["frobnicate"])) == 1

    @pytest.mark.parametrize(
        "cmd,module",
        [
            ("compile", "isir.cli.compile"),
            ("verify", "isir.cli.verify"),
            ("sim", "isir.cli.sim"),
            ("check", "isir.cli.check"),
            ("lift", "isir.cli.lift"),
            ("query", "isir.cli.query"),
            ("validate-config", "isir.cli.validate_config")
        ]
    )
    def test_routes_to_subcommand(self, cmd, module):
        args = _global_namespace([cmd, "d.isir"])
        with patch(f"{module}.main", return_value=0) as mock_main:
            assert _run_single(args) == 0
        mock_main.assert_called_once()

    def test_routes_return_value_is_propagated(self):
        args = _global_namespace(["compile", "d.isir"])
        with patch("isir.cli.compile.main", return_value=7):
            assert _run_single(args) == 7

    def test_output_format_propagated_to_subcommand(self):
        captured = {}

        def fake_main():
            captured["argv"] = list(sys.argv)
            return 0

        args = _global_namespace(["compile", "d.isir"], output_format="json")
        with patch("isir.cli.compile.main", side_effect=fake_main):
            assert _run_single(args) == 0
        assert "--output-format" in captured["argv"]
        assert "json" in captured["argv"]

    def test_no_duplicate_output_format(self):
        captured = {}

        def fake_main():
            captured["argv"] = list(sys.argv)
            return 0

        args = _global_namespace(
            ["compile", "d.isir", "--output-format", "json"], output_format="json"
        )
        with patch("isir.cli.compile.main", side_effect=fake_main):
            _run_single(args)
        assert captured["argv"].count("--output-format") == 1

    def test_vcd_to_trace_uses_subprocess(self):
        args = _global_namespace(["vcd-to-trace", "t.vcd"])
        with patch("isir.cli.main.subprocess.call", return_value=0) as mock_call:
            assert _run_single(args) == 0
        mock_call.assert_called_once()

    def test_extract_mapping_uses_subprocess(self):
        args = _global_namespace(["extract-mapping", "rtl.v"])
        with patch("isir.cli.main.subprocess.call", return_value=0) as mock_call:
            assert _run_single(args) == 0
        mock_call.assert_called_once()


class TestRunBatch:
    def _batch_args(self, tmp_path, cmd="compile", output_format="text",
                    report_file=None, debug=False):
        return _global_namespace(
            remaining=[cmd],
            output_format=output_format,
            report_file=report_file,
            batch=str(tmp_path),
            debug=debug
        )

    def test_no_subcommand(self):
        args = _global_namespace(batch=".")
        assert _run_batch(args) == 1

    def test_unsupported_command(self, tmp_path):
        args = self._batch_args(tmp_path, cmd="check")
        assert _run_batch(args) == 1

    def test_batch_dir_not_found(self):
        args = _global_namespace(remaining=["compile"], batch="/nonexistent/dir")
        assert _run_batch(args) == 1

    def test_no_files_found(self, tmp_path):
        args = self._batch_args(tmp_path, cmd="compile")
        with patch("isir.cli.main.find_isir_files", return_value=[]):
            assert _run_batch(args) == 0

    def test_batch_compile_success(self, tmp_path):
        report = CompilationReport(
            design_name="d", input_file="d.isir",
            results=[BackendResult(backend="koika", success=True)],
        )
        args = self._batch_args(tmp_path, cmd="compile")
        with patch("isir.cli.main.find_isir_files",
                   return_value=[tmp_path / "d.isir"]), \
             patch("isir.cli.main._run_command_on_file", return_value=report), \
             patch("isir.cli.main.aggregate_compilation_reports",
                   return_value={"total": 1}):
            assert _run_batch(args) == 0

    def test_batch_compile_failure(self, tmp_path):
        report = CompilationReport(
            design_name="d", input_file="d.isir",
            results=[BackendResult(backend="koika", success=False, error_message="x")],
        )
        args = self._batch_args(tmp_path, cmd="compile")
        with patch("isir.cli.main.find_isir_files",
                   return_value=[tmp_path / "d.isir"]), \
             patch("isir.cli.main._run_command_on_file", return_value=report), \
             patch("isir.cli.main.aggregate_compilation_reports",
                   return_value={"total": 1}):
            assert _run_batch(args) == 1

    def test_batch_exception_is_counted_as_failure(self, tmp_path):
        args = self._batch_args(tmp_path, cmd="compile")
        with patch("isir.cli.main.find_isir_files",
                   return_value=[tmp_path / "d.isir"]), \
             patch("isir.cli.main._run_command_on_file",
                   side_effect=RuntimeError("boom")), \
             patch("isir.cli.main.aggregate_compilation_reports",
                   return_value={"total": 0}):
            assert _run_batch(args) == 1
