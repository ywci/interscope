# tests/unit/test_koika_to_rtl.py
#
# Unit tests for the ISIR → Kōika RTL synthesis pass (Coq-DSL version).
# Covers Coq file generation, parameter resolution, and mocked compilation.

import subprocess
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from isir.dialects import isir, rtl
from isir.lowering import koika_to_rtl
from isir.lowering.koika_to_rtl import (
    convert,
    _generate_coq_design,
    _resolve_type,
    _safe_width,
    _capitalize,
    KoikaToRTLError,
)


def _make_spec_module(name="test", params=None):
    """Return a fresh SpecModule with optional parameters (dict)."""
    mod = isir.SpecModule(name=name)
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
            isir.SpecStateOp(state_name="cnt", kind="register", data_type="bits<8>", initial=0)
)
        mod.rule_ops.append(
            isir.SpecRuleOp(
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
        assert "Step_merged" in coq
        assert "bits_t 8" in coq
        assert "read0(Reg_Cnt)" in coq
        assert "write0(Reg_Cnt" in coq
        assert "|>" in coq
        assert "Extraction" in coq

    def test_conditional_rule(self):
        mod = _make_spec_module("cond")
        mod.state_ops.append(
            isir.SpecStateOp(state_name="flag", kind="register", data_type="bool", initial=False)
)
        mod.rule_ops.append(
            isir.SpecRuleOp(
                rule_name="toggle",
                condition="(not (read flag))",
                actions=["(write flag true)"]
)
)
        coq = _generate_coq_design(mod, {})
        assert "if" in coq
        assert "then" in coq
        assert "else" in coq
        assert "write0(Reg_Flag" in coq

    def test_arithmetic_expression(self):
        mod = _make_spec_module("arith")
        mod.state_ops.append(
            isir.SpecStateOp(state_name="x", kind="register", data_type="bits<32>", initial=0)
)
        mod.rule_ops.append(
            isir.SpecRuleOp(
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
            isir.SpecStateOp(state_name="a", kind="register", data_type="bits<8>", initial=0)
)
        mod.rule_ops.append(
            isir.SpecRuleOp(rule_name="step1", condition="true", actions=["(write a 1)"])
)
        mod.rule_ops.append(
            isir.SpecRuleOp(rule_name="step2", condition="true", actions=["(write a 2)"])
)
        coq = _generate_coq_design(mod, {})
        assert "Step_merged |> done" in coq

    def test_initial_values(self):
        mod = _make_spec_module("init")
        mod.state_ops.append(
            isir.SpecStateOp(state_name="ready", kind="register", data_type="bool", initial=True)
)
        mod.state_ops.append(
            isir.SpecStateOp(state_name="count", kind="register", data_type="bits<16>", initial=42)
)
        mod.rule_ops.append(
            isir.SpecRuleOp(rule_name="nop", condition="true", actions=[])
)
        coq = _generate_coq_design(mod, {})
        assert "Bits.of_nat 1 1" in coq
        assert "Bits.of_nat 16 42" in coq

    def test_parameterised_design(self):
        mod = _make_spec_module("param", {"W": {"default": 16}})
        mod.state_ops.append(
            isir.SpecStateOp(state_name="x", kind="register", data_type="bits<W>", initial=0)
)
        mod.rule_ops.append(
            isir.SpecRuleOp(rule_name="inc", condition="true", actions=["(write x (add (read x) 1))"])
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
            isir.SpecStateOp(state_name="cnt", kind="register", data_type="bits<8>", initial=0)
)
        mod.rule_ops.append(
            isir.SpecRuleOp(rule_name="inc", condition="true",
                               actions=["(write cnt (add (read cnt) 1))"])
)
        return mod

    @patch("subprocess.run")
    @patch("pathlib.Path.read_text", return_value="module test_design(); endmodule")
    @patch("pathlib.Path.exists", return_value=True)
    @patch("isir.lowering.koika_to_rtl._find_compiler", return_value=Path("/fake/koika"))
    @patch("isir.lowering.koika_to_rtl._find_or_build_koika_coq_path", return_value=("/fake/coq", "-Q"))
    def test_successful_conversion(self, mock_coq, mock_compiler, mock_exists, mock_read, mock_run):
        mod = self._make_mod()
        mock_run.return_value = MagicMock(returncode=0)
        container = convert(mod, Path("/tmp/output"))
        assert isinstance(container, rtl.RTLModuleContainer)
        assert container.design_name == "test_design"

    @patch("subprocess.run")
    @patch("pathlib.Path.exists", return_value=True)
    @patch("isir.lowering.koika_to_rtl._find_compiler", return_value=Path("/fake/koika"))
    @patch("isir.lowering.koika_to_rtl._find_or_build_koika_coq_path", return_value=("/fake/coq", "-Q"))
    def test_coqc_error_raises(self, mock_coq, mock_compiler, mock_exists, mock_run):
        mod = self._make_mod()
        mock_run.side_effect = subprocess.CalledProcessError(1, "coqc", stderr="coqc error message")
        with pytest.raises(KoikaToRTLError, match="Coq compilation failed"):
            convert(mod, Path("/tmp/output"))

    @patch("subprocess.run")
    @patch("pathlib.Path.read_text", return_value="module test_design(); endmodule")
    @patch("pathlib.Path.exists", return_value=True)
    @patch("isir.lowering.koika_to_rtl._find_compiler", return_value=Path("/fake/koika"))
    @patch("isir.lowering.koika_to_rtl._find_or_build_koika_coq_path", return_value=("/fake/coq", "-Q"))
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
    @patch("isir.lowering.koika_to_rtl._find_compiler", return_value=Path("/fake/koika"))
    @patch("isir.lowering.koika_to_rtl._find_or_build_koika_coq_path", return_value=("/fake/coq", "-Q"))
    def test_timeout_raises(self, mock_coq, mock_compiler, mock_exists, mock_run):
        mod = self._make_mod()
        with pytest.raises(subprocess.TimeoutExpired, match="cmd"):
            convert(mod, Path("/tmp/output"))


def test_try_find_koika_coq_path_rejects_nonexistent_dir():
    """A missing Koika dir must yield (None, None) without invoking coqc.

    coqc only warns about a missing `-Q` directory and can still return rc=0
    when the opam switch provides the Koika libs, which used to report a
    phantom library path.
    """
    from isir.lowering.koika_to_rtl import _try_find_koika_coq_path
    assert _try_find_koika_coq_path("/nonexistent/koika/root") == (None, None)


def test_find_or_build_raises_actionable_error_for_missing_dir():
    """A missing Koika checkout must raise guidance, not a shell failure."""
    from isir.lowering.koika_to_rtl import _find_or_build_koika_coq_path
    with pytest.raises(KoikaToRTLError, match="does not exist"):
        _find_or_build_koika_coq_path("/nonexistent/koika/root")


def test_register_named_r_does_not_collide():
    """A register literally named `r` used to produce a constructor `R` that
    collided with the type-function definition (Coq: "R already exists")."""
    mod = isir.SpecModule(name="edge")
    mod.state_ops = [isir.SpecStateOp(state_name="r", kind="register", data_type="bits<5>", initial=0)]
    mod.rule_ops = [isir.SpecRuleOp(rule_name="tick", condition="true", actions=["(write r 1)"])]
    coq = _generate_coq_design(mod, {})
    assert "| Reg_R" in coq
    assert "Definition RegT (reg : reg_t)" in coq
    assert "Definition R " not in coq
    assert "koika_reg_types := RegT" in coq


def test_signed_type_width():
    """`signed<bits<N>>` must parse to N, not silently default to 32."""
    assert koika_to_rtl._koika_width("signed<bits<16>>") == 16
    assert koika_to_rtl._koika_width("bits<8>") == 8


def test_negative_literal_two_complement():
    """Negative literals emit their two's-complement pattern, not `32`d-32768`."""
    assert koika_to_rtl._coq_bits_expr(-32768, {}, 32) == "|32`d4294934528|"


def test_negative_initial_two_complement():
    """Negative register initials emit the wrapped bit pattern (RTL-faithful)."""
    mod = isir.SpecModule(name="edge")
    mod.state_ops = [isir.SpecStateOp(state_name="acc", kind="register", data_type="bits<16>", initial=-1)]
    coq = _generate_coq_design(mod, {})
    assert "(Bits.of_nat 16 65535)" in coq


def test_unsupported_op_warns_reduced_design(caplog):
    """Dropping a rule/action for unsupported ops must warn loudly."""
    import logging
    mod = isir.SpecModule(name="edge")
    mod.state_ops = [isir.SpecStateOp(state_name="y", kind="register", data_type="bits<8>", initial=0)]
    mod.state_ops.append(isir.SpecStateOp(
        state_name="m", kind="memory", data_type={"type": "memory", "elem": "bits<8>", "depth": 16}))
    mod.rule_ops = [isir.SpecRuleOp(rule_name="ld", condition="true", actions=["(write y (mem_read m 0))"])]
    with caplog.at_level(logging.WARNING):
        _generate_coq_design(mod, {})
    assert any("REDUCED" in r.message for r in caplog.records)
