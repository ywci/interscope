# src/isir/verification/sat_gate/policy.py
#
# Evidence policy (objective-free) and disposition (objective-dependent).
# The split enforces P8: search objective must never influence evidence
# interpretation.  This module MUST NOT import solver/encoder modules (§27.5).
"""Objective-free evidence policy and objective-dependent disposition."""

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from isir.verification.sat_gate.obligation import (
    ModelApprox, QueryKind, TargetScope,
)


class Status(Enum):
    SAT = "sat"
    UNSAT = "unsat"
    UNKNOWN = "unknown"
    ERROR = "error"


class EvidenceAction(Enum):
    CLOSE_VACUOUS = "close_vacuous"
    PROVE_BASE = "prove_base"
    PROVE_STEP = "prove_step"
    REJECT_CANDIDATE = "reject_candidate"
    REPORT_CEX = "report_cex"
    PARK = "park"
    FORWARD = "forward"
    DISABLE_CLASS = "disable_class"


class CertState(Enum):
    UNCHECKED = "unchecked"
    CHECKED = "checked"
    FAILED = "failed"


class CertTier(Enum):
    T0 = "T0"
    T1 = "T1"
    T2 = "T2"
    T3 = "T3"
    REPLAY = "REPLAY"


class Objective(Enum):
    PROOF = "proof"
    BUG_HUNT = "bug_hunt"


# Hard actions are irreversible and soundness/completeness critical; soft
# actions are reversible.  The "no default hard action" invariant is enforced
# by the evidence_action function returning only soft actions on fall-through.
_HARD_ACTIONS = frozenset({
    EvidenceAction.CLOSE_VACUOUS,
    EvidenceAction.PROVE_BASE,
    EvidenceAction.PROVE_STEP,
    EvidenceAction.REJECT_CANDIDATE,
    EvidenceAction.REPORT_CEX,
})


def is_hard(action: EvidenceAction) -> bool:
    return action in _HARD_ACTIONS


def evidence_action(
    kind: QueryKind,
    status: Status,
    model_approx: ModelApprox,
    predicate_exact: bool,
    target_scope: TargetScope,
    cti_reachable: Optional[bool],
    cert_state: CertState,
    cert_tier: CertTier,
) -> EvidenceAction:
    """Objective-free evidence policy (§6.5).

    Total over all inputs; the final fall-through is FORWARD (never hard).
    """
    exact = model_approx is ModelApprox.EXACT
    checked = cert_state is CertState.CHECKED
    replay_checked = cert_tier is CertTier.REPLAY and checked
    t3_checked = cert_tier is CertTier.T3 and checked
    scope_theorem = target_scope is TargetScope.THEOREM_TARGET

    # Cross-cutting guards first (a failed check never authorizes anything hard).
    if cert_state is CertState.FAILED:
        return EvidenceAction.FORWARD  # P0 bug, flagged by the caller
    if status is Status.UNKNOWN:
        return EvidenceAction.FORWARD
    if status is Status.ERROR:
        return EvidenceAction.DISABLE_CLASS

    if kind is QueryKind.VACUITY:
        if status is Status.UNSAT:
            return EvidenceAction.CLOSE_VACUOUS if (predicate_exact and t3_checked) else EvidenceAction.PARK
        return EvidenceAction.FORWARD  # SAT

    if kind is QueryKind.FALSIFY_INIT:
        if status is Status.SAT:
            if exact and predicate_exact and replay_checked:
                return EvidenceAction.REPORT_CEX if scope_theorem else EvidenceAction.REJECT_CANDIDATE
            return EvidenceAction.PARK
        return EvidenceAction.FORWARD  # UNSAT: never prune

    if kind is QueryKind.IND_STEP:
        if status is Status.UNSAT:
            return EvidenceAction.PROVE_STEP if (predicate_exact and t3_checked) else EvidenceAction.PARK
        # SAT: CTI reachability decides.
        if cti_reachable is False:
            return EvidenceAction.FORWARD
        if cti_reachable is True:
            if exact and predicate_exact and replay_checked:
                return EvidenceAction.REPORT_CEX if scope_theorem else EvidenceAction.REJECT_CANDIDATE
            return EvidenceAction.PARK
        return EvidenceAction.PARK  # cti_reachable is None or unchecked

    if kind is QueryKind.BASE_ENTAIL:
        if status is Status.UNSAT:
            return EvidenceAction.PROVE_BASE if (predicate_exact and t3_checked) else EvidenceAction.PARK
        # SAT: reject the candidate only when exact + replay-certified.
        if exact and predicate_exact and replay_checked:
            return EvidenceAction.REJECT_CANDIDATE
        return EvidenceAction.PARK

    return EvidenceAction.FORWARD  # safety net: never hard


@dataclass(frozen=True)
class SearchAction:
    """Objective-dependent search directive (§6.6)."""
    action: EvidenceAction
    terminal: bool
    park_depth: int
    cti_probe_k: int


def disposition(action: EvidenceAction, objective: Objective,
                park_depth: int = 0) -> SearchAction:
    """Map an evidence action to a search action under an objective.

    The objective influences exactly three levers and never the evidence
    interpretation: terminality of REPORT_CEX, park ordering, and CTI probe
    budget (§6.6).
    """
    bug_hunt = objective is Objective.BUG_HUNT

    if action is EvidenceAction.REPORT_CEX:
        # PROOF: failure -> terminate this theorem.  BUG_HUNT: success -> terminate.
        return SearchAction(action=action, terminal=True, park_depth=park_depth,
                            cti_probe_k=4 if bug_hunt else 2)
    if action in (EvidenceAction.CLOSE_VACUOUS, EvidenceAction.PROVE_BASE,
                  EvidenceAction.PROVE_STEP, EvidenceAction.REJECT_CANDIDATE):
        return SearchAction(action=action, terminal=True, park_depth=park_depth,
                            cti_probe_k=4 if bug_hunt else 2)
    if action is EvidenceAction.PARK:
        # BUG_HUNT parks unresolved CTI/abstract SAT shallow (exploration lead);
        # PROOF parks them deep.
        depth = park_depth if bug_hunt else park_depth + 1
        return SearchAction(action=action, terminal=False, park_depth=depth,
                            cti_probe_k=4 if bug_hunt else 2)
    return SearchAction(action=action, terminal=False, park_depth=park_depth,
                        cti_probe_k=4 if bug_hunt else 2)
