# tests/sat_gate/test_mus.py

from isir.verification.sat_gate.bitblast import CNF
from isir.verification.sat_gate.assumptions import AssumptionRegistry
from isir.verification.sat_gate.solver_cadical import IncrementalSolver
from isir.verification.sat_gate.mus import group_mus


def test_group_mus_shrinks_redundant_core():
    registry = AssumptionRegistry()
    a = registry.activation_literal("g1")
    b = registry.activation_literal("g2")
    c = registry.activation_literal("g3")
    cnf = CNF()
    x = cnf.new_var()
    # F = (¬a ∨ ¬b ∨ x) ∧ (¬a ∨ ¬b ∨ ¬x):  a∧b is UNSAT, a or b alone is SAT.
    cnf.add([-a, -b, x])
    cnf.add([-a, -b, -x])

    solver = IncrementalSolver(clauses=cnf.clauses)
    try:
        # the failed core is {g1,g2,g3}; g3 is redundant.
        mus = group_mus(["g1", "g2", "g3"], registry, solver)
        assert set(mus) == {"g1", "g2"}
        # the MUS is still UNSAT
        lits = [registry.activation_literal(g) for g in mus]
        assert solver.solve(assumptions=lits) is False
    finally:
        solver.delete()


def test_group_mus_is_minimal():
    registry = AssumptionRegistry()
    a = registry.activation_literal("g1")
    b = registry.activation_literal("g2")
    cnf = CNF()
    x = cnf.new_var()
    cnf.add([-a, -b, x])
    cnf.add([-a, -b, -x])
    solver = IncrementalSolver(clauses=cnf.clauses)
    try:
        mus = group_mus(["g1", "g2"], registry, solver)
        assert set(mus) == {"g1", "g2"}  # already minimal
        # every proper subset is satisfiable
        for g in mus:
            rest = [r for r in mus if r != g]
            lits = [registry.activation_literal(r) for r in rest]
            assert solver.solve(assumptions=lits) is True
    finally:
        solver.delete()
