# src/isir/lowering/filters.py
#
# Garbage filtering (Section 7): the deterministic Stage 1-2 pre-filters and
# the end-of-Step-5 pinning, applied by the offline pipeline BEFORE `annotate`.

from __future__ import annotations

from typing import List, Set

from isir.dialects.evolving_spec import (
    ErrorClass,
    EvidenceSource,
    Finding,
    GenerationAction,
    IssueAttribution,
    ProofStatus,
    RawEvidenceRecord,
    VerificationMode,
)
from isir.dialects.isir import SpecModule
from isir.utils.expr import parse_sexpr


def _spec_item_ids(spec: SpecModule) -> Set[str]:
    ids = {s.state_name for s in spec.state_ops}
    ids |= {r.rule_name for r in spec.rule_ops}
    ids |= {p.prop_name for p in spec.property_ops}
    ids |= {f.get("name") for f in (getattr(spec, "functions", None) or []) if f.get("name")}
    return ids


def _collect_reads(expr, acc=None):
    """Return the set of register names read by an S-expression (`read` nodes)."""
    if acc is None:
        acc = set()
    if isinstance(expr, list):
        if expr and expr[0] == "read" and len(expr) > 1 and isinstance(expr[1], str):
            acc.add(expr[1])
        for a in expr:
            _collect_reads(a, acc)
    return acc


def _rule_by_name(spec, name):
    return next((r for r in spec.rule_ops if r.rule_name == name), None)


def _prop_by_name(spec, name):
    return next((p for p in spec.property_ops if p.prop_name == name), None)


def read_set(spec: SpecModule, item_id: str) -> set:
    """The registers an item reads (rule condition/action RHS, property operand)."""
    reads = set()
    r = _rule_by_name(spec, item_id)
    if r is not None:
        if r.condition:
            reads |= _collect_reads(parse_sexpr(r.condition))
        for act in r.actions:
            p = parse_sexpr(act)
            if isinstance(p, list) and p and p[0] == "write" and len(p) == 3:
                reads |= _collect_reads(p[2])
    prop = _prop_by_name(spec, item_id)
    if prop is not None and prop.expression.get("operand"):
        reads |= _collect_reads(parse_sexpr(prop.expression["operand"]))
    return reads


def write_set(spec: SpecModule, item_id: str) -> set:
    """The registers an item writes (rule action destinations)."""
    writes = set()
    r = _rule_by_name(spec, item_id)
    if r is not None:
        for act in r.actions:
            p = parse_sexpr(act)
            if isinstance(p, list) and p and p[0] == "write" and len(p) == 3 and isinstance(p[1], str):
                writes.add(p[1])
    return writes


def one_hop_cone(spec: SpecModule, item_id: str) -> set:
    """1-hop backward cone: the item plus the rules that write what it reads."""
    cone = {item_id}
    for reg in read_set(spec, item_id):
        for r in spec.rule_ops:
            if reg in write_set(spec, r.rule_name):
                cone.add(r.rule_name)
    return cone


def filter_scope(records: List[RawEvidenceRecord], spec: SpecModule) -> List[RawEvidenceRecord]:
    """Stage 1.1 + 1.3: the primary must map to a spec item, and every related
    item must lie in the primary's 1-hop cone of influence (relevance)."""
    ids = _spec_item_ids(spec)
    kept = []
    for r in records:
        if r.primary_spec_item_id not in ids:
            continue
        cone = one_hop_cone(spec, r.primary_spec_item_id)
        if all(ri in cone for ri in r.related_spec_item_ids):
            kept.append(r)
    return kept


def filter_status(records: List[RawEvidenceRecord]) -> List[RawEvidenceRecord]:
    """Stage 1.2 status filter: keep only disproved / inconclusive / timeout."""
    return [r for r in records
            if r.proof_status in (ProofStatus.DISPROVED, ProofStatus.INCONCLUSIVE, ProofStatus.TIMEOUT)]


def filter_verifiable(records: List[RawEvidenceRecord]) -> List[RawEvidenceRecord]:
    """Stage 1.6 verifiability filter: require a reproducible artifact."""
    return [r for r in records
            if r.counterexample is not None or r.failing_trace is not None or r.failing_subgoal is not None]


def filter_evidence(records: List[RawEvidenceRecord], spec: SpecModule) -> List[RawEvidenceRecord]:
    """Apply the Stage 1-2 deterministic pre-filters (scope, status, verifiability)."""
    return filter_verifiable(filter_status(filter_scope(records, spec)))


def apply_pinning(records: List[RawEvidenceRecord], pinned_refs: Set[str]) -> None:
    """End of Step 5: pin records referenced by findings that entered the
    verified state; unpin records no longer referenced."""
    for r in records:
        r.pinned = r.evidence_ref in pinned_refs


def check_grounding(finding: Finding) -> bool:
    """Stage 3.13 grounding check: the finding cites a concrete evidence record."""
    return bool(finding.evidence_ref) and finding.evidence_ref != "static_defer"


def check_non_hallucination(finding: Finding, record: RawEvidenceRecord) -> bool:
    """Stage 3.14 non-hallucination check: any counterexample/failing-subgoal
    referenced in the note must appear in the underlying evidence record."""
    # A note that cites a concrete counterexample/subgoal must not invent one.
    if finding.error_class is ErrorClass.COUNTEREXAMPLE and record.counterexample is None:
        return False
    if finding.error_class in (ErrorClass.MISSING_PREMISE, ErrorClass.INDUCTION_FAILURE) \
            and record.failing_subgoal is None:
        return False
    return True


def from_registry_row(row: Dict[str, Any]) -> RawEvidenceRecord:
    """Best-effort mapping from a registry evidence row to a RawEvidenceRecord.

    The registry's generic schema stores `type`/`engine`/`status`/`property_name`
    but NOT `verification_mode` / `error_class` / `counterexample` /
    `related_spec_item_ids` / `source_mapping_ref`.  Those are derived
    heuristically or left at defaults; full fidelity needs a registry schema
    extension (or a JSON payload column).
    """
    ref = str(row.get("ref_value") or row.get("id") or "?")
    prop = str(row.get("property_name") or ref)
    engine = str(row.get("engine") or "")
    status = str(row.get("status") or "")
    etype = str(row.get("type") or "")

    if "theorem" in engine or "coq" in engine or "acl2" in engine:
        source = EvidenceSource.ITP
    elif engine in ("BMC", "IC3", "sby", "model_checking"):
        source = EvidenceSource.MODEL_CHECKING
    else:
        source = EvidenceSource.SIMULATION

    proof_status = {
        "proved": ProofStatus.PROVED,
        "disproved": ProofStatus.DISPROVED,
        "counterexample": ProofStatus.DISPROVED,
        "timeout": ProofStatus.TIMEOUT,
    }.get(status, ProofStatus.INCONCLUSIVE)

    error_class = ErrorClass.COUNTEREXAMPLE if ("counterexample" in etype or "counterexample" in status) \
        else ErrorClass.MISSING_PREMISE

    return RawEvidenceRecord(
        evidence_ref=ref,
        primary_spec_item_id=prop,
        verification_mode=VerificationMode.SELF_CONSISTENCY,   # not stored; caller overrides
        evidence_source=source,
        proof_status=proof_status,
        error_class=error_class,
        source_mapping_ref=row.get("ref_value"),
        evidence_hash=str(abs(hash((ref, prop, engine, status, etype)))),
    )


def retained_view(registry: Any, design_name: str, limit: int = 100) -> List[RawEvidenceRecord]:
    """Query the evidence registry and return the retained RawEvidenceRecord view."""
    rows = registry.list_evidence(design_name=design_name, limit=limit)
    return [from_registry_row(r) for r in rows]


def dedup_minimal(records: List[RawEvidenceRecord]) -> List[RawEvidenceRecord]:
    """Stage 1.4: keep the minimal counterexample per (spec_item_id, error_class)."""
    best = {}
    for r in records:
        key = (r.primary_spec_item_id, r.error_class)
        cur = best.get(key)
        cur_size = len(str(cur.counterexample)) if cur is not None and cur.counterexample is not None else 10 ** 9
        new_size = len(str(r.counterexample)) if r.counterexample is not None else 10 ** 9
        if cur is None or new_size < cur_size:
            best[key] = r
    return list(best.values())


def schema_conformant(finding: Finding) -> bool:
    """Stage 2.10: the finding's controlled-vocabulary fields must be valid."""
    return (isinstance(finding.error_class, ErrorClass)
            and isinstance(finding.issue_attribution, IssueAttribution)
            and isinstance(finding.verification_mode, VerificationMode)
            and isinstance(finding.generation_action, GenerationAction))


def relevant(finding: Finding) -> bool:
    """Stage 2.11 relevance gate: the finding must carry an actionable attribution."""
    return (finding.issue_attribution is not IssueAttribution.UNDETERMINED
            and finding.generation_action is not None)
