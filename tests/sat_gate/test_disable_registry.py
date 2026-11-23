# tests/sat_gate/test_disable_registry.py

from isir.verification.sat_gate.observe import DisableRegistry


def test_disable_and_reprobe_due():
    r = DisableRegistry(reprobe_interval_steps=10)
    r.disable("cls", "error", current_step=0)
    assert r.is_disabled("cls")
    assert r.count == 1
    assert not r.reprobe_due("cls", current_step=9)
    assert r.reprobe_due("cls", current_step=10)


def test_reprobe_success_reenables():
    r = DisableRegistry(reprobe_interval_steps=10)
    r.disable("cls", "error", current_step=0)
    assert r.record_reprobe("cls", success=True, current_step=10) is True
    assert not r.is_disabled("cls")
    assert r.reprobe_count == 1


def test_reprobe_failure_stays_disabled():
    r = DisableRegistry(reprobe_interval_steps=10)
    r.disable("cls", "error", current_step=0)
    assert r.record_reprobe("cls", success=False, current_step=10) is False
    assert r.is_disabled("cls")
    # the interval restarts from the failed probe.
    assert not r.reprobe_due("cls", current_step=19)
    assert r.reprobe_due("cls", current_step=20)
