# src/isir/verification/cowork.py
#
# koika_acl2 co-work backend: run the Koika (Coq) and ACL2 provers on the same
# hard sub-goal concurrently.  First-wins; the proved auxiliary lemmas are
# shared back into the other side; if both fail, their progress (sub-goals,
# tactics, checkpoints) is merged for LLM reflection / retry.

from concurrent.futures import ThreadPoolExecutor, TimeoutError, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
from isir.utils.logger import get_logger
from isir.verification.proof.proof import ProofResult

logger = get_logger(__name__)


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


def build_reflection_prompt(cw: "CoWorkResult") -> str:
    """Build the cross-backend reflection prompt from a double-failure.

    When both Koika and ACL2 fail on the same sub-goal, the merged failure info
    pinpoints the common sub-goal and its root cause.  The prompt asks the LLM
    for ONE targeted fix (a helper lemma, induction hint, or tactic).
    """
    koika_err = cw.metadata.get("koika_error", "")
    acl2_err = cw.metadata.get("acl2_error", "")
    return (
        "Two proof assistants (Koika/Coq and ACL2) both failed to prove the same "
        "sub-goal.\n\n"
        f"Koika (Coq) failed with:\n{koika_err}\n\n"
        f"ACL2 failed with:\n{acl2_err}\n\n"
        "Analyze BOTH failures to identify the common failing sub-goal and its root "
        "cause (e.g. non-linear arithmetic, recursive induction, bit-level reasoning). "
        "Then output a COMPLETE Coq proof script that proves the goal. If a helper "
        "lemma is needed, declare it first (`Lemma <name> : <stmt>. Proof. ... Qed.`), "
        "then give the main proof (`Proof. ... Qed.`). Output ONLY the Coq code — no "
        "prose, no markdown fences."
    )


def reflect_on_failure(cw: "CoWorkResult", llm) -> Optional[str]:
    """Ask the LLM for a targeted repair when both backends failed.

    Returns the LLM's suggested fix, or None if the reflection is unavailable.
    """
    if cw.success:
        return None
    try:
        return llm.generate(build_reflection_prompt(cw))
    except Exception as e:  # noqa: BLE001
        logger.warning("Cross-backend reflection failed: %s", e)
        return None


def cowork_retry(cw: "CoWorkResult", llm,
                retry_fn: Callable[[str], "ProofResult"]) -> Optional["ProofResult"]:
    """Complete the cross-backend loop on a double-failure.

    Reflect (ask the LLM for a targeted Coq proof script), re-dispatch the
    script via `retry_fn` (which should re-prove using it as `initial_script`),
    and return the successful ProofResult, or None.
    """
    if cw.success:
        return None
    script = reflect_on_failure(cw, llm)
    if not script:
        return None
    result = retry_fn(script)
    if result.success:
        result.metadata["cowork_reflection_proved"] = True
        return result
    return None


def run_cowork(koika_fn: Callable[[], ProofResult],
               acl2_fn: Callable[[], ProofResult],
               timeout: Optional[float] = None) -> CoWorkResult:
    """Run both provers concurrently; return on the FIRST success.

    The original implementation blocked on *both* futures, so a slow (or
    hanging) loser stalled the whole obligation even after the winner had
    already proved it.  This version returns as soon as one side succeeds and
    does not await the loser (its thread runs to completion in the background
    but is never blocked on).
    """
    pool = ThreadPoolExecutor(max_workers=2)
    fut_koika = pool.submit(koika_fn)
    fut_acl2 = pool.submit(acl2_fn)
    futures = {fut_koika: "koika", fut_acl2: "acl2"}
    results: Dict[str, ProofResult] = {}
    try:
        for fut in as_completed(futures, timeout=timeout):
            name = futures[fut]
            try:
                results[name] = fut.result()
            except Exception as e:  # noqa: BLE001
                results[name] = ProofResult(success=False, error_message=str(e), backend=name)
            if results[name].success:
                break  # first-wins
    except TimeoutError:
        pass  # neither finished in time; treat as both-failed below
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

    for fut, name in futures.items():
        if name not in results:
            results[name] = ProofResult(
                success=False,
                error_message="co-work abandoned (other side won / timeout)",
                backend=name,
            )
    return merge_cowork(results["koika"], results["acl2"])
