# tests/sat_gate/test_isir_end_to_end.py
"""End-to-end: parse a real ISIR and run the inductive pair through the gate."""

from isir.parser.parser import parse_isir
from isir.lowering.ast_to_isir import convert_ast_to_isir_module

from isir.verification.sat_gate.isir_bridge import (
    always_operand, initial_values, transitions_of, widths_of,
)
from isir.verification.sat_gate.compile_dyn import compile_base_entail, compile_ind_step
from isir.verification.sat_gate.solver_oneshot import solve_cnf


def _load(name):
    return convert_ast_to_isir_module(
        parse_isir(f"examples/{name}/{name}.isir").module
    )


def test_saturating_counter_is_inductive():
    spec = _load("saturating_counter")
    widths = widths_of(spec)
    transitions = transitions_of(spec)
    inv = always_operand(spec, "count_in_range")
    init = initial_values(spec)
    assert widths["count"] == 4
    assert inv is not None

    # BASE_ENTAIL: count=0 ∧ ¬(0 <= count <= 8) is UNSAT.
    base = compile_base_entail(init, inv, widths)
    assert solve_cnf(base.cnf).status == "unsat"

    # IND_STEP: Inv ∧ T ∧ ¬Inv' is UNSAT (saturating bound is inductive).
    step = compile_ind_step(inv, transitions, widths)
    assert solve_cnf(step.cnf).status == "unsat"


def test_counter_is_not_a_tautological_pair():
    # counter: count <= 15 is a 4-bit tautology, so BASE_ENTAIL is UNSAT too.
    spec = _load("counter")
    widths = widths_of(spec)
    transitions = transitions_of(spec)
    inv = always_operand(spec, "counter_bound")
    init = initial_values(spec)
    base = compile_base_entail(init, inv, widths)
    assert solve_cnf(base.cnf).status == "unsat"


def test_transitions_of_combines_rules():
    spec = _load("saturating_counter")
    transitions = transitions_of(spec)
    # two rules write `count`; the combined expression nests both.
    assert "count" in transitions
    expr = transitions["count"]
    assert expr.startswith("(ite ")
    assert "inc" in expr and "dec" in expr
