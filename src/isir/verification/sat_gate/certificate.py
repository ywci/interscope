# src/isir/verification/sat_gate/certificate.py
#
# Risk class ↔ certification tier mapping and the certificate record.

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List
from isir.verification.sat_gate.policy import CertState, CertTier, EvidenceAction


class RiskClass(Enum):
    SOUNDNESS_CRITICAL = "soundness_critical"
    COMPLETENESS_CRITICAL = "completeness_critical"
    SOFT = "soft"


def risk_class_of(action: EvidenceAction) -> RiskClass:
    """Map an evidence action to its risk class ."""
    if action in (EvidenceAction.CLOSE_VACUOUS, EvidenceAction.PROVE_BASE,
                  EvidenceAction.PROVE_STEP, EvidenceAction.REPORT_CEX):
        return RiskClass.SOUNDNESS_CRITICAL
    if action in (EvidenceAction.REJECT_CANDIDATE, EvidenceAction.DISABLE_CLASS):
        return RiskClass.COMPLETENESS_CRITICAL
    return RiskClass.SOFT


def min_tier_for(action: EvidenceAction) -> CertTier:
    """Minimum certification tier an action may be authorized at ."""
    if action in (EvidenceAction.REPORT_CEX, EvidenceAction.REJECT_CANDIDATE):
        return CertTier.REPLAY
    if action in (EvidenceAction.CLOSE_VACUOUS, EvidenceAction.PROVE_BASE,
                  EvidenceAction.PROVE_STEP):
        return CertTier.T3
    if action is EvidenceAction.DISABLE_CLASS:
        return CertTier.T1
    return CertTier.T0


def verify_t3(formula: List[List[int]], assumptions: List[int],
              proof_lines: List[str]) -> bool:
    """Check a DRAT UNSAT proof against ``formula`` plus the assumption literals
    as unit clauses.

    The gotcha the plan calls out: checking against ``formula`` alone fails
    when the refutation used assumptions; the checker MUST receive the
    assumption literals as units.
    """
    from isir.verification.sat_gate.drat import check_drat

    checking = [list(c) for c in formula] + [[a] for a in assumptions]
    return check_drat(checking, proof_lines)


@dataclass
class Certificate:
    """Certificate record."""
    certificate_id: str
    epoch_hash: str
    query_kind: str
    target_scope: str
    risk_class: RiskClass
    cert_tier: CertTier
    cert_state: CertState
    model_approx: str
    predicate_exact: bool
    encoder_version: str = "0"
    f_exact_version: str = "0"
    solver_name: str = ""
    solver_version: str = ""
    oracle_solver_name: str = ""
    oracle_solver_version: str = ""
    seed: int = 0
    anchor: str = ""
    bound_k: int = 0
    abstraction_mode: str = ""
    assumption_group_ids: List[str] = field(default_factory=list)
    activation_literals: List[int] = field(default_factory=list)
    formula_ref: str = ""
    proof_ref: str = ""
    core_groups: List[str] = field(default_factory=list)
    model_ref: str = ""
    replay_ref: str = ""
    obligations_affected: List[str] = field(default_factory=list)
    theorem_ids_affected: List[str] = field(default_factory=list)
    timestamp: str = ""

    def to_dict(self) -> Dict[str, object]:
        return {
            "certificate_id": self.certificate_id,
            "epoch_hash": self.epoch_hash,
            "query_kind": self.query_kind,
            "target_scope": self.target_scope,
            "risk_class": self.risk_class.value,
            "cert_tier": self.cert_tier.value,
            "cert_state": self.cert_state.value,
            "model_approx": self.model_approx,
            "predicate_exact": self.predicate_exact,
            "encoder_version": self.encoder_version,
            "f_exact_version": self.f_exact_version,
            "solver_name": self.solver_name,
            "solver_version": self.solver_version,
            "oracle_solver_name": self.oracle_solver_name,
            "oracle_solver_version": self.oracle_solver_version,
            "seed": self.seed,
            "anchor": self.anchor,
            "bound_k": self.bound_k,
            "abstraction_mode": self.abstraction_mode,
            "assumption_group_ids": list(self.assumption_group_ids),
            "activation_literals": list(self.activation_literals),
            "formula_ref": self.formula_ref,
            "proof_ref": self.proof_ref,
            "core_groups": list(self.core_groups),
            "model_ref": self.model_ref,
            "replay_ref": self.replay_ref,
            "obligations_affected": list(self.obligations_affected),
            "theorem_ids_affected": list(self.theorem_ids_affected),
            "timestamp": self.timestamp,
        }
