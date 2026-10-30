# tests/unit/test_annotation.py
#
# Offline annotation (Section 8): pending -> verified in five ordered steps.

from isir.dialects.evolving_spec import (
    ErrorClass, EvolvingItem, EvolvingSpec, IssueAttribution, VerificationMode,
    GenerationAction, RawEvidenceRecord, EvidenceSource, ProofStatus,
)
from isir.lowering.annotation import annotate, record_to_finding


def _record(ref, primary, mode, error_class, related=(), counterexample=None, source_map=None):
    return RawEvidenceRecord(
        evidence_ref=ref, primary_spec_item_id=primary, verification_mode=mode,
        evidence_source=EvidenceSource.SIMULATION, proof_status=ProofStatus.DISPROVED,
        error_class=error_class, related_spec_item_ids=list(related),
        counterexample=counterexample, source_mapping_ref=source_map, evidence_hash=f"h:{ref}",
    )


class TestRecordToFinding:
    def test_counterexample_rtl_conformance(self):
        f = record_to_finding(_record("e1", "rule_write", VerificationMode.RTL_CONFORMANCE,
                                      ErrorClass.COUNTEREXAMPLE, counterexample="full=1", source_map="fifo.v:42"))
        assert f.issue_attribution is IssueAttribution.RTL_IMPLEMENTATION_ERROR
        assert f.generation_action is GenerationAction.REPAIR_RTL
        assert f.rtl_anchor == "fifo.v:42"
        assert f.evidence_note == "cex: full=1"

    def test_placeholder_symbol_read(self):
        f = record_to_finding(_record("e2", "r", VerificationMode.SELF_CONSISTENCY,
                                      ErrorClass.PLACEHOLDER_SYMBOL_READ))
        assert f.issue_attribution is IssueAttribution.UNRESOLVED_PLACEHOLDER
        assert f.generation_action is GenerationAction.STAGED_GENERATION


class TestAnnotate:
    def test_pending_to_verified(self):
        ev = EvolvingSpec("fifo", items=[EvolvingItem("rule_write")])
        evd = [_record("e1", "rule_write", VerificationMode.RTL_CONFORMANCE,
                       ErrorClass.COUNTEREXAMPLE, counterexample="full=1", source_map="fifo.v:42")]
        verified, pinned = annotate(ev, evd, round_num=1)
        item = verified.item("rule_write")
        assert item.verification_status.value == "verified"
        assert item.verification_round == 1
        assert len(item.findings) == 1
        assert item.findings[0].issue_attribution is IssueAttribution.RTL_IMPLEMENTATION_ERROR
        assert pinned == {"e1"}

    def test_deferred_item_gets_synthetic_finding(self):
        ev = EvolvingSpec("fifo", items=[EvolvingItem("rule_arbitrate", defer_verification=True)])
        verified, pinned = annotate(ev, [], round_num=1)
        item = verified.item("rule_arbitrate")
        assert item.findings[0].error_class is ErrorClass.DEFERRED_PLACEHOLDER
        assert item.findings[0].generation_action is GenerationAction.STAGED_GENERATION
        assert pinned == set()  # static_defer is not pinned

    def test_back_indexing(self):
        ev = EvolvingSpec("fifo", items=[EvolvingItem("rule_write"), EvolvingItem("rule_update_flags")])
        evd = [_record("e1", "rule_write", VerificationMode.RTL_CONFORMANCE,
                       ErrorClass.COUNTEREXAMPLE, related=["rule_update_flags"],
                       counterexample="full=1", source_map="fifo.v:42")]
        verified, _ = annotate(ev, evd, round_num=1)
        related = verified.item("rule_update_flags")
        assert any(f.back_indexed_from == "rule_write" for f in related.findings)
        back = next(f for f in related.findings if f.back_indexed_from == "rule_write")
        assert back.evidence_note == "cex: full=1"  # propagated from primary (cross-item)
        assert back.related_spec_item_ids == ["rule_write"]

    def test_cap_at_three_by_priority(self):
        ev = EvolvingSpec("fifo", items=[EvolvingItem("r")])
        evd = [
            _record("e1", "r", VerificationMode.SELF_CONSISTENCY, ErrorClass.MISSING_PREMISE),
            _record("e2", "r", VerificationMode.SELF_CONSISTENCY, ErrorClass.TYPE_ERROR),
            _record("e3", "r", VerificationMode.SELF_CONSISTENCY, ErrorClass.SCHEDULE_CONFLICT),
            _record("e4", "r", VerificationMode.SELF_CONSISTENCY, ErrorClass.PLACEHOLDER_SYMBOL_READ),
        ]
        verified, _ = annotate(ev, evd, round_num=1)
        attrs = {f.issue_attribution for f in verified.item("r").findings}
        assert len(verified.item("r").findings) == 3
        # unresolved_placeholder (rank 1) survives; missing_premise (rank 6) evicted
        assert IssueAttribution.UNRESOLVED_PLACEHOLDER in attrs
        assert IssueAttribution.MISSING_PREMISE not in attrs

    def test_unlocalizable_dropped(self):
        ev = EvolvingSpec("fifo", items=[EvolvingItem("rule_write")])
        evd = [_record("e1", "unknown_item", VerificationMode.SELF_CONSISTENCY, ErrorClass.COUNTEREXAMPLE)]
        verified, pinned = annotate(ev, evd, round_num=1)
        assert verified.item("rule_write").findings == []
        assert pinned == set()
