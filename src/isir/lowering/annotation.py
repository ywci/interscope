# src/isir/lowering/annotation.py
#
# Offline annotation (Section 8 of the Evolving Specification plan): the five
# ordered steps that drive the `pending` state to the `verified` state.

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Set, Tuple

from isir.dialects.evolving_spec import (
    ErrorClass,
    EvolvingItem,
    EvolvingSpec,
    Finding,
    GenerationAction,
    IssueAttribution,
    RawEvidenceRecord,
    VerificationMode,
    VerificationStatus,
    evict_findings,
    synthetic_deferred_finding,
)


# Step 1 attribution + action, derived from the evidence record (the
# placeholder-COI guard routes placeholder reads to unresolved_placeholder).
def record_to_finding(record: RawEvidenceRecord) -> Finding:
    mode = record.verification_mode
    ec = record.error_class

    if ec is ErrorClass.PLACEHOLDER_SYMBOL_READ:
        attr = IssueAttribution.UNRESOLVED_PLACEHOLDER
        action = GenerationAction.STAGED_GENERATION
    elif ec is ErrorClass.COUNTEREXAMPLE:
        if mode is VerificationMode.RTL_CONFORMANCE:
            attr = IssueAttribution.RTL_IMPLEMENTATION_ERROR
            action = GenerationAction.REPAIR_RTL
        else:
            attr = IssueAttribution.SPECIFICATION_OMISSION
            action = GenerationAction.INSERT_ASSUME_OR_ASSERT
    elif ec in (ErrorClass.MISSING_PREMISE, ErrorClass.INDUCTION_FAILURE):
        attr = IssueAttribution.MISSING_PREMISE
        action = GenerationAction.ADD_LEMMA
    elif ec is ErrorClass.SCHEDULE_CONFLICT:
        attr = IssueAttribution.CROSS_RULE_CONFLICT
        action = GenerationAction.RESOLVE_SCHEDULE_CONFLICT
    elif ec is ErrorClass.TYPE_ERROR:
        attr = IssueAttribution.TRANSLATION_AMBIGUITY
        action = GenerationAction.RE_TRANSLATE
    else:
        attr = IssueAttribution.UNDETERMINED
        action = GenerationAction.ADD_LEMMA

    return Finding(
        error_class=ec,
        issue_attribution=attr,
        verification_mode=mode,
        generation_action=action,
        evidence_note=_template_note(record),
        rtl_anchor=record.source_mapping_ref if mode is VerificationMode.RTL_CONFORMANCE else None,
        related_spec_item_ids=list(record.related_spec_item_ids),
        evidence_ref=record.evidence_ref,
        evidence_hash=record.evidence_hash,
    )


def _template_note(record: RawEvidenceRecord) -> str:
    if record.counterexample is not None:
        return f"cex: {record.counterexample}"
    if record.failing_trace is not None:
        return f"trace: {record.failing_trace}"
    if record.failing_subgoal is not None:
        return f"subgoal: {record.failing_subgoal}"
    return record.error_class.value


def _dedup_by_error_class(findings: List[Finding]) -> List[Finding]:
    """One finding per error_class; the primary (non-back-indexed) wins."""
    seen: Dict[ErrorClass, Finding] = {}
    for f in findings:
        if (f.error_class not in seen
                or (f.back_indexed_from is None and seen[f.error_class].back_indexed_from is not None)):
            seen[f.error_class] = f
    return list(seen.values())


def _tokens(note: str) -> int:
    return len(note.split())


def _enforce_budget(findings: List[Finding], note_budget: int, item_budget: int) -> List[Finding]:
    for f in findings:
        words = f.evidence_note.split()
        if len(words) > note_budget:
            f.evidence_note = " ".join(words[:note_budget])
    while len(findings) > 1 and sum(_tokens(f.evidence_note) for f in findings) > item_budget:
        findings = evict_findings(findings, len(findings) - 1)
    return findings


def annotate(
    evolving: EvolvingSpec,
    evidence: List[RawEvidenceRecord],
    round_num: int,
    note_budget: int = 40,
    item_budget: int = 120,
    cap: int = 3,
    note_generator: Optional[Callable[[Finding], str]] = None,
) -> Tuple[EvolvingSpec, Set[str]]:
    """Drive the `pending` state to the `verified` state (Section 8, five steps).

    Returns `(verified_spec, pinned_evidence_refs)`.  Records referenced by a
    finding that entered the verified state are pinned; the caller unpins any
    Round k-1 record not in the returned set.
    """
    by_item: Dict[str, List[Finding]] = {i.spec_item_id: [] for i in evolving.items}
    item_by_id = {i.spec_item_id: i for i in evolving.items}

    # Step 1: filter + attribute + inject synthetic deferred findings.
    for record in evidence:
        if record.primary_spec_item_id not in item_by_id:
            continue  # unlocalizable (Stage 1.1)
        finding = record_to_finding(record)
        if finding.issue_attribution is IssueAttribution.UNDETERMINED:
            continue  # Stage 2.8 drop
        by_item[record.primary_spec_item_id].append(finding)

    for item in evolving.items:
        if item.defer_verification:
            by_item[item.spec_item_id].append(synthetic_deferred_finding())

    # Step 2: materialize back-indexed entries into the related items.
    for item in evolving.items:
        for f in list(by_item[item.spec_item_id]):
            for ri in f.related_spec_item_ids:
                if ri == item.spec_item_id or ri not in item_by_id:
                    continue
                by_item[ri].append(Finding(
                    error_class=f.error_class,
                    issue_attribution=f.issue_attribution,
                    verification_mode=f.verification_mode,
                    generation_action=f.generation_action,
                    rtl_anchor=f.rtl_anchor,
                    related_spec_item_ids=[item.spec_item_id] + [r for r in f.related_spec_item_ids if r != ri],
                    back_indexed_from=item.spec_item_id,
                    evidence_ref=f.evidence_ref,
                    evidence_hash=f.evidence_hash,
                ))

    # Step 3: dedup by error_class + cap at `cap` by priority.
    for item in evolving.items:
        by_item[item.spec_item_id] = evict_findings(
            _dedup_by_error_class(by_item[item.spec_item_id]), cap)

    # Step 4: generate notes (template already set; LLM override via callback),
    # then propagate primary notes to back-indexed pointers.
    if note_generator is not None:
        for item in evolving.items:
            for f in by_item[item.spec_item_id]:
                if f.back_indexed_from is None:
                    f.evidence_note = note_generator(f)
    # Propagate primary notes to back-indexed pointers ACROSS items (a pointer's
    # primary lives in a different item, so collect all primaries first).
    all_primaries = {f.evidence_ref: f.evidence_note
                     for item in evolving.items
                     for f in by_item[item.spec_item_id] if f.back_indexed_from is None}
    for item in evolving.items:
        for f in by_item[item.spec_item_id]:
            if f.back_indexed_from is not None and not f.evidence_note:
                f.evidence_note = all_primaries.get(f.evidence_ref, "")

    # Step 5: token budgets, finalize the verified state, and pin.
    pinned: Set[str] = set()
    verified_items: List[EvolvingItem] = []
    for item in evolving.items:
        fs = _enforce_budget(by_item[item.spec_item_id], note_budget, item_budget)
        verified_items.append(EvolvingItem(
            spec_item_id=item.spec_item_id,
            verification_status=VerificationStatus.VERIFIED,
            provenance=item.provenance,
            alternatives=list(item.alternatives),
            partial_spec=item.partial_spec,
            defer_verification=item.defer_verification,
            nl_anchor=item.nl_anchor,
            verification_round=round_num,
            findings=fs,
        ))
        for f in fs:
            if f.evidence_ref != "static_defer":
                pinned.add(f.evidence_ref)

    return EvolvingSpec(name=evolving.name, items=verified_items), pinned
