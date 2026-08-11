# tests/unit/test_koika_to_rtl.py
#
# Unit tests for the SpecIR → Kōika RTL synthesis pass (Coq-DSL version).
# Covers Coq file generation, parameter resolution, and mocked compilation.

import subprocess
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from specir.dialects import spec_ir, rtl_ir
from specir.lowering import koika_to_rtl
from specir.lowering.koika_to_rtl import (
    convert,
    _generate_coq_design,
    _resolve_type,
    _safe_width,
    _capitalize,
    KoikaToRTLError,
)


def _make_spec_module(name="test", params=None):
    """Return a fresh SpecModule with optional parameters (dict)."""
    mod = spec_ir.SpecModule(name=name)
    if params is not None:
        mod.parameters = params
    return mod


class TestParameterResolution:
    def test_simple_substitution(self):
        assert _resolve_type("bits<DATA_WIDTH>", {"DATA_WIDTH": 16}) == "bits<16>"
        assert _resolve_type("bits<W>", {"W": 8}) == "bits<8>"
        assert _resolve_type("bool", {}) == "bool"

    def test_no_substitution_needed(self):
        assert _resolve_type("bits<32>", {"DATA_WIDTH": 16}) == "bits<32>"

    def test_multiple_params(self):
        assert _resolve_type("bits<W>", {"W": 12, "H": 8}) == "bits<12>"


class TestSafeWidth:
    def test_concrete_types(self):
        assert _safe_width("bool") == 1
        assert _safe_width("bits<8>") == 8
        assert _safe_width("bits<32>") == 32

    def test_fallback(self):
        assert _safe_width("bits<W>") == 32
        assert _safe_width("unknown") == 32


class TestCoqGeneration:
    def test_minimal_design(self):
        mod = _make_spec_module("minimal")
        mod.state_ops.append(
            spec_ir.SpecStateOp(state_name="cnt", kind="register", data_type="bits<8>", initial=0)
        )
        mod.rule_ops.append(
            spec_ir.SpecRuleOp(
                rule_name="inc",
                condition="true",
                actions=["(write cnt (add (read cnt) 1))"]
            )
        )
        coq = _generate_coq_design(mod, {})
        assert "Require Import Koika.Frontend." in coq
        assert "Inductive reg_t :=" in coq
        assert "Cnt" in coq
        assert "Inductive rule_name_t :=" in coq
        assert "Inc_act_0" in coq
        assert "bits_t 8" in coq
        assert "read0(Cnt)" in coq
        assert "write0(Cnt" in coq
        assert "|>" in coq
        assert "Extraction" in coq

    def test_conditional_rule(self):
        mod = _make_spec_module("cond")
        mod.state_ops.append(
            spec_ir.SpecStateOp(state_name="flag", kind="register", data_type="bool", initial=False)
        )
        mod.rule_ops.append(
            spec_ir.SpecRuleOp(
                rule_name="toggle",
                condition="(not (read flag))",
                actions=["(write flag true)"]
            )
        )
        coq = _generate_coq_design(mod, {})
        assert "if" in coq
        assert "then" in coq
        assert "else" in coq
        assert "write0(Flag" in coq

    def test_arithmetic_expression(self):
        mod = _make_spec_module("arith")
        mod.state_ops.append(
            spec_ir.SpecStateOp(state_name="x", kind="register", data_type="bits<32>", initial=0)
        )
        mod.rule_ops.append(
            spec_ir.SpecRuleOp(
                rule_name="compute",
                condition="true",
                actions=["(write x (add (mul (read x) 3) 1))"]
            )
        )
        coq = _generate_coq_design(mod, {})
        assert "Inductive reg_t" in coq
        assert "Extraction" in coq
        assert "Compute_act_0" not in coq

    def test_sequential_scheduler(self):
        mod = _make_spec_module("seq")
        mod.state_ops.append(
            spec_ir.SpecStateOp(state_name="a", kind="register", data_type="bits<8>", initial=0)
        )
        mod.rule_ops.append(
            spec_ir.SpecRuleOp(rule_name="step1", condition="true", actions=["(write a 1)"])
        )
        mod.rule_ops.append(
            spec_ir.SpecRuleOp(rule_name="step2", condition="true", actions=["(write a 2)"])
        )
        coq = _generate_coq_design(mod, {})
        assert "Step1_act_0 |> Step2_act_0 |> done" in coq

    def test_initial_values(self):
        mod = _make_spec_module("init")
        mod.state_ops.append(
            spec_ir.SpecStateOp(state_name="ready", kind="register", data_type="bool", initial=True)
        )
        mod.state_ops.append(
            spec_ir.SpecStateOp(state_name="count", kind="register", data_type="bits<16>", initial=42)
        )
        mod.rule_ops.append(
            spec_ir.SpecRuleOp(rule_name="nop", condition="true", actions=[])
        )
        coq = _generate_coq_design(mod, {})
        assert "Bits.of_nat 1 1" in coq
        assert "Bits.of_nat 16 42" in coq

    def test_parameterised_design(self):
        mod = _make_spec_module("param", {"W": {"default": 16}})
        mod.state_ops.append(
            spec_ir.SpecStateOp(state_name="x", kind="register", data_type="bits<W>", initial=0)
        )
        mod.rule_ops.append(
            spec_ir.SpecRuleOp(rule_name="inc", condition="true", actions=["(write x (add (read x) 1))"])
        )
        coq = _generate_coq_design(mod, {"W": 16})
        assert "bits_t 16" in coq

    def test_empty_design(self):
        mod = _make_spec_module("empty")
        coq = _generate_coq_design(mod, {})
        assert "Inductive reg_t :=" in coq
        assert "Inductive rule_name_t :=" in coq
        assert "Extraction" in coq
        assert "Dummy" in coq


class TestConvert:
    def _make_mod(self, name="test_design"):
        mod = _make_spec_module(name)
        mod.state_ops.append(
            spec_ir.SpecStateOp(state_name="cnt", kind="register", data_type="bits<8>", initial=0)
        )
        mod.rule_ops.append(
            spec_ir.SpecRuleOp(rule_name="inc", condition="true",
                               actions=["(write cnt (add (read cnt) 1))"])
        )
        return mod

    @patch("subprocess.run")
    @patch("pathlib.Path.read_text", return_value="module test_design(); endmodule")
    @patch("pathlib.Path.exists", return_value=True)
    @patch("specir.lowering.koika_to_rtl._find_compiler", return_value=Path("/fake/koika"))
    @patch("specir.lowering.koika_to_rtl._find_or_build_koika_coq_path", return_value=("/fake/coq", "-Q"))
    def test_successful_conversion(self, mock_coq, mock_compiler, mock_exists, mock_read, mock_run):
        mod = self._make_mod()
        mock_run.return_value = MagicMock(returncode=0)
        container = convert(mod, Path("/tmp/output"))
        assert isinstance(container, rtl_ir.RTLModuleContainer)
        assert container.design_name == "test_design"

    @patch("subprocess.run")
    @patch("pathlib.Path.exists", return_value=True)
    @patch("specir.lowering.koika_to_rtl._find_compiler", return_value=Path("/fake/koika"))
    @patch("specir.lowering.koika_to_rtl._find_or_build_koika_coq_path", return_value=("/fake/coq", "-Q"))
    def test_coqc_error_raises(self, mock_coq, mock_compiler, mock_exists, mock_run):
        mod = self._make_mod()
        mock_run.side_effect = subprocess.CalledProcessError(1, "coqc", stderr="coqc error message")
        with pytest.raises(KoikaToRTLError, match="Coq compilation failed"):
            convert(mod, Path("/tmp/output"))

    @patch("subprocess.run")
    @patch("pathlib.Path.read_text", return_value="module test_design(); endmodule")
    @patch("pathlib.Path.exists", return_value=True)
    @patch("specir.lowering.koika_to_rtl._find_compiler", return_value=Path("/fake/koika"))
    @patch("specir.lowering.koika_to_rtl._find_or_build_koika_coq_path", return_value=("/fake/coq", "-Q"))
    def test_cuttlec_error_raises(self, mock_coq, mock_compiler, mock_exists, mock_read, mock_run):
        mod = self._make_mod()
        mock_run.side_effect = [
            MagicMock(returncode=0),
            subprocess.CalledProcessError(1, "cuttlec", stderr="cuttlec error")
        ]
        with pytest.raises(KoikaToRTLError, match="Kōika compilation failed"):
            convert(mod, Path("/tmp/output"))

    @patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 300, output=b"", stderr=b""))
    @patch("pathlib.Path.exists", return_value=True)
    @patch("specir.lowering.koika_to_rtl._find_compiler", return_value=Path("/fake/koika"))
    @patch("specir.lowering.koika_to_rtl._find_or_build_koika_coq_path", return_value=("/fake/coq", "-Q"))
    def test_timeout_raises(self, mock_coq, mock_compiler, mock_exists, mock_run):
        mod = self._make_mod()
        with pytest.raises(subprocess.TimeoutExpired, match="cmd"):
            convert(mod, Path("/tmp/output"))
