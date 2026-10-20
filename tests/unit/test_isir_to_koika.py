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


def create_spec_with_independence():
    """Create a SpecModule with an independence (non-interference) property."""
    spec_mod = isir.SpecModule(name="indep")

    spec_mod.state_ops.append(
        isir.SpecStateOp(state_name="acc", kind="register", data_type="bits<8>", initial=0)
    )
    spec_mod.inputs = [
        isir.Interface(name="a", direction="input", data_type="bits<32>"),
        isir.Interface(name="mask", direction="input", data_type="bits<4>"),
    ]
    spec_mod.property_ops.append(
        isir.SpecPropertyOp(
            prop_name="reduction_independent_of_mask",
            kind="independence",
            expression={
                "kind": "independence",
                "operand": "(add (slice a 7 0) (slice a 15 8))",
                "independent_of": ["mask"],
            }
        )
    )
    spec_mod.proof_obligations.append({
        "property": "reduction_independent_of_mask",
        "status": "unproved",
        "engine": "theorem_proving",
        "backend": "koika"
    })
    return spec_mod


def test_independence_theorem_generation():
    """Independence lowers to `forall inputs inputs', (agreements) -> E = E'`."""
    spec_mod = create_spec_with_independence()
    koika_mod = isir_to_koika.convert(spec_mod)

    state_text = "\n".join(koika_mod.state_definitions)
    assert "Theorem reduction_independent_of_mask_proved" in state_text
    assert "(* PERF_Independence *)" in state_text
    assert "forall (inputs inputs' : inputs)" in state_text
    # Agreement hypothesis for the non-independent input `a`.
    assert "(a inputs) = (a inputs') ->" in state_text
    # Both unprimed and primed occurrences of the operand.
    assert "(slice (a inputs) 7 0)" in state_text
    assert "(slice (a inputs') 7 0)" in state_text
    # No reachability/step in the statement.
    theorem_block = state_text.split("Theorem reduction_independent_of_mask_proved")[1].split("Admitted.")[0]
    assert "reachable" not in theorem_block
    assert "step" not in theorem_block


def test_xor_lowering_nat_and_bool():
    """`xor` lowers to Nat.lxor for nat operands and xorb for bool operands."""
    spec_mod = isir.SpecModule(name="xor_test")
    spec_mod.state_ops.append(
        isir.SpecStateOp(state_name="acc", kind="register", data_type="bits<8>", initial=0)
    )
    spec_mod.inputs = [
        isir.Interface(name="a", direction="input", data_type="bits<8>"),
        isir.Interface(name="b", direction="input", data_type="bits<8>"),
        isir.Interface(name="x", direction="input", data_type="bool"),
        isir.Interface(name="y", direction="input", data_type="bool"),
    ]
    spec_mod.property_ops.append(
        isir.SpecPropertyOp(
            prop_name="nat_xor_self_zero",
            kind="combinational",
            expression={"kind": "combinational", "operand": "(xor a a)", "reference": 0},
        )
    )
    spec_mod.property_ops.append(
        isir.SpecPropertyOp(
            prop_name="bool_xor_commutative",
            kind="combinational",
            expression={"kind": "combinational", "operand": "(xor x y)", "reference": "(xor y x)"},
        )
    )
    spec_mod.proof_obligations.append({
        "property": "nat_xor_self_zero", "status": "unproved",
        "engine": "theorem_proving", "backend": "koika",
    })
    spec_mod.proof_obligations.append({
        "property": "bool_xor_commutative", "status": "unproved",
        "engine": "theorem_proving", "backend": "koika",
    })

    koika_mod = isir_to_koika.convert(spec_mod)
    state_text = "\n".join(koika_mod.state_definitions)
    assert "(Nat.lxor (a inputs) (a inputs))" in state_text
    assert "(xorb (x inputs) (y inputs))" in state_text


def test_shift_lowering():
    """`shl`/`shr` lower to Nat.shiftl/Nat.shiftr."""
    spec_mod = isir.SpecModule(name="shift_test")
    spec_mod.state_ops.append(
        isir.SpecStateOp(state_name="acc", kind="register", data_type="bits<8>", initial=0)
    )
    spec_mod.inputs = [
        isir.Interface(name="a", direction="input", data_type="bits<8>"),
        isir.Interface(name="b", direction="input", data_type="bits<8>"),
    ]
    spec_mod.property_ops.append(
        isir.SpecPropertyOp(
            prop_name="shl_shiftl",
            kind="combinational",
            expression={"kind": "combinational", "operand": "(shl a (slice b 2 0))", "reference": "(shl a (slice b 2 0))"},
        )
    )
    spec_mod.property_ops.append(
        isir.SpecPropertyOp(
            prop_name="shr_shiftr",
            kind="combinational",
            expression={"kind": "combinational", "operand": "(shr a (slice b 2 0))", "reference": "(shr a (slice b 2 0))"},
        )
    )
    spec_mod.proof_obligations.append({
        "property": "shl_shiftl", "status": "unproved",
        "engine": "theorem_proving", "backend": "koika",
    })
    spec_mod.proof_obligations.append({
        "property": "shr_shiftr", "status": "unproved",
        "engine": "theorem_proving", "backend": "koika",
    })

    koika_mod = isir_to_koika.convert(spec_mod)
    state_text = "\n".join(koika_mod.state_definitions)
    assert "(Nat.shiftl (a inputs) (slice (b inputs) 2 0))" in state_text
    assert "(Nat.shiftr (a inputs) (slice (b inputs) 2 0))" in state_text


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


def test_functions_and_axioms_lowering():
    """Functions lower to Parameter, axioms to Axiom + Hint Resolve."""
    spec_mod = isir.SpecModule(name="fpu")
    spec_mod.state_ops.append(
        isir.SpecStateOp(state_name="acc", kind="register", data_type="bits<16>", initial=0)
    )
    spec_mod.inputs = [
        isir.Interface(name="a", direction="input", data_type="bits<16>"),
        isir.Interface(name="b", direction="input", data_type="bits<16>"),
    ]
    spec_mod.functions.append({
        "name": "abstract_finite_add",
        "params": [{"name": "x", "type": "bits<16>"}, {"name": "y", "type": "bits<16>"}],
        "return": "bits<16>",
    })
    spec_mod.axioms.append({
        "name": "finite_add_commutative",
        "forall": [{"name": "x", "type": "bits<16>"}, {"name": "y", "type": "bits<16>"}],
        "statement": "(eq (abstract_finite_add x y) (abstract_finite_add y x))",
    })
    spec_mod.rule_ops.append(
        isir.SpecRuleOp(rule_name="upd", condition="true", actions=["(write acc (abstract_finite_add a b))"])
    )
    spec_mod.property_ops.append(
        isir.SpecPropertyOp(
            prop_name="add_commutes",
            kind="combinational",
            expression={"kind": "combinational", "operand": "(abstract_finite_add a b)", "reference": "(abstract_finite_add b a)"},
        )
    )
    spec_mod.proof_obligations.append({
        "property": "add_commutes", "status": "unproved",
        "engine": "theorem_proving", "backend": "koika",
    })

    koika_mod = isir_to_koika.convert(spec_mod)
    state_text = "\n".join(koika_mod.state_definitions)
    assert "Parameter abstract_finite_add : nat -> nat -> nat." in state_text
    assert "Axiom finite_add_commutative : forall (x : nat) (y : nat)," in state_text
    assert "Hint Resolve finite_add_commutative : core." in state_text
    assert "(abstract_finite_add (a inputs) (b inputs))" in state_text


def test_concat_and_bitset_lowering():
    """concat lowers to high*2^w+low (precomputed shift); bitset clears+sets."""
    spec_mod = isir.SpecModule(name="concat_test")
    spec_mod.state_ops.append(
        isir.SpecStateOp(state_name="r", kind="register", data_type="bits<16>", initial=0)
    )
    spec_mod.inputs = [
        isir.Interface(name="sign", direction="input", data_type="bits<1>"),
    ]
    spec_mod.property_ops.append(
        isir.SpecPropertyOp(
            prop_name="concat_def",
            kind="combinational",
            expression={"kind": "combinational", "operand": "(concat sign 32640 15)", "reference": "(add (mul sign 32768) 32640)"},
        )
    )
    spec_mod.property_ops.append(
        isir.SpecPropertyOp(
            prop_name="bitset_def",
            kind="combinational",
            expression={"kind": "combinational", "operand": "(bitset 32640 6 6 1)", "reference": 32704},
        )
    )
    spec_mod.proof_obligations.append({
        "property": "concat_def", "status": "unproved",
        "engine": "theorem_proving", "backend": "koika",
    })
    spec_mod.proof_obligations.append({
        "property": "bitset_def", "status": "unproved",
        "engine": "theorem_proving", "backend": "koika",
    })

    koika_mod = isir_to_koika.convert(spec_mod)
    state_text = "\n".join(koika_mod.state_definitions)
    # concat with literal width precomputes 2^15 = 32768.
    assert "((sign inputs) * 32768 + 32640)" in state_text
    # bitset emits the clear/set form (slice * 2^low).
    assert "(32640 - (slice 32640 6 6) * 64 + 1 * 64)" in state_text


def test_defined_function_lowering():
    """A function with a body lowers to Definition; without body to Parameter."""
    spec_mod = isir.SpecModule(name="deffn")
    spec_mod.state_ops.append(
        isir.SpecStateOp(state_name="r", kind="register", data_type="bool", initial=False)
    )
    spec_mod.inputs = [
        isir.Interface(name="a", direction="input", data_type="bits<16>"),
    ]
    spec_mod.functions.append({
        "name": "is_nan",
        "params": [{"name": "x", "type": "bits<16>"}],
        "return": "bool",
        "body": "(and (eq (slice x 14 7) 255) (neq (slice x 6 0) 0))",
    })
    spec_mod.functions.append({
        "name": "abstract_add",
        "params": [{"name": "x", "type": "bits<16>"}, {"name": "y", "type": "bits<16>"}],
        "return": "bits<16>",
    })

    koika_mod = isir_to_koika.convert(spec_mod)
    state_text = "\n".join(koika_mod.state_definitions)
    assert "Definition is_nan (x : nat) : bool := (andb (Nat.eqb (slice x 14 7) 255)" in state_text
    assert "Parameter abstract_add : nat -> nat -> nat." in state_text


def test_per_rule_transition_scoping():
    """A transition property with `rule:` scopes to that rule's step."""
    spec_mod = isir.SpecModule(name="scoped")
    spec_mod.state_ops.append(
        isir.SpecStateOp(state_name="x", kind="register", data_type="bits<8>", initial=0)
    )
    spec_mod.state_ops.append(
        isir.SpecStateOp(state_name="y", kind="register", data_type="bits<8>", initial=0)
    )
    spec_mod.inputs = [
        isir.Interface(name="a", direction="input", data_type="bits<8>"),
    ]
    spec_mod.rule_ops.append(
        isir.SpecRuleOp(rule_name="load", condition="true", actions=["(write x (read a))"])
    )
    spec_mod.rule_ops.append(
        isir.SpecRuleOp(rule_name="mac", condition="true", actions=["(write y (add (read y) (read x)))"])
    )
    spec_mod.property_ops.append(
        isir.SpecPropertyOp(
            prop_name="load_correct",
            kind="transition",
            expression={"kind": "transition", "rule": "load", "operand": "(eq (read x) a)"},
        )
    )
    spec_mod.proof_obligations.append({
        "property": "load_correct", "status": "unproved",
        "engine": "theorem_proving", "backend": "koika",
    })

    koika_mod = isir_to_koika.convert(spec_mod)
    state_text = "\n".join(koika_mod.state_definitions)
    theorem_block = state_text.split("Theorem load_correct_proved")[1].split("Admitted.")[0]
    # Scoped to `load`: no `s'` binder and no `step` relation.
    assert "forall (s : state) (inputs : inputs), True ->" in theorem_block
    assert "step s inputs s'" not in theorem_block
    assert "(x (mkState" in theorem_block


def test_combinational_assumes_lowering():
    """A combinational property with `assumes` lowers to an implication over inputs."""
    spec_mod = isir.SpecModule(name="bounded")
    spec_mod.inputs = [
        isir.Interface(name="a", direction="input", data_type="bits<8>"),
        isir.Interface(name="b", direction="input", data_type="bits<8>"),
    ]
    spec_mod.functions.append({
        "name": "mul_exact",
        "params": [{"name": "x", "type": "bits<8>"}, {"name": "y", "type": "bits<8>"}],
        "return": "bits<16>",
        "body": "(mul x y)",
    })
    spec_mod.property_ops.append(
        isir.SpecPropertyOp(
            prop_name="unsigned_max_bound",
            kind="combinational",
            expression={"kind": "combinational", "operand": "(le (mul_exact a b) (mul 255 255))", "reference": "true"},
            assumes=["(and (le a 255) (le b 255))"],
        )
    )
    spec_mod.proof_obligations.append({
        "property": "unsigned_max_bound", "status": "unproved",
        "engine": "theorem_proving", "backend": "koika",
    })

    koika_mod = isir_to_koika.convert(spec_mod)
    state_text = "\n".join(koika_mod.state_definitions)
    theorem_block = state_text.split("Theorem unsigned_max_bound_proved")[1].split("Admitted.")[0]
    assert "forall (inputs : inputs)" in theorem_block
    assert "((a inputs) <= 255) /\\ ((b inputs) <= 255)" in theorem_block
    assert "->" in theorem_block
    assert "Nat.leb (mul_exact (a inputs) (b inputs)) (255 * 255)" in theorem_block


def test_sum_operator_lowering():
    """The `sum` operator lowers to a left-associative `+` reduction."""
    from isir.lowering.isir_to_koika import _expr_to_coq, _type_of_expr
    e = ["sum", ["mul", "a", "b"], ["mul", "c", "d"], 5]
    it = {"a": "nat", "b": "nat", "c": "nat", "d": "nat"}
    out = _expr_to_coq(e, {}, it, [])
    assert out == "(((a inputs) * (b inputs)) + (((c inputs) * (d inputs)) + 5))"
    assert _type_of_expr(e, {}, it, []) == "nat"
    # single-argument sum collapses
    assert _expr_to_coq(["sum", "a"], {}, it, []) == "(a inputs)"


def test_after_k_steps_lowering():
    """A bounded (`after`) property lowers to a stepn-k theorem over the initial state."""
    spec_mod = isir.SpecModule(name="bounded")
    spec_mod.inputs = [
        isir.Interface(name="inc", direction="input", data_type="bool"),
    ]
    spec_mod.state_ops.append(
        isir.SpecStateOp(state_name="count", kind="register", data_type="bits<4>", initial=0)
    )
    spec_mod.rule_ops.append(
        isir.SpecRuleOp(rule_name="inc", condition="true", actions=["(write count (add (read count) 1))"])
    )
    spec_mod.property_ops.append(
        isir.SpecPropertyOp(
            prop_name="count_nonneg_after_3",
            kind="bounded",
            expression={"kind": "after", "bound": 3, "operand": "(ge (read count) 0)"},
        )
    )
    spec_mod.proof_obligations.append({
        "property": "count_nonneg_after_3", "status": "unproved",
        "engine": "theorem_proving", "backend": "koika",
    })

    koika_mod = isir_to_koika.convert(spec_mod)
    state_text = "\n".join(koika_mod.state_definitions)
    assert "Inductive stepn : nat -> state -> state -> Prop :=" in state_text
    theorem_block = state_text.split("Theorem count_nonneg_after_3_proved")[1].split("Admitted.")[0]
    assert "forall (s : state), stepn 3 initial_state s ->" in theorem_block


def test_gcd_operator_lowering():
    """The `gcd` operator lowers to Nat.gcd."""
    from isir.lowering.isir_to_koika import _expr_to_coq, _type_of_expr
    e = ["gcd", "a", "b"]
    it = {"a": "nat", "b": "nat"}
    assert _expr_to_coq(e, {}, it, []) == "(Nat.gcd (a inputs) (b inputs))"
    assert _type_of_expr(e, {}, it, []) == "nat"


def test_recursive_function_lowering():
    """A recursive function lowers to a structural fuel-based Coq Fixpoint."""
    spec_mod = isir.SpecModule(name="recfn")
    spec_mod.inputs = [
        isir.Interface(name="a", direction="input", data_type="bits<8>"),
        isir.Interface(name="b", direction="input", data_type="bits<8>"),
    ]
    spec_mod.functions.append({
        "name": "gcd_sub",
        "params": [{"name": "a", "type": "bits<8>"}, {"name": "b", "type": "bits<8>"}],
        "return": "bits<8>",
        "recursive": True,
        "measure": "(add a b)",
        "body": "(ite (eq a 0) b (ite (eq b 0) a (ite (gt a b) (gcd_sub (sub a b) b) (gcd_sub a (sub b a)))))",
    })

    koika_mod = isir_to_koika.convert(spec_mod)
    state_text = "\n".join(koika_mod.state_definitions)
    assert "Fixpoint gcd_sub (fuel : nat) (a : nat) (b : nat) : nat :=" in state_text
    assert "match fuel with 0 => 0 | S fuel' =>" in state_text
    # self-call recurses on the fuel predecessor, not a bare `gcd_sub a b`
    assert "(gcd_sub fuel' (a - b) b)" in state_text
    # function params must NOT be lowered as inputs (no `(a inputs)` in the body)
    assert "(a inputs)" not in state_text


def test_prev_operator_in_transition():
    """`prev` in a per-rule transition references the old state."""
    from isir.lowering.isir_to_koika import _expr_to_coq
    e = ["eq", ["read", "count"], ["add", ["prev", "count"], 1]]
    it = {"inc": "bool"}
    st = {"count": "nat"}
    out = _expr_to_coq(e, st, it, [], as_prop=True, state_var="(mkState 0)", prev_state_var="s")
    assert "(count (mkState 0))" in out
    assert "(count s)" in out


def test_invariants_section_lowering():
    """A user-declared invariant lowers to Lemma + Hint Resolve over reachable states."""
    spec_mod = isir.SpecModule(name="inv")
    spec_mod.inputs = [isir.Interface(name="inc", direction="input", data_type="bool")]
    spec_mod.state_ops.append(isir.SpecStateOp(state_name="count", kind="register", data_type="bits<4>", initial=0))
    spec_mod.rule_ops.append(isir.SpecRuleOp(rule_name="inc", condition="(and inc (lt (read count) 15))", actions=["(write count (add (read count) 1))"]))
    spec_mod.invariants.append({"name": "count_le_15", "operand": "(le (read count) 15)"})

    koika_mod = isir_to_koika.convert(spec_mod)
    state_text = "\n".join(koika_mod.state_definitions)
    assert "Lemma count_le_15 : forall s, reachable s -> ((count s) <= 15)." in state_text
    assert "Hint Resolve count_le_15 : core." in state_text
    assert "Hint Constructors reachable step : core." in state_text


def test_malformed_rule_condition_raises():
    """A 3-argument `and` in a rule condition must raise, not silently become True."""
    from isir.utils.expr import ExprError
    spec_mod = isir.SpecModule(name="badcond")
    spec_mod.inputs = [isir.Interface(name="a", direction="input", data_type="bool"),
                       isir.Interface(name="b", direction="input", data_type="bool"),
                       isir.Interface(name="c", direction="input", data_type="bool")]
    spec_mod.state_ops.append(isir.SpecStateOp(state_name="x", kind="register", data_type="bits<4>", initial=0))
    spec_mod.rule_ops.append(isir.SpecRuleOp(
        rule_name="bad",
        condition="(and a b c)",   # 3-arg and is invalid
        actions=["(write x (add (read x) 1))"],
    ))
    with pytest.raises(ExprError, match="invalid condition"):
        isir_to_koika.convert(spec_mod)


def test_bool_function_call_in_prop_context():
    """A bool-returning function used as a proposition lowers to `= true`."""
    from isir.utils.expr import parse_sexpr
    st = {"x": "nat"}
    it = {"a": "bits<8>"}
    ftypes = {"is_zero": "bool"}
    # `implies (is_zero a) ...` — is_zero returns bool, must reflect to Prop.
    out = isir_to_koika._expr_to_coq(
        parse_sexpr("(implies (is_zero a) (eq (read x) 0))"),
        st, it, [], as_prop=True, function_types=ftypes,
    )
    assert "(is_zero (a inputs)) = true" in out
    # In a value context (as_prop=False) the bool stays as-is.
    out2 = isir_to_koika._expr_to_coq(
        parse_sexpr("(is_zero a)"),
        st, it, [], as_prop=False, function_types=ftypes,
    )
    assert out2.strip() == "(is_zero (a inputs))"


def test_prelude_coherence_tools():
    """The prelude wires the generic boolean/equality reflection for coherence proofs."""
    spec_mod = isir.SpecModule(name="coh")
    spec_mod.inputs = [isir.Interface(name="i", direction="input", data_type="bool")]
    spec_mod.state_ops.append(isir.SpecStateOp(state_name="x", kind="register", data_type="bits<2>", initial=0))
    spec_mod.functions.append({
        "name": "has_line",
        "params": [{"name": "s", "type": "bits<2>"}, {"name": "a", "type": "bits<4>"}, {"name": "ra", "type": "bits<4>"}],
        "return": "bool",
        "body": "(and (neq s 0) (eq a ra))",
    })
    koika_mod = isir_to_koika.convert(spec_mod)
    text = "\n".join(koika_mod.state_definitions)
    assert "Require Import ZifyBool." in text
    assert "Hint Unfold has_line : core." in text
