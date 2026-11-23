# src/isir/verification/sat_gate/live_gate.py
#
# Live ITP obligation gating: the PERF-side hook. Before an expensive prover
# call the hook runs the gate and returns a disposition that the traversal acts
# on: SAT_GATED (a T3-certified inductive pair), PARK (heuristic evidence), or
# FORWARD (fall through to the ITP). A whitelist tracks obligations that pass
# the gate but fail downstream and escalates them to bounded model checking.

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional
from isir.verification.sat_gate.gate_config import GateConfig
from isir.verification.sat_gate.observe import GateMetrics
from isir.verification.sat_gate.policy import EvidenceAction


class ObligationAction(Enum):
    SAT_GATED = "sat_gated"   # T3-certified PROVE_STEP/PROVE_BASE short-circuit
    PARK = "park"             # heuristic evidence: deprioritize, never delete
    FORWARD = "forward"       # fall through to the ITP


@dataclass
class ObligationDisposition:
    action: ObligationAction
    property: str = ""
    reason: str = ""
    gate_result: Any = None


class Whitelist:
    """Obligations that pass the gate but fail downstream.

    After ``max_failures_before_escalation`` downstream failures, the obligation
    is escalated to bounded model checking (the gate is skipped for it).
    """

    def __init__(self, max_failures_before_escalation: int = 2) -> None:
        self.max_failures = max_failures_before_escalation
        self._failures: Dict[str, int] = {}

    def record_downstream_failure(self, prop_name: str) -> bool:
        self._failures[prop_name] = self._failures.get(prop_name, 0) + 1
        return self.escalated(prop_name)

    def escalated(self, prop_name: str) -> bool:
        return self._failures.get(prop_name, 0) >= self.max_failures


class LiveGate:
    """The PERF hook: gate an obligation before the expensive prover call."""

    def __init__(self, config: Optional[GateConfig] = None,
                 metrics: Optional[GateMetrics] = None,
                 whitelist: Optional[Whitelist] = None) -> None:
        self.config = config or GateConfig()
        self.metrics = metrics or GateMetrics()
        self.whitelist = whitelist or Whitelist()

    def gate_obligation(self, spec_module, property_name: str) -> ObligationDisposition:
        """Return the disposition for ``property_name``.

        The kill switch or an escalated whitelist entry forces FORWARD; otherwise
        the gate runs and the T3 inductive pair maps to SAT_GATED.
        """
        if not self.config.effective_enabled():
            return ObligationDisposition(ObligationAction.FORWARD, property_name,
                                         reason="kill-switch")
        if self.whitelist.escalated(property_name):
            return ObligationDisposition(ObligationAction.FORWARD, property_name,
                                         reason="whitelist-escalated")

        from isir.verification.sat_gate.gate_runner import run_gate
        rows, _ = run_gate(spec_module, self.metrics)
        for gr in rows:
            if gr.property == property_name:
                return self._route(gr, property_name)
        return ObligationDisposition(ObligationAction.FORWARD, property_name,
                                     reason="not-gateable")

    def _route(self, gate_result, property_name: str) -> ObligationDisposition:
        action = gate_result.evidence_action
        if action in (EvidenceAction.PROVE_STEP, EvidenceAction.PROVE_BASE,
                      EvidenceAction.CLOSE_VACUOUS):
            return ObligationDisposition(ObligationAction.SAT_GATED, property_name,
                                         gate_result=gate_result)
        if action is EvidenceAction.PARK:
            return ObligationDisposition(ObligationAction.PARK, property_name,
                                         gate_result=gate_result)
        return ObligationDisposition(ObligationAction.FORWARD, property_name,
                                     gate_result=gate_result)

    def resolve_cti_for(self, spec_module, property_name: str,
                        cti_probe_k: int = 10):
        """Run the CTI reachability probe for a non-inductive obligation.

        Returns ``(cti_reachable, composed_replay_checked)`` for the
        mandatory CTI probe + composed replay, or ``(None, False)`` when the
        property is not a resolvable IND_STEP obligation.
        """
        from isir.verification.sat_gate.isir_bridge import (
            always_operand, initial_values, transitions_of, widths_of,
        )
        from isir.verification.sat_gate.cti_probe import resolve_cti

        inv = always_operand(spec_module, property_name)
        if inv is None:
            return None, False
        widths = widths_of(spec_module)
        transitions = transitions_of(spec_module)
        init = initial_values(spec_module)
        return resolve_cti(init, transitions, widths, inv, cti_probe_k)
