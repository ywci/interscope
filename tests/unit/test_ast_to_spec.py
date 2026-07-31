# tests/unit/test_ast_to_spec.py
#
# Unit tests for the canonical AST → SpecModule conversion
# (lowering/ast_to_spec.py). Ensures that all AST fields
# are faithfully translated to the spec dialect.

import pytest
from specir.parser.ast import (
    Module, State, Rule, Property, TemporalExpr, Directive,
    Schedule, Clock, Reset, Interface as ASTInterface,
    Parameter, ComponentInstance, Fairness, ProofObligation,
    ProofObligationFeedback, Metadata, Evidence, EvidenceRef,
    UserType,
)
from specir.lowering.ast_to_spec import convert_ast_to_spec_module
from specir.dialects.spec_ir import (
    SpecModule, SpecStateOp, SpecRuleOp, SpecPropertyOp,
    SpecDirectiveOp, SpecScheduleOp, Interface,
)


def create_minimal_ast_module():
    """Build a Module with all optional sections populated."""
    state = [
        State(name="cnt", kind="register", type="bits<8>", initial=0,
              attributes=["stable"]),
        State(name="buf", kind="memory",
              type={"type": "memory", "elem": "bits<32>", "depth": 16}),
        State(name="flag", kind="register", type="bool", initial=False),
    ]
    rules = [
        Rule(name="inc", condition="(lt (read cnt) 255)",
             action=["(write cnt (add (read cnt) 1))"],
             priority=10, attributes=["atomic"]),
        Rule(name="reset", condition="true",
             action=["(write cnt 0)"],
             priority=5),
    ]
    prop_expr = TemporalExpr(kind="always", operand="(le (read cnt) 255)",
                             bound=None)
    properties = [
        Property(name="cnt_bound", kind="safety", expression=prop_expr,
                 assumes=["(not (read flag))"], guarantees=[],
                 proof_status="unproved",
                 evidence=[EvidenceRef(type="uri", value="file://proof.v")]),
    ]
    directives = [
        Directive(type="assume", name="no_overlap",
                  expression="(not (and enqueue dequeue))"),
        Directive(type="assert", name="flag_low",
                  expression="(not (read flag))",
                  clock="clk", severity="error"),
        Directive(type="cover", name="max_cnt",
                  expression="(eq (read cnt) 255)"),
    ]
    schedule = Schedule(kind="conflict_free",
                        rule_order=["inc", "reset"],
                        conflict_sets=[["inc", "reset"]])
    proof_obligations = [
        ProofObligation(property="cnt_bound", status="unproved",
                        engine="theorem_proving", backend="koika",
                        metadata={"coq_tactic": "induction cnt"},
                        confidence=0.9,
                        feedback=[ProofObligationFeedback(iteration=1,
                                                         error="type",
                                                         resolution="fixed")]),
    ]
    metadata = Metadata(engine="ic3", options={"max_depth": 50})
    top_evidence = [
        Evidence(type="simulation_trace",
                 ref=EvidenceRef(type="uri", value="file://sim.vcd"),
                 engine="verilator", status="active")
    ]

    clocks = [Clock(name="clk", edge="posedge", period="10ns")]
    resets = [Reset(name="rst_n", polarity="active_low",
                    async_reset=False, affects="all")]

    inputs = [ASTInterface(name="start", direction="input", type="bool")]
    outputs = [ASTInterface(name="done", direction="output", type="bool")]

    parameters = [Parameter(name="WIDTH", type="int", default=8)]
    types = [UserType(name="state_t", kind="enum",
                      values=["IDLE", "RUN"], encoding="bits<1>")]
    components = [ComponentInstance(name="sub", module="submod",
                                    parameters={"P": 1},
                                    port_map={"in": "out"})]
    fairness = [Fairness(name="fair", type="weak",
                         condition="(eventually start)")]

    module = Module(
        name="test_design",
        version="0.1",
        parameters=parameters,
        clocks=clocks,
        resets=resets,
        inputs=inputs,
        outputs=outputs,
        types=types,
        components=components,
        state=state,
        rules=rules,
        directives=directives,
        properties=properties,
        schedule=schedule,
        fairness=fairness,
        proof_obligations=proof_obligations,
        metadata=metadata,
        evidence=top_evidence,
    )
    return module


class TestAstToSpecConversion:
    def test_module_name_and_version(self):
        mod = create_minimal_ast_module()
        spec = convert_ast_to_spec_module(mod)
        assert isinstance(spec, SpecModule)
        assert spec.name == "test_design"
        assert spec.version == "0.1"

    def test_state_ops_conversion(self):
        spec = convert_ast_to_spec_module(create_minimal_ast_module())
        assert len(spec.state_ops) == 3
        cnt_op = spec.state_ops[0]
        assert cnt_op.state_name == "cnt"
        assert cnt_op.kind == "register"
        assert cnt_op.data_type == "bits<8>"
        assert cnt_op.initial == 0
        assert "stable" in cnt_op.attributes

        buf_op = spec.state_ops[1]
        assert buf_op.kind == "memory"
        assert "memory(" in buf_op.data_type

    def test_rule_ops_conversion(self):
        spec = convert_ast_to_spec_module(create_minimal_ast_module())
        assert len(spec.rule_ops) == 2
        inc = spec.rule_ops[0]
        assert inc.rule_name == "inc"
        assert inc.condition == "(lt (read cnt) 255)"
        assert len(inc.actions) == 1
        assert inc.priority == 10
        assert "atomic" in inc.rule_attributes

    def test_property_ops_conversion(self):
        spec = convert_ast_to_spec_module(create_minimal_ast_module())
        assert len(spec.property_ops) == 1
        prop = spec.property_ops[0]
        assert prop.prop_name == "cnt_bound"
        assert prop.kind == "safety"
        expr = prop.expression
        assert expr["kind"] == "always"
        assert expr["operand"] == "(le (read cnt) 255)"
        assert len(prop.assumes) == 1

    def test_directive_ops_conversion(self):
        spec = convert_ast_to_spec_module(create_minimal_ast_module())
        assert len(spec.directive_ops) == 3

        kinds = [d.kind for d in spec.directive_ops]
        assert "assume" in kinds
        assert "assert" in kinds
        assert "cover" in kinds

        assume_d = next(d for d in spec.directive_ops if d.kind == "assume")
        assert assume_d.directive_name == "no_overlap"
        assert assume_d.expression == "(not (and enqueue dequeue))"

        assert_d = next(d for d in spec.directive_ops if d.kind == "assert")
        assert assert_d.clock == "clk"
        assert assert_d.severity == "error"

    def test_schedule_conversion(self):
        spec = convert_ast_to_spec_module(create_minimal_ast_module())
        assert spec.schedule_op is not None
        sched = spec.schedule_op
        assert sched.kind == "conflict_free"
        assert sched.rule_order == ["inc", "reset"]
        assert sched.conflict_sets == [["inc", "reset"]]

    def test_proof_obligations_conversion(self):
        spec = convert_ast_to_spec_module(create_minimal_ast_module())
        assert len(spec.proof_obligations) == 1
        po = spec.proof_obligations[0]
        assert po["property"] == "cnt_bound"
        assert po["backend"] == "koika"
        assert po["metadata"]["coq_tactic"] == "induction cnt"
        assert po["confidence"] == 0.9

    def test_metadata_conversion(self):
        spec = convert_ast_to_spec_module(create_minimal_ast_module())
        md = spec.metadata
        assert md["engine"] == "ic3"
        assert md["options"]["max_depth"] == 50

    def test_interface_conversion(self):
        spec = convert_ast_to_spec_module(create_minimal_ast_module())
        assert len(spec.inputs) == 1
        inp = spec.inputs[0]
        assert isinstance(inp, Interface)
        assert inp.name == "start"
        assert inp.direction == "input"
        assert inp.data_type == "bool"
        assert len(spec.outputs) == 1
        out = spec.outputs[0]
        assert isinstance(out, Interface)
        assert out.name == "done"
        assert out.direction == "output"

    def test_clock_reset_conversion(self):
        spec = convert_ast_to_spec_module(create_minimal_ast_module())
        assert len(spec.clocks) == 1
        clk = spec.clocks[0]
        assert clk["name"] == "clk"
        assert clk["edge"] == "posedge"
        assert len(spec.resets) == 1
        rst = spec.resets[0]
        assert rst["name"] == "rst_n"
        assert rst["polarity"] == "active_low"
        assert rst["async"] is False

    def test_optional_sections_empty_by_default(self):
        minimal = Module(name="min", clocks=[], resets=[], state=[],
                        rules=[])
        spec = convert_ast_to_spec_module(minimal)
        assert spec.directive_ops == []
        assert spec.proof_obligations == []
        assert spec.schedule_op is None
        assert spec.inputs == []
        assert spec.outputs == []
