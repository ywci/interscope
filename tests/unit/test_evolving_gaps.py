# tests/unit/test_evolving_gaps.py
#
# The four gap-closing pieces: Round Reset Rule, RTL Conformance, evidence
# filtering, and pinning.

from isir.dialects.evolving_spec import (
    ErrorClass, EvolvingItem, EvolvingSpec, Finding, GenerationAction,
    IssueAttribution, ProofStatus, RawEvidenceRecord, VerificationMode,
    EvidenceSource, VerificationStatus,
)
from isir.dialects.isir import SpecModule, SpecPropertyOp, SpecRuleOp, SpecStateOp
from isir.lowering.evolving import reset_round
from isir.lowering.filters import (
    apply_pinning, check_grounding, check_non_hallucination, filter_evidence,
)
from isir.lowering.spec_consistency import check_rtl_conformance


def _rec(ref, primary, mode=VerificationMode.SELF_CONSISTENCY,
         ec=ErrorClass.COUNTEREXAMPLE, status=ProofStatus.DISPROVED,
         cex="full=1", subgoal=None, related=()):
    return RawEvidenceRecord(
        evidence_ref=ref, primary_spec_item_id=primary, verification_mode=mode,
        evidence_source=EvidenceSource.SIMULATION, proof_status=status,
        error_class=ec, related_spec_item_ids=list(related),
        counterexample=cex, failing_subgoal=subgoal, evidence_hash=f"h:{ref}",
    )


class TestRoundResetRule:
    def _verified(self):
        return EvolvingSpec("fifo", items=[
            EvolvingItem("rule_write", verification_status="verified", verification_round=1,
                         findings=[Finding(ErrorClass.COUNTEREXAMPLE, IssueAttribution.RTL_IMPLEMENTATION_ERROR,
                                           VerificationMode.RTL_CONFORMANCE, GenerationAction.REPAIR_RTL,
                                           evidence_note="cex", related_spec_item_ids=["rule_update_flags"])]),
            EvolvingItem("rule_update_flags", verification_status="verified", verification_round=1, findings=[]),
            EvolvingItem("rule_read", verification_status="verified", verification_round=1, findings=[]),
        ])

    def test_spec_modified_resets(self):
        ev = reset_round(self._verified(), modified_spec_items={"rule_write"}, modified_rtl_items=set())
        assert ev.item("rule_write").verification_status is VerificationStatus.PENDING
        assert ev.item("rule_write").findings == []
        assert ev.item("rule_write").verification_round is None

    def test_cascade_resets_linked_item(self):
        ev = reset_round(self._verified(), modified_spec_items={"rule_update_flags"}, modified_rtl_items=set())
        # rule_write holds a finding related to rule_update_flags -> cascade
        assert ev.item("rule_write").verification_status is VerificationStatus.PENDING
        assert ev.item("rule_update_flags").verification_status is VerificationStatus.PENDING
        # rule_read unmodified + unreached -> stays verified
        assert ev.item("rule_read").verification_status is VerificationStatus.VERIFIED

    def test_unmodified_retains_verified(self):
        ev = reset_round(self._verified(), modified_spec_items=set(), modified_rtl_items=set())
        assert all(i.verification_status is VerificationStatus.VERIFIED for i in ev.items)


class TestRtlConformance:
    def _spec(self):
        return SpecModule(
            name="fifo",
            state_ops=[SpecStateOp(state_name="full", kind="register", data_type="bool")],
            rule_ops=[SpecRuleOp(rule_name="tick", condition="true", actions=[])],
            property_ops=[SpecPropertyOp(prop_name="not_full", kind="safety",
                                         expression={"kind": "always", "operand": "(not (read full))"})],
            inputs=[], outputs=[], proof_obligations=[],
        )

    def test_failing_property_yields_conformance_record(self):
        spec = self._spec()
        trace = [{"state": {"full": True}, "inputs": {}, "memories": {}}]  # full -> (not full) = False
        records = check_rtl_conformance(spec, trace)
        assert len(records) == 1
        r = records[0]
        assert r.verification_mode is VerificationMode.RTL_CONFORMANCE
        assert r.error_class is ErrorClass.COUNTEREXAMPLE
        assert r.primary_spec_item_id == "not_full"

    def test_passing_property_yields_no_record(self):
        spec = self._spec()
        trace = [{"state": {"full": False}, "inputs": {}, "memories": {}}]
        assert check_rtl_conformance(spec, trace) == []


class TestFilters:
    def _spec(self):
        return SpecModule(name="f", state_ops=[SpecStateOp(state_name="x", kind="register", data_type="bits<4>")],
                          rule_ops=[], property_ops=[], inputs=[], outputs=[], proof_obligations=[])

    def test_filter_scope_drops_unlocalizable(self):
        recs = [_rec("e1", "unknown"), _rec("e2", "x")]
        kept = filter_evidence(recs, self._spec())
        assert [r.evidence_ref for r in kept] == ["e2"]

    def test_filter_status_drops_proved(self):
        recs = [_rec("e1", "x", status=ProofStatus.PROVED), _rec("e2", "x", status=ProofStatus.DISPROVED)]
        kept = filter_evidence(recs, self._spec())
        assert [r.evidence_ref for r in kept] == ["e2"]

    def test_filter_verifiable_drops_summary_only(self):
        recs = [_rec("e1", "x", cex=None), _rec("e2", "x", cex="full=1")]
        kept = filter_evidence(recs, self._spec())
        assert [r.evidence_ref for r in kept] == ["e2"]

    def test_apply_pinning(self):
        recs = [_rec("e1", "x"), _rec("e2", "x")]
        apply_pinning(recs, {"e1"})
        assert recs[0].pinned is True and recs[1].pinned is False

    def test_grounding_and_hallucination(self):
        f = Finding(ErrorClass.COUNTEREXAMPLE, IssueAttribution.RTL_IMPLEMENTATION_ERROR,
                    VerificationMode.RTL_CONFORMANCE, GenerationAction.REPAIR_RTL, evidence_ref="e1")
        assert check_grounding(f) is True
        rec = _rec("e1", "x", cex=None)  # counterexample finding but no cex -> hallucination
        assert check_non_hallucination(f, rec) is False
        rec2 = _rec("e1", "x", cex="full=1")
        assert check_non_hallucination(f, rec2) is True


class TestRegistryRetainedView:
    def test_from_registry_row_maps_generic_fields(self):
        from isir.lowering.filters import from_registry_row
        row = {"id": 1, "type": "counterexample_trace", "ref_type": "uri", "ref_value": "ev-1",
               "engine": "BMC", "status": "counterexample", "property_name": "rule_write",
               "design_name": "fifo"}
        r = from_registry_row(row)
        assert r.evidence_ref == "ev-1"
        assert r.primary_spec_item_id == "rule_write"
        assert r.proof_status is ProofStatus.DISPROVED
        assert r.error_class is ErrorClass.COUNTEREXAMPLE
        assert r.evidence_source is EvidenceSource.MODEL_CHECKING

    def test_retained_view_queries_registry(self, tmp_path):
        from isir.evidence.registry import EvidenceRegistry
        from isir.lowering.filters import retained_view
        reg = EvidenceRegistry(db_path=tmp_path / "e.db")
        reg.add_evidence(evidence_type="counterexample_trace", ref_type="local_id", ref_value="ev-1",
                         engine="BMC", status="counterexample", property_name="rule_write", design_name="fifo")
        recs = retained_view(reg, "fifo")
        assert len(recs) == 1
        assert recs[0].primary_spec_item_id == "rule_write"


class TestCOIScopeAndDedup:
    def _spec(self):
        return SpecModule(
            name="f",
            state_ops=[SpecStateOp(state_name="x", kind="register", data_type="bits<4>"),
                       SpecStateOp(state_name="y", kind="register", data_type="bits<4>")],
            rule_ops=[SpecRuleOp(rule_name="inc_x", condition="true", actions=["(write x (add (read x) 1))"]),
                      SpecRuleOp(rule_name="inc_y", condition="true", actions=["(write y (add (read y) 1))"])],
            property_ops=[SpecPropertyOp(prop_name="x_ok", kind="safety",
                                         expression={"kind": "always", "operand": "(lt (read x) 16)"})],
            inputs=[], outputs=[], proof_obligations=[],
        )

    def test_read_write_sets_and_cone(self):
        from isir.lowering.filters import one_hop_cone, read_set, write_set
        spec = self._spec()
        assert read_set(spec, "inc_x") == {"x"}
        assert write_set(spec, "inc_x") == {"x"}
        # inc_x reads x; x is written by inc_x -> 1-hop cone = {inc_x, inc_x}
        assert one_hop_cone(spec, "inc_x") == {"inc_x"}

    def test_filter_scope_drops_out_of_cone_related(self):
        from isir.lowering.filters import filter_scope
        spec = self._spec()
        rec = _rec("e1", "x_ok", related=["inc_y"])  # inc_y writes y, not in x_ok's cone
        assert filter_scope([rec], spec) == []
        rec2 = _rec("e2", "x_ok", related=["inc_x"])  # inc_x writes x -> in cone
        assert len(filter_scope([rec2], spec)) == 1

    def test_dedup_minimal(self):
        from isir.lowering.filters import dedup_minimal
        recs = [_rec("e1", "x", ec=ErrorClass.COUNTEREXAMPLE, cex="long-long-long"),
                _rec("e2", "x", ec=ErrorClass.COUNTEREXAMPLE, cex="s")]
        kept = dedup_minimal(recs)
        assert [r.evidence_ref for r in kept] == ["e2"]


class TestRetention:
    def test_ttl_expiry_skips_pinned(self):
        from isir.lowering.retained import RetainedView
        view = RetainedView(ttl_seconds=100)
        view.upsert(_rec("e1", "x"), now=0.0)
        view.upsert(_rec("e2", "x"), now=0.0)
        view.pin({"e1"})  # e1 pinned, e2 not
        view.expire(now=200.0)
        assert "e1" in view.records      # pinned survives TTL
        assert "e2" not in view.records  # unpinned expired
        assert "e2" in view.tombstones   # tombstone written

    def test_tombstone_hash_fallback(self):
        from isir.lowering.retained import RetainedView
        from isir.lowering.annotation import record_to_finding
        view = RetainedView()
        rec = _rec("e1", "x")
        view.upsert(rec, now=0.0)
        f = record_to_finding(rec)
        assert view.finding_valid(f) is True
        # administratively remove + tombstone with matching hash
        view.tombstone("e1", rec.evidence_hash)
        assert view.finding_valid(f) is True
        # a new verification run produces a different hash -> invalid
        view.tombstone("e1", "h:new")
        assert view.finding_valid(f) is False

    def test_cache_key(self):
        from isir.lowering.retained import cache_key
        rec = _rec("e1", "x", related=["y"])
        k = cache_key(rec, "spec-hash", "v1")
        assert k == ("x", ("y",), "spec-hash", rec.evidence_hash, "v1")


class TestSchemaAndRelevanceGates:
    def test_schema_conformant(self):
        from isir.lowering.filters import schema_conformant
        f = Finding(ErrorClass.COUNTEREXAMPLE, IssueAttribution.RTL_IMPLEMENTATION_ERROR,
                    VerificationMode.RTL_CONFORMANCE, GenerationAction.REPAIR_RTL)
        assert schema_conformant(f) is True

    def test_relevant_drops_undetermined(self):
        from isir.lowering.filters import relevant
        f = Finding(ErrorClass.COUNTEREXAMPLE, IssueAttribution.UNDETERMINED,
                    VerificationMode.SELF_CONSISTENCY, GenerationAction.ADD_LEMMA)
        assert relevant(f) is False
