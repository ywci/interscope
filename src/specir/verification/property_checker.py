# src/specir/verification/property_checker.py
#
# Evaluates SpecIR properties (temporal properties, safety, liveness)
# against an abstract trace. Supports always, eventually, until with
# bounded variants, temporal sub-operators (next, prev, rose, fell, stable),
# assumption handling (vacuous truth), and provides detailed results.

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union
from specir.parser.ast import Property, TemporalExpr
from specir.utils.expr import eval_expr, ExprError
from specir.utils.logger import get_logger

logger = get_logger(__name__)


class PropertyCheckError(Exception):
    """Raised when a property cannot be evaluated due to an invalid expression or trace."""
    pass


@dataclass
class PropertyCheckResult:
    """Detailed result of checking a single property against a trace."""
    name: str
    holds: bool
    failing_cycle: Optional[int] = None
    detail: Optional[str] = None
    vacuous: bool = False   # True if an assumption was violated -> property vacuously true


def _evaluate_operand(
    operand: Union[str, List],
    cycle: int,
    trace: List[Dict[str, Any]],
) -> Any:
    """
    Evaluate a boolean operand (S‑expression) at a given cycle.
    Returns the value as a Python object (int, bool, etc.).
    If the expression cannot be evaluated (e.g., temporal operator without context),
    returns False.
    """
    if not operand:
        return True

    cycle_data = trace[cycle]
    state = cycle_data.get("state", {})
    inputs = cycle_data.get("inputs", {})
    outputs = cycle_data.get("outputs", {})
    memories = cycle_data.get("memories", {})

    # Combine state, inputs, outputs for variable lookup.
    context = {}
    # Warn about name collisions between state, inputs and outputs
    # (inputs/outputs are typically disjoint from state names, but checking is cheap)
    for k in state:
        context[k] = state[k]
    for k in inputs:
        if k in context:
            logger.warning(
                "Cycle %d: input '%s' shadows a state variable of the same name. "
                "Expression evaluation may produce unexpected results.",
                cycle, k
            )
        context[k] = inputs[k]
    for k in outputs:
        if k in context:
            logger.warning(
                "Cycle %d: output '%s' shadows a state/input variable of the same name. "
                "Expression evaluation may produce unexpected results.",
                cycle, k
            )
        context[k] = outputs[k]

    # Previous and next cycle states for temporal operators
    prev_state = None
    if cycle > 0:
        prev_cycle = trace[cycle - 1]
        prev_state = prev_cycle.get("state", {})
    next_state = None
    if cycle < len(trace) - 1:
        next_cycle = trace[cycle + 1]
        next_state = next_cycle.get("state", {})

    try:
        result = eval_expr(
            operand,
            state=context,
            inputs=inputs,
            memories=memories,
            previous_state=prev_state,
            next_state=next_state,
        )
        return result
    except ExprError:
        # If evaluation fails (e.g., 'rose' at cycle 0 with no previous state),
        # treat the operand as false so the property check can continue.
        return False


def _check_always(
    operand: Union[str, List],
    trace: List[Dict[str, Any]],
) -> PropertyCheckResult:
    """Check 'always operand' over the whole trace."""
    for i in range(len(trace)):
        val = _evaluate_operand(operand, i, trace)
        if not val:
            return PropertyCheckResult(
                name="",
                holds=False,
                failing_cycle=i,
                detail=f"Operand evaluated to {val} at cycle {i}",
            )
    return PropertyCheckResult(name="", holds=True)


def _check_eventually(
    operand: Union[str, List],
    bound: Optional[int],
    trace: List[Dict[str, Any]],
) -> PropertyCheckResult:
    """Check 'eventually operand' with optional bound."""
    max_cycle = len(trace)
    for i in range(max_cycle):
        if _evaluate_operand(operand, i, trace):
            return PropertyCheckResult(name="", holds=True)
        if bound is not None and i >= bound:
            return PropertyCheckResult(
                name="",
                holds=False,
                detail=f"Operand not satisfied within bound {bound}",
            )
    return PropertyCheckResult(
        name="",
        holds=False,
        detail="Operand never satisfied",
    )


def _check_until(
    left: Union[str, List],
    right: Union[str, List],
    bound: Optional[int],
    trace: List[Dict[str, Any]],
) -> PropertyCheckResult:
    """Check 'left until right' (overlapping: right may hold in the same cycle as left)."""
    max_cycle = len(trace)
    for i in range(max_cycle):
        # Overlapping until: right can hold in the same cycle as left.
        if _evaluate_operand(right, i, trace):
            return PropertyCheckResult(name="", holds=True)
        if not _evaluate_operand(left, i, trace):
            return PropertyCheckResult(
                name="",
                holds=False,
                failing_cycle=i,
                detail="Left operand false before right became true",
            )
        if bound is not None and i >= bound:
            return PropertyCheckResult(
                name="",
                holds=False,
                detail=f"Until not satisfied within bound {bound}",
            )
    return PropertyCheckResult(
        name="",
        holds=False,
        detail="Right operand never became true",
    )


def check_property(prop: Property, trace: List[Dict[str, Any]]) -> PropertyCheckResult:
    """
    Check a single property against an abstract trace.

    Assumptions (prop.assumes) are checked first.  If any assumption fails,
    the property is considered vacuously true.

    Args:
        prop: The property object (from AST).
        trace: List of cycle dictionaries (from lifting).

    Returns:
        PropertyCheckResult indicating whether the property holds, with optional failure details.
    """
    # 1. Check assumptions (if any)
    for assumption in prop.assumes:
        assume_result = _check_always(assumption, trace)
        if not assume_result.holds:
            return PropertyCheckResult(
                name=prop.name,
                holds=True,
                vacuous=True,
                detail=f"Assumption violated at cycle {assume_result.failing_cycle}",
            )

    # 2. Evaluate the main temporal expression
    expr = prop.expression
    if expr.kind == "always":
        result = _check_always(expr.operand, trace)
    elif expr.kind == "eventually":
        result = _check_eventually(expr.operand, expr.bound, trace)
    elif expr.kind == "until":
        result = _check_until(expr.left, expr.right, expr.bound, trace)
    else:
        raise PropertyCheckError(f"Unknown temporal kind: {expr.kind}")

    result.name = prop.name
    return result


def check_all_properties(
    properties: List[Property],
    trace: List[Dict[str, Any]],
) -> List[PropertyCheckResult]:
    """
    Check all properties in a list against a trace.

    Args:
        properties: List of Property AST objects.
        trace: Abstract trace list.

    Returns:
        List of PropertyCheckResult objects.
    """
    results = []
    for prop in properties:
        try:
            result = check_property(prop, trace)
        except PropertyCheckError as e:
            logger.error("Property %s check failed with error: %s", prop.name, e)
            result = PropertyCheckResult(
                name=prop.name,
                holds=False,
                detail=str(e),
            )
        results.append(result)
    return results


def check_properties_from_spec(
    spec_module, trace: List[Dict[str, Any]]
) -> List[PropertyCheckResult]:
    """
    Convenience function: extract properties from a SpecModule (AST) and check them.

    Args:
        spec_module: The parsed SpecIR module (ast.Module).
        trace: Abstract trace list.

    Returns:
        List of PropertyCheckResult objects.
    """
    return check_all_properties(spec_module.properties, trace)


def check_properties_from_spec_dialect(
    spec_module_dialect, trace: List[Dict[str, Any]]
) -> List[PropertyCheckResult]:
    """
    Check properties stored in a SpecIR dialect SpecModule (spec_ir.SpecModule).

    The dialect stores properties as ``SpecPropertyOp`` objects with an expression
    dict.  This function adapts them to AST‑compatible objects on the fly.
    It is provided for future use when the CLI migrates to the dialect‑based
    property representation.
    """
    results = []
    for prop_op in spec_module_dialect.property_ops:
        try:
            expr_dict = prop_op.expression
            temporal_expr = TemporalExpr(
                kind=expr_dict.get("kind", "always"),
                operand=expr_dict.get("operand"),
                left=expr_dict.get("left"),
                right=expr_dict.get("right"),
                bound=expr_dict.get("bound"),
            )
            prop = Property(
                name=prop_op.prop_name,
                kind=prop_op.kind,
                expression=temporal_expr,
                assumes=prop_op.assumes,
                guarantees=prop_op.guarantees,
            )
            result = check_property(prop, trace)
        except Exception as e:
            logger.error("Property %s check error: %s", prop_op.prop_name, e)
            result = PropertyCheckResult(
                name=prop_op.prop_name,
                holds=False,
                detail=str(e),
            )
        results.append(result)
    return results
