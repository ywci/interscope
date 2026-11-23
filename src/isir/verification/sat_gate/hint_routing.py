# src/isir/verification/sat_gate/hint_routing.py
#
# Hint routing: harvested lemma candidates flow through the hint pool
# (offer/accept/reject/used-in-proof) and, on ITP acceptance, through the
# admission policy before any permanent-database effect.

from typing import List, Optional
from isir.verification.sat_gate.hint_pool import HintPool
from isir.verification.sat_gate.lemma_admission import (
    AdmissionEvidence, LemmaAdmissionPolicy,
)
from isir.verification.sat_gate.lemma_hint import HintProvenance, LemmaHint
from isir.verification.sat_gate.boosters import harvest_seed_candidates


class HintRouter:
    """Orchestrates the ITP-facing hint lifecycle."""

    def __init__(self, pool: Optional[HintPool] = None,
                 admission: Optional[LemmaAdmissionPolicy] = None) -> None:
        self.pool = pool or HintPool(ttl_steps=100)
        self.admission = admission or LemmaAdmissionPolicy(max_lemmas_per_epoch=100)

    def harvest_and_offer(self, clauses: List[str], source_obligation_id: str,
                          provenance: HintProvenance,
                          current_step: int,
                          suggested_strategy: Optional[str] = None) -> List[LemmaHint]:
        """Harvest already-proved/mined clauses + offer them as soft seeds."""
        hints = harvest_seed_candidates(clauses, source_obligation_id, provenance)
        for h in hints:
            if suggested_strategy is not None:
                h.suggested_strategy = suggested_strategy
            self.pool.offer(h, current_step)
        return hints

    def accept(self, hint_id: str) -> bool:
        """The ITP accepts a soft hint."""
        return self.pool.accept(hint_id)

    def admit(self, hint_id: str, evidence: AdmissionEvidence) -> bool:
        """The permanent admission (requires acceptance + full evidence)."""
        if self.pool.state_of(hint_id) != "accepted":
            return False
        return self.admission.admit(hint_id, evidence)

    def reject(self, hint_id: str) -> bool:
        return self.pool.reject(hint_id)

    def mark_used(self, hint_id: str) -> bool:
        """Record that an accepted hint reached the final proof."""
        return self.pool.mark_used(hint_id)

    def accepted_count(self) -> int:
        return self.admission.admitted_this_epoch
