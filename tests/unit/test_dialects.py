# tests/unit/test_dialects.py
#
# Unit tests for the SpecIR dialects (spec_ir, assert_ir, koika_ir,
# acl2_ir, rtl_ir, trace_ir). Validates creation, string representation,
# and that the koika_ir.from_spec_module function correctly delegates to
# the lowering pass.

import pytest
from specir.dialects import spec_ir
from specir.dialects import assert_ir
from specir.dialects import koika_ir
from specir.dialects import acl2_ir
from specir.dialects import rtl_ir
from specir.dialects import trace_ir


def test_spec_dialect_operations():
    state_op = spec_ir.SpecStateOp(
        state_name="head",
        kind="register",
        data_type="bits<3>",
        initial=0,
        attributes=["stable"]
    )
    assert state_op.name == "spec.state"
    assert state_op.state_name == "head"
    assert state_op.kind == "register"
    assert state_op.data_type == "bits<3>"
    assert state_op.initial == 0
    assert state_op.attributes == ["stable"]

    rule_op = spec_ir.SpecRuleOp(
        rule_name="enqueue",
        condition="(not (read full))",
        actions=["(mem_write mem head data_in)", "(write head 1)"],
        priority=1,
        rule_attributes=["atomic"]
    )
    assert rule_op.rule_name == "enqueue"
    assert rule_op.condition == "(not (read full))"
    assert len(rule_op.actions) == 2
    assert rule_op.priority == 1

    prop_op = spec_ir.SpecPropertyOp(
        prop_name="no_overflow",
        kind="safety",
        expression={"kind": "always", "operand": "(implies (read full) (not enqueue))"}
    )
    assert prop_op.prop_name == "no_overflow"
    assert prop_op.expression["kind"] == "always"

    directive_op = spec_ir.SpecDirectiveOp(
        directive_name="no_simultaneous",
        kind="assume",
        expression="(not (and enqueue dequeue))",
        clock="clk",
        severity="error"
    )
    assert directive_op.directive_name == "no_simultaneous"
    assert directive_op.kind == "assume"
    assert directive_op.expression == "(not (and enqueue dequeue))"
    assert directive_op.clock == "clk"
    assert directive_op.severity == "error"

    schedule_op = spec_ir.SpecScheduleOp(
        kind="conflict_free",
        rule_order=[],
        conflict_sets=[["enqueue", "dequeue"]]
    )
    assert schedule_op.kind == "conflict_free"
    assert schedule_op.conflict_sets == [["enqueue", "dequeue"]]

    spec_module = spec_ir.SpecModule(
        name="fifo",
        version="0.1",
        state_ops=[state_op],
        rule_ops=[rule_op],
        property_ops=[prop_op],
        directive_ops=[directive_op],
        schedule_op=schedule_op,
        proof_obligations=[{"property": "no_overflow"}]
    )
    assert spec_module.name == "fifo"
    assert spec_module.version == "0.1"
    assert len(spec_module.state_ops) == 1
    assert len(spec_module.rule_ops) == 1
    assert len(spec_module.property_ops) == 1
    assert len(spec_module.directive_ops) == 1
    assert len(spec_module.proof_obligations) == 1
    assert spec_module.schedule_op is not None


def test_spec_interface_dataclass():
    """The spec dialect now has a proper Interface dataclass."""
    iface = spec_ir.Interface(
        name="data_in",
        direction="input",
        data_type="bits<32>",
        protocol="ready_valid"
    )
    assert iface.name == "data_in"
    assert iface.direction == "input"
    assert iface.data_type == "bits<32>"
    assert iface.protocol == "ready_valid"


def test_ast_to_spec_module_exists():
    """The canonical AST→SpecIR converter is in lowering/ast_to_spec.py."""
    from specir.lowering.ast_to_spec import convert_ast_to_spec_module
    assert callable(convert_ast_to_spec_module)


def test_assert_dialect_operations():
    always = assert_ir.AssertAlwaysOp(condition="(not (full and empty))", clock="clk")
    assert always.condition == "(not (full and empty))"
    assert always.clock == "clk"

    seq = assert_ir.AssertSequenceOp(sequence=["req", "##2 grant"], clock="clk")
    assert seq.sequence == ["req", "##2 grant"]

    prop = assert_ir.AssertPropertyOp(kind="always", operand="(full -> not enqueue)")
    assert prop.kind == "always"

    assume = assert_ir.AssertAssumeOp(condition="(not (enqueue and dequeue))")
    assert assume.condition == "(not (enqueue and dequeue))"

    cover = assert_ir.AssertCoverOp(condition="full")
    assert cover.condition == "full"

    clock_op = assert_ir.AssertClockOp(clock_name="clk", edge="posedge")
    assert clock_op.clock_name == "clk"

    reset_op = assert_ir.AssertResetOp(reset_condition="(!rst_n)")
    assert reset_op.reset_condition == "(!rst_n)"

    mod = assert_ir.AssertModule(
        name="fifo_assert",
        clock=clock_op,
        reset=reset_op,
        assumptions=[assume],
        always_checks=[always],
        properties=[prop],
        covers=[cover]
    )
    assert mod.name == "fifo_assert"
    assert mod.clock == clock_op


def test_assert_from_spec_module_raises():
    with pytest.raises(NotImplementedError):
        assert_ir.from_spec_module(None)


def test_koika_dialect_operations():
    rule = koika_ir.KoikaRuleOp(
        rule_name="enqueue",
        condition="not full",
        actions=["write(head, head+1)"]
    )
    assert rule.rule_name == "enqueue"
    assert "write(head, head+1)" in rule.actions

    design = koika_ir.KoikaDesignOp(
        design_name="fifo",
        rules=["enqueue", "dequeue"],
        schedule="conflict_free"
    )
    assert design.design_name == "fifo"
    assert design.rules == ["enqueue", "dequeue"]

    thm = koika_ir.KoikaTheoremOp(
        theorem_name="no_overflow",
        statement="forall st, reachable st -> full st -> not enqueue st",
        tactic_hints=["induction", "simpl"]
    )
    assert thm.theorem_name == "no_overflow"

    mod = koika_ir.KoikaModule(
        name="fifo_koika",
        rule_ops=[rule],
        design_op=design,
        theorem_ops=[thm]
    )
    assert mod.name == "fifo_koika"


def test_koika_from_spec_module_succeeds():
    """from_spec_module now delegates to the real lowering pass and returns a KoikaModule."""
    spec_mod = spec_ir.SpecModule(name="test")
    spec_mod.state_ops.append(
        spec_ir.SpecStateOp(state_name="x", kind="register", data_type="bool", initial=False)
    )
    spec_mod.rule_ops.append(
        spec_ir.SpecRuleOp(rule_name="dummy", condition="true", actions=[])
    )
    result = koika_ir.from_spec_module(spec_mod)
    assert isinstance(result, koika_ir.KoikaModule)
    assert result.name == "test"


def test_acl2_dialect_operations():
    defun = acl2_ir.ACL2DefunOp(
        func_name="next-state",
        args=["st", "inputs"],
        body="(cond ((enqueue inputs) ...) (t st))"
    )
    assert defun.func_name == "next-state"
    assert defun.args == ["st", "inputs"]

    defthm = acl2_ir.ACL2DefthmOp(
        thm_name="no-overflow",
        statement="(implies (full st) (not (enqueue st)))",
        hints=["(Goal :induct t)"]
    )
    assert defthm.thm_name == "no-overflow"

    defun_sk = acl2_ir.ACL2DefunSkOp(
        pred_name="exists-full",
        exists_vars=["st"],
        body="(full st)"
    )
    assert defun_sk.pred_name == "exists-full"

    mod = acl2_ir.ACL2Module(
        name="fifo_acl2",
        defuns=[defun],
        defthms=[defthm],
        defun_sk_ops=[defun_sk]
    )
    assert len(mod.defuns) == 1


def test_acl2_from_spec_module_raises():
    with pytest.raises(NotImplementedError):
        acl2_ir.from_spec_module(None)


def test_rtl_dialect_operations():
    mod_op = rtl_ir.RTLModuleOp(module_name="fifo")
    assert mod_op.module_name == "fifo"

    reg = rtl_ir.RTLRegOp(reg_name="head", width=3, initial="0")
    assert reg.reg_name == "head"

    wire = rtl_ir.RTLWireOp(wire_name="tmp", width=32)
    assert wire.wire_name == "tmp"

    assign = rtl_ir.RTLAssignOp(lhs="data_out", rhs="read_data")
    assert assign.lhs == "data_out"

    always = rtl_ir.RTLAlwaysOp(sensitivity="@(posedge clk)", body=["head <= head_next"])
    assert always.sensitivity == "@(posedge clk)"

    inst = rtl_ir.RTLInstanceOp(instance_name="fifo0", module_name="fifo", port_map={"clk": "clk"})
    assert inst.instance_name == "fifo0"

    mapping = rtl_ir.RTLMapping(
        design_name="fifo",
        entries=[rtl_ir.MappingEntry(rtl_signal="top.head", specir_ref="module.state[name=head]", kind="register")]
    )
    assert len(mapping.entries) == 1
    json_dict = mapping.to_json()
    assert json_dict["design"] == "fifo"
    assert json_dict["mapping"][0]["rtl_signal"] == "top.head"

    rtl_module = rtl_ir.RTLModule(name="fifo")
    container = rtl_ir.RTLModuleContainer(
        modules={"fifo": rtl_module},
        mapping=mapping,
        design_name="fifo",
    )
    assert container.design_name == "fifo"
    assert "fifo" in container.modules
    assert container.mapping is not None


def test_rtl_from_koika_module_raises():
    with pytest.raises(NotImplementedError):
        rtl_ir.from_koika_module(None)


def test_trace_dialect_operations():
    module_op = trace_ir.TraceModuleOp(trace_name="fifo_sim")
    assert module_op.trace_name == "fifo_sim"

    clock = trace_ir.TraceClockOp(clock_name="clk", period="10ns", edge="posedge")
    assert clock.clock_name == "clk"

    signal = trace_ir.TraceSignalOp(signal_name="full", width=1)
    assert signal.signal_name == "full"

    annotation = trace_ir.TraceAnnotationOp(signal_name="full", specir_ref="module.state[name=full]", kind="register")
    assert annotation.signal_name == "full"

    cycle_op = trace_ir.TraceCycleOp(cycle_number=0)
    assert cycle_op.cycle_number == 0

    value_op = trace_ir.TraceValueOp(signal_name="full", value=0)
    assert value_op.signal_name == "full"

    trace_mod = trace_ir.TraceModule(module_op=module_op, clock=clock, signals=[signal], annotations=[annotation])
    trace_mod.add_cycle(0, {"full": 0})
    trace_mod.add_cycle(1, {"full": 1})
    assert len(trace_mod.cycles) == 2
    assert trace_mod.get_signal_value("full", 0) == 0
    assert trace_mod.get_signal_value("full", 1) == 1
    assert trace_mod.get_signal_value("full", 2) is None
