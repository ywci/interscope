# tests/sat_gate/test_compile_dyn.py

from sat_helper import dpll_sat, vars_of
from isir.verification.sat_gate.bitblast import BitBlaster
from isir.verification.sat_gate.compile_dyn import (
    compile_base_entail, compile_ind_step, lower_pred,
)


def test_lower_le_predicate():
    widths = {"count": 4}
    blaster = BitBlaster()
    inv = lower_pred("(le (read count) 8)", blaster, widths)
    base = blaster.symbols.intern("count", 4)
    for c in range(16):
        fixed = {inv: True}
        for i in range(4):
            fixed[base + i] = bool(c >> i & 1)
        unit = [[v if val else -v] for v, val in fixed.items()]
        nvars = vars_of(blaster.cnf.clauses + unit)
        sat = dpll_sat(blaster.cnf.clauses + unit, nvars) is not None
        assert sat == (c <= 8), c


def test_compile_base_entail_unsat_when_init_entails_inv():
    # count=0 init, inv = count <= 8 => Init ∧ ¬Inv is UNSAT
    blaster = compile_base_entail({"count": 0}, "(le (read count) 8)",
                                  {"count": 4})
    nvars = vars_of(blaster.cnf.clauses)
    assert dpll_sat(blaster.cnf.clauses, nvars) is None


def test_compile_base_entail_sat_when_init_violates_inv():
    # count=9 init, inv = count <= 8 => Init ∧ ¬Inv is SAT (a real base violation)
    blaster = compile_base_entail({"count": 9}, "(le (read count) 8)",
                                  {"count": 4})
    nvars = vars_of(blaster.cnf.clauses)
    assert dpll_sat(blaster.cnf.clauses, nvars) is not None


def _sat(blaster):
    nvars = vars_of(blaster.cnf.clauses)
    return dpll_sat(blaster.cnf.clauses, nvars) is not None


def test_ind_step_saturating_invariant_is_inductive():
    # count <= 8 with count' = (count < 8 ? count+1 : count) is inductive
    # (the saturating bound): Inv ∧ T ∧ ¬Inv' is UNSAT.
    blaster = compile_ind_step(
        "(le (read count) 8)",
        {"count": "(ite (lt (read count) 8) (add (read count) 1) (read count))"},
        {"count": 4},
)
    assert not _sat(blaster)


def test_ind_step_non_inductive_has_cti():
    # count <= 7 with count' = count + 1: at count=7 the next state is 8 > 7,
    # so Inv ∧ T ∧ ¬Inv' is SAT (a CTI).
    blaster = compile_ind_step(
        "(le (read count) 7)",
        {"count": "(add (read count) 1)"},
        {"count": 4},
)
    assert _sat(blaster)
