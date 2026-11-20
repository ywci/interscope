# tests/sat_gate/test_policy_matrix.py
"""Exhaustive evidence_action matrix tests (§6.5)."""

import itertools

from isir.verification.sat_gate.policy import (
    CertState, CertTier, EvidenceAction, Status, evidence_action, is_hard,
)
from isir.verification.sat_gate.obligation import ModelApprox, QueryKind, TargetScope


def test_table_rows():
    """The authoritative §6.5 rows, one per case."""
    cases = [
        # VACUITY
        (QueryKind.VACUITY, Status.UNSAT, ModelApprox.EXACT, True,
         TargetScope.THEOREM_TARGET, None, CertState.CHECKED, CertTier.T3,
         EvidenceAction.CLOSE_VACUOUS),
        (QueryKind.VACUITY, Status.UNSAT, ModelApprox.EXACT, True,
         TargetScope.THEOREM_TARGET, None, CertState.UNCHECKED, CertTier.T3,
         EvidenceAction.PARK),
        (QueryKind.VACUITY, Status.SAT, ModelApprox.EXACT, True,
         TargetScope.THEOREM_TARGET, None, CertState.CHECKED, CertTier.T3,
         EvidenceAction.FORWARD),
        # FALSIFY_INIT
        (QueryKind.FALSIFY_INIT, Status.SAT, ModelApprox.EXACT, True,
         TargetScope.THEOREM_TARGET, None, CertState.CHECKED, CertTier.REPLAY,
         EvidenceAction.REPORT_CEX),
        (QueryKind.FALSIFY_INIT, Status.SAT, ModelApprox.EXACT, True,
         TargetScope.CANDIDATE_LEMMA, None, CertState.CHECKED, CertTier.REPLAY,
         EvidenceAction.REJECT_CANDIDATE),
        (QueryKind.FALSIFY_INIT, Status.SAT, ModelApprox.OVER, True,
         TargetScope.THEOREM_TARGET, None, CertState.CHECKED, CertTier.REPLAY,
         EvidenceAction.PARK),
        (QueryKind.FALSIFY_INIT, Status.UNSAT, ModelApprox.EXACT, True,
         TargetScope.THEOREM_TARGET, None, CertState.CHECKED, CertTier.T3,
         EvidenceAction.FORWARD),  # never prune
        # IND_STEP
        (QueryKind.IND_STEP, Status.UNSAT, ModelApprox.EXACT, True,
         TargetScope.THEOREM_TARGET, None, CertState.CHECKED, CertTier.T3,
         EvidenceAction.PROVE_STEP),
        (QueryKind.IND_STEP, Status.UNSAT, ModelApprox.EXACT, True,
         TargetScope.THEOREM_TARGET, None, CertState.UNCHECKED, CertTier.T3,
         EvidenceAction.PARK),
        (QueryKind.IND_STEP, Status.SAT, ModelApprox.EXACT, True,
         TargetScope.THEOREM_TARGET, False, CertState.CHECKED, CertTier.T3,
         EvidenceAction.FORWARD),
        (QueryKind.IND_STEP, Status.SAT, ModelApprox.EXACT, True,
         TargetScope.THEOREM_TARGET, True, CertState.CHECKED, CertTier.REPLAY,
         EvidenceAction.REPORT_CEX),
        (QueryKind.IND_STEP, Status.SAT, ModelApprox.EXACT, True,
         TargetScope.CANDIDATE_LEMMA, True, CertState.CHECKED, CertTier.REPLAY,
         EvidenceAction.REJECT_CANDIDATE),
        (QueryKind.IND_STEP, Status.SAT, ModelApprox.EXACT, True,
         TargetScope.THEOREM_TARGET, None, CertState.CHECKED, CertTier.T3,
         EvidenceAction.PARK),
        # BASE_ENTAIL
        (QueryKind.BASE_ENTAIL, Status.UNSAT, ModelApprox.EXACT, True,
         TargetScope.THEOREM_TARGET, None, CertState.CHECKED, CertTier.T3,
         EvidenceAction.PROVE_BASE),
        (QueryKind.BASE_ENTAIL, Status.UNSAT, ModelApprox.EXACT, True,
         TargetScope.THEOREM_TARGET, None, CertState.UNCHECKED, CertTier.T3,
         EvidenceAction.PARK),
        (QueryKind.BASE_ENTAIL, Status.SAT, ModelApprox.EXACT, True,
         TargetScope.THEOREM_TARGET, None, CertState.CHECKED, CertTier.REPLAY,
         EvidenceAction.REJECT_CANDIDATE),
        (QueryKind.BASE_ENTAIL, Status.SAT, ModelApprox.OVER, True,
         TargetScope.THEOREM_TARGET, None, CertState.CHECKED, CertTier.REPLAY,
         EvidenceAction.PARK),
    ]
    for (kind, status, approx, pred_exact, scope, cti, cstate, ctier, expected) in cases:
        got = evidence_action(kind, status, approx, pred_exact, scope, cti, cstate, ctier)
        assert got is expected, (kind, status, got, expected)


def test_cross_cutting_guards():
    """FAILED -> FORWARD, UNKNOWN -> FORWARD, ERROR -> DISABLE_CLASS."""
    for kind in QueryKind:
        for status in (Status.SAT, Status.UNSAT):
            r = evidence_action(kind, status, ModelApprox.EXACT, True,
                                TargetScope.THEOREM_TARGET, None,
                                CertState.FAILED, CertTier.T3)
            assert r is EvidenceAction.FORWARD
        r = evidence_action(kind, Status.UNKNOWN, ModelApprox.EXACT, True,
                            TargetScope.THEOREM_TARGET, None,
                            CertState.CHECKED, CertTier.T3)
        assert r is EvidenceAction.FORWARD
        r = evidence_action(kind, Status.ERROR, ModelApprox.EXACT, True,
                            TargetScope.THEOREM_TARGET, None,
                            CertState.CHECKED, CertTier.T3)
        assert r is EvidenceAction.DISABLE_CLASS


def test_total_and_no_default_hard_action():
    """Total over all inputs, and the fall-through is never hard."""
    kinds = list(QueryKind)
    statuses = list(Status)
    approxes = list(ModelApprox)
    scopes = list(TargetScope)
    ctis = [None, True, False]
    cstates = list(CertState)
    ctiers = list(CertTier)
    n = 0
    for args in itertools.product(kinds, statuses, approxes, [True, False],
                                  scopes, ctis, cstates, ctiers):
        r = evidence_action(*args)
        assert isinstance(r, EvidenceAction)
        n += 1
    assert n == 4 * 4 * 3 * 2 * 2 * 3 * 3 * 5


def test_hard_actions_require_checking():
    """No hard action is emitted unless cert_state == CHECKED at a non-T0 tier."""
    for kind in QueryKind:
        for status in (Status.SAT, Status.UNSAT):
            for approx in ModelApprox:
                for scope in TargetScope:
                    for cti in (None, True, False):
                        r = evidence_action(kind, status, approx, True, scope, cti,
                                            CertState.UNCHECKED, CertTier.T3)
                        assert not is_hard(r), (kind, status, r)
