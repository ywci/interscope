# tests/sat_gate/test_park_precision.py

from isir.verification.sat_gate.observe import GateMetrics


def test_park_precision_defaults_to_one():
    m = GateMetrics()
    assert m.park_precision() == 1.0  # no sample yet -> no evidence of loss


def test_park_precision_perfect_when_no_loss():
    m = GateMetrics()
    m.record_resurrect(True)
    m.record_resurrect(True)
    assert m.park_precision() == 1.0


def test_park_precision_counts_loss():
    m = GateMetrics()
    m.record_resurrect(True)
    m.record_resurrect(True)
    m.record_resurrect(False)  # one parked obligation was not provable
    assert abs(m.park_precision() - 2.0 / 3.0) < 1e-9


def test_park_precision_meets_threshold():
    # a healthy sample stays above the 70% threshold.
    m = GateMetrics()
    for _ in range(7):
        m.record_resurrect(True)
    for _ in range(3):
        m.record_resurrect(False)
    assert m.park_precision() >= 0.7
