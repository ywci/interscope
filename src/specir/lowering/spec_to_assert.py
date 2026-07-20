# src/specir/lowering/spec_to_assert.py
#
# Lowers a SpecModule (spec dialect) to an AssertModule (unified assert dialect).
# Converts spec properties, directives, clocks, and resets into corresponding
# assert operations (always, property, assume, cover, clock, reset).

from typing import Optional
from specir.dialects import spec_ir, assert_ir
from specir.utils.logger import get_logger

logger = get_logger(__name__)


def _expr_to_string(expr) -> str:
    """Convert an S‑expression (string or nested list) to a string representation."""
    if isinstance(expr, str):
        return expr
    if isinstance(expr, list):
        return "(" + " ".join(_expr_to_string(e) for e in expr) + ")"
    return str(expr)


def _build_clock_op(clocks) -> Optional[assert_ir.AssertClockOp]:
    """Create an AssertClockOp from the first clock in the spec module."""
    if not clocks:
        return None
    clk = clocks[0]
    name = clk.get("name", "clk") if isinstance(clk, dict) else getattr(clk, "name", "clk")
    edge = clk.get("edge", "posedge") if isinstance(clk, dict) else getattr(clk, "edge", "posedge")
    return assert_ir.AssertClockOp(clock_name=name, edge=edge)


def _build_reset_op(resets) -> Optional[assert_ir.AssertResetOp]:
    """Create an AssertResetOp from the first reset in the spec module."""
    if not resets:
        return None
    rst = resets[0]
    name = rst.get("name", "rst") if isinstance(rst, dict) else getattr(rst, "name", "rst")
    polarity = rst.get("polarity", "active_high") if isinstance(rst, dict) else getattr(rst, "polarity", "active_high")
    if polarity == "active_low":
        cond = f"(not {name})"
    else:
        cond = name
    return assert_ir.AssertResetOp(reset_condition=cond)


def _convert_temporal_expr(expr: dict) -> assert_ir.AssertPropertyOp:
    """
    Convert a spec property temporal expression (as dict) to an AssertPropertyOp or AssertAlwaysOp.
    Expected dict keys: kind, operand (for always/eventually), left/right (for until), bound.
    """
    kind = expr.get("kind", "always")
    operand = _expr_to_string(expr.get("operand")) if expr.get("operand") else None
    left = _expr_to_string(expr.get("left")) if expr.get("left") else None
    right = _expr_to_string(expr.get("right")) if expr.get("right") else None
    bound = expr.get("bound")

    # For always with a simple boolean (no implication), return an AssertAlwaysOp.
    # Otherwise return a full AssertPropertyOp.
    if kind == "always":
        # If operand contains 'implies' or typical implication symbols, treat as temporal property
        if operand and ("implies" in operand or "->" in operand or "|->" in operand):
            return assert_ir.AssertPropertyOp(kind="always", operand=operand, bound=bound)
        else:
            return assert_ir.AssertAlwaysOp(condition=operand)

    elif kind == "eventually":
        return assert_ir.AssertPropertyOp(kind="eventually", operand=operand, bound=bound)
    elif kind == "until":
        return assert_ir.AssertPropertyOp(kind="until", left=left, right=right, bound=bound)
    else:
        raise ValueError(f"Unknown temporal kind: {kind}")


def convert(spec_module: spec_ir.SpecModule) -> assert_ir.AssertModule:
    """
    Convert a SpecModule to an AssertModule.

    Args:
        spec_module: The spec dialect module.

    Returns:
        An AssertModule containing all assertions and assumptions, with labels
        that reference the original property/directive name for traceability.
    """
    # Extract default clock and reset as dialect objects
    default_clock_op = _build_clock_op(spec_module.clocks)
    default_reset_op = _build_reset_op(spec_module.resets)

    assumptions = []
    always_checks = []
    properties = []
    covers = []

    for directive in spec_module.directive_ops:      # SpecDirectiveOp
        kind = directive.kind                         # "assume", "assert", "cover"
        expr = directive.expression                   # raw S‑expression string
        label = directive.directive_name              # original name

        # Determine per‑directive clock / reset overrides
        eff_clock = directive.clock if directive.clock else default_clock_op
        eff_reset = directive.reset if hasattr(directive, 'reset') and directive.reset else default_reset_op

        if kind == "assume":
            assumptions.append(
                assert_ir.AssertAssumeOp(
                    condition=expr,
                    clock=eff_clock.clock_name if eff_clock else None,
                    reset=eff_reset.reset_condition if eff_reset else None,
                    label=label
                )
            )
        elif kind == "assert":
            always_checks.append(
                assert_ir.AssertAlwaysOp(
                    condition=expr,
                    clock=eff_clock.clock_name if eff_clock else None,
                    reset=eff_reset.reset_condition if eff_reset else None,
                    label=label
                )
            )
        elif kind == "cover":
            covers.append(
                assert_ir.AssertCoverOp(
                    condition=expr,
                    clock=eff_clock.clock_name if eff_clock else None,
                    reset=eff_reset.reset_condition if eff_reset else None,
                    label=label
                )
            )
        else:
            logger.warning(f"Unknown directive kind '{kind}'; ignoring.")

    for prop_op in spec_module.property_ops:          # SpecPropertyOp
        name = prop_op.prop_name
        kind = prop_op.kind                            # safety / liveness / invariant
        expr_dict = prop_op.expression                 # dict with kind, operand, left, right, bound

        # Convert temporal expression – this may return an AssertAlwaysOp for
        # simple boolean invariants, otherwise an AssertPropertyOp.
        assert_op = _convert_temporal_expr(expr_dict)

        # Apply clock/reset defaults if not already set on the operation
        if isinstance(assert_op, assert_ir.AssertAlwaysOp):
            if not assert_op.clock and default_clock_op:
                assert_op.clock = default_clock_op.clock_name
            if not assert_op.reset and default_reset_op:
                assert_op.reset = default_reset_op.reset_condition
            assert_op.label = name
            always_checks.append(assert_op)
        else:
            # It's an AssertPropertyOp (or possibly other)
            if not assert_op.clock and default_clock_op:
                assert_op.clock = default_clock_op.clock_name
            if not assert_op.reset and default_reset_op:
                assert_op.reset = default_reset_op.reset_condition
            assert_op.label = name
            properties.append(assert_op)

        for assum_expr in prop_op.assumes:
            # Create an assume directive that references the property in its label
            assum_label = f"{name}_assume"
            assumptions.append(
                assert_ir.AssertAssumeOp(
                    condition=_expr_to_string(assum_expr),
                    clock=default_clock_op.clock_name if default_clock_op else None,
                    reset=default_reset_op.reset_condition if default_reset_op else None,
                    label=assum_label
                )
            )

    # Assemble the AssertModule
    return assert_ir.AssertModule(
        name=f"{spec_module.name}_assertions",
        clock=default_clock_op,
        reset=default_reset_op,
        assumptions=assumptions,
        always_checks=always_checks,
        properties=properties,
        covers=covers,
        metadata=spec_module.metadata
    )
