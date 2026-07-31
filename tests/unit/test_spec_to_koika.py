# tests/unit/test_spec_to_koika.py
#
# Unit tests for lowering from SpecModule to KoikaModule.
# Covers basic conversion, expression translation, theorem generation,
# boolean false handling, backend filtering, and macron acceptance.

import pytest
from specir.dialects import spec_ir, koika_ir
from specir.lowering import spec_to_koika


def create_basic_spec_module():
    """Create a simple SpecModule with a counter and a memory."""
    spec_mod = spec_ir.SpecModule(name="counter")

    spec_mod.state_ops.append(
        spec_ir.SpecStateOp(state_name="count", kind="register", data_type="bits<8>", initial=0)
    )
    spec_mod.state_ops.append(
        spec_ir.SpecStateOp(
            state_name="mem",
            kind="memory",
            data_type={"type": "memory", "elem": "bits<8>", "depth": 16}
        )
    )

    spec_mod.inputs = [spec_ir.Interface(name="data_in", direction="input", data_type="bits<8>")]

    rule1 = spec_ir.SpecRuleOp(
        rule_name="inc",
        condition="(lt (read count) 255)",
        actions=["(write count (add (read count) 1))"]
    )
    spec_mod.rule_ops.append(rule1)

    rule2 = spec_ir.SpecRuleOp(
        rule_name="write_mem",
        condition="true",
        actions=["(mem_write mem count data_in)"]
    )
    spec_mod.rule_ops.append(rule2)

    spec_mod.property_ops.append(
        spec_ir.SpecPropertyOp(
            prop_name="count_bound",
            kind="safety",
            expression={"kind": "always", "operand": "(le (read count) 255)"}
        )
    )

    spec_mod.proof_obligations.append({
        "property": "count_bound",
        "status": "unproved",
        "engine": "theorem_proving",
        "backend": "koika"
    })

    return spec_mod


def create_spec_with_false_operand():
    """Create a SpecModule that uses boolean false in a property operand."""
    spec_mod = spec_ir.SpecModule(name="fifo")

    spec_mod.state_ops.append(
        spec_ir.SpecStateOp(state_name="full", kind="register", data_type="bool", initial=False)
    )

    spec_mod.inputs = [
        spec_ir.Interface(name="write_en", direction="input", data_type="bool")
    ]

    spec_mod.property_ops.append(
        spec_ir.SpecPropertyOp(
            prop_name="no_overflow",
            kind="safety",
            expression={
                "kind": "always",
                "operand": "(implies (and write_en (read full)) false)"
            }
        )
    )

    spec_mod.proof_obligations.append({
        "property": "no_overflow",
        "status": "unproved",
        "engine": "theorem_proving",
        "backend": "koika"
    })

    return spec_mod


def create_spec_with_mixed_backends():
    """Create a SpecModule with one Koika and one ACL2 obligation."""
    spec_mod = spec_ir.SpecModule(name="mixed")

    spec_mod.state_ops.append(
        spec_ir.SpecStateOp(state_name="flag", kind="register", data_type="bool", initial=False)
    )
    spec_mod.inputs = [
        spec_ir.Interface(name="en", direction="input", data_type="bool")
    ]

    spec_mod.property_ops.append(
        spec_ir.SpecPropertyOp(
            prop_name="prop_a",
            kind="safety",
            expression={"kind": "always", "operand": "(not (read flag))"}
        )
    )
    spec_mod.property_ops.append(
        spec_ir.SpecPropertyOp(
            prop_name="prop_b",
            kind="safety",
            expression={"kind": "always", "operand": "(eq (read flag) false)"}
        )
    )

    spec_mod.proof_obligations.append({
        "property": "prop_a",
        "status": "unproved",
        "engine": "theorem_proving",
        "backend": "koika"
    })

    spec_mod.proof_obligations.append({
        "property": "prop_b",
        "status": "unproved",
        "engine": "theorem_proving",
        "backend": "acl2"
    })

    return spec_mod


def test_spec_to_koika_basic():
    """Test that the lowering produces a KoikaModule with correct content."""
    spec_mod = create_basic_spec_module()
    koika_mod = spec_to_koika.convert(spec_mod)

    assert isinstance(koika_mod, koika_ir.KoikaModule)
    assert koika_mod.name == "counter"

    state_text = "\n".join(koika_mod.state_definitions)
    assert "Record state : Type := mkState" in state_text
    assert "count : nat" in state_text
    assert "mem : list nat" in state_text
    assert "Definition initial_state" in state_text
    assert "Fixpoint list_update" in state_text
    assert "Inductive step" in state_text
    assert "Inductive reachable" in state_text
    assert "Theorem count_bound_proved" in state_text


def test_expr_to_koika_conversion():
    """Verify that expressions are converted to valid Kōika/Coq syntax."""
    spec_mod = create_basic_spec_module()
    koika_mod = spec_to_koika.convert(spec_mod)

    inc_rule = next(r for r in koika_mod.rule_ops if r.rule_name == "inc")
    assert "count" in inc_rule.condition
    assert "255" in inc_rule.condition
    assert "Count" not in inc_rule.condition

    write_rule = next(r for r in koika_mod.rule_ops if r.rule_name == "write_mem")
    assert write_rule.condition == "True"


def test_theorem_generation_with_reachable():
    """Test that proof obligations become theorems with reachability."""
    spec_mod = create_basic_spec_module()
    koika_mod = spec_to_koika.convert(spec_mod)

    state_text = "\n".join(koika_mod.state_definitions)
    assert "Theorem count_bound_proved" in state_text
    assert "reachable" in state_text
    assert "<= 255" in state_text


def test_imports_and_helpers():
    """Test that required Coq imports and helpers are present."""
    spec_mod = create_basic_spec_module()
    koika_mod = spec_to_koika.convert(spec_mod)

    state_text = "\n".join(koika_mod.state_definitions)
    assert "Require Import Init.Datatypes." in state_text
    assert "Require Import Arith.PeanoNat." in state_text
    assert "Require Import Lists.List." in state_text
    assert "Require Import Bool.Bool." in state_text
    assert "Fixpoint list_update" in state_text


def test_state_initialization():
    """Test that initial_state is correctly built."""
    spec_mod = create_basic_spec_module()
    koika_mod = spec_to_koika.convert(spec_mod)

    state_text = "\n".join(koika_mod.state_definitions)
    assert "Definition initial_state : state := (mkState 0 nil)" in state_text


def test_boolean_false_converts_to_coq_false():
    """The expression (implies ... false) must produce a non‑trivial Coq conclusion."""
    spec_mod = create_spec_with_false_operand()
    koika_mod = spec_to_koika.convert(spec_mod)

    state_text = "\n".join(koika_mod.state_definitions)

    assert "Theorem no_overflow_proved" in state_text
    after_thm = state_text.split("Theorem no_overflow_proved")[1]
    assert "-> True" not in after_thm
    assert "False" in after_thm or "~" in after_thm


def test_acl2_obligation_not_added_to_coq():
    """Only obligations with backend 'koika' (or 'kōika') appear in Coq."""
    spec_mod = create_spec_with_mixed_backends()
    koika_mod = spec_to_koika.convert(spec_mod)

    state_text = "\n".join(koika_mod.state_definitions)

    assert "Theorem prop_a_proved" in state_text
    assert "Theorem prop_b_proved" not in state_text


def test_macron_koika_backend_accepted():
    """The backend string 'kōika' (with macron) is recognised."""
    spec_mod = spec_ir.SpecModule(name="macron_test")
    spec_mod.state_ops.append(
        spec_ir.SpecStateOp(state_name="x", kind="register", data_type="bool", initial=False)
    )
    spec_mod.inputs = [
        spec_ir.Interface(name="a", direction="input", data_type="bool")
    ]
    spec_mod.property_ops.append(
        spec_ir.SpecPropertyOp(
            prop_name="test_prop",
            kind="safety",
            expression={"kind": "always", "operand": "(not (read x))"}
        )
    )
    spec_mod.proof_obligations.append({
        "property": "test_prop",
        "status": "unproved",
        "engine": "theorem_proving",
        "backend": "kōika"
    })

    koika_mod = spec_to_koika.convert(spec_mod)
    state_text = "\n".join(koika_mod.state_definitions)
    assert "Theorem test_prop_proved" in state_text
