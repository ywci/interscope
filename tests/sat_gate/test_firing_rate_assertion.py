# tests/sat_gate/test_firing_rate_assertion.py

from isir.verification.sat_gate.observe import GateMetrics


def test_firing_rate_flagged_when_eligible_but_idle():
    m = GateMetrics(eligible_pre=10, gateable=10, calls=0)
    assert m.firing_rate_flagged() is True  # eligible but never fires


def test_firing_rate_not_flagged_when_healthy():
    m = GateMetrics(eligible_pre=10, gateable=10, calls=10)
    assert m.firing_rate() == 1.0
    assert m.firing_rate_flagged() is False


def test_firing_rate_not_flagged_without_eligible():
    # no eligible obligations -> the  assertion does not apply.
    m = GateMetrics(eligible_pre=0, gateable=0, calls=0)
    assert m.firing_rate_flagged() is False
