# tests/sat_gate/test_coverage_firing_pair.py
"""Coverage and firing rate are always reported as a pair (§18)."""

from isir.verification.sat_gate.observe import GateMetrics


def test_coverage_firing_pair():
    m = GateMetrics(eligible_pre=10, gateable=8, calls=7)
    cov, rate = m.coverage_firing_pair()
    assert cov == 0.8
    assert rate == 7 / 8


def test_zero_denominator_does_not_divide():
    m = GateMetrics(eligible_pre=0, gateable=0, calls=0)
    assert m.coverage_firing_pair() == (0.0, 0.0)


def test_record_call_and_unknown():
    m = GateMetrics()
    m.record_call("sat")
    m.record_call("unsat")
    m.record_call("sat")
    m.record_unknown("quantifier")
    assert m.status_histogram == {"sat": 2, "unsat": 1}
    assert m.unknown_reasons == {"quantifier": 1}
