# src/isir/lowering/evolving.py
#
# Phase 1 lowering for the Evolving Specification:
#   - `confirmed_projection`  : pending state -> Confirmed specification (Section 4)
#   - `ast_to_evolving`       : preservation pass bridging ast.py's Candidate/OneOf
#                               uncertainty wrappers into the pending state.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional

from isir.dialects.evolving_spec import EvolvingItem, EvolvingSpec, VerificationStatus
from isir.dialects.isir import SpecModule
from isir.parser.ast import Candidate, Module, OneOf


@dataclass
class ConfirmedSpec:
    """The Confirmed specification: the spec body plus the placeholder record.

    Section 4: unresolved placeholders are *lowered* by default (the existing
    lowering emits uninterpreted functions / stubbed rules) or *deferred* when
    the owning item carries `defer_verification: true`.
    """
    spec_module: SpecModule
    lowered_placeholders: List[str] = field(default_factory=list)
    deferred_placeholders: List[str] = field(default_factory=list)


def confirmed_projection(evolving: EvolvingSpec, spec_module: SpecModule) -> ConfirmedSpec:
    """Project the `pending` state to the Confirmed specification (Section 4).

    Bodyless functions are ISIR's partial-spec placeholders.  A placeholder whose
    `spec_item_id` is marked `defer_verification` is carried; all others are
    lowered (uninterpreted).
    """
    deferred = {i.spec_item_id for i in evolving.items if i.defer_verification}
    lowered: List[str] = []
    deferred_placeholders: List[str] = []
    for f in getattr(spec_module, "functions", None) or []:
        fname = f.get("name") if isinstance(f, dict) else getattr(f, "name", None)
        body = f.get("body") if isinstance(f, dict) else getattr(f, "body", None)
        if not fname or body is not None:
            continue  # defined function, not a placeholder
        (deferred_placeholders if fname in deferred else lowered).append(fname)
    return ConfirmedSpec(spec_module, lowered, deferred_placeholders)


def _collect_uncertainty(value: Any, sources: List[str], alternatives: List[Any]) -> bool:
    """Walk a value; collect `Candidate.source` and Candidate/OneOf alternatives.

    Returns True if an unresolved `OneOf` (an ambiguity placeholder) was seen.
    """
    unresolved = False
    if isinstance(value, Candidate):
        if value.source is not None:
            sources.append(value.source)
        alternatives.extend(value.alternatives)
        return _collect_uncertainty(value.value, sources, alternatives)
    if isinstance(value, OneOf):
        alternatives.extend(value.alternatives)
        return value.resolution is None
    if isinstance(value, list):
        for e in value:
            unresolved = _collect_uncertainty(e, sources, alternatives) or unresolved
    return unresolved


def _item_from(name: str, fields: List[Any]) -> EvolvingItem:
    sources: List[str] = []
    alternatives: List[Any] = []
    unresolved = False
    for f in fields:
        unresolved = _collect_uncertainty(f, sources, alternatives) or unresolved
    if not (sources or alternatives or unresolved):
        return None  # type: ignore[return-value]
    return EvolvingItem(
        spec_item_id=name,
        provenance=sources[0] if sources else None,
        alternatives=alternatives,
        partial_spec={"unresolved": True} if unresolved else None,
    )


def ast_to_evolving(module: Module) -> EvolvingSpec:
    """Preservation pass: bridge `ast.py`'s Candidate/OneOf into the `pending` state.

    Each rule / state / property whose fields carry a `Candidate` or `OneOf`
    wrapper becomes an `EvolvingItem` with its `provenance`, `alternatives`, and
    (for unresolved `OneOf`) a `partial_spec` placeholder.  Bodyless functions
    are also emitted as `partial_spec` items.
    """
    items: List[EvolvingItem] = []

    for r in getattr(module, "rules", None) or []:
        item = _item_from(r.name, [getattr(r, "condition", None)] + list(getattr(r, "action", []) or []))
        if item is not None:
            items.append(item)

    for s in getattr(module, "state", None) or []:
        item = _item_from(s.name, [getattr(s, "initial", None)])
        if item is not None:
            items.append(item)

    for p in getattr(module, "properties", None) or []:
        expr = getattr(p, "expression", None)
        operand = getattr(expr, "operand", None) if expr is not None else None
        item = _item_from(p.name, [operand])
        if item is not None:
            items.append(item)

    for fn in getattr(module, "functions", None) or []:
        body = getattr(fn, "body", None)
        if body is None:
            items.append(EvolvingItem(
                spec_item_id=fn.name,
                partial_spec={"unresolved": True},
            ))

    return EvolvingSpec(name=module.name, items=items)


def reset_round(verified: EvolvingSpec, modified_spec_items: set, modified_rtl_items: set) -> EvolvingSpec:
    """Section 6 Round Reset Rule: verified Round k -> pending Round k+1.

    Items reset to `pending` (empty findings, no round) when (1) their spec
    fields changed, (2) their Candidate RTL span changed, or (3) they hold a
    finding implicating a reset item (fixpoint cascade).  Unmodified items keep
    their `verified` state and round.
    """
    to_reset: set = set(modified_spec_items) | set(modified_rtl_items)

    # Fixpoint cascade: an item resets if any finding references a reset item.
    changed = True
    while changed:
        changed = False
        for item in verified.items:
            if item.spec_item_id in to_reset:
                continue
            for f in item.findings:
                implicated = set(f.related_spec_item_ids)
                if f.back_indexed_from is not None:
                    implicated.add(f.back_indexed_from)
                if implicated & to_reset:
                    to_reset.add(item.spec_item_id)
                    changed = True
                    break

    new_items: list = []
    for item in verified.items:
        if item.spec_item_id in to_reset:
            new_items.append(EvolvingItem(
                spec_item_id=item.spec_item_id,
                verification_status=VerificationStatus.PENDING,
                provenance=item.provenance,
                alternatives=list(item.alternatives),
                partial_spec=item.partial_spec,
                defer_verification=item.defer_verification,
                nl_anchor=item.nl_anchor,
                verification_round=None,
                findings=[],
            ))
        else:
            new_items.append(item)
    return EvolvingSpec(name=verified.name, items=new_items)
