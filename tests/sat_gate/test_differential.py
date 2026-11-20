# tests/sat_gate/test_differential.py
"""Dual-encoder agreement: the bit-blast path and the SMT path agree (§20.3)."""

from isir.parser.parser import parse_isir
from isir.lowering.ast_to_isir import convert_ast_to_isir_module

from isir.verification.sat_gate.isir_bridge import (
    always_operand, initial_values, transitions_of, widths_of,
)
from isir.verification.sat_gate.compile_dyn import compile_base_entail, compile_ind_step
from isir.verification.sat_gate.solver_oneshot import solve_cnf
from isir.verification.sat_gate.smt_encode import (
    solve_smt_base_entail, solve_smt_ind_step,
)


def _load(name):
    return convert_ast_to_isir_module(
        parse_isir(f"examples/{name}/{name}.isir").module
    )


def test_dual_encoder_agreement_saturating():
    spec = _load("saturating_counter")
    widths = widths_of(spec)
    transitions = transitions_of(spec)
    inv = always_operand(spec, "count_in_range")
    init = initial_values(spec)

    # bit-blast path (CNF -> one-shot)
    base = compile_base_entail(init, inv, widths)
    step = compile_ind_step(inv, transitions, widths)
    assert solve_cnf(base.cnf).status == "unsat"
    assert solve_cnf(step.cnf).status == "unsat"

    # SMT path (QF_BV -> z3)
    assert solve_smt_base_entail(init, inv, widths) == "unsat"
    assert solve_smt_ind_step(inv, transitions, widths) == "unsat"


def test_dual_encoder_agreement_cti():
    # a non-inductive bound yields a CTI on BOTH encoders.
    widths = {"count": 4}
    transitions = {"count": "(add (read count) 1)"}
    inv = "(le (read count) 7)"
    init = {"count": 0}

    base = compile_base_entail(init, inv, widths)
    step = compile_ind_step(inv, transitions, widths)
    assert solve_cnf(base.cnf).status == "unsat"       # base holds (0 <= 7)
    assert solve_cnf(step.cnf).status == "sat"         # CTI at 7 -> 8

    assert solve_smt_base_entail(init, inv, widths) == "unsat"
    assert solve_smt_ind_step(inv, transitions, widths) == "sat"
