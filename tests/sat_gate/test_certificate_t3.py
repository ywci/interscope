# tests/sat_gate/test_certificate_t3.py

from isir.verification.sat_gate.bitblast import CNF
from isir.verification.sat_gate.solver_oneshot import solve_cnf_with_proof
from isir.verification.sat_gate.certificate import verify_t3


def _build_gated_unsat():
    cnf = CNF()
    a = cnf.new_var()   # the activation literal
    x = cnf.new_var()
    # F = (¬a ∨ x) ∧ (¬a ∨ ¬x); with a asserted it is UNSAT.
    cnf.add([-a, x])
    cnf.add([-a, -x])
    cnf.add([a])        # the assumption as a unit (the full query)
    return cnf, a


def test_t3_drat_checks_with_assumption_units():
    cnf, a = _build_gated_unsat()
    result, proof = solve_cnf_with_proof(cnf)
    assert result.status == "unsat"
    assert proof is not None

    F = [c for c in cnf.clauses if c != [a]]
    # the correct checking formula: F plus the assumption literal as a unit.
    assert verify_t3(F, [a], proof) is True


def test_t3_drat_fails_without_assumption_units():
    cnf, a = _build_gated_unsat()
    result, proof = solve_cnf_with_proof(cnf)
    assert result.status == "unsat"
    F = [c for c in cnf.clauses if c != [a]]
    # the gotcha: checking against F alone (no assumption unit) must fail.
    assert verify_t3(F, [], proof) is False
