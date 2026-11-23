# tests/sat_gate/oracle/differential.py

from isir.verification.sat_gate.compile_dyn import compile_base_entail, compile_ind_step
from isir.verification.sat_gate.solver_oneshot import solve_cnf
from isir.verification.sat_gate.smt_encode import solve_smt_base_entail, solve_smt_ind_step


def run_base_entail(init, inv, widths):
    """Return (bit-blast_status, smt_status) for BASE_ENTAIL."""
    bb = solve_cnf(compile_base_entail(init, inv, widths).cnf).status
    smt = solve_smt_base_entail(init, inv, widths)
    return bb, smt


def run_ind_step(inv, transitions, widths):
    """Return (bit-blast_status, smt_status) for IND_STEP."""
    bb = solve_cnf(compile_ind_step(inv, transitions, widths).cnf).status
    smt = solve_smt_ind_step(inv, transitions, widths)
    return bb, smt


def assert_agreement(base, step):
    """Assert the bit-blast and SMT routes agree on both queries."""
    assert base[0] == base[1], f"BASE_ENTAIL disagreement: {base}"
    assert step[0] == step[1], f"IND_STEP disagreement: {step}"
