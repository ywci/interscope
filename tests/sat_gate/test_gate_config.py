# tests/sat_gate/test_gate_config.py

from isir.verification.sat_gate.gate_config import GateConfig


def test_kill_switch_forces_forward():
    cfg = GateConfig(sat_gating_enabled=True)
    assert cfg.effective_enabled() is True
    cfg.trip_kill_switch()
    assert cfg.effective_enabled() is False


def test_disabled_config_is_off():
    cfg = GateConfig(sat_gating_enabled=False)
    assert cfg.effective_enabled() is False
