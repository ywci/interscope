# src/isir/dialects/evolving_spec.py
#
# Evolving Specification dialect — the LLM-consumable, ISIR-based semi-formal
# specification with a `pending` / `verified` lifecycle.  It is layered over the
# spec dialect (it does NOT modify SpecModule) and holds the per-item
# uncertainty, the `verification_status`, and the evidence-derived `findings`.

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from isir.dialects.isir import Dialect


class EvolvingSpecDialect(Dialect):
    name = "evolving_spec"


class VerificationStatus(str, Enum):
    PENDING = "pending"
    VERIFIED = "verified"


class ErrorClass(str, Enum):
    TYPE_ERROR = "type_error"
    MISSING_PREMISE = "missing_premise"
    INDUCTION_FAILURE = "induction_failure"
    COUNTEREXAMPLE = "counterexample"
    SCHEDULE_CONFLICT = "schedule_conflict"
    PLACEHOLDER_SYMBOL_READ = "placeholder_symbol_read"
    DEFERRED_PLACEHOLDER = "deferred_placeholder"


class IssueAttribution(str, Enum):
    TRANSLATION_AMBIGUITY = "translation_ambiguity"
    SPECIFICATION_OMISSION = "specification_omission"
    RTL_IMPLEMENTATION_ERROR = "rtl_implementation_error"
    MISSING_PREMISE = "missing_premise"
    UNRESOLVED_PLACEHOLDER = "unresolved_placeholder"
    CROSS_RULE_CONFLICT = "cross_rule_conflict"
    UNDETERMINED = "undetermined"


class VerificationMode(str, Enum):
    SELF_CONSISTENCY = "self_consistency"
    RTL_CONFORMANCE = "rtl_conformance"
    STATIC_CARRY_OVER = "static_carry_over"   # findings-only (synthetic deferred)


class GenerationAction(str, Enum):
    RE_TRANSLATE = "re_translate"
    BRANCH_ON_ALTERNATIVES = "branch_on_alternatives"
    INSERT_ASSUME_OR_ASSERT = "insert_assume_or_assert"
    REPAIR_RTL = "repair_rtl"
    ADD_LEMMA = "add_lemma"
    STAGED_GENERATION = "staged_generation"
    RESOLVE_SCHEDULE_CONFLICT = "resolve_schedule_conflict"


class EvidenceSource(str, Enum):
    SIMULATION = "simulation"
    MODEL_CHECKING = "model_checking"
    ITP = "itp"


class ProofStatus(str, Enum):
    PROVED = "proved"
    DISPROVED = "disproved"
    INCONCLUSIVE = "inconclusive"
    TIMEOUT = "timeout"

# Lower rank = higher priority = kept first under the 3-finding cap / token budget.
ISSUE_ATTRIBUTION_PRIORITY: Dict[IssueAttribution, int] = {
    IssueAttribution.UNRESOLVED_PLACEHOLDER: 1,
    IssueAttribution.TRANSLATION_AMBIGUITY: 2,
    IssueAttribution.SPECIFICATION_OMISSION: 3,
    IssueAttribution.CROSS_RULE_CONFLICT: 4,
    IssueAttribution.RTL_IMPLEMENTATION_ERROR: 5,
    IssueAttribution.MISSING_PREMISE: 6,
    IssueAttribution.UNDETERMINED: 7,   # dropped at Stage 2.8; completeness entry
}

# The one explicit attribution -> action rule (Stage 2.9).
ATTRIBUTION_TO_ACTION: Dict[IssueAttribution, GenerationAction] = {
    IssueAttribution.CROSS_RULE_CONFLICT: GenerationAction.RESOLVE_SCHEDULE_CONFLICT,
}


def _as(value: Any, enum_cls: type) -> Any:
    return value if isinstance(value, enum_cls) else enum_cls(value)


def _v(value: Any) -> str:
    return value.value if isinstance(value, Enum) else str(value)


def attribution_priority(attribution: IssueAttribution) -> int:
    return ISSUE_ATTRIBUTION_PRIORITY.get(_as(attribution, IssueAttribution), 99)


@dataclass
class Finding:
    """One evidence-derived finding (Section 6)."""
    error_class: ErrorClass
    issue_attribution: IssueAttribution
    verification_mode: VerificationMode
    generation_action: GenerationAction
    evidence_note: str = ""
    rtl_anchor: Optional[str] = None
    related_spec_item_ids: List[str] = field(default_factory=list)
    back_indexed_from: Optional[str] = None
    evidence_ref: str = ""
    evidence_hash: str = ""

    def __post_init__(self) -> None:
        self.error_class = _as(self.error_class, ErrorClass)
        self.issue_attribution = _as(self.issue_attribution, IssueAttribution)
        self.verification_mode = _as(self.verification_mode, VerificationMode)
        self.generation_action = _as(self.generation_action, GenerationAction)

    def sort_key(self) -> tuple:
        """Stage 2.9/3.15 tie-breaker: priority, primary-first, shorter note."""
        return (
            attribution_priority(self.issue_attribution),
            0 if self.back_indexed_from is None else 1,
            len(self.evidence_note),
        )

    def to_prompt_dict(self) -> Dict[str, Any]:
        """Canonical -> prompt-serialized (Section 9); ev_ref/ev_hash omitted."""
        d: Dict[str, Any] = {
            "error_class": _v(self.error_class),
            "issue_attribution": _v(self.issue_attribution),
            "verification_mode": _v(self.verification_mode),
            "evidence": self.evidence_note,
            "action": _v(self.generation_action),
        }
        if self.rtl_anchor is not None:
            d["rtl"] = self.rtl_anchor
        if self.related_spec_item_ids:
            d["related_items"] = list(self.related_spec_item_ids)
        if self.back_indexed_from is not None:
            d["from_item"] = self.back_indexed_from
        return d


@dataclass
class EvolvingItem:
    """Per-item view: uncertainty + lifecycle state + findings (Section 6)."""
    spec_item_id: str
    verification_status: VerificationStatus = VerificationStatus.PENDING
    provenance: Optional[str] = None
    alternatives: List[Any] = field(default_factory=list)
    partial_spec: Optional[Dict[str, Any]] = None
    defer_verification: bool = False
    nl_anchor: Optional[str] = None
    verification_round: Optional[int] = None
    findings: List[Finding] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.verification_status = _as(self.verification_status, VerificationStatus)
        self.findings = [f if isinstance(f, Finding) else Finding(**f) for f in self.findings]

    def validate(self) -> List[str]:
        """Return the Section-6 consistency-constraint violations."""
        errs: List[str] = []
        tag = self.spec_item_id
        if self.verification_status is VerificationStatus.PENDING:
            if self.findings:
                errs.append(f"{tag}: pending item must have empty findings")
            if self.verification_round is not None:
                errs.append(f"{tag}: pending item must not carry verification_round")
        else:
            if self.verification_round is None:
                errs.append(f"{tag}: verified item must carry verification_round")
            if self.defer_verification and not any(
                    f.error_class is ErrorClass.DEFERRED_PLACEHOLDER for f in self.findings):
                errs.append(f"{tag}: deferred item must carry a synthetic deferred finding")
        return errs

    def to_prompt_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"item": self.spec_item_id}
        if self.nl_anchor is not None:
            d["nl"] = self.nl_anchor
        if self.findings:
            d["findings"] = [f.to_prompt_dict()
                             for f in sorted(self.findings, key=Finding.sort_key)]
        if self.alternatives:
            d["alternatives"] = list(self.alternatives)
        if self.partial_spec is not None:
            d["partial_spec"] = self.partial_spec
        return d


@dataclass
class EvolvingSpec:
    """The single Evolving Specification artifact (two lifecycle states)."""
    name: str
    items: List[EvolvingItem] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.items = [i if isinstance(i, EvolvingItem) else EvolvingItem(**i) for i in self.items]

    @property
    def verification_round(self) -> Optional[int]:
        rounds = [i.verification_round for i in self.items if i.verification_round is not None]
        return max(rounds) if rounds else None

    def item(self, spec_item_id: str) -> Optional[EvolvingItem]:
        return next((i for i in self.items if i.spec_item_id == spec_item_id), None)

    def validate(self) -> List[str]:
        return [e for i in self.items for e in i.validate()]

    def to_prompt_dict(self) -> Dict[str, Any]:
        return {
            "module_header": {"round": self.verification_round},
            "items": [i.to_prompt_dict() for i in self.items],
        }

    def to_prompt_yaml(self) -> str:
        import yaml
        return yaml.safe_dump(self.to_prompt_dict(), sort_keys=False, default_flow_style=False)


@dataclass
class RawEvidenceRecord:
    evidence_ref: str
    primary_spec_item_id: str
    verification_mode: VerificationMode
    evidence_source: EvidenceSource
    proof_status: ProofStatus
    error_class: ErrorClass
    related_spec_item_ids: List[str] = field(default_factory=list)
    failing_subgoal: Optional[str] = None
    counterexample: Optional[Any] = None
    failing_trace: Optional[str] = None
    source_mapping_ref: Optional[str] = None
    evidence_hash: str = ""
    pinned: bool = False

    def __post_init__(self) -> None:
        self.verification_mode = _as(self.verification_mode, VerificationMode)
        self.evidence_source = _as(self.evidence_source, EvidenceSource)
        self.proof_status = _as(self.proof_status, ProofStatus)
        self.error_class = _as(self.error_class, ErrorClass)


def evict_findings(findings: List[Finding], cap: int = 3) -> List[Finding]:
    """Stage 2.9 / 3.15: keep the highest-priority `cap` findings."""
    if len(findings) <= cap:
        return list(findings)
    return sorted(findings, key=Finding.sort_key)[:cap]


def synthetic_deferred_finding() -> Finding:
    """Section 8 Step 1: the deterministic synthetic finding for a deferred item."""
    return Finding(
        error_class=ErrorClass.DEFERRED_PLACEHOLDER,
        issue_attribution=IssueAttribution.UNRESOLVED_PLACEHOLDER,
        verification_mode=VerificationMode.STATIC_CARRY_OVER,
        generation_action=GenerationAction.STAGED_GENERATION,
        evidence_note="Verification deferred; stage generation around partial_spec",
        evidence_ref="static_defer",
        evidence_hash="static_defer",
    )
