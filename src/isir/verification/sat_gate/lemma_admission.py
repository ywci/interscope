# src/isir/verification/sat_gate/lemma_admission.py
#
# Lemma Addition Policy. A lemma hint is a soft output; it becomes a
# permanent fact only with BOTH an ITP proof AND T3 encoding-correspondence
# evidence, exact translation, dual-encoder agreement, and shared-library tests.

from dataclasses import dataclass
from typing import List, Tuple


@dataclass(frozen=True)
class AdmissionEvidence:
    itp_proved: bool = False
    t3_certified: bool = False
    exact_translation: bool = False
    dual_encoder_agreement: bool = False
    shared_library_tests: bool = False


class LemmaAdmissionPolicy:
    """Rate-limited permanent-admission gate ."""

    def __init__(self, max_lemmas_per_epoch: int) -> None:
        self.max_lemmas_per_epoch = max_lemmas_per_epoch
        self.epoch = 0
        self.admitted_this_epoch = 0
        self.log: List[Tuple[str, int]] = []  # (hint_id, epoch)

    def admit(self, hint_id: str, evidence: AdmissionEvidence) -> bool:
        """Return True iff the hint may become a permanent fact this epoch.

        Requires the ITP proof, T3 cert, exact translation, dual-encoder
        agreement, and shared-library tests; rate-limited.
        """
        if not (evidence.itp_proved and evidence.t3_certified
                and evidence.exact_translation
                and evidence.dual_encoder_agreement
                and evidence.shared_library_tests):
            return False
        if self.admitted_this_epoch >= self.max_lemmas_per_epoch:
            return False
        self.admitted_this_epoch += 1
        self.log.append((hint_id, self.epoch))
        return True

    def bump_epoch(self) -> None:
        """A permanent addition bumps the epoch; the rate limit resets."""
        self.epoch += 1
        self.admitted_this_epoch = 0
