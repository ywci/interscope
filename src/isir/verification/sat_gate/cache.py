# src/isir/verification/sat_gate/cache.py
#
# Caching. The cache is certification avoidance, not only solver
# avoidance: a hit on a CHECKED certificate reuses it at ~0 marginal cost.

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class CacheKey:
    """Cache key.  Not keyed by lifted symbol sets; cross-kind transfer
    is forbidden; model_approx and predicate_exact are part of the key."""
    epoch_hash: str
    query_kind: str
    anchor: str
    bound_k: int
    abstraction_mode: str
    model_approx: str
    predicate_exact: bool


class CertCache:
    """Certification reuse : flag-matched reuse of CHECKED certificates.

    Reuse REQUIRES model_approx and predicate_exact agreement; a mismatch is
    rejected and counted, never silently reused.
    """

    def __init__(self) -> None:
        self._certs: Dict[CacheKey, Tuple[str, bool, Any]] = {}
        self.reuse_count = 0
        self.flag_mismatch_rejects = 0

    def put(self, key: CacheKey, model_approx: str, predicate_exact: bool,
            certificate: Any) -> None:
        self._certs[key] = (model_approx, predicate_exact, certificate)

    def reuse(self, key: CacheKey, model_approx: str, predicate_exact: bool) -> Any:
        entry = self._certs.get(key)
        if entry is None:
            return None
        if entry[0] != model_approx or entry[1] != predicate_exact:
            self.flag_mismatch_rejects += 1
            return None
        self.reuse_count += 1
        return entry[2]


class SatCache:
    """FALSIFY_INIT SAT cache : Init-anchored, SAT-at-k ⇒ SAT-at-k'>=k.

    Per (epoch_hash, target_group), store (k, model_ref, replay_ref, cert_ref).
    A call at k' answers from the entry with the maximal stored k <= k'.
    """

    def __init__(self, max_entries: int = 64) -> None:
        self._entries: Dict[Tuple[str, str], List[Tuple[int, Any, Any, Any]]] = {}
        self.max_entries = max_entries
        self.hit_count = 0

    def put(self, epoch_hash: str, target_group: str, k: int,
            model_ref: Any, replay_ref: Any, cert_ref: Any) -> None:
        key = (epoch_hash, target_group)
        self._entries.setdefault(key, []).append((k, model_ref, replay_ref, cert_ref))

    def lookup(self, epoch_hash: str, target_group: str, k_prime: int):
        key = (epoch_hash, target_group)
        entries = self._entries.get(key, [])
        candidates = [e for e in entries if e[0] <= k_prime]
        if not candidates:
            return None
        self.hit_count += 1
        return max(candidates, key=lambda e: e[0])


class SubsumptionCache:
    """UNSAT core subsumption.

    A stored core ``C`` subsumes a candidate ``A`` iff ``C ⊆ A``: the candidate
    carries a superset of the assumptions, so ``F ∧ C`` UNSAT ⇒ ``F ∧ A`` UNSAT
    (monotone because assumptions only add constraints).
    """

    def __init__(self, max_entries: int = 256) -> None:
        self._cores: List[frozenset] = []
        self.max_entries = max_entries
        self.hit_count = 0
        self.filter_count = 0

    def put(self, core) -> None:
        self._cores.append(frozenset(core))
        if len(self._cores) > self.max_entries:
            self._cores.pop(0)  # LRU evict

    def is_subsumed(self, candidate) -> bool:
        """True iff any stored core is a subset of the candidate."""
        c = frozenset(candidate)
        for core in self._cores:
            self.filter_count += 1
            if core <= c:
                self.hit_count += 1
                return True
        return False


class LemmaHintCache:
    """Lemma-hint cache per epoch : TTL-expiring, epoch-invalidated."""

    def __init__(self, ttl_steps: int) -> None:
        self.ttl_steps = ttl_steps
        self._hints: Dict[Tuple[str, str, str], Dict[str, Any]] = {}

    def put(self, epoch_hash: str, source_obligation_id: str, cube_hash: str,
            hint: Any, current_step: int) -> None:
        key = (epoch_hash, source_obligation_id, cube_hash)
        self._hints[key] = {"hint": hint, "expires_step": current_step + self.ttl_steps}

    def get(self, epoch_hash: str, source_obligation_id: str, cube_hash: str,
            current_step: int) -> Any:
        key = (epoch_hash, source_obligation_id, cube_hash)
        entry = self._hints.get(key)
        if entry is None:
            return None
        if current_step > entry["expires_step"]:
            del self._hints[key]
            return None
        return entry["hint"]

    def invalidate_epoch(self, epoch_hash: str) -> int:
        dead = [k for k in self._hints if k[0] == epoch_hash]
        for k in dead:
            del self._hints[k]
        return len(dead)
