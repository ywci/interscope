# src/isir/verification/attribution.py
#
# When a lowering-refinement item fails, determine *what* failed, so the right
# team/step fixes it:
#
#   lowering_bug       the Kōika lowering emitted a DSL that diverges from the
#                      reference → route to lowering repair (finding:
#                      lowering_refinement_violation)
#   spec_ambiguity     the ISIR source itself is ambiguous (e.g. a comparison
#                      against a literal wider than the operand) → translation
#                      review
#   koika_modeling_gap the item uses an operator the Kōika DSL cannot model
#                      (slice/mul/div/mod/mem_*/shl/shr/partial_spec) →
#                      correspondence-relation extension
#   bound_exhausted    the bounded check could not decide within its bound →
#                      increase the bound

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from isir.utils.logger import get_logger

logger = get_logger(__name__)


class AttributionCategory(str, Enum):
    LOWERING_BUG = "lowering_bug"
    SPEC_AMBIGUITY = "spec_ambiguity"
    KOIKA_MODELING_GAP = "koika_modeling_gap"
    BOUND_EXHAUSTED = "bound_exhausted"
    NONE = "none"


# Category → routing + surfaced finding.
_ROUTES = {
    AttributionCategory.LOWERING_BUG: ("lowering repair", "lowering_refinement_violation"),
    AttributionCategory.SPEC_AMBIGUITY: ("translation review", None),
    AttributionCategory.KOIKA_MODELING_GAP: ("correspondence extension", None),
    AttributionCategory.BOUND_EXHAUSTED: ("increase bound", None),
    AttributionCategory.NONE: (None, None),
}


@dataclass
class Attribution:
    item_id: str
    category: AttributionCategory
    reason: str
    route: Optional[str] = None
    finding: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "item_id": self.item_id,
            "category": self.category.value,
            "reason": self.reason,
            "route": self.route,
            "finding": self.finding,
        }


@dataclass
class AttributionReport:
    design: str
    attributions: List[Attribution] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        by_cat: Dict[str, int] = {}
        for a in self.attributions:
            by_cat[a.category.value] = by_cat.get(a.category.value, 0) + 1
        return {
            "design": self.design,
            "attributions": [a.to_dict() for a in self.attributions],
            "summary": by_cat,
        }


def _bit_length(n: int) -> int:
    return max(1, n.bit_length())


def _expr_width(expr: Any, width: int, widths: Dict[str, int]) -> int:
    if isinstance(expr, bool):
        return 1
    if isinstance(expr, int):
        return max(width, _bit_length(expr))
    if isinstance(expr, str):
        return widths.get(expr, width)
    op = expr[0]
    args = expr[1:]
    if op == "read":
        return widths.get(args[0], width)
    if op in ("add", "sub", "and", "or", "xor", "shl", "shr", "lshift", "rshift"):
        return max((_expr_width(a, width, widths) for a in args), default=width)
    if op == "not":
        return 1
    if op == "slice" and len(args) == 3 and isinstance(args[1], int) and isinstance(args[2], int):
        return args[1] - args[2] + 1
    if op == "concat" and len(args) == 3 and isinstance(args[2], int):
        return _expr_width(args[0], width, widths) + args[2]
    if op == "ite" and len(args) == 3:
        return max(_expr_width(args[1], width, widths), _expr_width(args[2], width, widths))
    if op in ("eq", "neq", "gt", "lt", "gte", "lte", "le", "ge"):
        return 1
    return width


_CMP_OPS = ("eq", "neq", "gt", "lt", "gte", "lte", "le", "ge")


def has_spec_ambiguity(expr: Any, width: int, widths: Dict[str, int]) -> bool:
    """Detect a source-level width ambiguity: a comparison against an integer
    literal wider than the other operand (the canonical example is
    `(ge (add x y) 256)` where `x`,`y` are 8-bit and `256` needs 9 bits)."""
    if not isinstance(expr, list) or not expr:
        return False
    op = expr[0]
    args = expr[1:]
    if op in _CMP_OPS and len(args) == 2:
        a, b = args[0], args[1]
        wa = _expr_width(a, width, widths)
        wb = _expr_width(b, width, widths)
        if isinstance(a, int) and _bit_length(a) > wb:
            return True
        if isinstance(b, int) and _bit_length(b) > wa:
            return True
    return any(has_spec_ambiguity(e, width, widths) for e in args if isinstance(e, list))


def attribute_item(item: Any, rhs: Any, width: int, widths: Dict[str, int]) -> Attribution:
    from isir.verification.lowering_refinement import LoweringRefinementStatus

    status = item.status

    if status == LoweringRefinementStatus.PROOF_OUT_OF_SCOPE:
        if item.category == "bound_exhausted":
            return Attribution(item.item_id, AttributionCategory.BOUND_EXHAUSTED,
                               item.detail or "bounded check undecided")
        return Attribution(item.item_id, AttributionCategory.KOIKA_MODELING_GAP,
                           item.detail or "operator outside the Kōika DSL subset")

    if status == LoweringRefinementStatus.BOUNDED_FAIL:
        if has_spec_ambiguity(rhs, width, widths):
            return Attribution(item.item_id, AttributionCategory.SPEC_AMBIGUITY,
                               "comparison against a literal wider than the operand "
                               "(ambiguous source width intent)")
        return Attribution(item.item_id, AttributionCategory.LOWERING_BUG,
                           "the Kōika DSL diverges from the ISIR reference")

    return Attribution(item.item_id, AttributionCategory.NONE, "passing")


def attribute_report(ref_report: Any, spec: Any) -> AttributionReport:
    """Attach a category to every refinement item in a report."""
    from isir.lowering.koika_to_rtl import _internalize_inputs
    from isir.lowering.isir_to_rtl_direct import _width_of
    from isir.utils.expr import parse_sexpr, unfold_user_functions

    int_spec = _internalize_inputs(spec)
    widths = {s.state_name: _width_of(s.data_type) for s in int_spec.state_ops}
    functions = getattr(spec, "functions", None) or []

    # item_id -> (dest width, rhs)  so attribution can run the ambiguity heuristic.
    rhs_map: Dict[str, tuple[int, Any]] = {}
    for rule in spec.rule_ops:
        for act in rule.actions:
            p = parse_sexpr(act)
            if isinstance(p, list) and p and p[0] == "write" and len(p) == 3:
                dest = p[1]
                rhs = parse_sexpr(unfold_user_functions(p[2], functions))
                item_id = f"rule:{rule.rule_name}/write:{dest}"
                rhs_map[item_id] = (widths.get(dest, 1), rhs)

    report_out = AttributionReport(design=ref_report.design)
    for item in ref_report.items:
        dw, rhs = rhs_map.get(item.item_id, (1, item.item_id))
        attr = attribute_item(item, rhs, dw, widths)
        route, finding = _ROUTES[attr.category]
        attr.route = route
        attr.finding = finding
        report_out.attributions.append(attr)

    return report_out


def print_attribution_report(report: AttributionReport) -> None:
    print(f"\n{report.design}: attribution")
    for a in report.attributions:
        finding = f"  [finding: {a.finding}]" if a.finding else ""
        print(f"  [{a.category.value:20}] {a.item_id:40} -> {a.route or '-'}{finding}")
    summary = report.to_dict()["summary"]
    if summary:
        print(f"  summary: {summary}")
