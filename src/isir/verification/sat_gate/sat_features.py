# src/isir/verification/sat_gate/sat_features.py
#
# SAT-derived scoring features. The keyword `trace_alignment` score
# in the PERF scorer is replaced by evidence from the gate: a lemma hint, a
# reachable CTI, an UNSAT/cert-reuse cache hit. These are ranking-only signals.

from typing import List
from isir.verification.sat_gate.ranker import ObligationFeatures


def gate_evidence_score(features: ObligationFeatures) -> float:
    """The SAT-derived replacement for the keyword ``trace_alignment`` score."""
    if features.lemma_hint_generated:
        return 1.0
    if features.cti_reachable == "reachable":
        return 0.8
    if features.unsat_hit:
        return 0.6
    if features.dedup_hit:
        return 0.4
    return 0.0


def sat_features_vector(features: ObligationFeatures) -> List[float]:
    """A fixed-order SAT-derived feature vector for the PERF scorer."""
    return [
        gate_evidence_score(features),
        float(features.failed_group_count),
        float(features.minimized_core_size),
        1.0 if features.cert_reuse else 0.0,
        1.0 if features.hint_acceptance else 0.0,
    ]


def promote_ranker(ranker, held_out_improvement: float,
                   threshold: float = 0.0) -> bool:
    """Promote a shadow ranker to active only on the held-out improvement.

    Returns True iff the ranker was activated; ranking only, never a hard action.
    """
    if held_out_improvement > threshold:
        ranker.activate()
        return True
    return False
