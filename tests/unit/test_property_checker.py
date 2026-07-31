# tests/unit/test_property_checker.py
#
# Unit tests for the SpecIR property checker.
# Verifies temporal operators, assumption handling, and result details.

import pytest
from specir.parser.ast import Property, TemporalExpr
from specir.verification.property_checker import (
    check_property,
    check_all_properties,
    PropertyCheckResult,
    PropertyCheckError
)


def make_trace(*cycles):
    """Create a list of cycle dicts suitable for the property checker.

    Each argument is a dict with optional keys: state, inputs, outputs, memories.
    """
    trace = []
    for i, c in enumerate(cycles):
        entry = {
            "state": c.get("state", {}),
            "inputs": c.get("inputs", {}),
            "outputs": c.get("outputs", {}),
            "memories": c.get("memories", {})
        }
        trace.append(entry)
    return trace


def make_property(name="p", kind="safety", temporal_kind="always",
                  operand=None, left=None, right=None, bound=None,
                  assumes=None, guarantees=None):
    """Build an AST Property object for testing."""
    expr = TemporalExpr(
        kind=temporal_kind,
        operand=operand,
        left=left,
        right=right,
        bound=bound
    )
    return Property(
        name=name,
        kind=kind,
        expression=expr,
        assumes=assumes or [],
        guarantees=guarantees or []
    )


class TestAlways:
    def test_holds(self):
        trace = make_trace(
            {"state": {"a": 1}},
            {"state": {"a": 1}},
            {"state": {"a": 1}}
        )
        prop = make_property(operand="(eq (read a) 1)")
        result = check_property(prop, trace)
        assert result.holds is True
        assert not result.vacuous

    def test_fails(self):
        trace = make_trace(
            {"state": {"a": 1}},
            {"state": {"a": 2}}
        )
        prop = make_property(operand="(eq (read a) 1)")
        result = check_property(prop, trace)
        assert result.holds is False
        assert result.failing_cycle == 1
        assert "at cycle 1" in result.detail


class TestEventually:
    def test_holds(self):
        trace = make_trace(
            {"state": {"a": 0}},
            {"state": {"a": 0}},
            {"state": {"a": 1}}
        )
        prop = make_property(kind="liveness", temporal_kind="eventually",
                             operand="(eq (read a) 1)")
        result = check_property(prop, trace)
        assert result.holds is True

    def test_fails(self):
        trace = make_trace(
            {"state": {"a": 0}},
            {"state": {"a": 0}}
        )
        prop = make_property(kind="liveness", temporal_kind="eventually",
                             operand="(eq (read a) 1)")
        result = check_property(prop, trace)
        assert result.holds is False
        assert "never satisfied" in result.detail

    def test_bounded_holds(self):
        trace = make_trace(
            {"state": {"a": 0}},
            {"state": {"a": 1}},
            {"state": {"a": 0}}
        )
        prop = make_property(kind="liveness", temporal_kind="eventually",
                             operand="(eq (read a) 1)", bound=2)
        result = check_property(prop, trace)
        assert result.holds is True

    def test_bounded_fails(self):
        trace = make_trace(
            {"state": {"a": 0}},
            {"state": {"a": 0}},
            {"state": {"a": 1}}
        )
        prop = make_property(kind="liveness", temporal_kind="eventually",
                             operand="(eq (read a) 1)", bound=1)
        result = check_property(prop, trace)
        assert result.holds is False
        assert "bound" in result.detail


class TestUntil:
    def test_holds(self):
        trace = make_trace(
            {"state": {"a": 1}},
            {"state": {"a": 1}},
            {"state": {"a": 0}}
        )
        prop = make_property(temporal_kind="until",
                             left="(eq (read a) 1)",
                             right="(eq (read a) 0)")
        result = check_property(prop, trace)
        assert result.holds is True

    def test_fails_left_broken(self):
      trace = make_trace(
          {"state": {"a": 1}},
          {"state": {"a": 2}},
          {"state": {"a": 3}}
      )
      prop = make_property(temporal_kind="until",
                          left="(eq (read a) 1)",
                          right="(eq (read a) 0)")
      result = check_property(prop, trace)
      assert result.holds is False
      assert "Left operand false" in result.detail

    def test_fails_right_never(self):
        trace = make_trace(
            {"state": {"a": 1}},
            {"state": {"a": 1}}
        )
        prop = make_property(temporal_kind="until",
                             left="(eq (read a) 1)",
                             right="(eq (read a) 0)")
        result = check_property(prop, trace)
        assert result.holds is False
        assert "never became true" in result.detail


class TestAssumptions:
    def test_assumption_holds(self):
        trace = make_trace({"state": {"rst": 0}}, {"state": {"rst": 0}})
        prop = make_property(
            operand="(eq (read rst) 0)",
            assumes=["(eq (read rst) 0)"]
        )
        result = check_property(prop, trace)
        assert result.holds is True
        assert not result.vacuous

    def test_assumption_violated_makes_vacuous(self):
        trace = make_trace({"state": {"rst": 1}}, {"state": {"rst": 0}})
        prop = make_property(
            operand="(eq (read rst) 0)",
            assumes=["(eq (read rst) 0)"]
        )
        result = check_property(prop, trace)
        assert result.holds is True
        assert result.vacuous is True
        assert "Assumption violated" in result.detail

    def test_assumption_fails_but_operand_also_fails(self):
        trace = make_trace({"state": {"a": 2}}, {"state": {"a": 2}})
        prop = Property(
            name="p",
            kind="safety",
            expression=TemporalExpr(kind="always", operand="(eq (read a) 1)"),
            assumes=["(eq (read a) 0)"]
        )
        result = check_property(prop, trace)
        assert result.holds is True
        assert result.vacuous is True


class TestTemporalSubOperators:
    def test_rose_in_always(self):
        trace = make_trace(
            {"state": {"sig": 0}},
            {"state": {"sig": 1}},
            {"state": {"sig": 1}}
        )
        prop = make_property(
            kind="liveness",
            temporal_kind="eventually",
            operand="(rose (read sig))"
        )
        result = check_property(prop, trace)
        assert result.holds is True

    def test_fell_in_always(self):
        trace = make_trace(
            {"state": {"sig": 1}},
            {"state": {"sig": 0}}
        )
        prop = make_property(
            temporal_kind="always",
            operand="(not (fell (read sig)))"
        )
        result = check_property(prop, trace)
        assert result.holds is False

    def test_next_operator(self):
        trace = make_trace(
            {"state": {"a": 1}},
            {"state": {"a": 2}}
        )
        prop = make_property(
            kind="liveness",
            temporal_kind="eventually",
            operand="(eq (next (read a)) 2)",
            bound=0
        )
        result = check_property(prop, trace)
        assert result.holds is True

    def test_stable(self):
        trace = make_trace(
            {"state": {"a": 1}},
            {"state": {"a": 1}},
            {"state": {"a": 2}}
        )
        prop = make_property(
            temporal_kind="always",
            operand="(implies (not (eq (read a) 2)) (stable (read a)))"
        )
        result = check_property(prop, trace)
        assert result.holds is False
        assert result.failing_cycle == 0


def test_evaluation_error_caught():
    trace = make_trace({"state": {}})
    prop = make_property(operand="(read unknown)")
    results = check_all_properties([prop], trace)
    assert len(results) == 1
    assert results[0].holds is False
    assert "evaluated to false" in results[0].detail.lower()


def test_check_all_properties():
    p1 = make_property(name="p1", operand="(eq 1 1)")
    p2 = make_property(name="p2", operand="(eq 1 2)")
    trace = make_trace({"state": {}})
    results = check_all_properties([p1, p2], trace)
    assert len(results) == 2
    assert results[0].holds is True
    assert results[1].holds is False


def test_property_check_result_fields():
    trace = make_trace({"state": {"x": 0}})
    prop = make_property(operand="(eq (read x) 1)")
    result = check_property(prop, trace)
    assert result.name == "p"
    assert result.holds is False
    assert result.failing_cycle == 0
    assert result.vacuous is False
    assert result.detail is not None
