# tests/unit/test_lowering.py
#
# Unit tests for lowering passes: spec_to_assert, assert_to_sva,
# assert_to_vhdl, assert_to_verilog_ovl.

import pytest
from specir.dialects import spec_ir
from specir.dialects import assert_ir
from specir.lowering import spec_to_assert
from specir.lowering import assert_to_sva
from specir.lowering import assert_to_vhdl
from specir.lowering import assert_to_verilog_ovl


def create_test_spec_module():
    """Return a SpecModule with basic clock, reset, directives, and a simple boolean property."""
    clocks = [{"name": "clk", "edge": "posedge"}]
    resets = [{"name": "rst", "polarity": "active_high", "async": False, "affects": "all"}]

    directives = [
        spec_ir.SpecDirectiveOp(
            directive_name="no_simultaneous",
            kind="assume",
            expression="(not (and enqueue dequeue))",
        ),
        spec_ir.SpecDirectiveOp(
            directive_name="always_not_full",
            kind="assert",
            expression="(implies (read full) (not enqueue))",
        ),
        spec_ir.SpecDirectiveOp(
            directive_name="full_reached",
            kind="cover",
            expression="(read full)",
        ),
    ]

    prop_op = spec_ir.SpecPropertyOp(
        prop_name="no_overflow",
        kind="safety",
        expression={"kind": "always", "operand": "(not (and (read full) enqueue))"},
    )

    spec_module = spec_ir.SpecModule(
        name="fifo",
        clocks=clocks,
        resets=resets,
        state_ops=[],
        rule_ops=[],
        property_ops=[prop_op],
        directive_ops=directives,
    )
    return spec_module


def test_spec_to_assert_basic():
    spec_mod = create_test_spec_module()
    assert_mod = spec_to_assert.convert(spec_mod)

    assert assert_mod.name == "fifo_assertions"
    assert assert_mod.clock is not None
    assert assert_mod.clock.clock_name == "clk"
    assert assert_mod.reset is not None
    assert "rst" in assert_mod.reset.reset_condition

    assert len(assert_mod.assumptions) == 1
    assume = assert_mod.assumptions[0]
    assert assume.condition == "(not (and enqueue dequeue))"

    assert len(assert_mod.always_checks) == 2
    always_conditions = [a.condition for a in assert_mod.always_checks]

    assert any("(implies (read full) (not enqueue))" in c for c in always_conditions)
    assert any("(not (and (read full) enqueue))" in c for c in always_conditions)

    assert len(assert_mod.properties) == 0

    assert len(assert_mod.covers) == 1
    cover = assert_mod.covers[0]
    assert cover.condition == "(read full)"


def test_spec_to_assert_eventually_property():
    """Eventually properties are lowered to AssertPropertyOp with kind=eventually."""
    spec_mod = spec_ir.SpecModule(
        name="test",
        clocks=[{"name": "clk", "edge": "posedge"}],
        resets=[],
    )
    prop_op = spec_ir.SpecPropertyOp(
        prop_name="eventual_grant",
        kind="liveness",
        expression={"kind": "eventually", "operand": "(read grant)", "bound": 10},
    )
    spec_mod.property_ops = [prop_op]
    spec_mod.directive_ops = []

    assert_mod = spec_to_assert.convert(spec_mod)
    assert len(assert_mod.properties) == 1
    assert assert_mod.properties[0].kind == "eventually"
    assert assert_mod.properties[0].bound == 10


def test_assert_to_sva_basic():
    spec_mod = create_test_spec_module()
    assert_mod = spec_to_assert.convert(spec_mod)
    sva_code = assert_to_sva.convert(assert_mod)

    assert "module fifo_assertions" in sva_code
    assert "assert" in sva_code
    assert "assume" in sva_code or "// assume" in sva_code
    assert "cover" in sva_code or "// cover" in sva_code


def test_assert_to_sva_with_eventually():
    """The procedural SVA backend skips eventually properties; the module should be empty."""
    spec_mod = spec_ir.SpecModule(name="test", clocks=[], resets=[])
    prop_op = spec_ir.SpecPropertyOp(
        prop_name="eventual_grant",
        kind="liveness",
        expression={"kind": "eventually", "operand": "(read grant)", "bound": 10},
    )
    spec_mod.property_ops = [prop_op]
    spec_mod.directive_ops = []
    assert_mod = spec_to_assert.convert(spec_mod)
    sva_code = assert_to_sva.convert(assert_mod)
    assert "s_eventually" not in sva_code
    assert "endmodule" in sva_code


def test_assert_to_vhdl_basic():
    spec_mod = create_test_spec_module()
    assert_mod = spec_to_assert.convert(spec_mod)
    vhdl_code = assert_to_vhdl.convert(assert_mod)

    assert "package fifo_assertions" in vhdl_code
    assert "assume always" in vhdl_code
    assert "assert always" in vhdl_code
    assert "cover {" in vhdl_code
    assert "default clock is rising_edge(clk)" in vhdl_code


def test_assert_to_ovl_basic():
    spec_mod = create_test_spec_module()
    assert_mod = spec_to_assert.convert(spec_mod)
    ovl_code = assert_to_verilog_ovl.convert(assert_mod)

    assert "module fifo_assertions" in ovl_code
    assert "ovl_assert_always" in ovl_code
    assert "ovl_cover" in ovl_code
    assert "assert property" not in ovl_code


def test_assert_to_ovl_unsupported_property():
    spec_mod = spec_ir.SpecModule(name="test", clocks=[], resets=[])
    prop_op = spec_ir.SpecPropertyOp(
        prop_name="eventual_grant",
        kind="liveness",
        expression={"kind": "eventually", "operand": "(read grant)"},
    )
    spec_mod.property_ops = [prop_op]
    spec_mod.directive_ops = []
    assert_mod = spec_to_assert.convert(spec_mod)
    with pytest.raises(NotImplementedError, match="OVL backend does not support"):
        assert_to_verilog_ovl.convert(assert_mod)


def test_assert_to_ovl_unsupported_sequence():
    assert_mod = assert_ir.AssertModule(name="test")
    seq_op = assert_ir.AssertSequenceOp(sequence=["req", "##1 grant"])
    assert_mod.sequences = [seq_op]
    with pytest.raises(NotImplementedError, match="OVL backend does not support"):
        assert_to_verilog_ovl.convert(assert_mod)
