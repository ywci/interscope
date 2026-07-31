# tests/unit/test_spec_to_acl2.py
#
# Unit tests for lowering from SpecModule to ACL2Module.

import pytest
from specir.dialects import spec_ir, acl2_ir
from specir.lowering import spec_to_acl2


def create_basic_spec_module():
    """Return a SpecModule with two registers, one memory, three rules, and a property."""
    state_ops = [
        spec_ir.SpecStateOp(
            state_name="count",
            kind="register",
            data_type="bits<8>",
            initial=0
        ),
        spec_ir.SpecStateOp(
            state_name="flag",
            kind="register",
            data_type="bool",
            initial=False
        ),
        spec_ir.SpecStateOp(
            state_name="mem",
            kind="memory",
            data_type={"type": "memory", "elem": "bits<32>", "depth": 8}
        )
    ]

    rule_ops = [
        spec_ir.SpecRuleOp(
            rule_name="inc",
            condition="(lt (read count) 255)",
            actions=[
                "(write count (add (read count) 1))",
                "(write flag true)",
            ],
            priority=10
        ),
        spec_ir.SpecRuleOp(
            rule_name="reset_flag",
            condition="(read flag)",
            actions=["(write flag false)"],
            priority=5
        ),
        spec_ir.SpecRuleOp(
            rule_name="noop",
            condition="true",
            actions=[],
            priority=0
        )
    ]

    property_ops = [
        spec_ir.SpecPropertyOp(
            prop_name="count_bound",
            kind="safety",
            expression={"kind": "always", "operand": "(le (read count) 255)"},
            assumes=["(not (read flag))"],
            guarantees=[]
        )
    ]

    proof_obligations = [
        {
            "property": "count_bound",
            "status": "unproved",
            "engine": "theorem_proving",
            "backend": "acl2",
            "metadata": {"acl2_hints": ['("Goal" :induct t)']}
        }
    ]

    inputs = [
        spec_ir.Interface(name="start", direction="input", data_type="bool")
    ]
    outputs = [
        spec_ir.Interface(name="done", direction="output", data_type="bool")
    ]

    spec_mod = spec_ir.SpecModule(
        name="counter",
        state_ops=state_ops,
        rule_ops=rule_ops,
        property_ops=property_ops,
        proof_obligations=proof_obligations,
        inputs=inputs,
        outputs=outputs,
        clocks=[],
        resets=[]
    )
    return spec_mod


class TestSpecToAcl2Basic:
    def test_convert_returns_acl2_module(self):
        spec_mod = create_basic_spec_module()
        acl2_mod = spec_to_acl2.convert(spec_mod)
        assert isinstance(acl2_mod, acl2_ir.ACL2Module)
        assert acl2_mod.name == "counter"

    def test_contains_initial_state_defun(self):
        acl2_mod = spec_to_acl2.convert(create_basic_spec_module())
        init_def = next(d for d in acl2_mod.defuns if d.func_name.endswith("_init"))
        assert init_def.args == []
        assert "0" in init_def.body
        assert "nil" in init_def.body

    def test_transition_function_exists(self):
        acl2_mod = spec_to_acl2.convert(create_basic_spec_module())
        step_def = next(d for d in acl2_mod.defuns if d.func_name.endswith("_step"))
        assert step_def.func_name == "counter_step"
        assert "st" in step_def.args
        assert "start" in step_def.args

    def test_transition_function_uses_cond(self):
        acl2_mod = spec_to_acl2.convert(create_basic_spec_module())
        step_def = next(d for d in acl2_mod.defuns if d.func_name == "counter_step")
        assert "(cond" in step_def.body

    def test_rule_priority_order_in_cond(self):
        """Highest priority rule (inc, priority 10) should appear first in cond."""
        acl2_mod = spec_to_acl2.convert(create_basic_spec_module())
        step_def = next(d for d in acl2_mod.defuns if d.func_name == "counter_step")
        inc_cond_start = step_def.body.find("(< (nth 0 st)")
        flag_cond_start = step_def.body.find("(nth 1 st)")
        assert inc_cond_start != -1, "inc condition not found in transition function"
        assert flag_cond_start != -1, "flag condition not found in transition function"
        assert inc_cond_start < flag_cond_start, "inc rule should appear before flag rule"

    def test_write_action_updates_state_correctly(self):
        """Write actions should produce (update-nth idx val st) chains."""
        acl2_mod = spec_to_acl2.convert(create_basic_spec_module())
        step_def = next(d for d in acl2_mod.defuns if d.func_name == "counter_step")
        assert "update-nth" in step_def.body
        assert "update-nth 0" in step_def.body
        assert "update-nth 1" in step_def.body

    def test_read_expression_becomes_nth(self):
        """Condition (read count) should become (nth idx st)."""
        acl2_mod = spec_to_acl2.convert(create_basic_spec_module())
        step_def = next(d for d in acl2_mod.defuns if d.func_name == "counter_step")
        assert "(nth 0 st)" in step_def.body

    def test_no_rules_creates_identity_step(self):
        """If no rules exist, transition function returns st unchanged."""
        spec_mod = spec_ir.SpecModule(
            name="empty",
            state_ops=[spec_ir.SpecStateOp(state_name="r", kind="register", data_type="bits<1>")],
            rule_ops=[],
            proof_obligations=[],
            inputs=[],
            outputs=[],
            clocks=[],
            resets=[]
        )
        acl2_mod = spec_to_acl2.convert(spec_mod)
        step_def = next(d for d in acl2_mod.defuns if d.func_name == "empty_step")
        assert step_def.body.strip() == "st"


class TestAcl2TheoremGeneration:
    def test_generates_defthm_for_proof_obligation(self):
        acl2_mod = spec_to_acl2.convert(create_basic_spec_module())
        assert len(acl2_mod.defthms) == 1
        thm = acl2_mod.defthms[0]
        assert thm.thm_name == "count_bound_correct"
        assert "implies" in thm.statement
        assert "(<= (nth 0 st) 255)" in thm.statement

    def test_hints_from_metadata(self):
        acl2_mod = spec_to_acl2.convert(create_basic_spec_module())
        thm = acl2_mod.defthms[0]
        assert thm.hints == ['("Goal" :induct t)']

    def test_no_proof_obligations_no_theorems(self):
        spec_mod = create_basic_spec_module()
        spec_mod.proof_obligations = []
        acl2_mod = spec_to_acl2.convert(spec_mod)
        assert len(acl2_mod.defthms) == 0
