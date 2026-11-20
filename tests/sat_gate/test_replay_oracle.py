# tests/sat_gate/test_replay_oracle.py
"""Independent replay oracle: re-derive the state and confirm a CTI (§20.2)."""

from isir.verification.sat_gate.compile_dyn import compile_ind_step
from isir.verification.sat_gate.solver_oneshot import solve_cnf
from isir.verification.sat_gate.oracle.replay import (
    extract_signal, replay_ind_step,
)


def test_replay_confirms_cti():
    blaster = compile_ind_step(
        "(le (read count) 7)",
        {"count": "(add (read count) 1)"},
        {"count": 4},
    )
    r = solve_cnf(blaster.cnf)
    assert r.status == "sat"

    def inv(s):
        return s["count"] <= 7

    def trans(s):
        return {"count": (s["count"] + 1) & 15}

    assert replay_ind_step(blaster, r.model, inv, trans, {"count": 4})
    # the extracted counterexample state is 7 (the CTI)
    assert extract_signal(blaster, r.model, "count", 4) == 7


def test_replay_rejects_non_cti():
    # a model that already violates Inv is not a CTI
    blaster = compile_ind_step(
        "(le (read count) 7)",
        {"count": "(add (read count) 1)"},
        {"count": 4},
    )
    # force a state with count=9 (violates Inv directly)
    base = blaster.symbols.intern("count", 4)
    model = {base + i: bool(9 >> i & 1) for i in range(4)}

    def inv(s):
        return s["count"] <= 7

    def trans(s):
        return {"count": (s["count"] + 1) & 15}

    assert replay_ind_step(blaster, model, inv, trans, {"count": 4}) is False
