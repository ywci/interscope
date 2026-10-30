# tests/unit/test_spec_consistency.py
#
# Self-Consistency verification (Section 3): property satisfiability + rule
# fireability via z3.

import shutil
import pytest
from isir.dialects.isir import SpecModule, SpecPropertyOp, SpecRuleOp, SpecStateOp
from isir.lowering.spec_consistency import check_self_consistency


pytestmark = pytest.mark.skipif(shutil.which("z3") is None, reason="z3 not installed")


def _spec(name, rules, props, states=None, inputs=()):
    return SpecModule(
        name=name,
        state_ops=states or [SpecStateOp(state_name="x", kind="register", data_type="bits<4>")],
        rule_ops=rules, property_ops=props, proof_obligations=[],
        inputs=list(inputs), outputs=[],
    )


class TestSelfConsistency:
    def test_consistent_spec(self):
        spec = _spec("ok",
                     rules=[SpecRuleOp(rule_name="tick", condition="true", actions=["(write x (add (read x) 1))"])],
                     props=[SpecPropertyOp(prop_name="x_nonneg", kind="safety",
                                           expression={"kind": "always", "operand": "(gte (read x) 0)"})])
        r = check_self_consistency(spec)
        assert r.status == "consistent"
        assert r.properties[0].status == "sat"
        assert r.rules[0].status == "sat"

    def test_contradictory_property(self):
        spec = _spec("bad",
                     rules=[],
                     props=[SpecPropertyOp(prop_name="x_both", kind="safety",
                                           expression={"kind": "always", "operand": "(and (eq (read x) 1) (eq (read x) 2))"})])
        r = check_self_consistency(spec)
        assert r.status == "inconsistent"
        assert r.properties[0].status == "unsat"

    def test_dead_rule(self):
        spec = _spec("dead",
                     rules=[SpecRuleOp(rule_name="never", condition="false", actions=["(write x 1)"])],
                     props=[])
        r = check_self_consistency(spec)
        assert r.status == "inconsistent"
        assert r.rules[0].status == "unsat"

    def test_no_properties_is_consistent(self):
        spec = _spec("empty", rules=[], props=[])
        r = check_self_consistency(spec)
        assert r.status == "consistent"
        assert r.properties == [] and r.rules == []


class TestAgainstExamples:
    def test_counter_gcd_arbiter_consistent(self):
        from pathlib import Path
        from isir.parser.parser import parse_isir
        from isir.lowering.ast_to_isir import convert_ast_to_isir_module
        for name in ["counter", "gcd", "arbiter", "saturating_adder"]:
            spec = convert_ast_to_isir_module(parse_isir(Path(f"examples/{name}/{name}.isir")).module)
            r = check_self_consistency(spec)
            assert r.status == "consistent", (name, r.to_dict())
