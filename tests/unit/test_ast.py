# tests/unit/test_ast.py
#
# Unit tests for the SpecIR AST dataclasses.

import pytest
from specir.parser.ast import (
    Clock, ComponentInstance, Directive, Evidence, EvidenceRef, Fairness,
    Interface, Metadata, Module, Parameter, Property, ProofObligation,
    ProofObligationFeedback, Reset, Rule, Schedule, SpecIR, State,
    TemporalExpr, UserType,
)


def test_evidence_ref():
    ref = EvidenceRef(type="uri", value="file://test")
    assert ref.type == "uri"
    assert ref.value == "file://test"


def test_evidence():
    ref = EvidenceRef(type="local_id", value="abc")
    ev = Evidence(type="counterexample_trace", ref=ref, engine="BMC", status="active")
    assert ev.type == "counterexample_trace"
    assert ev.ref == ref
    assert ev.engine == "BMC"
    assert ev.status == "active"


def test_parameter():
    param = Parameter(name="WIDTH", type="int", default=32)
    assert param.name == "WIDTH"
    assert param.type == "int"
    assert param.default == 32


def test_clock():
    clk = Clock(name="clk", edge="posedge", period="10ns")
    assert clk.name == "clk"
    assert clk.edge == "posedge"
    assert clk.period == "10ns"


def test_reset():
    # Field renamed from async_ to async_reset to avoid Python keyword clash
    reset = Reset(name="rst", polarity="active_high", async_reset=False, affects="all")
    assert reset.name == "rst"
    assert reset.polarity == "active_high"
    assert reset.async_reset is False
    assert reset.affects == "all"


def test_interface():
    iface = Interface(name="data_in", direction="input", type="bits<32>", protocol="ready_valid")
    assert iface.name == "data_in"
    assert iface.direction == "input"
    assert iface.type == "bits<32>"
    assert iface.protocol == "ready_valid"


def test_user_type_enum():
    ut = UserType(name="state_t", kind="enum", values=["IDLE", "RUN"], encoding="bits<1>")
    assert ut.name == "state_t"
    assert ut.kind == "enum"
    assert ut.values == ["IDLE", "RUN"]
    assert ut.encoding == "bits<1>"


def test_user_type_struct():
    ut = UserType(name="pair", kind="struct", fields={"first": "bits<8>", "second": "bool"})
    assert ut.kind == "struct"
    assert ut.fields == {"first": "bits<8>", "second": "bool"}


def test_component_instance():
    comp = ComponentInstance(
        name="fifo_inst",
        module="fifo",
        parameters={"WIDTH": 32},
        port_map={"data_in": "parent_data_in"}
    )
    assert comp.name == "fifo_inst"
    assert comp.module == "fifo"
    assert comp.parameters == {"WIDTH": 32}
    assert comp.port_map == {"data_in": "parent_data_in"}


def test_state():
    state = State(name="head", kind="register", type="bits<3>", initial=0, attributes=["stable"])
    assert state.name == "head"
    assert state.kind == "register"
    assert state.type == "bits<3>"
    assert state.initial == 0
    assert state.attributes == ["stable"]


def test_rule():
    rule = Rule(
        name="enqueue",
        condition="(not (read full))",
        action=["(mem_write mem head data_in)", "(write head 1)"],
        priority=1,
        attributes=["atomic"]
    )
    assert rule.name == "enqueue"
    assert rule.condition == "(not (read full))"
    assert len(rule.action) == 2
    assert rule.priority == 1
    assert rule.attributes == ["atomic"]


def test_directive():
    directive = Directive(
        type="assume",
        name="no_simultaneous",
        expression="(not (and enqueue dequeue))",
        clock="clk",
        severity=None
    )
    assert directive.type == "assume"
    assert directive.name == "no_simultaneous"
    assert directive.expression == "(not (and enqueue dequeue))"
    assert directive.clock == "clk"


def test_temporal_expr():
    texpr = TemporalExpr(kind="always", operand="(read full)", bound=10)
    assert texpr.kind == "always"
    assert texpr.operand == "(read full)"
    assert texpr.bound == 10


def test_property():
    texpr = TemporalExpr(kind="always", operand="(implies (read full) (not enqueue))")
    prop = Property(name="no_overflow", kind="safety", expression=texpr)
    assert prop.name == "no_overflow"
    assert prop.kind == "safety"
    assert prop.expression == texpr
    assert prop.proof_status == "unproved"
    # evidence defaults to empty list
    assert prop.evidence == []


def test_property_evidence_list():
    """Property.evidence is now a list of EvidenceRef."""
    texpr = TemporalExpr(kind="always", operand="(read full)")
    ev_ref1 = EvidenceRef(type="uri", value="file://proof1")
    ev_ref2 = EvidenceRef(type="local_id", value="proof2")
    prop = Property(
        name="no_overflow",
        kind="safety",
        expression=texpr,
        evidence=[ev_ref1, ev_ref2]
    )
    assert len(prop.evidence) == 2
    assert prop.evidence[0] == ev_ref1
    assert prop.evidence[1] == ev_ref2


def test_schedule():
    sched = Schedule(
        kind="conflict_free",
        rule_order=[],
        conflict_sets=[["enqueue", "dequeue"]]
    )
    assert sched.kind == "conflict_free"
    assert sched.conflict_sets == [["enqueue", "dequeue"]]


def test_fairness():
    fair = Fairness(name="enqueue_fair", type="weak", condition="(eventually enqueue)")
    assert fair.name == "enqueue_fair"
    assert fair.type == "weak"
    assert fair.condition == "(eventually enqueue)"


def test_proof_obligation_feedback():
    fb = ProofObligationFeedback(iteration=1, error="type mismatch", resolution="fixed")
    assert fb.iteration == 1
    assert fb.error == "type mismatch"
    assert fb.resolution == "fixed"


def test_proof_obligation():
    po = ProofObligation(
        property="no_overflow",
        status="unproved",
        engine="theorem_proving",
        backend="koika",
        metadata={"coq_tactic": "induction"}
    )
    assert po.property == "no_overflow"
    assert po.status == "unproved"
    assert po.engine == "theorem_proving"
    assert po.backend == "koika"
    assert po.metadata == {"coq_tactic": "induction"}


def test_metadata():
    md = Metadata(engine="ic3", options={"max_depth": 100})
    assert md.engine == "ic3"
    assert md.options == {"max_depth": 100}


def test_module():
    module = Module(
        name="fifo",
        version="1.0",
        clocks=[Clock(name="clk", edge="posedge")],
        resets=[Reset(name="rst", polarity="active_high", async_reset=False, affects="all")],
        state=[State(name="head", kind="register", type="bits<3>")],
        rules=[Rule(name="enqueue", condition="(read enqueue)", action=[])],
    )
    assert module.name == "fifo"
    assert len(module.clocks) == 1
    assert len(module.resets) == 1
    assert len(module.state) == 1
    assert len(module.rules) == 1


def test_specir_root():
    module = Module(name="test")
    spec = SpecIR(specir_version="0.1", module=module)
    assert spec.specir_version == "0.1"
    assert spec.module.name == "test"


def test_specir_top_level_metadata():
    """SpecIR root now accepts top-level metadata and evidence."""
    module = Module(name="test")
    md = Metadata(engine="bmc")
    ev = Evidence(
        type="simulation_trace",
        ref=EvidenceRef(type="uri", value="file://trace.vcd"),
        engine="verilator"
    )
    spec = SpecIR(specir_version="0.1", module=module, metadata=md, evidence=[ev])
    assert spec.metadata.engine == "bmc"
    assert len(spec.evidence) == 1
    assert spec.evidence[0].type == "simulation_trace"
