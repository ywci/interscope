# src/specir/lowering/assert_to_vhdl.py
#
# Lowers a unified AssertModule to VHDL PSL (VHDL-2008) code.
# Uses proper S-expression parsing and generates correct PSL
# assertions with default clock, reset abort, and temporal operators.

from typing import Dict, List, Optional, Union

from specir.dialects import assert_ir
from specir.utils.expr import parse_sexpr, ExprError
from specir.utils.logger import get_logger

logger = get_logger(__name__)


def _vhdl_expr(expr: Union[str, List, int, bool],
               context: str = "boolean") -> str:
    """
    Convert a parsed S‑expression (or raw string) into a VHDL / PSL
    expression string with proper infix notation.
    """
    if isinstance(expr, str):
        try:
            expr = parse_sexpr(expr)
        except ExprError:
            return expr

    if isinstance(expr, bool):
        return "true" if expr else "false"
    if isinstance(expr, int):
        return str(expr)

    if not isinstance(expr, list) or len(expr) == 0:
        return str(expr)

    op = expr[0]
    args = expr[1:]

    # Binary arithmetic
    if op in ('add', 'sub', 'mul', 'div', 'mod'):
        if len(args) != 2:
            raise ValueError(f"{op} expects 2 arguments")
        a = _vhdl_expr(args[0], context)
        b = _vhdl_expr(args[1], context)
        vhdl_op = {'add': '+', 'sub': '-', 'mul': '*', 'div': '/', 'mod': 'mod'}[op]
        return f"({a} {vhdl_op} {b})"

    # Logical operators
    elif op == 'and':
        if len(args) != 2:
            raise ValueError("and expects 2 arguments")
        a = _vhdl_expr(args[0], context)
        b = _vhdl_expr(args[1], context)
        return f"({a} and {b})"
    elif op == 'or':
        if len(args) != 2:
            raise ValueError("or expects 2 arguments")
        a = _vhdl_expr(args[0], context)
        b = _vhdl_expr(args[1], context)
        return f"({a} or {b})"
    elif op == 'not':
        if len(args) != 1:
            raise ValueError("not expects 1 argument")
        a = _vhdl_expr(args[0], context)
        return f"not {a}"

    # Comparison
    elif op in ('eq', 'neq', 'gt', 'lt', 'gte', 'lte', 'le', 'ge'):
        if len(args) != 2:
            raise ValueError(f"{op} expects 2 arguments")
        a = _vhdl_expr(args[0], context)
        b = _vhdl_expr(args[1], context)
        vhdl_op = {'eq': '=', 'neq': '/=', 'gt': '>', 'lt': '<',
                   'gte': '>=', 'lte': '<=', 'le': '<=', 'ge': '>='}[op]
        return f"({a} {vhdl_op} {b})"

    # Implication
    elif op == 'implies':
        if len(args) != 2:
            raise ValueError("implies expects 2 arguments")
        a = _vhdl_expr(args[0], "boolean")
        b = _vhdl_expr(args[1], "boolean")
        if context == "property":
            return f"({a} -> {b})"
        else:
            return f"((not {a}) or {b})"

    # Concatenation / slicing
    elif op == 'concat':
        if len(args) != 2:
            raise ValueError("concat expects 2 arguments")
        a = _vhdl_expr(args[0], context)
        b = _vhdl_expr(args[1], context)
        return f"({a} & {b})"
    elif op == 'slice':
        if len(args) != 3:
            raise ValueError("slice expects 3 arguments")
        e = _vhdl_expr(args[0], context)
        h = int(_vhdl_expr(args[1], context))
        l = int(_vhdl_expr(args[2], context))
        return f"{e}({h} downto {l})"

    # if‑then‑else
    elif op == 'ite':
        if len(args) != 3:
            raise ValueError("ite expects 3 arguments")
        cond = _vhdl_expr(args[0], context)
        then_expr = _vhdl_expr(args[1], context)
        else_expr = _vhdl_expr(args[2], context)
        return f"({then_expr} when {cond} else {else_expr})"

    # read a signal
    elif op == 'read':
        if len(args) != 1:
            raise ValueError("read expects 1 argument")
        name = args[0]
        if isinstance(name, str):
            return name
        raise ValueError("read argument must be a signal name string")

    # Temporal operators (only inside property context)
    elif op == 'next':
        if context != "property":
            raise ValueError("'next' can only be used inside a temporal property")
        if len(args) != 1:
            raise ValueError("next expects 1 argument")
        return f"next {_vhdl_expr(args[0], context)}"
    elif op == 'rose':
        if len(args) != 1:
            raise ValueError("rose expects 1 argument")
        return f"rose({_vhdl_expr(args[0], context)})"
    elif op == 'fell':
        if len(args) != 1:
            raise ValueError("fell expects 1 argument")
        return f"fell({_vhdl_expr(args[0], context)})"
    elif op == 'stable':
        if len(args) != 1:
            raise ValueError("stable expects 1 argument")
        return f"stable({_vhdl_expr(args[0], context)})"

    else:
        raise ValueError(f"Unknown operator '{op}' in VHDL expression")


def _psl_default_clock(clock_op: Optional[assert_ir.AssertClockOp]) -> str:
    """Return PSL default clock declaration if a clock is defined."""
    if clock_op is None:
        return ""
    edge = "rising_edge" if clock_op.edge == "posedge" else "falling_edge"
    return f"default clock is {edge}({clock_op.clock_name});"


def _psl_reset_abort(reset_cond_raw: Optional[str]) -> str:
    """
    Convert a reset condition string into a VHDL expression suitable for
    the ``abort`` clause in PSL.
    """
    if not reset_cond_raw:
        return ""
    try:
        return _vhdl_expr(reset_cond_raw, "boolean")
    except (ExprError, ValueError) as e:
        logger.warning(
            "Could not convert reset condition '%s' to VHDL PSL expression: %s. "
            "Using raw string.",
            reset_cond_raw, e
        )
        return reset_cond_raw


def _label_comment(op: object, lang: str = "--") -> str:
    """Return a comment string containing the operation's label, if any."""
    label = getattr(op, 'label', None)
    return f"{lang} Property: {label}\n" if label else ""


def _assume_to_vhdl(assume: assert_ir.AssertAssumeOp,
                    mod_clock: Optional[assert_ir.AssertClockOp],
                    mod_reset: Optional[assert_ir.AssertResetOp]) -> str:
    cond = _vhdl_expr(assume.condition, "boolean")
    reset_expr = assume.reset if assume.reset else (
        mod_reset.reset_condition if mod_reset else None
    )
    abort_clause = ""
    if reset_expr:
        abort_expr = _psl_reset_abort(reset_expr)
        if abort_expr:
            abort_clause = f" abort {abort_expr}"
    comment = _label_comment(assume)
    return f"{comment}assume always {cond}{abort_clause};"


def _always_to_vhdl(always: assert_ir.AssertAlwaysOp,
                    mod_clock: Optional[assert_ir.AssertClockOp],
                    mod_reset: Optional[assert_ir.AssertResetOp]) -> str:
    cond = _vhdl_expr(always.condition, "boolean")
    reset_expr = always.reset if always.reset else (
        mod_reset.reset_condition if mod_reset else None
    )
    abort_clause = ""
    if reset_expr:
        abort_expr = _psl_reset_abort(reset_expr)
        if abort_expr:
            abort_clause = f" abort {abort_expr}"
    comment = _label_comment(always)
    return f"{comment}assert always {cond}{abort_clause};"


def _property_to_vhdl(prop: assert_ir.AssertPropertyOp,
                      mod_clock: Optional[assert_ir.AssertClockOp],
                      mod_reset: Optional[assert_ir.AssertResetOp]) -> str:
    reset_expr = prop.reset if prop.reset else (
        mod_reset.reset_condition if mod_reset else None
    )
    abort_clause = ""
    if reset_expr:
        abort_expr = _psl_reset_abort(reset_expr)
        if abort_expr:
            abort_clause = f" abort {abort_expr}"
    comment = _label_comment(prop)

    if prop.kind == "always":
        expr = _vhdl_expr(prop.operand, "property") if prop.operand else "true"
        return f"{comment}assert always {expr}{abort_clause};"
    elif prop.kind == "eventually":
        expr = _vhdl_expr(prop.operand, "property") if prop.operand else "true"
        if prop.bound is not None:
            return f"{comment}assert always eventually[0 to {prop.bound}] {expr}{abort_clause};"
        else:
            return f"{comment}assert always eventually! {expr}{abort_clause};"
    elif prop.kind == "until":
        left = _vhdl_expr(prop.left, "property") if prop.left else "true"
        right = _vhdl_expr(prop.right, "property") if prop.right else "true"
        return f"{comment}assert always {left} until {right}{abort_clause};"
    else:
        raise ValueError(f"Unknown property kind: {prop.kind}")


def _cover_to_vhdl(cover: assert_ir.AssertCoverOp,
                   mod_clock: Optional[assert_ir.AssertClockOp],
                   mod_reset: Optional[assert_ir.AssertResetOp]) -> str:
    cond = _vhdl_expr(cover.condition, "boolean")
    comment = _label_comment(cover)
    return f"{comment}cover {{{cond}}};"


def convert(assert_module: assert_ir.AssertModule) -> str:
    """
    Convert an AssertModule to VHDL PSL code (VHDL‑2008).

    The output is a VHDL package containing PSL directives that can be
    referenced by a testbench or verification unit.
    """
    # Reject unsupported sequence operations
    if assert_module.sequences:
        seq_names = [
            getattr(s, 'label', '?') if hasattr(s, 'label') else '?'
            for s in assert_module.sequences
        ]
        raise NotImplementedError(
            f"VHDL PSL backend does not yet support sequences: {seq_names}."
        )

    mod_clock = assert_module.clock
    mod_reset = assert_module.reset

    lines = []
    lines.append("-- Generated by InterScope from SpecIR assertion dialect")
    lines.append(f"-- Design: {assert_module.name}")
    lines.append("")
    lines.append("library ieee;")
    lines.append("use ieee.std_logic_1164.all;")
    lines.append("")

    # Use the assert_module.name directly (already ends with _assertions)
    lines.append(f"package {assert_module.name} is")
    lines.append("")

    # Default clock
    if mod_clock:
        lines.append(f"    {_psl_default_clock(mod_clock)}")
        lines.append("")

    # Assumptions
    for a in assert_module.assumptions:
        lines.append(f"    {_assume_to_vhdl(a, mod_clock, mod_reset)}")

    # Always checks
    for c in assert_module.always_checks:
        lines.append(f"    {_always_to_vhdl(c, mod_clock, mod_reset)}")

    # Properties
    for p in assert_module.properties:
        lines.append(f"    {_property_to_vhdl(p, mod_clock, mod_reset)}")

    # Covers
    for cv in assert_module.covers:
        lines.append(f"    {_cover_to_vhdl(cv, mod_clock, mod_reset)}")

    lines.append("")
    lines.append(f"end package {assert_module.name};")

    return "\n".join(lines)
