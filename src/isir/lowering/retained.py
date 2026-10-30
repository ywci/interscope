# src/isir/lowering/retained.py
#
# Retention machinery (Section 7.5 / 8 / 10): the retention-bounded view over
# the evidence registry — TTL expiry, tombstone records, pinning, and the
# tombstone-hash fallback for cache invalidation.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Set, Tuple

from isir.dialects.evolving_spec import Finding, RawEvidenceRecord
from isir.lowering.filters import apply_pinning


def cache_key(record: RawEvidenceRecord, spec_content_hash: str, filter_rule_version: str) -> tuple:
    """The pipeline cache key (Section 7.5)."""
    return (record.primary_spec_item_id, tuple(record.related_spec_item_ids),
            spec_content_hash, record.evidence_hash, filter_rule_version)


@dataclass
class RetainedView:
    """A retention-bounded view over the evidence registry.

    - `records`    : evidence_ref -> RawEvidenceRecord (the live retained view)
    - `tombstones` : evidence_ref -> evidence_hash (administratively removed records)
    - `created_at` : evidence_ref -> insertion timestamp (for TTL expiry)
    - pinning keeps referenced records alive past TTL; the tombstone-hash
      fallback keeps a cached finding valid when its record is removed but the
      tombstone's `evidence_hash` still matches.
    """
    records: Dict[str, RawEvidenceRecord] = field(default_factory=dict)
    tombstones: Dict[str, str] = field(default_factory=dict)
    created_at: Dict[str, float] = field(default_factory=dict)
    ttl_seconds: float = 3600.0

    def upsert(self, record: RawEvidenceRecord, now: float = 0.0) -> None:
        self.records[record.evidence_ref] = record
        self.created_at[record.evidence_ref] = now

    def pin(self, pinned_refs: Set[str]) -> None:
        apply_pinning(list(self.records.values()), pinned_refs)

    def expire(self, now: float) -> None:
        """TTL-expire unpinned records; write a tombstone for each expired one."""
        for ref, rec in list(self.records.items()):
            if not rec.pinned and (now - self.created_at.get(ref, now)) > self.ttl_seconds:
                self.tombstones[ref] = rec.evidence_hash
                del self.records[ref]

    def tombstone(self, evidence_ref: str, evidence_hash: str) -> None:
        self.tombstones[evidence_ref] = evidence_hash
        self.records.pop(evidence_ref, None)

    def finding_valid(self, finding: Finding) -> bool:
        """Tombstone-hash fallback: a finding is valid if its record is present
        with a matching hash, or a tombstone with the matching hash exists."""
        if finding.evidence_ref == "static_defer":
            return True
        rec = self.records.get(finding.evidence_ref)
        if rec is not None:
            return rec.evidence_hash == finding.evidence_hash
        tomb = self.tombstones.get(finding.evidence_ref)
        return tomb is not None and tomb == finding.evidence_hash
