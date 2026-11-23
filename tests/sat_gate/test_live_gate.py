# tests/sat_gate/test_live_gate.py

from isir.parser.parser import parse_isir
from isir.lowering.ast_to_isir import convert_ast_to_isir_module
from isir.verification.sat_gate.live_gate import (
    LiveGate, ObligationAction, Whitelist,
)
from isir.verification.sat_gate.gate_config import GateConfig


def _spec():
    return convert_ast_to_isir_module(
        parse_isir("examples/counter/counter.isir").module
    )


def test_kill_switch_forces_forward():
    cfg = GateConfig(kill_switch=True)
    gate = LiveGate(config=cfg)
    d = gate.gate_obligation(_spec(), "counter_bound")
    assert d.action is ObligationAction.FORWARD


def test_inductive_property_is_sat_gated():
    gate = LiveGate()
    d = gate.gate_obligation(_spec(), "counter_bound")
    assert d.action is ObligationAction.SAT_GATED


def test_unknown_property_forwards():
    gate = LiveGate()
    d = gate.gate_obligation(_spec(), "no_such_property")
    assert d.action is ObligationAction.FORWARD


def test_whitelist_escalation_skips_gate():
    wl = Whitelist(max_failures_before_escalation=2)
    gate = LiveGate(whitelist=wl)
    # two downstream failures -> the escalation.
    assert wl.record_downstream_failure("counter_bound") is False
    assert wl.record_downstream_failure("counter_bound") is True
    d = gate.gate_obligation(_spec(), "counter_bound")
    assert d.action is ObligationAction.FORWARD
    assert d.reason == "whitelist-escalated"
