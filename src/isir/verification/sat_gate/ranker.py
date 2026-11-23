# src/isir/verification/sat_gate/ranker.py
#
# Learned ranker: a calibrated predictor P(obligation closes | features).
# Shadow-first protocol: off-policy logging, rule-based fallback, ranking only.
# The ranker MUST NOT construct hard actions (architectural invariant).

from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class ObligationFeatures:
    """Feature vector for P(obligation closes | features) (table)."""
    status: str = "unknown"
    kind: str = "IND_STEP"
    anchor: str = "free"
    model_approx: str = "EXACT"
    bound_k: int = 1
    unknown_reason: str = ""
    failed_group_count: int = 0
    minimized_core_size: int = 0
    cti_reachable: str = ""
    lemma_hint_generated: bool = False
    term_nodes: int = 0
    total_width: int = 0
    depth: int = 0
    retry_count: int = 0
    park_count: int = 0
    dedup_hit: bool = False
    unsat_hit: bool = False
    sat_hit: bool = False
    cert_reuse: bool = False
    hint_acceptance: bool = False

    def vector(self) -> List[float]:
        """Fixed-order numeric feature vector."""
        return [
            float(self.bound_k),
            float(self.failed_group_count),
            float(self.minimized_core_size),
            1.0 if self.lemma_hint_generated else 0.0,
            float(self.term_nodes),
            float(self.total_width),
            float(self.depth),
            float(self.retry_count),
            float(self.park_count),
            1.0 if self.dedup_hit else 0.0,
            1.0 if self.unsat_hit else 0.0,
            1.0 if self.sat_hit else 0.0,
            1.0 if self.cert_reuse else 0.0,
            1.0 if self.hint_acceptance else 0.0,
        ]


def rule_based_score(features: ObligationFeatures) -> float:
    """Conservative rule-based fallback : higher = more likely to close.

    Deterministic and side-effect-free; used while the ranker is in shadow mode.
    """
    score = 0.0
    if features.lemma_hint_generated:
        score += 1.0
    if features.unsat_hit:
        score += 0.5
    if features.dedup_hit:
        score += 0.2
    score -= 0.1 * features.park_count
    score -= 0.05 * features.retry_count
    return score


class ShadowRanker:
    """Shadow-first ranker : logs off-policy, ranks rule-based until
    activated.  Ranking only — it never emits a hard action."""

    def __init__(self) -> None:
        self.active = False
        self.log: List[Tuple[List[float], bool]] = []

    def score(self, features: ObligationFeatures) -> float:
        return rule_based_score(features)

    def rank(self, items) -> List:
        """Order by score descending; deterministic and side-effect-free."""
        return sorted(items, key=lambda f: self.score(f), reverse=True)

    def observe(self, features: ObligationFeatures, closed: bool) -> None:
        """Off-policy logging: record (feature vector, outcome)."""
        self.log.append((features.vector(), bool(closed)))

    def activate(self) -> None:
        """Promote the shadow to active (the learned coefficients land here)."""
        self.active = True
