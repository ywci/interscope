# tests/sat_gate/test_incremental_vs_oneshot.py

from isir.parser.parser import parse_isir
from isir.lowering.ast_to_isir import convert_ast_to_isir_module
from isir.verification.sat_gate.isir_bridge import (
    always_operand, initial_values, transitions_of, widths_of,
)
from isir.verification.sat_gate.compile_dyn import compile_base_entail, compile_ind_step
from isir.verification.sat_gate.solver_oneshot import solve_cnf
from isir.verification.sat_gate.solver_cadical import IncrementalSolver


def _load(name):
    return convert_ast_to_isir_module(
        parse_isir(f"examples/{name}/{name}.isir").module
)


def _status_of(sat_or_unsat):
    return "sat" if sat_or_unsat else "unsat"


def test_incremental_agrees_with_oneshot_saturating():
    spec = _load("saturating_counter")
    widths = widths_of(spec)
    transitions = transitions_of(spec)
    inv = always_operand(spec, "count_in_range")
    init = initial_values(spec)

    for compiled in (
        compile_base_entail(init, inv, widths),
        compile_ind_step(inv, transitions, widths),
):
        one = solve_cnf(compiled.cnf).status
        inc = IncrementalSolver(clauses=compiled.cnf.clauses)
        try:
            inc_status = _status_of(inc.solve())
        finally:
            inc.delete()
        assert inc_status == one, (one, inc_status)


def test_incremental_agrees_with_oneshot_cti():
    widths = {"count": 4}
    transitions = {"count": "(add (read count) 1)"}
    inv = "(le (read count) 7)"
    init = {"count": 0}

    base = compile_base_entail(init, inv, widths)
    step = compile_ind_step(inv, transitions, widths)

    assert solve_cnf(base.cnf).status == "unsat"
    assert solve_cnf(step.cnf).status == "sat"

    inc = IncrementalSolver(clauses=base.cnf.clauses)
    try:
        assert inc.solve() is False  # base unsat
    finally:
        inc.delete()

    inc = IncrementalSolver(clauses=step.cnf.clauses)
    try:
        assert inc.solve() is True   # step sat (CTI)
    finally:
        inc.delete()


def test_incremental_failed_assumptions_core():
    # (¬a∨x) ∧ (¬a∨¬x) under assumption [a] is UNSAT with core {a} (or a superset).
    from isir.verification.sat_gate.bitblast import CNF
    cnf = CNF()
    a = cnf.new_var()
    x = cnf.new_var()
    cnf.add([-a, x])
    cnf.add([-a, -x])

    inc = IncrementalSolver(clauses=cnf.clauses)
    try:
        assert inc.solve(assumptions=[a]) is False
        core = inc.get_core()
        assert set(core) == {a} or set(core) == {a, x}  # valid (non-minimal) superset
    finally:
        inc.delete()
