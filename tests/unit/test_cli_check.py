# tests/unit/test_cli_check.py
#
# Unit tests for the `isir check` CLI subcommand.

import argparse
import yaml
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from jsonschema import ValidationError
from isir.cli.check import _setup_arg_parser, check_trace, _extract_cycles
from isir.verification.property_checker import PropertyCheckResult


def _make_args(trace_path, spec_path, no_validate=False, debug=False):
    return argparse.Namespace(
        trace=str(trace_path),
        spec=str(spec_path),
        no_validate=no_validate,
        debug=debug,
    )


def _make_spec():
    spec = MagicMock()
    spec.module = MagicMock()
    spec.module.properties = [MagicMock(), MagicMock()]
    return spec


def _write_trace(tmp_path, data, name="trace.yaml"):
    p = tmp_path / name
    p.write_text(yaml.dump(data), encoding="utf-8")
    return p


class TestArgumentParser:
    def test_requires_spec(self):
        parser = _setup_arg_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["trace.yaml"])

    def test_defaults(self):
        parser = _setup_arg_parser()
        args = parser.parse_args(["trace.yaml", "--spec", "spec.isir"])
        assert args.trace == "trace.yaml"
        assert args.spec == "spec.isir"
        assert args.no_validate is False
        assert args.debug is False

    def test_no_validate_and_debug_flags(self):
        parser = _setup_arg_parser()
        args = parser.parse_args(
            ["trace.yaml", "--spec", "spec.isir", "--no-validate", "--debug"]
        )
        assert args.no_validate is True
        assert args.debug is True

    def test_short_spec_flag(self):
        parser = _setup_arg_parser()
        args = parser.parse_args(["trace.yaml", "-s", "spec.isir"])
        assert args.spec == "spec.isir"


class TestExtractCycles:
    def test_flat_cycles(self):
        assert _extract_cycles({"cycles": [{"step": 0}]}) == [{"step": 0}]

    def test_wrapped_cycles(self):
        assert _extract_cycles({"trace": {"cycles": [{"step": 0}]}}) == [{"step": 0}]

    def test_missing_cycles(self):
        assert _extract_cycles({"trace": {"other": []}}) == []
        assert _extract_cycles({}) == []
        assert _extract_cycles({"cycles": "not-a-list"}) == []
        assert _extract_cycles({"trace": "not-a-dict"}) == []


class TestCheckTrace:
    def test_trace_file_not_found(self, tmp_path):
        args = _make_args(tmp_path / "missing_trace.yaml", tmp_path / "spec.isir")
        assert check_trace(args) == 1

    def test_spec_file_not_found(self, tmp_path):
        trace = _write_trace(tmp_path, {"cycles": [{"step": 0}]})
        args = _make_args(trace, tmp_path / "missing_spec.isir")
        assert check_trace(args) == 1

    def test_parse_failure(self, tmp_path):
        trace = _write_trace(tmp_path, {"cycles": [{"step": 0}]})
        spec_path = tmp_path / "spec.isir"
        spec_path.write_text("dummy", encoding="utf-8")
        args = _make_args(trace, spec_path)
        with patch("isir.cli.check.parse_isir", side_effect=Exception("parse error")):
            assert check_trace(args) == 1

    def test_no_module(self, tmp_path):
        trace = _write_trace(tmp_path, {"cycles": [{"step": 0}]})
        spec_path = tmp_path / "spec.isir"
        spec_path.write_text("dummy", encoding="utf-8")
        args = _make_args(trace, spec_path)
        with patch("isir.cli.check.parse_isir", return_value=MagicMock(module=None)):
            assert check_trace(args) == 1

    def test_invalid_trace_not_a_dict(self, tmp_path):
        trace = tmp_path / "trace.yaml"
        trace.write_text("- a\n- b\n", encoding="utf-8")
        spec_path = tmp_path / "spec.isir"
        spec_path.write_text("dummy", encoding="utf-8")
        args = _make_args(trace, spec_path)
        with patch("isir.cli.check.parse_isir", return_value=_make_spec()), \
             patch("isir.cli.check._load_trace_schema", return_value={}), \
             patch("isir.cli.check._validate_trace"):
            assert check_trace(args) == 1

    def test_no_cycles(self, tmp_path):
        trace = _write_trace(tmp_path, {"trace": {"cycles": []}})
        spec_path = tmp_path / "spec.isir"
        spec_path.write_text("dummy", encoding="utf-8")
        args = _make_args(trace, spec_path)
        with patch("isir.cli.check.parse_isir", return_value=_make_spec()), \
             patch("isir.cli.check._load_trace_schema", return_value={}), \
             patch("isir.cli.check._validate_trace"):
            assert check_trace(args) == 1

    def test_schema_validation_failure(self, tmp_path):
        trace = _write_trace(tmp_path, {"cycles": [{"step": 0}]})
        spec_path = tmp_path / "spec.isir"
        spec_path.write_text("dummy", encoding="utf-8")
        args = _make_args(trace, spec_path)
        with patch("isir.cli.check.parse_isir", return_value=_make_spec()), \
             patch("isir.cli.check._load_trace_schema", return_value={}), \
             patch("isir.cli.check._validate_trace",
                   side_effect=ValidationError("schema violation")):
            assert check_trace(args) == 1

    def test_all_properties_pass(self, tmp_path):
        trace = _write_trace(tmp_path, {"trace": {"cycles": [{"step": 0}]}})
        spec_path = tmp_path / "spec.isir"
        spec_path.write_text("dummy", encoding="utf-8")
        args = _make_args(trace, spec_path)
        results = [
            PropertyCheckResult(name="p1", holds=True),
            PropertyCheckResult(name="p2", holds=True, vacuous=True),
        ]
        with patch("isir.cli.check.parse_isir", return_value=_make_spec()), \
             patch("isir.cli.check._load_trace_schema", return_value={}), \
             patch("isir.cli.check._validate_trace"), \
             patch("isir.cli.check.check_all_properties", return_value=results):
            assert check_trace(args) == 0

    def test_property_fails(self, tmp_path, capsys):
        trace = _write_trace(tmp_path, {"cycles": [{"step": 0}]})
        spec_path = tmp_path / "spec.isir"
        spec_path.write_text("dummy", encoding="utf-8")
        args = _make_args(trace, spec_path)
        results = [
            PropertyCheckResult(name="p1", holds=True),
            PropertyCheckResult(
                name="p2", holds=False, failing_cycle=3, detail="state mismatch"
            ),
        ]
        with patch("isir.cli.check.parse_isir", return_value=_make_spec()), \
             patch("isir.cli.check._load_trace_schema", return_value={}), \
             patch("isir.cli.check._validate_trace"), \
             patch("isir.cli.check.check_all_properties", return_value=results):
            ret = check_trace(args)
        assert ret == 1
        out = capsys.readouterr().out
        assert "FAIL: p2" in out
        assert "Failing cycle: 3" in out

    def test_no_validate_skips_schema(self, tmp_path):
        trace = _write_trace(tmp_path, {"cycles": [{"step": 0}]})
        spec_path = tmp_path / "spec.isir"
        spec_path.write_text("dummy", encoding="utf-8")
        args = _make_args(trace, spec_path, no_validate=True)
        results = [PropertyCheckResult(name="p1", holds=True)]
        with patch("isir.cli.check.parse_isir", return_value=_make_spec()), \
             patch("isir.cli.check._load_trace_schema") as mock_schema, \
             patch("isir.cli.check._validate_trace") as mock_validate, \
             patch("isir.cli.check.check_all_properties", return_value=results):
            assert check_trace(args) == 0
        mock_schema.assert_not_called()
        mock_validate.assert_not_called()

    def test_property_check_raises(self, tmp_path):
        trace = _write_trace(tmp_path, {"cycles": [{"step": 0}]})
        spec_path = tmp_path / "spec.isir"
        spec_path.write_text("dummy", encoding="utf-8")
        args = _make_args(trace, spec_path)
        with patch("isir.cli.check.parse_isir", return_value=_make_spec()), \
             patch("isir.cli.check._load_trace_schema", return_value={}), \
             patch("isir.cli.check._validate_trace"), \
             patch("isir.cli.check.check_all_properties",
                   side_effect=Exception("check boom")):
            assert check_trace(args) == 1

    def test_check_all_properties_called_with_cycles(self, tmp_path):
        trace = _write_trace(
            tmp_path, {"trace": {"cycles": [{"step": 0}, {"step": 1}]}}
        )
        spec_path = tmp_path / "spec.isir"
        spec_path.write_text("dummy", encoding="utf-8")
        args = _make_args(trace, spec_path)
        spec = _make_spec()
        results = [PropertyCheckResult(name="p1", holds=True)]
        with patch("isir.cli.check.parse_isir", return_value=spec), \
             patch("isir.cli.check._load_trace_schema", return_value={}), \
             patch("isir.cli.check._validate_trace"), \
             patch("isir.cli.check.check_all_properties",
                   return_value=results) as mock_check:
            assert check_trace(args) == 0
        mock_check.assert_called_once_with(spec.module.properties, [{"step": 0}, {"step": 1}])
