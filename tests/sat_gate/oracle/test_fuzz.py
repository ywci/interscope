# tests/sat_gate/oracle/test_fuzz.py

import random
from isir.verification.sat_gate.compile_dyn import compile_ind_step
from isir.verification.sat_gate.solver_oneshot import solve_cnf
from isir.verification.sat_gate.smt_encode import solve_smt_ind_step


def test_fuzz_counter_ind_step_agreement():
    widths = {"count": 4}
    transitions = {"count": "(add (read count) 1)"}
    for bound in range(16):
        inv = f"(le (read count) {bound})"
        bb = solve_cnf(compile_ind_step(inv, transitions, widths).cnf).status
        smt = solve_smt_ind_step(inv, transitions, widths)
        assert bb == smt, (bound, bb, smt)


def test_fuzz_seeded_base_entail_agreement():
    from isir.verification.sat_gate.compile_dyn import compile_base_entail
    from isir.verification.sat_gate.smt_encode import solve_smt_base_entail
    widths = {"count": 4}
    rng = random.Random(7)
    for _ in range(20):
        init = {"count": rng.randint(0, 15)}
        bound = rng.randint(0, 15)
        inv = f"(le (read count) {bound})"
        bb = solve_cnf(compile_base_entail(init, inv, widths).cnf).status
        smt = solve_smt_base_entail(init, inv, widths)
        assert bb == smt, (init, bound, bb, smt)
