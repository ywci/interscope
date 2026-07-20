# src/specir/lowering/assert_to_verilog_ovl.py
#
# Lowers a unified AssertModule to Verilog OVL (Open Verification Library)
# macro calls. Supports only boolean always checks and covers; temporal
# properties (sequences, eventually, until) are not supported and will
# raise NotImplementedError. Simple "always" properties expressible as
# Boolean expressions are automatically promoted to ovl_assert_always.

from typing import Optional
from specir.dialects import assert_ir
from specir.utils.expr import parse_sexpr, ExprError
from specir.utils.logger import get_logger

logger = get_logger(__name__)


def _ovl_expr(expr_str: str) -> str:
    """
    Convert a SpecIR S‑expression string into a Verilog boolean expression.

    This is a recursive converter that handles the standard logical,
    comparison, and arithmetic operators.  Temporal operators are not
    supported (the OVL backend rejects them anyway).
    """
    parsed = parse_sexpr(expr_str)

    def _convert(expr):
        if isinstance(expr, bool):
            return "1'b1" if expr else "1'b0"
        if isinstance(expr, int):
            return str(expr)
        if isinstance(expr, str):
            return expr
        if not isinstance(expr, list) or len(expr) == 0:
            return str(expr)

        op = expr[0]
        args = expr[1:]

        if op in ('add', 'sub', 'mul', 'div', 'mod'):
            if len(args) != 2: raise ExprError(f"{op} expects 2 arguments")
            a = _convert(args[0]); b = _convert(args[1])
            vop = {'add': '+', 'sub': '-', 'mul': '*', 'div': '/', 'mod': '%'}[op]
            return f"({a} {vop} {b})"

        elif op == 'and':
            if len(args) != 2: raise ExprError("and expects 2 arguments")
            a = _convert(args[0]); b = _convert(args[1])
            return f"({a} && {b})"
        elif op == 'or':
            if len(args) != 2: raise ExprError("or expects 2 arguments")
            a = _convert(args[0]); b = _convert(args[1])
            return f"({a} || {b})"
        elif op == 'not':
            if len(args) != 1: raise ExprError("not expects 1 argument")
            return f"!{_convert(args[0])}"

        elif op == 'implies':
            if len(args) != 2: raise ExprError("implies expects 2 arguments")
            a = _convert(args[0]); b = _convert(args[1])
            return f"(!{a} || {b})"

        elif op in ('eq', 'neq', 'gt', 'lt', 'gte', 'lte', 'le', 'ge'):
            if len(args) != 2: raise ExprError(f"{op} expects 2 arguments")
            a = _convert(args[0]); b = _convert(args[1])
            vop = {'eq': '==', 'neq': '!=', 'gt': '>', 'lt': '<',
                   'gte': '>=', 'lte': '<=', 'le': '<=', 'ge': '>='}[op]
            return f"({a} {vop} {b})"

        elif op == 'ite':
            if len(args) != 3: raise ExprError("ite expects 3 arguments")
            cond = _convert(args[0])
            then_expr = _convert(args[1])
            else_expr = _convert(args[2])
            return f"({cond} ? {then_expr} : {else_expr})"

        elif op == 'read':
            if len(args) != 1: raise ExprError("read expects 1 argument")
            name = args[0]
            if isinstance(name, str):
                return name
            raise ExprError("read argument must be a signal name string")

        elif op == 'slice':
            if len(args) != 3: raise ExprError("slice expects 3 arguments")
            e = _convert(args[0])
            h = int(_convert(args[1]))
            l = int(_convert(args[2]))
            return f"{e}[{h}:{l}]"

        elif op in ('next', 'prev', 'rose', 'fell', 'stable'):
            raise ExprError(f"Temporal operator '{op}' is not supported by the OVL backend")

        else:
            raise ExprError(f"Unknown operator '{op}' in OVL expression")

    return _convert(parsed)


def _resolve_clock(op_clock: Optional[str],
                   module_clock: Optional[assert_ir.AssertClockOp]) -> str:
    """Return clock signal name, using module default if per‑op is None."""
    if op_clock:
        return op_clock
    if module_clock:
        return module_clock.clock_name
    return "clk"


def _resolve_reset(op_reset: Optional[str],
                   module_reset: Optional[assert_ir.AssertResetOp]) -> str:
    """
    Return reset signal name for OVL (active‑low expected).

    If the reset condition is a simple signal name (e.g., "rst"), it is
    returned directly.  If it is of the form ``(not <name>)``, the inner
    name is returned.  Otherwise a warning is issued and the raw string
    is returned as a best‑effort.
    """
    if op_reset:
        cond = op_reset
    elif module_reset:
        cond = module_reset.reset_condition
    else:
        return "rst_n"

    cond_stripped = cond.strip()

    if cond_stripped.startswith("(not ") and cond_stripped.endswith(")"):
        inner = cond_stripped[5:-1].strip()
        try:
            parsed = parse_sexpr(inner)
            if isinstance(parsed, str):
                return parsed
        except ExprError:
            pass
        return inner

    try:
        parsed = parse_sexpr(cond_stripped)
        if isinstance(parsed, str):
            return parsed
    except ExprError:
        pass

    logger.warning(
        "Reset condition '%s' is not a simple signal name; "
        "using it as‑is – verify active‑low polarity.",
        cond
    )
    return cond_stripped


def _label_comment(op: object, lang: str = "//") -> str:
    """Return a comment string containing the operation's label, if any."""
    label = getattr(op, 'label', None)
    if label:
        return f"{lang} Property: {label}\n"
    return ""


def _always_to_ovl(always_op: assert_ir.AssertAlwaysOp,
                   instance_counter: int,
                   module_clock: Optional[assert_ir.AssertClockOp],
                   module_reset: Optional[assert_ir.AssertResetOp]) -> str:
    cond = _ovl_expr(always_op.condition)
    clk = _resolve_clock(always_op.clock, module_clock)
    rst = _resolve_reset(always_op.reset, module_reset)
    label = getattr(always_op, 'label', None)
    comment = _label_comment(always_op)
    inst_label = label or f"u_assert_{instance_counter}"
    return f"{comment}ovl_assert_always #(2,0,\"{always_op.condition}\") {inst_label} ({clk}, {rst}, {cond});"


def _cover_to_ovl(cover_op: assert_ir.AssertCoverOp,
                  instance_counter: int,
                  module_clock: Optional[assert_ir.AssertClockOp],
                  module_reset: Optional[assert_ir.AssertResetOp]) -> str:
    cond = _ovl_expr(cover_op.condition)
    clk = _resolve_clock(cover_op.clock, module_clock)
    rst = _resolve_reset(cover_op.reset, module_reset)
    label = getattr(cover_op, 'label', None)
    comment = _label_comment(cover_op)
    inst_label = label or f"u_cover_{instance_counter}"
    return f"{comment}ovl_cover #(2,0,\"{cover_op.condition}\") {inst_label} ({clk}, {rst}, {cond});"


def convert(assert_module: assert_ir.AssertModule) -> str:
    """
    Convert an AssertModule to Verilog OVL code.

    Args:
        assert_module: The unified assert module.

    Returns:
        A string containing Verilog module with OVL macro calls.

    Raises:
        NotImplementedError: If the module contains temporal properties that
                             cannot be lowered to Boolean assertions (i.e.,
                             eventually, until, or sequences).
    """
    # Separate supported "always" properties from unsupported ones
    supported_props = []
    unsupported_props = []
    for p in assert_module.properties:
        if p.kind == "always" and p.operand:
            try:
                _ovl_expr(p.operand)   # test conversion
                supported_props.append(p)
            except ExprError:
                unsupported_props.append(p)
        else:
            unsupported_props.append(p)

    if unsupported_props:
        prop_names = [getattr(p, 'label', '?') for p in unsupported_props]
        raise NotImplementedError(
            f"OVL backend does not support these temporal properties: {prop_names}. "
            "Use the SVA or VHDL PSL backend instead."
        )

    if assert_module.sequences:
        seq_names = [
            getattr(s, 'label', '?') if hasattr(s, 'label') else '?'
            for s in assert_module.sequences
        ]
        raise NotImplementedError(
            f"OVL backend does not support sequences: {seq_names}. "
            "Use the SVA or VHDL PSL backend instead."
        )

    module_clock = assert_module.clock
    module_reset = assert_module.reset

    lines = []
    lines.append("// Generated by InterScope from SpecIR assertion dialect (OVL backend)")
    lines.append(f"// Design: {assert_module.name}")
    lines.append("// Note: Only boolean always checks and covers are supported.")
    lines.append("// Assumptions and simple always properties are emitted as assertions.")
    lines.append("// Ensure `include \"ovl_macros.svh\" is present in the design.")
    lines.append("")
    lines.append(f"module {assert_module.name} ();")
    lines.append("    // OVL monitor instances")
    lines.append("")

    instance_counter = 0

    # Assumptions – emit as assertion checks with a comment
    for a in assert_module.assumptions:
        instance_counter += 1
        cond = _ovl_expr(a.condition)
        clk = _resolve_clock(a.clock, module_clock)
        rst = _resolve_reset(a.reset, module_reset)
        label = getattr(a, 'label', None)
        comment = _label_comment(a)
        inst_label = label or f"u_assume_{instance_counter}"
        lines.append(f"    {comment}// Assumption (checked as assertion): {a.condition}")
        lines.append(f"    ovl_assert_always #(2,0,\"{a.condition}\") {inst_label} ({clk}, {rst}, {cond});")

    # Always checks
    for c in assert_module.always_checks:
        instance_counter += 1
        lines.append(f"    {_always_to_ovl(c, instance_counter, module_clock, module_reset)}")

    # Supported temporal properties (always with boolean operand)
    for p in supported_props:
        instance_counter += 1
        cond = _ovl_expr(p.operand)
        clk = _resolve_clock(p.clock, module_clock)
        rst = _resolve_reset(p.reset, module_reset)
        label = getattr(p, 'label', None)
        comment = _label_comment(p)
        inst_label = label or f"u_prop_{instance_counter}"
        lines.append(f"    {comment}ovl_assert_always #(2,0,\"{p.operand}\") {inst_label} ({clk}, {rst}, {cond});")

    # Covers
    for cv in assert_module.covers:
        instance_counter += 1
        lines.append(f"    {_cover_to_ovl(cv, instance_counter, module_clock, module_reset)}")

    lines.append("")
    lines.append("endmodule")
    lines.append("")
    lines.append("// To use these assertions, bind or instantiate this module alongside the design:")
    lines.append(f"// bind <design_module> {assert_module.name} u_ovl (.*);")

    return "\n".join(lines)
