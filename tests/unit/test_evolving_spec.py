# tests/unit/test_evolving_spec.py
#
# Phase 1 of the Evolving Specification plan: the schema (dialect), the
# priority/tie-breaker, the prompt serialization, and the consistency rules.

from isir.dialects.evolving_spec import (
    VerificationStatus, ErrorClass, IssueAttribution, VerificationMode,
    GenerationAction, Finding, EvolvingItem, EvolvingSpec,
    RawEvidenceRecord, ISSUE_ATTRIBUTION_PRIORITY, attribution_priority,
    evict_findings, synthetic_deferred_finding,
)


class TestEnumsAndPriority:
    def test_priority_rank_1_is_unresolved_placeholder(self):
        assert attribution_priority(IssueAttribution.UNRESOLVED_PLACEHOLDER) == 1
        assert attribution_priority(IssueAttribution.MISSING_PREMISE) == 6
        assert attribution_priority(IssueAttribution.UNDETERMINED) == 7

    def test_enums_are_strings(self):
        assert VerificationStatus.PENDING.value == "pending"
        assert VerificationMode.RTL_CONFORMANCE.value == "rtl_conformance"


class TestFinding:
    def test_coerces_strings_to_enums(self):
        f = Finding(error_class="counterexample", issue_attribution="rtl_implementation_error",
                    verification_mode="rtl_conformance", generation_action="repair_rtl")
        assert f.error_class is ErrorClass.COUNTEREXAMPLE
        assert f.generation_action is GenerationAction.REPAIR_RTL

    def test_prompt_dict_omits_evidence_refs(self):
        f = Finding(ErrorClass.COUNTEREXAMPLE, IssueAttribution.RTL_IMPLEMENTATION_ERROR,
                    VerificationMode.RTL_CONFORMANCE, GenerationAction.REPAIR_RTL,
                    evidence_note="cex: write_ptr", rtl_anchor="fifo.v:42",
                    related_spec_item_ids=["rule_update_flags"], evidence_ref="ev-1", evidence_hash="h1")
        d = f.to_prompt_dict()
        assert d["evidence"] == "cex: write_ptr"
        assert d["action"] == "repair_rtl"
        assert d["rtl"] == "fifo.v:42"
        assert d["related_items"] == ["rule_update_flags"]
        assert "evidence_ref" not in d and "evidence_hash" not in d

    def test_back_indexed_serializes_from_item(self):
        f = Finding(ErrorClass.COUNTEREXAMPLE, IssueAttribution.RTL_IMPLEMENTATION_ERROR,
                    VerificationMode.RTL_CONFORMANCE, GenerationAction.REPAIR_RTL,
                    back_indexed_from="rule_write")
        assert f.to_prompt_dict()["from_item"] == "rule_write"


class TestEviction:
    def _f(self, attr, back=None, note=""):
        return Finding(ErrorClass.COUNTEREXAMPLE, attr, VerificationMode.SELF_CONSISTENCY,
                       GenerationAction.ADD_LEMMA, evidence_note=note, back_indexed_from=back)

    def test_keeps_highest_priority(self):
        fs = [self._f(IssueAttribution.MISSING_PREMISE),
              self._f(IssueAttribution.UNRESOLVED_PLACEHOLDER),
              self._f(IssueAttribution.TRANSLATION_AMBIGUITY),
              self._f(IssueAttribution.UNDETERMINED)]
        kept = evict_findings(fs, cap=3)
        assert [f.issue_attribution for f in kept] == [
            IssueAttribution.UNRESOLVED_PLACEHOLDER,
            IssueAttribution.TRANSLATION_AMBIGUITY,
            IssueAttribution.MISSING_PREMISE,
        ]

    def test_primary_before_back_indexed_on_tie(self):
        fs = [self._f(IssueAttribution.MISSING_PREMISE, back="rule_write"),
              self._f(IssueAttribution.MISSING_PREMISE)]
        kept = evict_findings(fs, cap=1)
        assert kept[0].back_indexed_from is None


class TestConsistencyRules:
    def test_pending_requires_empty_findings(self):
        i = EvolvingItem("x", findings=[synthetic_deferred_finding()])
        assert any("empty findings" in e for e in i.validate())

    def test_verified_requires_round(self):
        i = EvolvingItem("x", verification_status="verified")
        assert any("verification_round" in e for e in i.validate())

    def test_deferred_requires_synthetic_finding(self):
        i = EvolvingItem("x", verification_status="verified", verification_round=1,
                         defer_verification=True)
        assert any("deferred finding" in e for e in i.validate())


class TestSyntheticDeferredFinding:
    def test_fields(self):
        f = synthetic_deferred_finding()
        assert f.error_class is ErrorClass.DEFERRED_PLACEHOLDER
        assert f.issue_attribution is IssueAttribution.UNRESOLVED_PLACEHOLDER
        assert f.verification_mode is VerificationMode.STATIC_CARRY_OVER
        assert f.generation_action is GenerationAction.STAGED_GENERATION
        assert f.evidence_ref == "static_defer" and f.evidence_hash == "static_defer"


class TestPromptSerialization:
    def test_full_yaml(self):
        item = EvolvingItem(
            "rule_write", verification_status="verified", verification_round=7,
            nl_anchor="ignore writes when full", alternatives=["overwrite oldest"],
            findings=[
                Finding(ErrorClass.COUNTEREXAMPLE, IssueAttribution.RTL_IMPLEMENTATION_ERROR,
                        VerificationMode.RTL_CONFORMANCE, GenerationAction.REPAIR_RTL,
                        evidence_note="cex: write_ptr increments when full=1",
                        rtl_anchor="fifo.v:42", related_spec_item_ids=["rule_update_flags"]),
                Finding(ErrorClass.MISSING_PREMISE, IssueAttribution.MISSING_PREMISE,
                        VerificationMode.SELF_CONSISTENCY, GenerationAction.ADD_LEMMA,
                        evidence_note="Coq: full -> count < depth unproven"),
            ])
        spec = EvolvingSpec("fifo", items=[item])
        d = spec.to_prompt_dict()
        assert d["module_header"]["round"] == 7
        assert d["items"][0]["item"] == "rule_write"
        assert d["items"][0]["findings"][0]["evidence"] == "cex: write_ptr increments when full=1"
        assert d["items"][0]["findings"][0]["action"] == "repair_rtl"
        assert "from_item" not in d["items"][0]["findings"][0]
        assert "ev_ref" not in d["items"][0]["findings"][0]
        assert "ev_hash" not in d["items"][0]["findings"][0]
        y = spec.to_prompt_yaml()
        assert "round: 7" in y and "action: repair_rtl" in y
