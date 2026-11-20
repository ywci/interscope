# tests/sat_gate/test_solver_oneshot.py
"""One-shot solver: SAT / UNSAT / model extraction."""

from isir.verification.sat_gate.bitblast import CNF
from isir.verification.sat_gate.solver_oneshot import solve_cnf


def test_sat_model():
    cnf = CNF()
    x = cnf.new_var()
    cnf.add([x])
    r = solve_cnf(cnf)
    assert r.status == "sat"
    assert r.model is not None and r.model.get(x) is True


def test_unsat():
    cnf = CNF()
    x = cnf.new_var()
    cnf.add([x])
    cnf.add([-x])
    r = solve_cnf(cnf)
    assert r.status == "unsat"
    assert r.model is None


def test_missing_solver_returns_unknown():
    r = solve_cnf(CNF(), solver="definitely-not-a-solver-binary")
    assert r.status == "unknown"
