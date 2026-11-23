# tests/sat_gate/test_budget.py

from isir.verification.sat_gate.budget import calibrate_budget


def test_calibrate_on_linear_samples():
    # wall_ms = 2 * conflicts + 10  =>  target 110 ms -> K_conf = 50
    samples = [(c, 2 * c + 10) for c in (10, 20, 30, 40, 50)]
    budget = calibrate_budget(samples, target_ms=110)
    assert budget.target_ms == 110
    assert abs(budget.k_conf - 50) <= 1


def test_calibrate_flat_samples_falls_back():
    samples = [(5, 1.0), (6, 1.0), (7, 1.0)]
    budget = calibrate_budget(samples, target_ms=100)
    assert budget.k_conf >= 1  # no positive slope -> minimal budget


def test_calibrate_zero_samples():
    budget = calibrate_budget([], target_ms=50)
    assert budget.k_conf >= 1
