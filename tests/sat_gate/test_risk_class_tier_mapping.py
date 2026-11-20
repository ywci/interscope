# tests/sat_gate/test_risk_class_tier_mapping.py
"""Risk class ↔ certification tier mapping (§5)."""

from isir.verification.sat_gate.certificate import (
    RiskClass, min_tier_for, risk_class_of,
)
from isir.verification.sat_gate.policy import CertTier, EvidenceAction


def test_soundness_critical_actions_map_to_t3_or_replay():
    for a in (EvidenceAction.CLOSE_VACUOUS, EvidenceAction.PROVE_BASE,
              EvidenceAction.PROVE_STEP):
        assert risk_class_of(a) is RiskClass.SOUNDNESS_CRITICAL
        assert min_tier_for(a) is CertTier.T3
    assert risk_class_of(EvidenceAction.REPORT_CEX) is RiskClass.SOUNDNESS_CRITICAL
    assert min_tier_for(EvidenceAction.REPORT_CEX) is CertTier.REPLAY


def test_completeness_critical_action_is_t1():
    assert risk_class_of(EvidenceAction.REJECT_CANDIDATE) is RiskClass.COMPLETENESS_CRITICAL
    assert min_tier_for(EvidenceAction.REJECT_CANDIDATE) is CertTier.T1


def test_soft_actions_are_t0():
    for a in (EvidenceAction.PARK, EvidenceAction.FORWARD, EvidenceAction.DISABLE_CLASS):
        assert risk_class_of(a) is RiskClass.SOFT
        assert min_tier_for(a) is CertTier.T0
