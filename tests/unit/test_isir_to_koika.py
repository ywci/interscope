# tests/unit/test_isir_to_koika.py
#
# Unit tests for lowering from SpecModule to KoikaModule.
# Covers basic conversion, expression translation, theorem generation,
# boolean false handling, backend filtering, and macron acceptance.

import pytest
from isir.dialects import isir, koika
from isir.lowering import isir_to_koika


def create_basic_spec_module():
    """Create a simple SpecModule with a counter and a memory."""
    spec_mod = isir.SpecModule(name="counter")

    spec_mod.state_ops.append(
        isir.SpecStateOp(state_name="count", kind="register", data_type="bits<8>", initial=0)
    )
    spec_mod.state_ops.append(
        isir.SpecStateOp(
            state_name="mem",
            kind="memory",
            data_type={"type": "memory", "elem": "bits<8>", "depth": 16}
        )
    )

    spec_mod.inputs = [isir.Interface(name="data_in", direction="input", data_type="bits<8>")]

    rule1 = isir.SpecRuleOp(
        rule_name="inc",
        condition="(lt (read count) 255)",
        actions=["(write count (add (read count) 1))"]
    )
    spec_mod.rule_ops.append(rule1)

    rule2 = isir.SpecRuleOp(
        rule_name="write_mem",
        condition="true",
        actions=["(mem_write mem count data_in)"]
    )
    spec_mod.rule_ops.append(rule2)

    spec_mod.property_ops.append(
        isir.SpecPropertyOp(
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
    spec_mod = isir.SpecModule(name="fifo")

    spec_mod.state_ops.append(
        isir.SpecStateOp(state_name="full", kind="register", data_type="bool", initial=False)
    )

    spec_mod.inputs = [
        isir.Interface(name="write_en", direction="input", data_type="bool")
    ]

    spec_mod.property_ops.append(
        isir.SpecPropertyOp(
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
    spec_mod = isir.SpecModule(name="mixed")

    spec_mod.state_ops.append(
        isir.SpecStateOp(state_name="flag", kind="register", data_type="bool", initial=False)
    )
    spec_mod.inputs = [
        isir.Interface(name="en", direction="input", data_type="bool")
    ]

    spec_mod.property_ops.append(
        isir.SpecPropertyOp(
            prop_name="prop_a",
            kind="safety",
            expression={"kind": "always", "operand": "(not (read flag))"}
        )
    )
    spec_mod.property_ops.append(
        isir.SpecPropertyOp(
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


def test_isir_to_koika_basic():
    """Test that the lowering produces a KoikaModule with correct content."""
    spec_mod = create_basic_spec_module()
    koika_mod = isir_to_koika.convert(spec_mod)

    assert isinstance(koika_mod, koika.KoikaModule)
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
    koika_mod = isir_to_koika.convert(spec_mod)

    inc_rule = next(r for r in koika_mod.rule_ops if r.rule_name == "inc")
    assert "count" in inc_rule.condition
    assert "255" in inc_rule.condition
    assert "Count" not in inc_rule.condition

    write_rule = next(r for r in koika_mod.rule_ops if r.rule_name == "write_mem")
    assert write_rule.condition == "True"


def test_theorem_generation_with_reachable():
    """Test that proof obligations become theorems with reachability."""
    spec_mod = create_basic_spec_module()
    koika_mod = isir_to_koika.convert(spec_mod)

    state_text = "\n".join(koika_mod.state_definitions)
    assert "Theorem count_bound_proved" in state_text
    assert "reachable" in state_text
    assert "<= 255" in state_text


def test_imports_and_helpers():
    """Test that required Coq imports and helpers are present."""
    spec_mod = create_basic_spec_module()
    koika_mod = isir_to_koika.convert(spec_mod)

    state_text = "\n".join(koika_mod.state_definitions)
    assert "Require Import Init.Datatypes." in state_text
    assert "Require Import Arith.PeanoNat." in state_text
    assert "Require Import Lists.List." in state_text
    assert "Require Import Bool.Bool." in state_text
    assert "Fixpoint list_update" in state_text


def test_state_initialization():
    """Test that initial_state is correctly built."""
    spec_mod = create_basic_spec_module()
    koika_mod = isir_to_koika.convert(spec_mod)

    state_text = "\n".join(koika_mod.state_definitions)
    assert "Definition initial_state : state := (mkState 0 nil)" in state_text


def test_boolean_false_converts_to_coq_false():
    """The expression (implies ... false) must produce a non‑trivial Coq conclusion."""
    spec_mod = create_spec_with_false_operand()
    koika_mod = isir_to_koika.convert(spec_mod)

    state_text = "\n".join(koika_mod.state_definitions)

    assert "Theorem no_overflow_proved" in state_text
    after_thm = state_text.split("Theorem no_overflow_proved")[1]
    assert "-> True" not in after_thm
    assert "False" in after_thm or "~" in after_thm


def test_acl2_obligation_not_added_to_coq():
    """Only obligations with backend 'koika' (or 'kōika') appear in Coq."""
    spec_mod = create_spec_with_mixed_backends()
    koika_mod = isir_to_koika.convert(spec_mod)

    state_text = "\n".join(koika_mod.state_definitions)

    assert "Theorem prop_a_proved" in state_text
    assert "Theorem prop_b_proved" not in state_text


def test_macron_koika_backend_accepted():
    """The backend string 'kōika' (with macron) is recognised."""
    spec_mod = isir.SpecModule(name="macron_test")
    spec_mod.state_ops.append(
        isir.SpecStateOp(state_name="x", kind="register", data_type="bool", initial=False)
    )
    spec_mod.inputs = [
        isir.Interface(name="a", direction="input", data_type="bool")
    ]
    spec_mod.property_ops.append(
        isir.SpecPropertyOp(
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

    koika_mod = isir_to_koika.convert(spec_mod)
    state_text = "\n".join(koika_mod.state_definitions)
    assert "Theorem test_prop_proved" in state_text


def create_spec_with_combinational():
    """Create a SpecModule with a combinational-equivalence property."""
    spec_mod = isir.SpecModule(name="comb")

    spec_mod.state_ops.append(
        isir.SpecStateOp(state_name="acc", kind="register", data_type="bits<8>", initial=0)
    )
    spec_mod.inputs = [
        isir.Interface(name="a", direction="input", data_type="bits<8>"),
        isir.Interface(name="b", direction="input", data_type="bits<8>"),
    ]

    spec_mod.property_ops.append(
        isir.SpecPropertyOp(
            prop_name="add_commutative",
            kind="combinational",
            expression={
                "kind": "combinational",
                "operand": "(add a b)",
                "reference": "(add b a)",
            }
        )
    )
    spec_mod.proof_obligations.append({
        "property": "add_commutative",
        "status": "unproved",
        "engine": "theorem_proving",
        "backend": "koika"
    })
    return spec_mod


def test_combinational_theorem_generation():
    """Combinational properties lower to `forall inputs, impl = ref` (no reachable)."""
    spec_mod = create_spec_with_combinational()
    koika_mod = isir_to_koika.convert(spec_mod)

    state_text = "\n".join(koika_mod.state_definitions)
    assert "Theorem add_commutative_proved" in state_text
    assert "(* PERF_Combinational *)" in state_text
    # Statement quantifies only over inputs and equates impl with reference.
    assert "forall (inputs : inputs)" in state_text
    assert "((a inputs) + (b inputs))" in state_text
    assert "((b inputs) + (a inputs))" in state_text
    # Combinational theorems must not carry a reachability hypothesis.
    theorem_block = state_text.split("Theorem add_commutative_proved")[1].split("Admitted.")[0]
    assert "reachable" not in theorem_block


def create_spec_with_transition():
    """Create a SpecModule with a transitional property."""
    spec_mod = isir.SpecModule(name="trans")

    spec_mod.state_ops.append(
        isir.SpecStateOp(state_name="acc", kind="register", data_type="bits<8>", initial=0)
    )
    spec_mod.inputs = [
        isir.Interface(name="a", direction="input", data_type="bits<8>"),
        isir.Interface(name="b", direction="input", data_type="bits<8>"),
    ]
    spec_mod.rule_ops.append(
        isir.SpecRuleOp(
            rule_name="add",
            condition="true",
            actions=["(write acc (add (read a) (read b)))"]
        )
    )
    spec_mod.property_ops.append(
        isir.SpecPropertyOp(
            prop_name="acc_updates_to_sum",
            kind="transition",
            expression={
                "kind": "transition",
                "operand": "(eq (read acc) (add a b))",
            }
        )
    )
    spec_mod.proof_obligations.append({
        "property": "acc_updates_to_sum",
        "status": "unproved",
        "engine": "theorem_proving",
        "backend": "koika"
    })
    return spec_mod


def test_transition_theorem_generation():
    """Transition properties lower to `step s inputs s' -> P(s', inputs)`."""
    spec_mod = create_spec_with_transition()
    koika_mod = isir_to_koika.convert(spec_mod)

    state_text = "\n".join(koika_mod.state_definitions)
    assert "Theorem acc_updates_to_sum_proved" in state_text
    assert "(* PERF_Transition *)" in state_text
    assert "forall (s : state) (inputs : inputs) (s' : state)" in state_text
    assert "step s inputs s' ->" in state_text
    # The operand's `read acc` must reference the *next* state s'.
    assert "(acc s')" in state_text
    # Inputs stay quantified over the transition's inputs.
    assert "((a inputs) + (b inputs))" in state_text
    # Transition theorems carry no reachability hypothesis.
    theorem_block = state_text.split("Theorem acc_updates_to_sum_proved")[1].split("Admitted.")[0]
    assert "reachable" not in theorem_block


def test_combinational_boolean_reference():
    """A boolean golden reference lowers to a Coq `true`/`false` literal."""
    spec_mod = isir.SpecModule(name="comb_bool")
    spec_mod.state_ops.append(
        isir.SpecStateOp(state_name="f", kind="register", data_type="bool", initial=False)
    )
    spec_mod.inputs = [
        isir.Interface(name="en", direction="input", data_type="bool")
    ]
    spec_mod.property_ops.append(
        isir.SpecPropertyOp(
            prop_name="excluded_middle",
            kind="combinational",
            expression={
                "kind": "combinational",
                "operand": "(or en (not en))",
                "reference": True,
            }
        )
    )
    spec_mod.proof_obligations.append({
        "property": "excluded_middle",
        "status": "unproved",
        "engine": "theorem_proving",
        "backend": "koika"
    })

    koika_mod = isir_to_koika.convert(spec_mod)
    state_text = "\n".join(koika_mod.state_definitions)
    assert "Theorem excluded_middle_proved" in state_text
    assert "(orb (en inputs) (negb (en inputs)))" in state_text
    assert "= true" in state_text
