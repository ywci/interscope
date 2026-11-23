# tests/sat_gate/test_target_scope.py

from isir.verification.sat_gate.policy import (
    CertState, CertTier, EvidenceAction, Status, evidence_action,
)
from isir.verification.sat_gate.obligation import ModelApprox, QueryKind, TargetScope


def _falsify(scope):
    return evidence_action(
        QueryKind.FALSIFY_INIT, Status.SAT, ModelApprox.EXACT, True,
        scope, None, False, CertState.CHECKED, CertTier.REPLAY,
)


def test_theorem_target_reports_cex():
    assert _falsify(TargetScope.THEOREM_TARGET) is EvidenceAction.REPORT_CEX


def test_candidate_lemma_rejects_candidate():
    assert _falsify(TargetScope.CANDIDATE_LEMMA) is EvidenceAction.REJECT_CANDIDATE


def test_ind_step_cti_scope():
    """IND_STEP SAT with a reachable CTI + composed replay scopes the same way."""
    for scope, expected in ((TargetScope.THEOREM_TARGET, EvidenceAction.REPORT_CEX),
                            (TargetScope.CANDIDATE_LEMMA, EvidenceAction.REJECT_CANDIDATE)):
        r = evidence_action(QueryKind.IND_STEP, Status.SAT, ModelApprox.EXACT, True,
                            scope, True, True, CertState.CHECKED, CertTier.REPLAY)
        assert r is expected


def test_ind_step_cti_without_composed_replay_parks():
    r = evidence_action(QueryKind.IND_STEP, Status.SAT, ModelApprox.EXACT, True,
                        TargetScope.THEOREM_TARGET, True, False,
                        CertState.CHECKED, CertTier.REPLAY)
    assert r is EvidenceAction.PARK
