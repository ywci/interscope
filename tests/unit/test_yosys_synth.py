# tests/unit/test_yosys_synth.py
#
# Unit tests for Yosys synthesis wrapper (isir.utils.yosys_synth).
# subprocess.run and yosys discovery are mocked so no external binary runs.

import pytest
import subprocess
from pathlib import Path
from unittest.mock import Mock, patch
from isir.utils.yosys_synth import (
    YosysSynthesisError,
    synthesize_rtl,
    synthesize_from_config,
    _parse_area,
    _parse_cell_count,
    _parse_delay,
)


YOSYS_LOG = "\n".join([
    "1. Executing SYNTH pass.",
    "Chip area for top module: 1234.56",
    "Number of cells: 42",
    "Delay: 12.34 ps",
    "Done.",
])


def _make_result(stdout, returncode=0, stderr=""):
    result = Mock()
    result.returncode = returncode
    result.stdout = stdout
    result.stderr = stderr
    return result


@pytest.fixture
def verilog(tmp_path):
    v = tmp_path / "rtl.v"
    v.write_text("module top; endmodule")
    return v


class TestParseArea:
    def test_chip_area_line(self):
        assert _parse_area("Chip area for top module: 1234.56") == 1234.56

    def test_area_line_with_unit(self):
        assert _parse_area("Area: 42 um^2") == 42.0

    def test_area_line_without_unit(self):
        assert _parse_area("Area: 7.5") == 7.5

    def test_no_area(self):
        assert _parse_area("some unrelated log\nwithout area") is None


class TestParseCellCount:
    def test_cell_count(self):
        assert _parse_cell_count("Number of cells: 1234") == 1234

    def test_cell_count_with_whitespace(self):
        assert _parse_cell_count("Number of cells:     99") == 99

    def test_no_cell_count(self):
        assert _parse_cell_count("no cells here") is None


class TestParseDelay:
    def test_delay_line(self):
        assert _parse_delay("Delay: 12.34 ps") == 12.34

    def test_delay_keyword_elsewhere(self):
        assert _parse_delay("Critical path Delay: 5.5 ns") == 5.5

    def test_no_delay(self):
        assert _parse_delay("nothing timing related") is None


class TestSynthesizeRtl:
    def test_success_parses_metrics(self, verilog, tmp_path):
        out_dir = tmp_path / "out"
        with patch(
            "isir.utils.yosys_synth.shutil.which", return_value="/usr/bin/yosys"
        ), patch("isir.utils.yosys_synth.get_config", return_value={}), patch(
            "isir.utils.yosys_synth.subprocess.run",
            return_value=_make_result(YOSYS_LOG),
        ) as mock_run:
            result = synthesize_rtl(
                verilog, top_module="top", output_dir=out_dir
            )

        assert result["area"] == 1234.56
        assert result["cells"] == 42
        assert result["delay"] == 12.34
        assert YOSYS_LOG in result["log"]
        assert result["netlist"] is None

        args, kwargs = mock_run.call_args
        assert args[0][0] == "/usr/bin/yosys"
        assert "-s" in args[0]
        assert kwargs["cwd"] == str(out_dir.resolve())

    def test_netlist_present_when_file_exists(self, verilog, tmp_path):
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        netlist = out_dir / "top_synth.v"
        netlist.write_text("module top; endmodule")

        with patch(
            "isir.utils.yosys_synth.shutil.which", return_value="/usr/bin/yosys"
        ), patch("isir.utils.yosys_synth.get_config", return_value={}), patch(
            "isir.utils.yosys_synth.subprocess.run",
            return_value=_make_result(YOSYS_LOG),
        ):
            result = synthesize_rtl(
                verilog, top_module="top", output_dir=out_dir
            )

        assert result["netlist"] == netlist.resolve()

    def test_uses_config_tools_yosys_when_not_on_path(self, verilog, tmp_path):
        with patch("isir.utils.yosys_synth.shutil.which", return_value=None), patch(
            "isir.utils.yosys_synth.get_config",
            return_value={"tools": {"yosys": "/custom/yosys"}},
        ), patch(
            "isir.utils.yosys_synth.subprocess.run",
            return_value=_make_result(YOSYS_LOG),
        ) as mock_run:
            synthesize_rtl(verilog, top_module="top", output_dir=tmp_path / "out")

        assert mock_run.call_args[0][0][0] == "/custom/yosys"

    def test_missing_yosys_raises(self, verilog, tmp_path):
        with patch("isir.utils.yosys_synth.shutil.which", return_value=None), patch(
            "isir.utils.yosys_synth.get_config", return_value={}
        ):
            with pytest.raises(YosysSynthesisError) as exc:
                synthesize_rtl(verilog, top_module="top", output_dir=tmp_path / "out")
            assert "Yosys not found" in str(exc.value)

    def test_missing_verilog_raises(self, tmp_path):
        missing = tmp_path / "missing.v"
        with patch(
            "isir.utils.yosys_synth.shutil.which", return_value="/usr/bin/yosys"
        ), patch("isir.utils.yosys_synth.get_config", return_value={}):
            with pytest.raises(FileNotFoundError):
                synthesize_rtl(missing, top_module="top", output_dir=tmp_path / "out")

    def test_nonzero_returncode_raises(self, verilog, tmp_path):
        with patch(
            "isir.utils.yosys_synth.shutil.which", return_value="/usr/bin/yosys"
        ), patch("isir.utils.yosys_synth.get_config", return_value={}), patch(
            "isir.utils.yosys_synth.subprocess.run",
            return_value=_make_result("", returncode=1, stderr="synthesis blew up"),
        ):
            with pytest.raises(YosysSynthesisError) as exc:
                synthesize_rtl(verilog, top_module="top", output_dir=tmp_path / "out")
            assert "failed with code 1" in str(exc.value)
            assert "synthesis blew up" in str(exc.value)

    def test_timeout_raises(self, verilog, tmp_path):
        with patch(
            "isir.utils.yosys_synth.shutil.which", return_value="/usr/bin/yosys"
        ), patch("isir.utils.yosys_synth.get_config", return_value={}), patch(
            "isir.utils.yosys_synth.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="yosys", timeout=300),
        ):
            with pytest.raises(YosysSynthesisError) as exc:
                synthesize_rtl(
                    verilog, top_module="top", output_dir=tmp_path / "out"
                )
            assert "timed out after 300s" in str(exc.value)

    def test_tcl_script_flatten_and_library(self, verilog, tmp_path):
        out_dir = tmp_path / "out"
        library = "/libs/tech.lib"
        with patch(
            "isir.utils.yosys_synth.shutil.which", return_value="/usr/bin/yosys"
        ), patch("isir.utils.yosys_synth.get_config", return_value={}), patch(
            "isir.utils.yosys_synth.subprocess.run",
            return_value=_make_result(YOSYS_LOG),
        ):
            synthesize_rtl(
                verilog,
                top_module="top",
                output_dir=out_dir,
                library=library,
                flatten=True,
            )

        script = (out_dir / "synth.ys").read_text()
        assert f"read_verilog {verilog.resolve()}" in script
        assert "hierarchy -top top" in script
        assert "\nflatten\n" in script
        assert f"dfflibmap -liberty {library}" in script
        assert f"abc -liberty {library}" in script

    def test_tcl_script_no_flatten(self, verilog, tmp_path):
        out_dir = tmp_path / "out"
        with patch(
            "isir.utils.yosys_synth.shutil.which", return_value="/usr/bin/yosys"
        ), patch("isir.utils.yosys_synth.get_config", return_value={}), patch(
            "isir.utils.yosys_synth.subprocess.run",
            return_value=_make_result(YOSYS_LOG),
        ):
            synthesize_rtl(
                verilog, top_module="top", output_dir=out_dir, flatten=False
            )

        script = (out_dir / "synth.ys").read_text()
        assert "hierarchy -check -top top" in script
        assert "\nflatten\n" not in script
        assert "dfflibmap" not in script

    def test_extra_args_appended_to_command(self, verilog, tmp_path):
        with patch(
            "isir.utils.yosys_synth.shutil.which", return_value="/usr/bin/yosys"
        ), patch("isir.utils.yosys_synth.get_config", return_value={}), patch(
            "isir.utils.yosys_synth.subprocess.run",
            return_value=_make_result(YOSYS_LOG),
        ) as mock_run:
            synthesize_rtl(
                verilog,
                top_module="top",
                output_dir=tmp_path / "out",
                extra_args=["-p", "stat"],
            )

        cmd = mock_run.call_args[0][0]
        assert cmd[-2:] == ["-p", "stat"]


class TestSynthesizeFromConfig:
    def test_passes_config_defaults(self, verilog):
        with patch(
            "isir.utils.yosys_synth.get_config",
            return_value={
                "synthesis": {
                    "library": "/libs/lib.lib",
                    "flatten": False,
                    "timeout": 120,
                }
            },
        ), patch(
            "isir.utils.yosys_synth.synthesize_rtl",
            return_value={"area": None, "cells": None, "delay": None,
                         "netlist": None, "log": ""},
        ) as mock_rtl:
            synthesize_from_config(verilog, top_module="top")

        kwargs = mock_rtl.call_args.kwargs
        assert kwargs["verilog_path"] == verilog
        assert kwargs["top_module"] == "top"
        assert kwargs["library"] == "/libs/lib.lib"
        assert kwargs["flatten"] is False
        assert kwargs["timeout"] == 120
