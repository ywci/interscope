# tests/unit/test_perf_analyzer.py
#
# Unit tests for the PERF structural analyzer (PERFAnalyzer).

import pytest
from isir.verification.perf.perf_analyzer import PERFAnalyzer, ObligationAnalysis


def _write(tmp_path, name, content):
    """Write a .v file and return its path."""
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


class TestStepConstructors:
    def test_extracts_step_constructors(self, tmp_path):
        content = """\
Inductive step : state -> inputs -> state -> Prop := step_load_inputs : forall s inputs, True -> step s inputs inputs
  | step_execute : forall s inputs,
      True ->
      step s inputs (if op_reg s =? 0 then A else B).

Theorem sample_thm : forall s inputs, step s inputs inputs.
"""
        path = _write(tmp_path, "sample.v", content)
        analysis = PERFAnalyzer().analyze(path, "sample_thm")

        assert analysis.num_step_constructors == 2
        assert analysis.step_constructor_names == ["step_load_inputs", "step_execute"]
        assert analysis.max_ite_depth == 1
        assert analysis.has_nested_ite is False

    def test_no_step_definition(self, tmp_path):
        content = "Theorem sample_thm : forall s inputs, True.\n"
        path = _write(tmp_path, "no_step.v", content)
        analysis = PERFAnalyzer().analyze(path, "sample_thm")
        assert analysis.num_step_constructors == 0
        assert analysis.step_constructor_names == []


class TestNestedIte:
    def test_else_if_chain_depth(self, tmp_path):
        content = """\
Inductive step : state -> inputs -> state -> Prop := step_execute : forall s inputs,
      True ->
      step s inputs
        (if op_reg s =? 0 then A
         else if op_reg s =? 1 then B
         else if op_reg s =? 2 then C
         else D).

Theorem sample_thm : forall s inputs, step s inputs inputs.
"""
        path = _write(tmp_path, "chain.v", content)
        analysis = PERFAnalyzer().analyze(path, "sample_thm")

        assert analysis.num_step_constructors == 1
        assert analysis.max_ite_depth == 3
        assert analysis.has_nested_ite is True

    def test_parenthesized_nested_if_depth(self, tmp_path):
        content = """\
Inductive step : state -> inputs -> state -> Prop := step_execute : forall s inputs,
      True ->
      step s inputs (if a then (if b then X else Y) else Z).

Theorem sample_thm : forall s inputs, step s inputs inputs.
"""
        path = _write(tmp_path, "nested.v", content)
        analysis = PERFAnalyzer().analyze(path, "sample_thm")

        assert analysis.max_ite_depth == 2
        assert analysis.has_nested_ite is True


class TestRuleSplitting:
    def test_suggests_rule_splitting(self, tmp_path):
        content = """\
Inductive step : state -> inputs -> state -> Prop := step_execute : forall s inputs,
      True ->
      step s inputs
        (if op_reg s =? 0 then A
         else if op_reg s =? 1 then B
         else if op_reg s =? 2 then C
         else D).

Theorem sample_thm : forall s inputs, step s inputs inputs.
"""
        path = _write(tmp_path, "split.v", content)
        analysis = PERFAnalyzer().analyze(path, "sample_thm")
        assert analysis.suggests_rule_splitting is True

    def test_no_splitting_when_depth_too_shallow(self, tmp_path):
        content = """\
Inductive step : state -> inputs -> state -> Prop := step_execute : forall s inputs,
      True ->
      step s inputs (if op_reg s =? 0 then A else B).

Theorem sample_thm : forall s inputs, step s inputs inputs.
"""
        path = _write(tmp_path, "shallow.v", content)
        analysis = PERFAnalyzer().analyze(path, "sample_thm")
        assert analysis.suggests_rule_splitting is False

    def test_no_splitting_without_step_execute(self, tmp_path):
        content = """\
Inductive step : state -> inputs -> state -> Prop := step_other : forall s inputs,
      True ->
      step s inputs
        (if a then A
         else if b then B
         else if c then C
         else D).

Theorem sample_thm : forall s inputs, step s inputs inputs.
"""
        path = _write(tmp_path, "no_execute.v", content)
        analysis = PERFAnalyzer().analyze(path, "sample_thm")
        assert analysis.suggests_rule_splitting is False


class TestDuplicatedSubexpressions:
    def test_duplicated_result_and_zero_reg(self, tmp_path):
        content = """\
Inductive step : state -> inputs -> state -> Prop := step_execute : forall s inputs,
      True ->
      step s inputs {| result_reg := add_reg s a b; zero_reg := add_reg s a b; |}.

Theorem sample_thm : forall s inputs, True.
"""
        path = _write(tmp_path, "dup.v", content)
        analysis = PERFAnalyzer().analyze(path, "sample_thm")

        assert len(analysis.duplicated_subexpressions) == 1
        assert "zero_reg computation duplicates result_reg expression" in analysis.duplicated_subexpressions[0]
        assert analysis.suggests_lemma_introduction is True
        assert analysis.suggested_helper_lemmas == ["helper_result_reg_zero_reg"]

    def test_duplicated_overflow_and_result_reg(self, tmp_path):
        content = """\
Inductive step : state -> inputs -> state -> Prop := step_execute : forall s inputs,
      True ->
      step s inputs {| result_reg := add_reg s a b; zero_reg := zz; overflow_reg := add_reg s a b; |}.

Theorem sample_thm : forall s inputs, True.
"""
        path = _write(tmp_path, "dup_overflow.v", content)
        analysis = PERFAnalyzer().analyze(path, "sample_thm")

        assert len(analysis.duplicated_subexpressions) == 1
        assert "overflow_reg and result_reg share common sub" in analysis.duplicated_subexpressions[0]
        assert analysis.suggests_lemma_introduction is True
        assert analysis.suggested_helper_lemmas == ["helper_overflow_reg_result_reg"]

    def test_no_duplicates_when_no_record(self, tmp_path):
        content = """\
Inductive step : state -> inputs -> state -> Prop := step_execute : forall s inputs, True -> step s inputs inputs.

Theorem sample_thm : forall s inputs, step s inputs inputs.
"""
        path = _write(tmp_path, "no_dup.v", content)
        analysis = PERFAnalyzer().analyze(path, "sample_thm")
        assert analysis.duplicated_subexpressions == []
        assert analysis.suggests_lemma_introduction is False
        assert analysis.suggested_helper_lemmas == []


class TestTheoremAndDefinitional:
    def test_expression_size_and_missing_theorem(self, tmp_path):
        content = """\
Inductive step : state -> inputs -> state -> Prop := step_execute : forall s inputs, True -> step s inputs inputs.

Theorem sample_thm : forall s inputs, step s inputs inputs.
"""
        path = _write(tmp_path, "expr.v", content)
        analysis = PERFAnalyzer().analyze(path, "sample_thm")
        statement = "forall s inputs, step s inputs inputs"
        assert analysis.expression_size == len(statement)

        missing = PERFAnalyzer().analyze(path, "does_not_exist")
        assert missing.expression_size == 0

    def test_is_definitional_direct(self):
        analyzer = PERFAnalyzer()
        assert analyzer._is_definitional("zero_reg s = (Nat.eqb (result_reg s) 0)") is True
        assert analyzer._is_definitional("forall s, step s s") is False
        assert analyzer._is_definitional("") is False

    def test_find_theorem_direct(self):
        analyzer = PERFAnalyzer()
        content = "Theorem foo : forall x, x = x.\nTheorem bar : True.\n"
        name, stmt = analyzer._find_theorem(content, "foo")
        assert name == "foo"
        assert stmt == "forall x, x = x"
        assert analyzer._find_theorem(content, "nope") == (None, None)


class TestMissingFile:
    def test_analyze_missing_file_returns_default(self, tmp_path):
        missing = tmp_path / "does_not_exist.v"
        analysis = PERFAnalyzer().analyze(missing, "sample_thm")
        assert analysis == ObligationAnalysis()
        assert analysis.num_step_constructors == 0
        assert analysis.max_ite_depth == 0
        assert analysis.duplicated_subexpressions == []
        assert analysis.suggests_rule_splitting is False
