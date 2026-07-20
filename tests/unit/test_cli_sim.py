# tests/unit/test_cli_sim.py
#
# Unit tests for the `specir sim` CLI subcommand.
# Verifies argument parsing and the main execution flow
# with mocked simulation backend.

import argparse
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from specir.cli.sim import _setup_arg_parser, sim_spec
from specir.verification.simulation import SimulationError


class TestArgumentParser:
    def test_required_input_argument(self):
        parser = _setup_arg_parser()
        with pytest.raises(SystemExit):
            parser.parse_args([])

    def test_default_values(self):
        parser = _setup_arg_parser()
        args = parser.parse_args(["input.specir"])
        assert args.input == "input.specir"
        assert args.out_dir is None
        assert args.cycles is None
        assert args.verilator_path is None
        assert args.koika_path is None
        assert args.debug is False

    def test_all_optional_arguments(self):
        parser = _setup_arg_parser()
        args = parser.parse_args([
            "input.specir",
            "--out-dir", "/tmp/build",
            "--cycles", "500",
            "--verilator-path", "/usr/local/bin/verilator",
            "--koika-path", "/usr/local/bin/koika",
            "--debug",
        ])
        assert args.out_dir == "/tmp/build"
        assert args.cycles == 500
        assert args.verilator_path == "/usr/local/bin/verilator"
        assert args.koika_path == "/usr/local/bin/koika"
        assert args.debug is True

    def test_short_flags(self):
        parser = _setup_arg_parser()
        args = parser.parse_args([
            "input.specir",
            "-o", "/tmp/build",
            "-c", "200",
        ])
        assert args.out_dir == "/tmp/build"
        assert args.cycles == 200


class TestSimSpecExecution:
    @pytest.fixture
    def mock_args(self):
        """Return an argparse.Namespace with typical values."""
        args = argparse.Namespace()
        args.input = "/path/to/design.specir"
        args.out_dir = None
        args.cycles = None
        args.verilator_path = None
        args.koika_path = None
        args.debug = False
        return args

    def test_file_not_found(self, mock_args):
        mock_args.input = "/nonexistent.specir"
        with patch("pathlib.Path.exists", return_value=False):
            ret = sim_spec(mock_args)
            assert ret == 1

    def test_schema_validation_failure(self, mock_args):
        with patch("pathlib.Path.exists", return_value=True), \
             patch("specir.cli.sim.validate_specir_file",
                   side_effect=Exception("schema error")):
            ret = sim_spec(mock_args)
            assert ret == 1

    def test_parsing_failure(self, mock_args):
        with patch("pathlib.Path.exists", return_value=True), \
             patch("specir.cli.sim.validate_specir_file"), \
             patch("specir.cli.sim.parse_specir",
                   side_effect=Exception("parse error")):
            ret = sim_spec(mock_args)
            assert ret == 1

    def test_ast_to_spec_conversion_failure(self, mock_args):
        with patch("pathlib.Path.exists", return_value=True), \
             patch("specir.cli.sim.validate_specir_file"), \
             patch("specir.cli.sim.parse_specir") as mock_parse, \
             patch("specir.cli.sim.convert_ast_to_spec_module",
                   side_effect=Exception("conversion error")):
            # parse_specir must return an object with a .module attribute
            mock_ast = MagicMock()
            mock_ast.module = MagicMock()
            mock_parse.return_value = mock_ast
            ret = sim_spec(mock_args)
            assert ret == 1

    def test_successful_simulation(self, mock_args, tmp_path):
        vcd = tmp_path / "sim.vcd"
        vcd.write_text("dummy")
        with patch("pathlib.Path.exists", return_value=True), \
             patch("specir.cli.sim.validate_specir_file"), \
             patch("specir.cli.sim.parse_specir") as mock_parse, \
             patch("specir.cli.sim.convert_ast_to_spec_module") as mock_convert, \
             patch("specir.cli.sim.simulate_design") as mock_sim:
            mock_ast = MagicMock()
            mock_ast.module = MagicMock()
            mock_parse.return_value = mock_ast
            mock_spec = MagicMock()
            mock_spec.name = "my_design"
            mock_convert.return_value = mock_spec
            mock_sim.return_value = vcd
            ret = sim_spec(mock_args)
            assert ret == 0

    def test_simulation_error(self, mock_args):
        with patch("pathlib.Path.exists", return_value=True), \
             patch("specir.cli.sim.validate_specir_file"), \
             patch("specir.cli.sim.parse_specir") as mock_parse, \
             patch("specir.cli.sim.convert_ast_to_spec_module") as mock_convert, \
             patch("specir.cli.sim.simulate_design",
                   side_effect=SimulationError("sim failed")):
            mock_ast = MagicMock()
            mock_ast.module = MagicMock()
            mock_parse.return_value = mock_ast
            mock_spec = MagicMock()
            mock_spec.name = "my_design"
            mock_convert.return_value = mock_spec
            ret = sim_spec(mock_args)
            assert ret == 1

    def test_unexpected_error(self, mock_args):
        with patch("pathlib.Path.exists", return_value=True), \
             patch("specir.cli.sim.validate_specir_file"), \
             patch("specir.cli.sim.parse_specir") as mock_parse, \
             patch("specir.cli.sim.convert_ast_to_spec_module",
                   side_effect=RuntimeError("unexpected")):
            mock_ast = MagicMock()
            mock_ast.module = MagicMock()
            mock_parse.return_value = mock_ast
            ret = sim_spec(mock_args)
            assert ret == 1
