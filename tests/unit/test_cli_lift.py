# tests/unit/test_cli_lift.py
#
# Unit tests for the `isir lift` CLI subcommand.

import argparse
import yaml
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from isir.cli.lift import _setup_arg_parser, lift_trace


def _make_args(vcd_path, spec_path, mapping=None, out=None, debug=False):
    return argparse.Namespace(
        vcd=str(vcd_path),
        spec=str(spec_path),
        mapping=mapping,
        out=out,
        debug=debug,
    )


def _write(tmp_path, name, content="dummy"):
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


class TestArgumentParser:
    def test_requires_vcd_and_spec(self):
        with pytest.raises(SystemExit):
            _setup_arg_parser().parse_args([])
        with pytest.raises(SystemExit):
            _setup_arg_parser().parse_args(["t.vcd"])

    def test_defaults(self):
        args = _setup_arg_parser().parse_args(["t.vcd", "--spec", "s.isir"])
        assert args.vcd == "t.vcd"
        assert args.spec == "s.isir"
        assert args.mapping is None
        assert args.out is None
        assert args.debug is False

    def test_all_optional_arguments(self):
        args = _setup_arg_parser().parse_args([
            "t.vcd", "-s", "s.isir", "-m", "map.json", "-o", "out.yaml", "--debug",
        ])
        assert args.mapping == "map.json"
        assert args.out == "out.yaml"
        assert args.debug is True


class TestLiftTrace:
    def test_vcd_not_found(self, tmp_path):
        spec = _write(tmp_path, "s.isir")
        args = _make_args(tmp_path / "missing.vcd", spec)
        assert lift_trace(args) == 1

    def test_spec_not_found(self, tmp_path):
        vcd = _write(tmp_path, "t.vcd")
        args = _make_args(vcd, tmp_path / "missing.isir")
        assert lift_trace(args) == 1

    def test_mapping_not_found(self, tmp_path):
        vcd = _write(tmp_path, "t.vcd")
        spec = _write(tmp_path, "s.isir")
        args = _make_args(vcd, spec, mapping=str(tmp_path / "missing.json"))
        assert lift_trace(args) == 1

    def test_parse_failure(self, tmp_path):
        vcd = _write(tmp_path, "t.vcd")
        spec = _write(tmp_path, "s.isir")
        args = _make_args(vcd, spec)
        with patch("isir.cli.lift.parse_isir", side_effect=Exception("parse error")):
            assert lift_trace(args) == 1

    def test_vcd_conversion_failure(self, tmp_path):
        vcd = _write(tmp_path, "t.vcd")
        spec = _write(tmp_path, "s.isir")
        args = _make_args(vcd, spec)
        with patch("isir.cli.lift.parse_isir",
                   return_value=MagicMock(module=MagicMock())), \
             patch("isir.cli.lift.vcd_to_trace.convert",
                   side_effect=Exception("vcd error")):
            assert lift_trace(args) == 1

    def test_ast_conversion_failure(self, tmp_path):
        vcd = _write(tmp_path, "t.vcd")
        spec = _write(tmp_path, "s.isir")
        args = _make_args(vcd, spec)
        with patch("isir.cli.lift.parse_isir",
                   return_value=MagicMock(module=MagicMock())), \
             patch("isir.cli.lift.vcd_to_trace.convert", return_value=MagicMock()), \
             patch("isir.cli.lift.convert_ast_to_isir_module",
                   side_effect=Exception("conversion error")):
            assert lift_trace(args) == 1

    def test_trace_lift_failure(self, tmp_path):
        vcd = _write(tmp_path, "t.vcd")
        spec = _write(tmp_path, "s.isir")
        args = _make_args(vcd, spec)
        with patch("isir.cli.lift.parse_isir",
                   return_value=MagicMock(module=MagicMock())), \
             patch("isir.cli.lift.vcd_to_trace.convert", return_value=MagicMock()), \
             patch("isir.cli.lift.convert_ast_to_isir_module",
                   return_value=MagicMock()), \
             patch("isir.cli.lift.trace_to_isir.convert",
                   side_effect=Exception("lift error")):
            assert lift_trace(args) == 1

    def test_successful_lift_writes_yaml(self, tmp_path):
        vcd = _write(tmp_path, "t.vcd")
        spec = _write(tmp_path, "s.isir")
        out = tmp_path / "out.yaml"
        abstract = {"trace": {"cycles": [{"step": 0, "state": {"x": 0}}]}}
        ast = MagicMock()
        ast.module = MagicMock()
        spec_module = MagicMock()
        trace_mod = MagicMock()
        with patch("isir.cli.lift.parse_isir", return_value=ast), \
             patch("isir.cli.lift.vcd_to_trace.convert",
                   return_value=trace_mod) as mock_vcd, \
             patch("isir.cli.lift.convert_ast_to_isir_module",
                   return_value=spec_module), \
             patch("isir.cli.lift.trace_to_isir.convert",
                   return_value=abstract) as mock_lift:
            args = _make_args(vcd, spec, out=str(out))
            ret = lift_trace(args)
        assert ret == 0
        assert out.exists()
        data = yaml.safe_load(out.read_text(encoding="utf-8"))
        assert data["trace"]["cycles"][0]["step"] == 0
        mock_vcd.assert_called_once()
        mock_lift.assert_called_once_with(trace_mod, spec_module)

    def test_default_out_path(self, tmp_path):
        vcd = _write(tmp_path, "t.vcd")
        spec = _write(tmp_path, "s.isir")
        abstract = {"trace": {"cycles": []}}
        ast = MagicMock()
        ast.module = MagicMock()
        with patch("isir.cli.lift.parse_isir", return_value=ast), \
             patch("isir.cli.lift.vcd_to_trace.convert", return_value=MagicMock()), \
             patch("isir.cli.lift.convert_ast_to_isir_module",
                   return_value=MagicMock()), \
             patch("isir.cli.lift.trace_to_isir.convert", return_value=abstract):
            args = _make_args(vcd, spec)
            ret = lift_trace(args)
        assert ret == 0
        assert (tmp_path / "t.abstract.yaml").exists()

    def test_vcd_conversion_receives_mapping(self, tmp_path):
        vcd = _write(tmp_path, "t.vcd")
        spec = _write(tmp_path, "s.isir")
        mapping = _write(tmp_path, "mapping.json", "{}")
        ast = MagicMock()
        ast.module = MagicMock()
        with patch("isir.cli.lift.parse_isir", return_value=ast), \
             patch("isir.cli.lift.vcd_to_trace.convert",
                   return_value=MagicMock()) as mock_vcd, \
             patch("isir.cli.lift.convert_ast_to_isir_module",
                   return_value=MagicMock()), \
             patch("isir.cli.lift.trace_to_isir.convert",
                   return_value={"trace": {"cycles": []}}):
            args = _make_args(vcd, spec, mapping=str(mapping))
            ret = lift_trace(args)
        assert ret == 0
        assert mock_vcd.call_args.kwargs.get("mapping_file") is not None
