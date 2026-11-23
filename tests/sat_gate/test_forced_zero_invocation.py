# tests/sat_gate/test_forced_zero_invocation.py

from isir.verification.sat_gate.observe import GateMetrics


def test_uninvoked_gate_reports_zero_pair():
    m = GateMetrics()
    assert m.coverage_firing_pair() == (0.0, 0.0)
    # the pair is always present, so a consumer cannot misread a missing metric.


def test_uninvoked_gate_does_not_flag_d3():
    # zero eligible obligations is NOT the  silent-no-op class.
    m = GateMetrics()
    assert m.firing_rate_flagged() is False


def test_eligible_but_zero_calls_flags_d3():
    m = GateMetrics(eligible_pre=5, gateable=5, calls=0)
    assert m.firing_rate_flagged() is True
