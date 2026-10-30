# src/isir/lowering/smt_refine.py
#
# Encodes an ISIR expression (S-expression) as SMT-LIB2 bit-vectors and checks
# value refinement between two encodings (e.g. the ISIR reference semantics and
# the Kōika-lowered semantics) by asking z3 whether the negation is satisfiable:
#
#     sat   -> a divergence exists (a counterexample: input, observed vs allowed)
#     unsat -> no divergence within the bounded bit-vector widths (a certificate)
#
# This is a *bounded, exhaustive* counterpart to the random-input differential
# harness (rtl_differential.py): it reasons over all inputs at a fixed width
# instead of sampling a few.

from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from isir.utils.expr import parse_sexpr


def _bit_length(n: int) -> int:
    """Bits needed to represent non-negative n (>= 1)."""
    return max(1, n.bit_length())


def _expr_width(expr: Any, width: int, widths: Dict[str, int]) -> int:
    """The bit-vector width of an expression (mirrors eval_expr's _wrap op_w:
    arithmetic uses the OPERAND width, not the destination width)."""
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
    # comparisons / mem ops: fall back to the wrap width
    return width


def _zero_extend(term: str, delta: int) -> str:
    """Zero-extend a bit-vector term by `delta` bits."""
    return f"((_ zero_extend {delta}) {term})" if delta > 0 else term


def expr_to_smt(expr: Any, width: int, widths: Dict[str, int],
                decls: Set[Tuple[str, int]],
                blackboxes: Optional[Set[str]] = None) -> str:
    """Encode an ISIR S-expression (parsed) as an SMT-LIB2 bit-vector term.

    `width` is the wrap width; `widths` maps register/input names to widths;
    `decls` collects (name, width) variable declarations to emit.
    """
    if isinstance(expr, bool):
        return f"(_ bv{1 if expr else 0} 1)"
    if isinstance(expr, int):
        w = max(width, _bit_length(expr))
        return f"(_ bv{expr} {w})"
    if isinstance(expr, str):
        w = widths.get(expr, width)
        decls.add((expr, w))
        return expr

    op = expr[0]
    args = expr[1:]

    if blackboxes and isinstance(op, str) and op in blackboxes:
        # partial_spec: a bodyless function is non-deterministic, not a silent
        # default.  Encode it as a fresh unconstrained variable.
        w = widths.get(op, width)
        decls.add((op, w))
        return op

    if op == "read":
        name = args[0]
        w = widths.get(name, width)
        decls.add((name, w))
        return name

    if op == "write":
        raise ValueError("write is an action, not an expression")

    if op in ("add", "sub", "and", "or", "xor", "shl", "shr", "lshift", "rshift"):
        # Arithmetic wraps to the OPERAND width (the max of the operands), so
        # literals are encoded at that width, not the destination width.
        wa = _expr_width(args[0], width, widths)
        wb = _expr_width(args[1], width, widths)
        op_w = max(wa, wb)
        a = expr_to_smt(args[0], op_w, widths, decls, blackboxes)
        b = expr_to_smt(args[1], op_w, widths, decls, blackboxes)
        # bvadd/bvshl/... require equal-width operands (e.g. a 3-bit slice used
        # as a shift amount must be widened to the operand width).
        a = _zero_extend(a, op_w - wa)
        b = _zero_extend(b, op_w - wb)
        table = {"add": "bvadd", "sub": "bvsub", "and": "bvand", "or": "bvor",
                 "xor": "bvxor", "shl": "bvshl", "lshift": "bvshl",
                 "shr": "bvlshr", "rshift": "bvlshr"}
        return f"({table[op]} {a} {b})"

    if op == "not":
        op_w = _expr_width(args[0], width, widths)
        a = expr_to_smt(args[0], op_w, widths, decls, blackboxes)
        # eval_expr's `not` is LOGICAL (`return not a`), yielding a 1-bit bool.
        return f"(ite (= {a} (_ bv0 {op_w})) (_ bv1 1) (_ bv0 1))"

    if op == "implies":
        # Boolean implication `(not a) or b`, encoded as 1-bit bit-vectors.
        a = expr_to_smt(args[0], 1, widths, decls, blackboxes)
        b = expr_to_smt(args[1], 1, widths, decls, blackboxes)
        return f"(ite (= {a} (_ bv0 1)) (_ bv1 1) {b})"

    if op in ("eq", "neq", "gt", "lt", "gte", "lte", "le", "ge"):
        wa = _expr_width(args[0], width, widths)
        wb = _expr_width(args[1], width, widths)
        w = max(wa, wb)
        # Encode each operand at its own width, then widen both to the common
        # width (avoids over-extending a literal that _expr_width sized small).
        a = expr_to_smt(args[0], wa, widths, decls, blackboxes)
        b = expr_to_smt(args[1], wb, widths, decls, blackboxes)
        a = _zero_extend(a, w - wa)
        b = _zero_extend(b, w - wb)
        table = {"eq": "=", "neq": "(not (= {0} {1}))",
                 "gt": "bvugt", "lt": "bvult", "gte": "bvuge", "lte": "bvule",
                 "le": "bvule", "ge": "bvuge"}
        if op == "eq":
            return f"(ite (= {a} {b}) (_ bv1 1) (_ bv0 1))"
        if op == "neq":
            return f"(ite (not (= {a} {b})) (_ bv1 1) (_ bv0 1))"
        return f"(ite ({table[op]} {a} {b}) (_ bv1 1) (_ bv0 1))"

    if op == "slice":
        v = expr_to_smt(args[0], width, widths, decls, blackboxes)
        h = args[1]
        l = args[2]
        return f"((_ extract {h} {l}) {v})"

    if op == "concat":
        high = expr_to_smt(args[0], width, widths, decls, blackboxes)
        low = expr_to_smt(args[1], width, widths, decls, blackboxes)
        lw = args[2]
        return f"(concat {high} ((_ extract {lw - 1} 0) {low}))"

    if op == "ite":
        c = expr_to_smt(args[0], width, widths, decls, blackboxes)
        wt = _expr_width(args[1], width, widths)
        wf = _expr_width(args[2], width, widths)
        w = max(wt, wf)
        t = expr_to_smt(args[1], w, widths, decls, blackboxes)
        f = expr_to_smt(args[2], w, widths, decls, blackboxes)
        t = _zero_extend(t, w - wt)
        f = _zero_extend(f, w - wf)
        return f"(ite (= {c} (_ bv0 1)) {f} {t})"

    raise NotImplementedError(f"expr_to_smt: unsupported operator {op}")


def build_value_refinement_query(
    dest: str,
    isir_rhs: Any,
    koika_rhs: Any,
    dest_width: int,
    widths: Dict[str, int],
) -> Tuple[str, Set[Tuple[str, int]]]:
    """Build an SMT-LIB2 query asserting the negation of value refinement for a
    single write: `dest := isir_rhs` vs `dest := koika_rhs`.

    Returns (smt2_text, decls).  `sat` means the two encodings diverge.
    """
    decls: Set[Tuple[str, int]] = set()
    isir = expr_to_smt(isir_rhs, dest_width, widths, decls)
    koika = expr_to_smt(koika_rhs, dest_width, widths, decls)

    decl_lines = [f"(declare-const {name} (_ BitVec {w}))" for name, w in sorted(decls)]
    # Widen both RHS terms to the destination width so the equality is total.
    wi = _expr_width(isir_rhs, dest_width, widths)
    wk = _expr_width(koika_rhs, dest_width, widths)
    w = max(dest_width, wi, wk)
    isir = _zero_extend(isir, w - wi)
    koika = _zero_extend(koika, w - wk)

    lines = [
        "(set-logic QF_BV)",
        *decl_lines,
        f"(assert (not (= {isir} {koika})))",
        "(check-sat)",
        "(get-model)",
    ]
    return "\n".join(lines) + "\n", decls


def run_z3(smt2_text: str, z3_bin: str = "z3") -> Tuple[str, str]:
    """Run z3 on SMT-LIB2 text; return (status, output)."""
    with tempfile.NamedTemporaryFile("w", suffix=".smt2", delete=False) as f:
        f.write(smt2_text)
        path = f.name
    try:
        r = subprocess.run([z3_bin, path], capture_output=True, text=True, timeout=120)
        out = r.stdout or ""
        status = "sat" if "sat" in out.splitlines()[:1] else ("unsat" if "unsat" in out else "error")
        return status, out
    finally:
        Path(path).unlink(missing_ok=True)


def refine_write(dest: str, isir_rhs: Any, koika_rhs: Any, dest_width: int,
                 widths: Dict[str, int], z3_bin: str = "z3") -> Dict[str, Any]:
    """Check value refinement for one write action.

    Returns a dict with status ('unsat' = no divergence, 'sat' = divergence)
    and, on sat, a model line if z3 produced one.
    """
    smt2, decls = build_value_refinement_query(dest, isir_rhs, koika_rhs, dest_width, widths)
    status, out = run_z3(smt2, z3_bin)
    model = ""
    if status == "sat":
        model = "\n".join(l for l in out.splitlines() if l.startswith("  ") or "->" in l)
    return {"status": status, "dest": dest, "decls": sorted(decls), "model": model, "smt2": smt2}


def smt_eval(expr: Any, width: int, widths: Dict[str, int],
             values: Dict[str, int], z3_bin: str = "z3") -> Optional[int]:
    """Evaluate an expression via z3 at the given variable values.

    Returns the bit-vector value as an int, or None if z3 cannot decide.
    """
    decls: Set[Tuple[str, int]] = set()
    term = expr_to_smt(expr, width, widths, decls)
    w = _expr_width(expr, width, widths)

    lines = ["(set-logic QF_BV)"]
    for name, w_ in sorted(decls):
        v = values.get(name, 0) & ((1 << w_) - 1)
        lines.append(f"(declare-const {name} (_ BitVec {w_}))")
        lines.append(f"(assert (= {name} (_ bv{v} {w_})))")
    lines.append("(check-sat)")
    lines.append(f"(get-value ({term}))")
    smt2 = "\n".join(lines) + "\n"

    status, out = run_z3(smt2, z3_bin)
    if status != "sat":
        return None
    # Parse the bit-vector value from the `(get-value ...)` output, e.g.
    # `(((bvadd a b) #x0f))` or `#b00001111` or `(_ bv15 8)`.
    import re
    m = re.search(r"#x([0-9a-fA-F]+)", out)
    if m:
        return int(m.group(1), 16)
    m = re.search(r"#b([01]+)", out)
    if m:
        return int(m.group(1), 2)
    m = re.search(r"\(_ bv(\d+) \d+\)", out)
    if m:
        return int(m.group(1))
    return None


def validate_encoder(expr: Any, width: int, widths: Dict[str, int],
                     samples: List[Dict[str, int]], z3_bin: str = "z3") -> bool:
    """Validate the SMT encoder against eval_expr over `samples` inputs.

    Returns True iff the z3 evaluation of the encoded term matches eval_expr
    for every sample.
    """
    from isir.utils.expr import eval_expr
    state = {}
    memories = {}
    ok = True
    for values in samples:
        expected = eval_expr(expr, state, values, memories, width=width, widths=widths)
        expected = int(expected) if isinstance(expected, (int, bool)) else None
        got = smt_eval(expr, width, widths, values, z3_bin)
        if got != expected:
            ok = False
    return ok


_KOIKA_LITERAL = re.compile(r"\|(\d+)`([bdh])([0-9a-zA-Z_?]+)\|")
_KOIKA_TOKENS = re.compile(r"""
    \s*(
      \( | \) | , |
      \|\d+`[bdh][0-9a-zA-Z_?]+\| |
      read0 | zeroExtend | if | then | else |
      && | \|\| | == | != | <= | >= | < | > |
      \+ | - | \^ | ! |
      [A-Za-z_][A-Za-z0-9_]* | \d+
    )
""", re.VERBOSE)


def _decapitalize(name: str) -> str:
    return name[0].lower() + name[1:] if name else name


def _koika_literal(tok: str) -> Tuple[int, int]:
    """Parse `|W'dV|` (or `|W'b...|`, `|W'h...|`) into (value, width)."""
    m = _KOIKA_LITERAL.match(tok)
    width = int(m.group(1))
    base = m.group(2)
    digits = m.group(3)
    val = int(digits, {"d": 10, "b": 2, "h": 16}[base])
    return val, width


def _koika_to_smt(tokens: List[str], i: List[int], widths: Dict[str, int],
                  decls: Set[Tuple[str, int]]) -> Tuple[str, int]:
    """Recursive-descent encoder for the Kōika Coq DSL emitted by
    `koika_to_rtl._coq_bits_expr`.  Returns (term, width)."""

    def peek() -> str:
        return tokens[i[0]] if i[0] < len(tokens) else ""

    def advance() -> str:
        tok = tokens[i[0]]
        i[0] += 1
        return tok

    tok = advance()
    if tok == "(":
        op = peek()
        if op == "if":
            advance()  # 'if'
            c, _ = _koika_to_smt(tokens, i, widths, decls)
            advance()  # 'then'
            t, wt = _koika_to_smt(tokens, i, widths, decls)
            advance()  # 'else'
            f, wf = _koika_to_smt(tokens, i, widths, decls)
            advance()  # ')'
            return f"(ite (= {c} (_ bv0 1)) {f} {t})", max(wt, wf)
        if op == "!":
            advance()  # '!'
            a, wa = _koika_to_smt(tokens, i, widths, decls)
            advance()  # ')'
            return f"(bvnot {a})", wa
        # binary operator
        a, wa = _koika_to_smt(tokens, i, widths, decls)
        binop = advance()
        b, wb = _koika_to_smt(tokens, i, widths, decls)
        advance()  # ')'
        table = {"+": "bvadd", "-": "bvsub", "&&": "bvand", "||": "bvor",
                 "^": "bvxor", "<": "bvult", "<=": "bvule", ">": "bvugt", ">=": "bvuge",
                 "==": "=", "!=": "distinct"}
        if binop == "==":
            return f"(ite (= {a} {b}) (_ bv1 1) (_ bv0 1))", 1
        if binop == "!=":
            return f"(ite (not (= {a} {b})) (_ bv1 1) (_ bv0 1))", 1
        if binop in ("<", "<=", ">", ">="):
            return f"(ite ({table[binop]} {a} {b}) (_ bv1 1) (_ bv0 1))", 1
        # arithmetic: result width is the operand width (the max of the two)
        return f"({table[binop]} {a} {b})", max(wa, wb)

    if tok == "extcall":
        # partial_spec: an extcall to a bodyless function is non-deterministic
        # (any value of its return type), not a silent default.
        fname = advance()          # e.g. Sigmoid
        # Skip the parenthesized argument (read0(X) etc.) without parsing.
        if peek() == "(":
            depth = 0
            while i[0] < len(tokens):
                t = advance()
                if t == "(":
                    depth += 1
                elif t == ")":
                    depth -= 1
                    if depth == 0:
                        break
        reg = _decapitalize(fname)
        w = widths.get(reg, 1)
        decls.add((reg, w))
        return reg, w

    if tok == "read0":
        advance()  # '('
        name = advance()
        advance()  # ')'
        reg = _decapitalize(name)
        w = widths.get(reg, widths.get(name, 1))
        decls.add((reg, w))
        return reg, w

    if tok == "zeroExtend":
        advance()  # '('
        a, wa = _koika_to_smt(tokens, i, widths, decls)
        advance()  # ','
        target = int(advance())
        advance()  # ')'
        # Kōika `zeroExtend(a, W)` extends `a` to the TARGET width W.
        return f"((_ zero_extend {target - wa}) {a})", target

    if _KOIKA_LITERAL.match(tok):
        val, w = _koika_literal(tok)
        return f"(_ bv{val} {w})", w

    raise NotImplementedError(f"coq_dsl_to_smt: unhandled token {tok!r} (next={peek()!r})")


def coq_dsl_to_smt(text: str, widths: Dict[str, int]) -> Tuple[str, Set[Tuple[str, int]]]:
    """Encode a Kōika Coq DSL expression string (from `_coq_bits_expr`) as SMT-LIB2.

    Returns (term, decls).
    """
    tokens = [t for t in _KOIKA_TOKENS.findall(text) if t.strip()]
    decls: Set[Tuple[str, int]] = set()
    idx = [0]
    term, _ = _koika_to_smt(tokens, idx, widths, decls)
    return term, decls


def _rename_term(term: str, rename: Dict[str, str]) -> str:
    """Rename whole-word identifiers in an SMT term (longest names first)."""
    for old, new in sorted(rename.items(), key=lambda kv: -len(kv[0])):
        term = re.sub(rf"\b{re.escape(old)}\b", new, term)
    return term


def refine_trace(spec: Any, cycles: int, z3_bin: str = "z3") -> Dict[str, Any]:
    """Bounded multi-cycle unrolling: verify the reference and the Kōika
    lowering agree on the register trace for `cycles` cycles.

    Registers evolve per the write actions (last-write-wins); inputs are free
    per cycle.  `unsat` = no divergence within the bound; `sat` = a trace that
    diverges.  `spec` is the ORIGINAL SpecModule (inputs separate from state).
    """
    from isir.lowering.koika_to_rtl import (
        _coq_bits_expr, _capitalize, _has_unsupported_ops, _internalize_inputs,
    )
    from isir.lowering.isir_to_rtl_direct import _width_of
    from isir.utils.expr import parse_sexpr, unfold_user_functions

    # Bodyless functions are partial_spec placeholders (non-deterministic).
    blackboxes = {f.get("name") for f in (getattr(spec, "functions", None) or [])
                  if f.get("body") is None}

    registers = {s.state_name: s for s in spec.state_ops if s.kind == "register"}
    reg_widths = {n: _width_of(s.data_type) for n, s in registers.items()}
    in_widths = {i.name: _width_of(i.data_type) for i in spec.inputs}
    widths = {**reg_widths, **in_widths}
    functions = getattr(spec, "functions", None) or []

    # Internalized spec (inputs become registers) drives the Kōika lowering.
    int_spec = _internalize_inputs(spec)
    int_widths = {s.state_name: _width_of(s.data_type) for s in int_spec.state_ops}
    int_reg_widths = {_capitalize(n): w for n, w in int_widths.items()}

    # Collect the write actions, gated by their rule's condition:
    #   dest := (ite cond rhs (read dest))   — the register holds if the rule
    #   does not fire.  This matches the Kōika rule-merging (last-write-wins).
    writes: List[Tuple[str, Any, int]] = []
    for rule in spec.rule_ops:
        cond = parse_sexpr(unfold_user_functions(rule.condition or "true", functions))
        for act in rule.actions:
            p = parse_sexpr(act)
            if isinstance(p, list) and p and p[0] == "write" and len(p) == 3:
                dest = p[1]
                rhs = parse_sexpr(unfold_user_functions(p[2], functions))
                if _has_unsupported_ops(rhs) or _has_unsupported_ops(cond):
                    continue
                gated = ["ite", cond, rhs, ["read", dest]]
                writes.append((dest, gated, widths.get(dest, 1)))

    all_decls: Set[Tuple[str, int]] = set()
    all_asserts: List[str] = []

    # Initial registers.
    for n, s in sorted(registers.items()):
        w = reg_widths[n]
        if s.initial is None:
            init = 0
        elif s.initial is True:
            init = 1
        else:
            init = int(s.initial)
        all_decls.add((f"{n}_0", w))
        all_asserts.append(f"(= {n}_0 (_ bv{init & ((1 << w) - 1)} {w}))")

    written = {dest for dest, _, _ in writes}

    # Unroll.
    for k in range(cycles):
        # Free inputs this cycle.
        for n, w in in_widths.items():
            all_decls.add((f"{n}_{k}", w))
        # Unwritten registers hold their value.
        for n, w in reg_widths.items():
            if n not in written:
                all_decls.add((f"{n}_{k + 1}", w))
                all_asserts.append(f"(= {n}_{k + 1} {n}_{k})")
        # Written registers: reference + Kōika RHS agree, and define next state.
        for dest, rhs, dw in writes:
            rename = {n: f"{n}_{k}" for n in widths}
            decls: Set[Tuple[str, int]] = set()
            ref = expr_to_smt(rhs, dw, widths, decls, blackboxes)
            dsl = _coq_bits_expr(rhs, int_reg_widths, dw)
            koika, kdecls = coq_dsl_to_smt(dsl, int_widths)
            decls |= kdecls
            ref = _rename_term(ref, rename)
            koika = _rename_term(koika, rename)
            for name, w in sorted(decls):
                all_decls.add((rename.get(name, name), w))
            all_decls.add((f"{dest}_{k + 1}", dw))
            all_asserts.append(f"(= {dest}_{k + 1} {ref})")
            all_asserts.append(f"(not (= {ref} {koika}))")

    lines = ["(set-logic QF_BV)"]
    for name, w in sorted(all_decls):
        lines.append(f"(declare-const {name} (_ BitVec {w}))")
    for a in all_asserts:
        lines.append(f"(assert {a})")
    lines.append("(check-sat)")
    lines.append("(get-model)")
    smt2 = "\n".join(lines) + "\n"
    status, out = run_z3(smt2, z3_bin)
    model = "\n".join(l for l in out.splitlines() if l.startswith("  ") or "->" in l) if status == "sat" else ""
    return {"status": status, "cycles": cycles, "model": model, "smt2": smt2}


def refine_isir_vs_koika(dest: str, isir_rhs: Any, koika_dsl: str, dest_width: int,
                         widths: Dict[str, int], z3_bin: str = "z3",
                         blackboxes: Optional[Set[str]] = None) -> Dict[str, Any]:
    """Check value refinement between the ISIR reference semantics and the
    actual Kōika-lowered Coq DSL for one write action.

    Returns {'status': 'unsat' | 'sat', 'model': ..., 'smt2': ...}.
    """
    decls: Set[Tuple[str, int]] = set()
    isir = expr_to_smt(isir_rhs, dest_width, widths, decls, blackboxes)
    koika, kdecls = coq_dsl_to_smt(koika_dsl, widths)
    decls |= kdecls

    wi = _expr_width(isir_rhs, dest_width, widths)
    isir = _zero_extend(isir, max(dest_width, wi) - wi)

    lines = ["(set-logic QF_BV)"]
    for name, w in sorted(decls):
        lines.append(f"(declare-const {name} (_ BitVec {w}))")
    lines.append(f"(assert (not (= {isir} {koika})))")
    lines.append("(check-sat)")
    lines.append("(get-model)")
    smt2 = "\n".join(lines) + "\n"

    status, out = run_z3(smt2, z3_bin)
    model = "\n".join(l for l in out.splitlines() if l.startswith("  ") or "->" in l) if status == "sat" else ""
    return {"status": status, "dest": dest, "decls": sorted(decls), "model": model, "smt2": smt2}
