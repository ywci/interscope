# tests/unit/test_split_rules.py
#
# Unit tests for the monolithic-rule splitting pass
# (src/isir/lowering/split_rules.py).

import pytest
from isir.dialects.isir import SpecModule, SpecRuleOp, SpecScheduleOp
from isir.lowering.split_rules import (
    split_rules,
    _conjoin_conditions,
    _contains_ite,
    _flatten_ite_chain,
    _negate_disjunction,
    _original_rule_name,
)


def make_module(name="alu", schedule_op=None):
    """Build a bare SpecModule with no rules."""
    return SpecModule(name=name, schedule_op=schedule_op)


def exec_rule(**kwargs):
    """Return a SpecRuleOp with sensible defaults for an execute rule."""
    defaults = dict(
        rule_name="exec",
        condition=None,
        actions=["(ite (read op) (write out 1) (write out 2))"],
        priority=None,
        rule_attributes=["split"],
    )
    defaults.update(kwargs)
    return SpecRuleOp(**defaults)


def test_single_ite_splits_into_two_rules():
    mod = make_module()
    mod.rule_ops = [exec_rule()]

    new_mod = split_rules(mod)

    assert len(new_mod.rule_ops) == 2
    names = [r.rule_name for r in new_mod.rule_ops]
    assert names == ["exec_0", "exec_1"]

    by_name = {r.rule_name: r for r in new_mod.rule_ops}
    assert by_name["exec_0"].condition == "(read op)"
    assert by_name["exec_0"].actions == ["(write out 1)"]
    assert by_name["exec_1"].condition == "(not (read op))"
    assert by_name["exec_1"].actions == ["(write out 2)"]


def test_nested_ite_chain_splits_with_default():
    """A nested ite cascade becomes one rule per branch plus a default rule."""
    mod = make_module()
    mod.rule_ops = [
        SpecRuleOp(
            rule_name="dispatch",
            condition=None,
            actions=[
                "(ite (eq (read op) 0) (write out 1) "
                "(ite (eq (read op) 1) (write out 2) (write out 3)))"
            ],
            rule_attributes=["split"],
        )
    ]

    new_mod = split_rules(mod)

    assert len(new_mod.rule_ops) == 3
    by_name = {r.rule_name: r for r in new_mod.rule_ops}
    assert set(by_name) == {"dispatch_0", "dispatch_1", "dispatch_2"}

    assert by_name["dispatch_0"].condition == "(eq (read op) 0)"
    assert by_name["dispatch_0"].actions == ["(write out 1)"]
    assert by_name["dispatch_1"].condition == "(eq (read op) 1)"
    assert by_name["dispatch_1"].actions == ["(write out 2)"]
    assert by_name["dispatch_2"].condition == "(not (or (eq (read op) 0) (eq (read op) 1)))"
    assert by_name["dispatch_2"].actions == ["(write out 3)"]


def test_split_preserves_surrounding_actions():
    """Non-ite actions before/after the ite action are kept in every branch."""
    mod = make_module()
    mod.rule_ops = [
        SpecRuleOp(
            rule_name="exec",
            condition=None,
            actions=[
                "(write log 0)",
                "(ite (read op) (write out 1) (write out 2))",
                "(write done 1)",
            ],
            rule_attributes=["split"],
        )
    ]

    new_mod = split_rules(mod)

    assert len(new_mod.rule_ops) == 2
    for r in new_mod.rule_ops:
        assert r.actions[0] == "(write log 0)"
        assert r.actions[-1] == "(write done 1)"
    assert new_mod.rule_ops[0].actions[1] == "(write out 1)"
    assert new_mod.rule_ops[1].actions[1] == "(write out 2)"


def test_split_conjoins_original_condition():
    mod = make_module()
    mod.rule_ops = [exec_rule(condition="(read en)")]

    new_mod = split_rules(mod)

    by_name = {r.rule_name: r for r in new_mod.rule_ops}
    assert by_name["exec_0"].condition == "(and (read en) (read op))"
    assert by_name["exec_1"].condition == "(and (read en) (not (read op)))"


def test_split_preserves_priority_and_attributes():
    mod = make_module()
    mod.rule_ops = [exec_rule(priority=7, rule_attributes=["split", "atomic"])]

    new_mod = split_rules(mod)

    for r in new_mod.rule_ops:
        assert r.priority == 7
        assert r.rule_attributes == ["split", "atomic"]


def test_rule_without_split_attribute_is_not_split():
    """Absence of the attribute is opt-out: the rule is left untouched."""
    mod = make_module()
    mod.rule_ops = [exec_rule(rule_attributes=[])]

    new_mod = split_rules(mod)

    assert new_mod is mod
    assert len(new_mod.rule_ops) == 1
    assert new_mod.rule_ops[0].rule_name == "exec"
    assert new_mod.rule_ops[0].actions == ["(ite (read op) (write out 1) (write out 2))"]


def test_rule_with_other_attribute_is_not_split():
    """Only the exact split attribute triggers splitting."""
    mod = make_module()
    mod.rule_ops = [exec_rule(rule_attributes=["atomic", "commutative"])]

    new_mod = split_rules(mod)

    assert new_mod is mod
    assert len(new_mod.rule_ops) == 1


def test_rule_with_split_attribute_but_no_ite_is_not_split():
    """An opt-in rule without an ite action is left unchanged."""
    mod = make_module()
    mod.rule_ops = [
        SpecRuleOp(
            rule_name="plain",
            actions=["(write out 1)"],
            rule_attributes=["split"],
        )
    ]

    new_mod = split_rules(mod)

    assert new_mod is mod
    assert len(new_mod.rule_ops) == 1


def test_custom_split_attribute():
    mod = make_module()
    mod.rule_ops = [
        SpecRuleOp(
            rule_name="exec",
            condition=None,
            actions=["(ite (read op) (write out 1) (write out 2))"],
            rule_attributes=["explode"],
        )
    ]

    new_mod = split_rules(mod, split_attribute="explode")

    assert len(new_mod.rule_ops) == 2


def test_multiple_ite_actions_raise_value_error():
    mod = make_module()
    mod.rule_ops = [
        SpecRuleOp(
            rule_name="bad",
            actions=[
                "(ite (read a) (write x 1) (write x 2))",
                "(ite (read b) (write y 1) (write y 2))",
            ],
            rule_attributes=["split"],
        )
    ]

    with pytest.raises(ValueError, match="multiple independent"):
        split_rules(mod)


def test_unparseable_action_is_not_split():
    """A rule with a malformed action cannot be split and is left as-is."""
    mod = make_module()
    mod.rule_ops = [
        SpecRuleOp(
            rule_name="weird",
            actions=["(ite (read op) (write out 1)"],
            rule_attributes=["split"]
        )
    ]

    new_mod = split_rules(mod)

    assert new_mod is mod
    assert len(new_mod.rule_ops) == 1


def test_schedule_becomes_conflict_free():
    mod = make_module()
    mod.rule_ops = [exec_rule()]

    new_mod = split_rules(mod)

    assert new_mod.schedule_op is not None
    assert new_mod.schedule_op.kind == "conflict_free"
    assert new_mod.schedule_op.conflict_sets == [["exec_0", "exec_1"]]


def test_no_schedule_creates_conflict_free():
    mod = make_module(schedule_op=None)
    mod.rule_ops = [exec_rule()]

    new_mod = split_rules(mod)

    assert new_mod.schedule_op is not None
    assert new_mod.schedule_op.kind == "conflict_free"


def test_existing_conflict_sets_are_preserved():
    mod = make_module(
        schedule_op=SpecScheduleOp(
            kind="conflict_free", conflict_sets=[["other_a", "other_b"]]
        )
    )
    mod.rule_ops = [exec_rule()]

    new_mod = split_rules(mod)

    assert new_mod.schedule_op.kind == "conflict_free"
    assert ["other_a", "other_b"] in new_mod.schedule_op.conflict_sets
    assert ["exec_0", "exec_1"] in new_mod.schedule_op.conflict_sets


def test_sequential_schedule_switches_to_conflict_free(caplog):
    import logging

    mod = make_module(
        schedule_op=SpecScheduleOp(kind="sequential", rule_order=["exec"])
    )
    mod.rule_ops = [exec_rule()]

    with caplog.at_level(logging.WARNING, logger="isir.lowering.split_rules"):
        new_mod = split_rules(mod)

    assert new_mod.schedule_op.kind == "conflict_free"
    assert any("sequential" in rec.message for rec in caplog.records)


def test_original_module_is_not_mutated():
    mod = make_module()
    mod.rule_ops = [exec_rule()]

    split_rules(mod)

    assert len(mod.rule_ops) == 1
    assert mod.rule_ops[0].rule_name == "exec"
    assert mod.schedule_op is None


def test_non_split_rules_are_preserved_alongside_split_rules():
    mod = make_module()
    mod.rule_ops = [
        exec_rule(),
        SpecRuleOp(rule_name="tick", condition="true", actions=["(write t 1)"])
    ]

    new_mod = split_rules(mod)

    names = [r.rule_name for r in new_mod.rule_ops]
    assert "exec_0" in names
    assert "exec_1" in names
    assert "tick" in names
    tick = next(r for r in new_mod.rule_ops if r.rule_name == "tick")
    assert tick.condition == "true"
    assert tick.actions == ["(write t 1)"]


def test_conjoin_conditions_variants():
    assert _conjoin_conditions(None, "(read op)") == "(read op)"
    assert _conjoin_conditions("", "(read op)") == "(read op)"
    assert _conjoin_conditions("   ", "(read op)") == "(read op)"
    assert _conjoin_conditions("true", "(read op)") == "(read op)"
    assert _conjoin_conditions("True", "(read op)") == "(read op)"
    assert _conjoin_conditions("(read en)", "(read op)") == "(and (read en) (read op))"


def test_negate_disjunction_variants():
    assert _negate_disjunction([]) == "true"
    assert _negate_disjunction(["a"]) == "(not a)"
    assert _negate_disjunction(["a", "b"]) == "(not (or a b))"
    assert _negate_disjunction(["a", "b", "c"]) == "(not (or a b c))"


def test_original_rule_name_strips_numeric_suffix():
    assert _original_rule_name("exec_0") == "exec"
    assert _original_rule_name("exec_10") == "exec"
    assert _original_rule_name("exec") == "exec"
    assert _original_rule_name("exec_foo") == "exec_foo"
    assert _original_rule_name("foo_bar_1") == "foo_bar"


def test_contains_ite():
    assert _contains_ite(["ite", "c", "t", "e"]) is True
    assert _contains_ite(["write", "out", ["ite", "c", "t", "e"]]) is True
    assert _contains_ite(["write", "out", 1]) is False
    assert _contains_ite("not-a-list") is False
    assert _contains_ite([]) is False


def test_flatten_ite_chain_non_ite_returns_none():
    assert _flatten_ite_chain(["write", "out", 1]) is None
    assert _flatten_ite_chain("not-a-list") is None
    assert _flatten_ite_chain(["ite", "c", "t"]) is None


def test_flatten_ite_chain_single_level():
    conditions, bodies, default = _flatten_ite_chain(
        ["ite", ["read", "op"], ["write", "out", 1], ["write", "out", 2]]
    )
    assert conditions == ["(read op)"]
    assert bodies == [["write", "out", 1]]
    assert default == ["write", "out", 2]
