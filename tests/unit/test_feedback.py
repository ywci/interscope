# tests/unit/test_feedback.py
#
# LLM consumption interface (assemble_prompt) + Phase 2 feedback tracker.

from isir.dialects.evolving_spec import (
    EvolvingItem, EvolvingSpec, Finding, ErrorClass, IssueAttribution,
    VerificationMode, GenerationAction,
)
from isir.lowering.feedback import FeedbackTracker, action_instruction, assemble_prompt


def _verified_spec():
    item = EvolvingItem(
        "rule_write", verification_status="verified", verification_round=7,
        nl_anchor="ignore writes when full",
        findings=[
            Finding(ErrorClass.COUNTEREXAMPLE, IssueAttribution.RTL_IMPLEMENTATION_ERROR,
                    VerificationMode.RTL_CONFORMANCE, GenerationAction.REPAIR_RTL,
                    evidence_note="cex: write_ptr increments when full=1", rtl_anchor="fifo.v:42"),
        ])
    return EvolvingSpec("fifo", items=[item])


class TestActionInstruction:
    def test_repair_rtl_instruction(self):
        assert "repair the RTL" in action_instruction(GenerationAction.REPAIR_RTL)
    def test_staged_generation_instruction(self):
        assert "Defer this item" in action_instruction(GenerationAction.STAGED_GENERATION)


class TestAssemblePrompt:
    def test_orders_and_renders_instruction(self):
        p = assemble_prompt(_verified_spec())
        assert "Round 7" in p
        assert "rule_write" in p
        assert "ignore writes when full" in p
        assert "repair the RTL" in p
        assert "fifo.v:42" in p


class TestFeedbackTracker:
    def test_retrieval_coverage(self):
        t = FeedbackTracker()
        spec = _verified_spec()
        f = spec.items[0].findings[0]
        assert t.retrieval_coverage([f]) == 0.0
        t.log_retrieval("req1", f.evidence_ref)
        assert t.retrieval_coverage([f]) == 1.0

    def test_usefulness_rate(self):
        t = FeedbackTracker()
        t.log_review("a", True)
        t.log_review("b", False)
        assert abs(t.usefulness_rate() - 0.5) < 1e-9

    def test_false_attribution_rate(self):
        t = FeedbackTracker()
        t.log_audit("e1", True)
        t.log_audit("e2", False)
        assert abs(t.false_attribution_rate() - 0.5) < 1e-9
