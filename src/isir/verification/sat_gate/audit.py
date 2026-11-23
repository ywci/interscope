# src/isir/verification/sat_gate/audit.py
#
# Content-addressed audit store + run manifest. Every certificate,
# formula, proof, model, replay result (incl. composed replay), and lemma hint is
# stored content-addressed and indexed so a later encoder bug can invalidate
# exactly the affected results.

import hashlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class RunManifest:
    """Run-level configuration record ."""
    cert_audit_rate: float = 0.0
    cert_ramp_n: int = 0
    max_ctg_depth: int = 0
    lemma_hints_enabled: bool = False
    memory_map_threshold_bits: int = 0
    disable_reprobe_interval_steps: int = 0
    tool_versions: Dict[str, str] = field(default_factory=dict)
    seeds: List[int] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cert_audit_rate": self.cert_audit_rate,
            "cert_ramp_n": self.cert_ramp_n,
            "max_ctg_depth": self.max_ctg_depth,
            "lemma_hints_enabled": self.lemma_hints_enabled,
            "memory_map_threshold_bits": self.memory_map_threshold_bits,
            "disable_reprobe_interval_steps": self.disable_reprobe_interval_steps,
            "tool_versions": dict(self.tool_versions),
            "seeds": list(self.seeds),
        }


def content_hash(record: Any) -> str:
    """A stable SHA-256 content hash over the repr of a record."""
    return hashlib.sha256(repr(record).encode("utf-8")).hexdigest()


class AuditStore:
    """Content-addressed store with the  indexes."""

    def __init__(self) -> None:
        self._records: Dict[str, Any] = {}
        self._by_obligation: Dict[str, List[str]] = {}
        self._by_theorem: Dict[str, List[str]] = {}
        self._by_epoch: Dict[str, List[str]] = {}
        self._by_hint: Dict[str, str] = {}
        self.manifest = RunManifest()

    def put(self, record: Any, obligation_id: Optional[str] = None,
            theorem_id: Optional[str] = None, epoch_hash: Optional[str] = None,
            hint_id: Optional[str] = None) -> str:
        """Store a record and return its content hash."""
        h = content_hash(record)
        self._records[h] = record
        if obligation_id:
            self._by_obligation.setdefault(obligation_id, []).append(h)
        if theorem_id:
            self._by_theorem.setdefault(theorem_id, []).append(h)
        if epoch_hash:
            self._by_epoch.setdefault(epoch_hash, []).append(h)
        if hint_id:
            self._by_hint[hint_id] = h
        return h

    def get(self, h: str) -> Any:
        return self._records.get(h)

    def for_obligation(self, oid: str) -> List[str]:
        return list(self._by_obligation.get(oid, []))

    def for_theorem(self, tid: str) -> List[str]:
        return list(self._by_theorem.get(tid, []))

    def for_epoch(self, epoch: str) -> List[str]:
        return list(self._by_epoch.get(epoch, []))

    def provenance(self, hint_id: str) -> Optional[str]:
        return self._by_hint.get(hint_id)

    def invalidate_epoch(self, epoch_hash: str) -> int:
        """Drop every record for an epoch; return the number removed."""
        hashes = self._by_epoch.pop(epoch_hash, [])
        for h in hashes:
            self._records.pop(h, None)
        return len(hashes)
