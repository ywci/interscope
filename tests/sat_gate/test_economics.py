# tests/sat_gate/test_economics.py

from isir.verification.sat_gate.economics import (
    gate_cost, is_economic, per_class_verdict, required_pq, saving,
)


def test_required_pq_matches_spec_table():
    # per-class break-even values.
    assert abs(required_pq(36, 50) - 2.16) < 0.01
    assert abs(required_pq(36, 500) - 0.216) < 0.01
    assert abs(required_pq(60, 5000) - 0.036) < 0.001


def test_gate_cost_adds_certification():
    base = gate_cost(C_triage=30)
    with_cert = gate_cost(C_triage=30, h_hard=0.1, h_t3_hard=0.1, C_T3=500)
    assert with_cert > base


def test_is_economic_requires_margin():
    # saving 500 >= 3 * 36 -> economic; saving 50 < 3 * 36 -> not.
    assert is_economic(C_g_avg=36, E_avoid=500)
    assert not is_economic(C_g_avg=36, E_avoid=50)


def test_per_class_verdict():
    # cheap leaf (required p·q = 2.16 > 1) -> do not gate; proof-step -> gate.
    assert per_class_verdict(36, 50) == "do_not_gate"
    assert per_class_verdict(36, 500) == "gate"
    assert per_class_verdict(60, 5000) == "gate"


def test_saving():
    assert saving(0.5, 1.0, 500) == 250.0
