# src/isir/verification/cowork.py
#
# koika_acl2 co-work backend: run the Koika (Coq) and ACL2 provers on the same
# hard sub-goal concurrently.  First-wins; the proved auxiliary lemmas are
# shared back into the other side; if both fail, their progress (sub-goals,
# tactics, checkpoints) is merged for LLM reflection / retry.

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from isir.verification.proof.proof import ProofResult


@dataclass
class CoWorkResult:
    success: bool
    winner: Optional[str] = None        # "koika" | "acl2" | None (both failed)
    proof_script: str = ""
    auxiliary_lemmas: List[str] = field(default_factory=list)   # shared lemmas
    metadata: Dict[str, Any] = field(default_factory=dict)       # merged progress
    error_message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "winner": self.winner,
            "proof_script": self.proof_script,
            "auxiliary_lemmas": self.auxiliary_lemmas,
            "metadata": self.metadata,
            "error_message": self.error_message,
        }


def merge_cowork(koika: ProofResult, acl2: ProofResult) -> CoWorkResult:
    """Merge two ProofResults.

    - either PASS  -> that backend wins; the other's auxiliary lemmas are shared
                      in so the winner's proof can use them on retry;
    - both FAIL   -> merge both `metadata`/`error_message` for reflection.
    """
    shared = list(koika.auxiliary_lemmas or []) + list(acl2.auxiliary_lemmas or [])
    if koika.success:
        return CoWorkResult(
            success=True, winner="koika",
            proof_script=koika.proof_script or "",
            auxiliary_lemmas=shared,
            metadata={"koika": koika.metadata, "acl2": acl2.metadata},
        )
    if acl2.success:
        return CoWorkResult(
            success=True, winner="acl2",
            proof_script=acl2.proof_script or "",
            auxiliary_lemmas=shared,
            metadata={"koika": koika.metadata, "acl2": acl2.metadata},
        )
    return CoWorkResult(
        success=False, winner=None,
        metadata={
            "koika": koika.metadata,
            "acl2": acl2.metadata,
            "koika_error": koika.error_message,
            "acl2_error": acl2.error_message,
        },
        error_message=(
            f"koika: {koika.error_message or 'unknown'}; "
            f"acl2: {acl2.error_message or 'unknown'}"
        ),
    )


def run_cowork(koika_fn: Callable[[], ProofResult],
               acl2_fn: Callable[[], ProofResult]) -> CoWorkResult:
    """Run both prove callables concurrently and merge (first-wins)."""
    with ThreadPoolExecutor(max_workers=2) as pool:
        fut_koika = pool.submit(koika_fn)
        fut_acl2 = pool.submit(acl2_fn)
        koika = fut_koika.result()
        acl2 = fut_acl2.result()
    return merge_cowork(koika, acl2)
