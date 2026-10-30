# src/isir/lowering/feedback.py
#
# LLM consumption interface (Section 9) + Phase 2 feedback refinement (Stage 4):
#   - action_instruction : render a generation_action as an explicit instruction
#   - assemble_prompt    : render the verified state as a generation prompt
#   - FeedbackTracker    : retrieval tracking, usefulness review, attribution audit

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from isir.dialects.evolving_spec import EvolvingSpec, Finding, GenerationAction


# Section 9 "Generation action semantics": the explicit instruction per action.
ACTION_INSTRUCTIONS: Dict[GenerationAction, str] = {
    GenerationAction.RE_TRANSLATE: "Re-run NL-to-spec translation; do not patch RTL",
    GenerationAction.BRANCH_ON_ALTERNATIVES: "Generate parallel candidates from the alternatives",
    GenerationAction.INSERT_ASSUME_OR_ASSERT: "Add a constraint/assertion for the implicit assumption or undefined behavior",
    GenerationAction.REPAIR_RTL: "Localize and repair the RTL fragment at the given span",
    GenerationAction.ADD_LEMMA: "Add a lemma/invariant for the missing premise or induction failure",
    GenerationAction.STAGED_GENERATION: "Defer this item; implement the confirmed parts first",
    GenerationAction.RESOLVE_SCHEDULE_CONFLICT: "Adjust priority/mutex/schedule across the implicated items",
}


def action_instruction(action: GenerationAction) -> str:
    return ACTION_INSTRUCTIONS.get(action, str(action))


def assemble_prompt(verified: EvolvingSpec) -> str:
    """Render the verified state as a generation prompt (Section 9): items and
    findings ordered by priority, each action rendered as an explicit instruction.
    """
    lines: List[str] = [f"# Round {verified.verification_round} verification feedback"]
    for item in verified.items:
        lines.append(f"\n## {item.spec_item_id}")
        if item.nl_anchor:
            lines.append(f"NL: {item.nl_anchor}")
        if item.alternatives:
            lines.append(f"Alternatives: {', '.join(map(str, item.alternatives))}")
        for f in sorted(item.findings, key=Finding.sort_key):
            lines.append(f"- [{f.issue_attribution.value}] {f.evidence_note}")
            lines.append(f"    ACTION: {action_instruction(f.generation_action)}")
            if f.rtl_anchor:
                lines.append(f"    RTL: {f.rtl_anchor}")
            if f.back_indexed_from:
                lines.append(f"    (reported via {f.back_indexed_from})")
    return "\n".join(lines) + "\n"


@dataclass
class FeedbackTracker:
    """Phase 2 (Stage 4) bookkeeping: retrieval, usefulness, attribution audit."""

    retrievals: List[Tuple[str, str]] = field(default_factory=list)   # (request_id, evidence_ref)
    reviews: List[Tuple[str, bool]] = field(default_factory=list)     # (spec_item_id, useful)
    audits: List[Tuple[str, bool]] = field(default_factory=list)      # (evidence_ref, correct)

    def log_retrieval(self, request_id: str, evidence_ref: str) -> None:
        self.retrievals.append((request_id, evidence_ref))

    def retrieval_coverage(self, findings: List[Finding]) -> float:
        """Fraction of findings that have been retrieved at least once."""
        if not findings:
            return 1.0
        retrieved = {r for _, r in self.retrievals}
        return sum(1 for f in findings if f.evidence_ref in retrieved) / len(findings)

    def log_review(self, spec_item_id: str, useful: bool) -> None:
        self.reviews.append((spec_item_id, useful))

    def usefulness_rate(self) -> float:
        """Fraction of reviewed items judged useful."""
        if not self.reviews:
            return 1.0
        return sum(1 for _, u in self.reviews if u) / len(self.reviews)

    def log_audit(self, evidence_ref: str, correct: bool) -> None:
        self.audits.append((evidence_ref, correct))

    def false_attribution_rate(self) -> float:
        """Fraction of audited attributions that were wrong."""
        if not self.audits:
            return 0.0
        return sum(1 for _, c in self.audits if not c) / len(self.audits)
