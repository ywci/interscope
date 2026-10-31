# src/isir/verification/combinational_check.py
#
# Combinational-property differential: evaluate each combinational property's
# `operand` and `reference` under the reference interpreter (eval_expr) on
# random inputs (respecting the property's `assumes`) and check they agree.
#
# This detects *semantically wrong* properties (e.g. a `reference` that wraps to
# an unintended value) independent of the ACL2/Koika prover, complementing the
# step-refinement verification (which does not touch property statements).

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from isir.dialects.isir import SpecModule
from isir.utils.expr import ExprError, eval_expr, parse_sexpr, unfold_user_functions


def _width_of_type(dt: str) -> int:
    if dt == "bool":
        return 1
    if isinstance(dt, str) and dt.startswith("bits<"):
        return int(dt[5:-1])
    return 1


@dataclass
class CombinationalCheckResult:
    prop_name: str
    status: str = "agree"          # agree | divergent | error
    case: int = 0
    operand_value: Any = None
    reference_value: Any = None
    inputs: Dict[str, Any] = field(default_factory=dict)
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "prop_name": self.prop_name,
            "status": self.status,
            "case": self.case,
            "operand_value": self.operand_value,
            "reference_value": self.reference_value,
            "inputs": self.inputs,
            "message": self.message,
        }


def _eval_sexpr(sexpr: Any, inputs: Dict[str, Any], widths: Dict[str, int]) -> Any:
    return eval_expr(sexpr, state={}, inputs=inputs, memories={}, width=None, widths=widths)


def check_combinational_properties(
    spec: SpecModule, num_cases: int = 50, seed: int = 0
) -> List[CombinationalCheckResult]:
    """Evaluate each combinational property on random inputs and report any
    disagreement between `operand` and `reference`."""
    widths = {i.name: _width_of_type(i.data_type) for i in spec.inputs}
    # Only inline DEFINED, NON-recursive functions (recursive inlining is
    # exponential; recursive calls are left as-is and will report "error").
    functions = [f for f in (getattr(spec, "functions", None) or [])
                 if f.get("body") is not None and not f.get("recursive")]

    results: List[CombinationalCheckResult] = []
    rng = random.Random(seed)

    for prop in spec.property_ops:
        if prop.expression.get("kind") != "combinational":
            continue
        operand = prop.expression.get("operand")
        reference = prop.expression.get("reference")
        if operand is None or reference is None:
            continue

        try:
            operand_parsed = parse_sexpr(unfold_user_functions(operand, functions))
        except ExprError as e:
            results.append(CombinationalCheckResult(prop.prop_name, "error", message=f"operand: {e}"))
            continue
        try:
            ref_raw = reference if not isinstance(reference, str) else reference
            reference_parsed = parse_sexpr(unfold_user_functions(ref_raw, functions))
        except ExprError as e:
            results.append(CombinationalCheckResult(prop.prop_name, "error", message=f"reference: {e}"))
            continue

        assumes_parsed = []
        for assume in getattr(prop, "assumes", None) or []:
            try:
                assumes_parsed.append(parse_sexpr(unfold_user_functions(assume, functions)))
            except ExprError:
                pass

        divergent = None
        for case in range(num_cases):
            inputs = {name: rng.getrandbits(w) for name, w in widths.items()}
            # Respect the property's assumptions: skip inputs that violate them.
            try:
                if any(not _eval_sexpr(a, inputs, widths) for a in assumes_parsed):
                    continue
                v_impl = _eval_sexpr(operand_parsed, inputs, widths)
                v_ref = _eval_sexpr(reference_parsed, inputs, widths)
            except ExprError as e:
                divergent = CombinationalCheckResult(prop.prop_name, "error", case, message=str(e))
                break
            if v_impl != v_ref:
                divergent = CombinationalCheckResult(
                    prop.prop_name, "divergent", case, v_impl, v_ref, inputs,
                    f"operand != reference at case {case}")
                break

        results.append(divergent or CombinationalCheckResult(prop.prop_name, "agree"))

    return results

