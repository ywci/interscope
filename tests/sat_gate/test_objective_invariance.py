# tests/sat_gate/test_objective_invariance.py
"""Objective invariance (P8 / §6.6): objective never changes the evidence action."""

from isir.verification.sat_gate.policy import (
    CertState, CertTier, EvidenceAction, Objective, Status, disposition,
    evidence_action,
)
from isir.verification.sat_gate.obligation import ModelApprox, QueryKind, TargetScope


def test_evidence_action_is_objective_free():
    """evidence_action has no objective parameter by construction."""
    import inspect
    params = inspect.signature(evidence_action).parameters
    assert "objective" not in params


def test_disposition_preserves_action():
    """Flipping the objective never changes the SearchAction.action."""
    for action in EvidenceAction:
        for obj in (Objective.PROOF, Objective.BUG_HUNT):
            sa = disposition(action, obj)
            assert sa.action is action, (action, obj, sa.action)


def test_disposition_terminality_only_for_report_cex_under_bug_hunt():
    """REPORT_CEX is terminal in both objectives (semantics differ, not action)."""
    for obj in (Objective.PROOF, Objective.BUG_HUNT):
        sa = disposition(EvidenceAction.REPORT_CEX, obj)
        assert sa.terminal is True


def test_cti_probe_k_differs_by_objective():
    """The CTI probe budget is the one lever the objective may move."""
    assert disposition(EvidenceAction.PARK, Objective.PROOF).cti_probe_k == 2
    assert disposition(EvidenceAction.PARK, Objective.BUG_HUNT).cti_probe_k == 4
