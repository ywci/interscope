# src/specir/lowering/assert_to_sva.py
#
# Lowers a unified AssertModule to Yosys‑compatible SystemVerilog assertions.
#
# This backend generates a module with **scalar input ports only** so that no
# vector port declarations (`input [N-1:0]`) ever appear.  Multi‑bit signals
# are represented inside assertion expressions as concatenations of scalar
# ports:
#
#   {sig_7, sig_6, sig_5, sig_4, sig_3, sig_2, sig_1, sig_0}
#
# `slice` expressions over known multi‑bit signals are expanded into the
# corresponding concatenation of the selected scalar ports.  This completely
# removes `[` and `]` characters from the module header and assertion lines.

import re
from typing import Dict, List, Optional, Set, Union
from specir.dialects import assert_ir
from specir.utils.expr import parse_sexpr, ExprError
from specir.utils.logger import get_logger

logger = get_logger(__name__)


def _sanitize_signal_name(name: str) -> str:
    """Replace any character that is not a valid Verilog identifier with `_`."""
    if re.fullmatch(r'[a-zA-Z_][a-zA-Z0-9_]*', name):
        return name
    sanitised = re.sub(r'[^a-zA-Z0-9_]', '_', name)
    if not sanitised or not (sanitised[0].isalpha() or sanitised[0] == '_'):
        sanitised = '_' + sanitised
    return sanitised


def _label_comment(op: object, lang: str = "//") -> str:
    label = getattr(op, 'label', None)
    return f"{lang} Property: {label}\n" if label else ""


def _collect_signals_robust(assert_module: assert_ir.AssertModule) -> Set[str]:
    signals: Set[str] = set()
    ops = (
        assert_module.assumptions +
        assert_module.always_checks +
        assert_module.properties +
        assert_module.covers
    )
    for op in ops:
        for attr in ("condition", "operand", "left", "right"):
            expr_str = getattr(op, attr, None)
            if expr_str:
                try:
                    parsed = parse_sexpr(expr_str)
                    _collect_from_parsed(parsed, signals)
                except ExprError:
                    signals.add(expr_str.strip())
    return signals


_KNOWN_OPERATORS = {
    "and", "or", "not", "eq", "neq", "gt", "lt", "gte", "lte", "le", "ge",
    "add", "sub", "mul", "div", "mod", "implies", "concat", "slice", "ite",
    "read", "write", "mem_read", "mem_write", "next", "prev", "rose", "fell",
    "stable"
}


def _collect_from_parsed(expr, signals):
    if isinstance(expr, (int, bool)):
        return
    if isinstance(expr, str):
        if expr not in _KNOWN_OPERATORS:
            signals.add(expr)
        return
    if isinstance(expr, list):
        for child in expr:
            _collect_from_parsed(child, signals)


def _bit_name(sig_name: str, bit_index: int) -> str:
    return f"{sig_name}_{bit_index}"


def _signal_to_verilog(signal_name: str,
                       width: int,
                       high: Optional[int] = None,
                       low: Optional[int] = None) -> str:
    """Convert a signal (or slice) to scalar concatenation."""
    if width == 1:
        return _sanitize_signal_name(signal_name)

    if high is None:
        high = width - 1
        low = 0
    elif low is None:
        low = high

    if high < low:
        high, low = low, high

    if high == low:
        return _sanitize_signal_name(_bit_name(signal_name, high))

    bits = [
        _sanitize_signal_name(_bit_name(signal_name, i))
        for i in range(high, low - 1, -1)
    ]
    return "{ " + ", ".join(bits) + " }"


def _is_signal_reference(expr, signal_widths: Dict[str, int]) -> Optional[str]:
    if isinstance(expr, str) and expr in signal_widths:
        return expr
    if (isinstance(expr, list) and len(expr) >= 2 and expr[0] == "read"
            and isinstance(expr[1], str) and expr[1] in signal_widths):
        return expr[1]
    return None


def _infer_width(expr, signal_widths: Dict[str, int]) -> int:
    """Heuristic width inference for temporary wires."""
    if isinstance(expr, (int, bool)):
        return 1
    if isinstance(expr, str):
        return signal_widths.get(expr, 1)
    if not isinstance(expr, list) or len(expr) == 0:
        return 1

    op = expr[0]
    args = expr[1:]

    if op in ('eq', 'neq', 'gt', 'lt', 'gte', 'lte', 'le', 'ge'):
        return 1
    elif op in ('and', 'or', 'not', 'implies'):
        return 1
    elif op == 'ite':
        if len(args) >= 3:
            return max(_infer_width(args[1], signal_widths),
                       _infer_width(args[2], signal_widths))
    elif op in ('add', 'sub', 'mul', 'div', 'mod'):
        widths = [_infer_width(a, signal_widths) for a in args]
        return max(widths) if widths else 32
    elif op == 'concat':
        return sum(_infer_width(a, signal_widths) for a in args)
    elif op == 'slice':
        if len(args) >= 3:
            try:
                # Fixed: pass None instead of {} to _sva_expr
                high = int(_sva_expr(args[1], signal_widths, None))
                low = int(_sva_expr(args[2], signal_widths, None))
                return high - low + 1
            except (ValueError, TypeError):
                pass
    elif op == 'read':
        if len(args) >= 1:
            return signal_widths.get(args[0], 1)
    return 32


class TempWireCollector:
    """Collects temporary wire declarations and assignments."""
    def __init__(self):
        self.wires: Dict[str, int] = {}      # name -> width
        self.assignments: List[str] = []     # Verilog assign statements

    def add_wire(self, expr_verilog: str, width: int) -> str:
        idx = len(self.wires)
        name = f"__tmp_{idx}"
        self.wires[name] = width
        self.assignments.append(f"  assign {name} = {expr_verilog};")
        return name


def _sva_expr(expr: Union[str, List, int, bool],
              signal_widths: Optional[Dict[str, int]] = None,
              temp: Optional[TempWireCollector] = None) -> str:
    """
    Convert an S‑expression to Verilog.
    `temp` is a TempWireCollector instance used for non‑signal slices.
    """
    if signal_widths is None:
        signal_widths = {}
    if temp is None:
        temp = TempWireCollector()

    if isinstance(expr, str):
        try:
            expr = parse_sexpr(expr)
        except ExprError:
            name = expr.strip()
            if name in signal_widths:
                width = signal_widths[name]
                return _signal_to_verilog(name, width)
            return _sanitize_signal_name(name)

    if isinstance(expr, bool):
        return "1'b1" if expr else "1'b0"
    if isinstance(expr, int):
        return str(expr)

    if not isinstance(expr, list) or len(expr) == 0:
        return str(expr)

    op = expr[0]
    args = expr[1:]

    # Arithmetic
    if op in ('add', 'sub', 'mul', 'div', 'mod'):
        if len(args) != 2:
            raise ValueError(f"{op} expects 2 arguments")
        a = _sva_expr(args[0], signal_widths, temp)
        b = _sva_expr(args[1], signal_widths, temp)
        sv_op = {'add': '+', 'sub': '-', 'mul': '*', 'div': '/', 'mod': '%'}[op]
        return f"({a} {sv_op} {b})"

    # Logical
    elif op == 'and':
        a = _sva_expr(args[0], signal_widths, temp)
        b = _sva_expr(args[1], signal_widths, temp)
        return f"({a} && {b})"
    elif op == 'or':
        a = _sva_expr(args[0], signal_widths, temp)
        b = _sva_expr(args[1], signal_widths, temp)
        return f"({a} || {b})"
    elif op == 'not':
        a = _sva_expr(args[0], signal_widths, temp)
        return f"!{a}"

    # Comparisons
    elif op in ('eq', 'neq', 'gt', 'lt', 'gte', 'lte', 'le', 'ge'):
        a = _sva_expr(args[0], signal_widths, temp)
        b = _sva_expr(args[1], signal_widths, temp)
        sv_op = {'eq': '==', 'neq': '!=', 'gt': '>', 'lt': '<',
                 'gte': '>=', 'lte': '<=', 'le': '<=', 'ge': '>='}[op]
        return f"({a} {sv_op} {b})"

    elif op == 'implies':
        a = _sva_expr(args[0], signal_widths, temp)
        b = _sva_expr(args[1], signal_widths, temp)
        return f"(!({a}) || ({b}))"

    elif op == 'concat':
        a = _sva_expr(args[0], signal_widths, temp)
        b = _sva_expr(args[1], signal_widths, temp)
        return f"{{{a}, {b}}}"

    elif op == 'slice':
        if len(args) != 3:
            raise ValueError("slice expects 3 arguments")
        base = args[0]
        high = int(_sva_expr(args[1], signal_widths, temp))
        low = int(_sva_expr(args[2], signal_widths, temp))

        # Direct signal reference: use scalar concatenation
        signal_name = _is_signal_reference(base, signal_widths)
        if signal_name is not None:
            width = signal_widths[signal_name]
            return _signal_to_verilog(signal_name, width, high=high, low=low)

        # Non‑signal: create temporary wire
        base_verilog = _sva_expr(base, signal_widths, temp)
        width = _infer_width(base, signal_widths)
        tmp_name = temp.add_wire(base_verilog, width)
        return f"{tmp_name}[{high}:{low}]"

    elif op == 'ite':
        cond = _sva_expr(args[0], signal_widths, temp)
        t = _sva_expr(args[1], signal_widths, temp)
        e = _sva_expr(args[2], signal_widths, temp)
        return f"({cond} ? {t} : {e})"

    elif op == 'read':
        name = args[0]
        if name in signal_widths:
            return _signal_to_verilog(name, signal_widths[name])
        return _sanitize_signal_name(name)

    else:
        raise ValueError(f"Unsupported operator '{op}' in procedural assertion")


def convert(assert_module: assert_ir.AssertModule,
            signal_widths: Optional[Dict[str, int]] = None) -> str:
    """
    Convert an AssertModule to Yosys‑compatible SystemVerilog code.

    The generated module contains only **scalar input ports**.  Multi‑bit
    signals are reconstructed inside assertion expressions using
    concatenations of scalar ports.  Slices of non‑signal expressions are
    handled via temporary internal wires.

    Args:
        assert_module: The unified assert module.
        signal_widths: Optional dictionary mapping signal names to their bit
                       widths.  If provided, multi‑bit signals are broken into
                       scalar ports and expanded accordingly.  If omitted, all
                       signals are treated as single‑bit.
    """
    mod_clock = assert_module.clock
    mod_reset = assert_module.reset

    signals = _collect_signals_robust(assert_module)

    if signal_widths is None:
        signal_widths = {}
    widths: Dict[str, int] = {}
    for sig in signals:
        widths[sig] = int(signal_widths.get(sig, 1))

    port_names = []
    port_set = set()

    def _add_port(name: str) -> None:
        if name not in port_set:
            port_set.add(name)
            port_names.append(name)

    if mod_clock:
        _add_port(_sanitize_signal_name(mod_clock.clock_name))

    rst_sig = None
    if mod_reset:
        rst_cond = mod_reset.reset_condition.strip()
        if rst_cond.startswith("(not ") and rst_cond.endswith(")"):
            rst_sig = _sanitize_signal_name(rst_cond[5:-1].strip())
        else:
            try:
                parsed = parse_sexpr(rst_cond)
                if isinstance(parsed, str):
                    rst_sig = _sanitize_signal_name(parsed)
                else:
                    rst_sig = _sanitize_signal_name(rst_cond)
            except ExprError:
                rst_sig = _sanitize_signal_name(rst_cond)
        _add_port(rst_sig)

    for sig in sorted(signals):
        if mod_clock and sig == mod_clock.clock_name:
            continue
        if rst_sig and sig == rst_sig:
            continue

        width = widths[sig]
        sig_sane = _sanitize_signal_name(sig)
        if width == 1:
            _add_port(sig_sane)
        else:
            for i in range(width):
                _add_port(_sanitize_signal_name(_bit_name(sig_sane, i)))

    lines = []
    lines.append("// Generated by InterScope – Yosys‑compatible scalar‑port assertions")
    lines.append(f"// Design: {assert_module.name}")
    lines.append("")

    module_name = _sanitize_signal_name(assert_module.name)
    if port_names:
        lines.append(f"module {module_name} (")
        for idx, p in enumerate(port_names):
            comma = "," if idx < len(port_names) - 1 else ""
            lines.append(f"    input {p}{comma}")
        lines.append(");")
    else:
        lines.append(f"module {module_name} ();")

    lines.append("")

    assertions = []
    temp = TempWireCollector()

    def _try_append_assertion(comment: str, cond_expr: str, note: str = "") -> None:
        try:
            cond = _sva_expr(cond_expr, widths, temp)
        except ValueError as e:
            logger.warning("Skipping assertion: %s", e)
            return
        line = f"{comment}assert ({cond});"
        if note:
            line += f"  // {note}"
        assertions.append(line)

    for a in assert_module.assumptions:
        _try_append_assertion(_label_comment(a), a.condition, "assume")

    for c in assert_module.always_checks:
        _try_append_assertion(_label_comment(c), c.condition)

    for p in assert_module.properties:
        if p.kind == "always" and p.operand:
            _try_append_assertion(_label_comment(p), p.operand)
        else:
            logger.warning(
                "Temporal property '%s' (kind=%s) not supported in procedural mode; skipping.",
                getattr(p, 'label', '?'),
                p.kind,
            )

    for cv in assert_module.covers:
        _try_append_assertion(_label_comment(cv), cv.condition, "cover")

    if temp.wires:
        lines.append("  // Internal wires for non‑signal slice expressions")
        for name, width in temp.wires.items():
            lines.append(f"  wire [{width-1}:0] {name};")
        lines.append("")
        for assign in temp.assignments:
            lines.append(assign)
        lines.append("")

    if assertions:
        clock_name = _sanitize_signal_name(mod_clock.clock_name) if mod_clock else "clk"
        edge = mod_clock.edge if mod_clock else "posedge"

        lines.append(f"  always @({edge} {clock_name}) begin")
        if mod_reset:
            try:
                rst_expr = _sva_expr(mod_reset.reset_condition, widths, temp)
            except Exception:
                rst_expr = _sanitize_signal_name(mod_reset.reset_condition)
            lines.append(f"    if ({rst_expr}) begin")
            lines.append(f"      // reset active – no assertion check")
            lines.append(f"    end else begin")
            for a in assertions:
                lines.append(f"      {a}")
            lines.append(f"    end")
        else:
            for a in assertions:
                lines.append(f"    {a}")
        lines.append(f"  end")

    lines.append("")
    lines.append("endmodule")

    generated = "\n".join(lines)

    header = generated.split(");")[0] + ");"
    if '[' in header or ']' in header:
        raise ValueError(
            f"Generated SVA module header contains bracket characters. "
            f"Header: ...{header[max(0,len(header)-100):]}..."
        )

    return generated
