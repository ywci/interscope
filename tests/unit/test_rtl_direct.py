# tests/unit/test_rtl_direct.py
#
# Unit tests for the direct (short-path) ISIR -> Verilog emitter, in particular
# the identifier sanitization that makes emitted names legal Verilog for any
# source name (ONNX tensor paths, leading digits, keywords, collisions).

from isir.dialects.isir import SpecModule, SpecStateOp, SpecRuleOp, Interface
from isir.lowering.isir_to_rtl_direct import RtlDirectEmitter


def _emitter(states, rule_actions, inputs=(), outputs=()):
    return RtlDirectEmitter(SpecModule(
        name="edge",
        state_ops=[SpecStateOp(state_name=n, kind="register", data_type=t)
                   for n, t in states],
        rule_ops=[SpecRuleOp(rule_name="tick", condition="true", actions=rule_actions)],
        inputs=list(inputs), outputs=list(outputs),
        property_ops=[], proof_obligations=[],
    ))


class TestSigSanitization:
    def test_illegal_chars_become_underscore(self):
        em = _emitter([("a/b", "bits<8>")], ["(write a/b (read a/b))"])
        assert em._sig("a/b") == "a_b"

    def test_leading_digit_prefixed(self):
        em = _emitter([("2x", "bits<8>")], ["(write 2x (read 2x))"])
        assert em._sig("2x") == "_2x"

    def test_keyword_escaped(self):
        em = _emitter([("always", "bits<8>")], ["(write always (read always))"])
        assert em._sig("always") == "\\always "

    def test_collision_resolved(self):
        em = _emitter([("a/b", "bits<8>"), ("a_b", "bits<8>")], [])
        assert em._sig("a/b") == "a_b"
        assert em._sig("a_b") == "a_b_2"

    def test_normal_names_unchanged(self):
        em = _emitter([("count", "bits<8>"), ("overflow", "bool")], [])
        assert em._sig("count") == "count"
        assert em._sig("overflow") == "overflow"


class TestLowerUsesSanitizedNames:
    def test_read_prev_mem_read(self):
        from isir.utils.expr import parse_sexpr
        em = _emitter([("a/b", "bits<8>")], ["(write a/b (read a/b))"])
        assert em._lower(parse_sexpr("(read a/b)")) == "a_b"
        assert em._lower(parse_sexpr("(prev a/b)")) == "prev_a_b"

    def test_mem_read_sanitized(self):
        from isir.utils.expr import parse_sexpr
        em = RtlDirectEmitter(SpecModule(
            name="m", state_ops=[SpecStateOp(state_name="mem/data", kind="memory", data_type="memory(bits<8>, 4)")],
            rule_ops=[], inputs=[], outputs=[], property_ops=[], proof_obligations=[]))
        assert em._lower(parse_sexpr("(mem_read mem/data 0)")) == "mem_data[0]"


class TestEmitConsistency:
    def test_emitted_verilog_uses_sanitized_names(self):
        em = _emitter([("a/b", "bits<8>"), ("always", "bits<8>")],
                      ["(write a/b (read always))"])
        v = em.emit_module()
        assert "logic [7:0] a_b;" in v
        assert "logic [7:0] \\always ;" in v
        assert "next_a_b" in v and "next_always" in v
        # the write's RHS references the sanitized register names
        assert "next_a_b = \\always ;" in v or "next_a_b = (\\always " in v

    def test_mapping_rtl_signals_sanitized(self):
        import json
        em = _emitter([("a/b", "bits<8>")], ["(write a/b (read a/b))"])
        m = json.loads(em.emit_mapping("x.v", "x.isir"))
        state_item = next(i for i in m["items"] if i["spec_item_id"] == "a/b")
        assert state_item["rtl_signals"] == ["a_b", "next_a_b"]
