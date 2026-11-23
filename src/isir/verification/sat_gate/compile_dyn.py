# src/isir/verification/sat_gate/compile_dyn.py
#
# Dynamic obligation compiler: lower an ITP-side predicate (the `always`
# operand) into a bit-blasted formula. Backend-agnostic w.r.t. the model
# encoding path, but it drives the shared bit-blaster.

from typing import Dict, List, Optional, Sequence, Union
from isir.utils.expr import parse_sexpr
from isir.verification.sat_gate.bitblast import BitBlaster


def const_vector(value: int, width: int, blaster: BitBlaster) -> List[int]:
    """Return an LSB-first var list for a constant value."""
    return [
        blaster.const_true() if (value >> i) & 1 else blaster.const_false()
        for i in range(width)
    ]


def lower_term(term: Union[str, int, List], blaster: BitBlaster,
               widths: Dict[str, int], width: Optional[int] = None,
               name_map: Optional[Dict[str, str]] = None) -> List[int]:
    """Lower a term S-expression to an LSB-first var list.

    ``name_map`` remaps ``(read <name>)`` to an interned name (used for the
    primed next-state copy).
    """
    if isinstance(term, str):
        term = parse_sexpr(term)
    if isinstance(term, bool):
        return [blaster.const_true() if term else blaster.const_false()]
    if isinstance(term, int):
        w = width or max(1, term.bit_length())
        return const_vector(term, w, blaster)
    if isinstance(term, str):
        # a bare signal atom (e.g. the `inc` in a rule condition)
        raw = term
        name = name_map.get(raw, raw) if name_map else raw
        if raw in widths:
            w = widths[raw]
            return [blaster.symbols.intern(name, w) + i for i in range(w)]
        raise ValueError(f"unknown signal or term: {raw!r}")
    if not isinstance(term, list) or not term:
        raise ValueError(f"malformed term: {term!r}")

    op = term[0]
    args = term[1:]

    if op == "read":
        raw = args[0]
        name = name_map.get(raw, raw) if name_map else raw
        w = widths[raw]
        return [blaster.symbols.intern(name, w) + i for i in range(w)]
    if op == "const":
        value, w = args[0], args[1]
        return const_vector(int(value), int(w), blaster)
    if op == "slice":
        # (slice term hi lo) -> bits [lo..hi] (LSB-first).
        a = lower_term(args[0], blaster, widths, name_map=name_map)
        hi, lo = int(args[1]), int(args[2])
        return a[lo:hi + 1]
    if op == "concat":
        # (concat high low) -> LSB-first: low ++ high.
        hi = lower_term(args[0], blaster, widths, name_map=name_map)
        lo = lower_term(args[1], blaster, widths, name_map=name_map)
        return lo + hi
    if op in ("add", "sub"):
        a = lower_term(args[0], blaster, widths, name_map=name_map)
        b = lower_term(args[1], blaster, widths, width=len(a), name_map=name_map)
        out = [blaster.cnf.new_var() for _ in a]
        (blaster.blast_add if op == "add" else blaster.blast_sub)(a, b, out)
        return out
    if op == "ite":
        sel = lower_pred(args[0], blaster, widths, name_map=name_map)
        a = lower_term(args[1], blaster, widths, name_map=name_map)
        b = lower_term(args[2], blaster, widths, width=len(a), name_map=name_map)
        out = [blaster.cnf.new_var() for _ in a]
        blaster.blast_ite(sel, a, b, out)
        return out
    if op in ("and", "or", "xor"):
        a = lower_term(args[0], blaster, widths, name_map=name_map)
        b = lower_term(args[1], blaster, widths, width=len(a), name_map=name_map)
        out = [blaster.cnf.new_var() for _ in a]
        blaster.blast_bitwise(op, a, b, out)
        return out
    if op == "not":
        a = lower_term(args[0], blaster, widths, name_map=name_map)
        out = [blaster.cnf.new_var() for _ in a]
        blaster.blast_not(a, out)
        return out
    if op in ("eq", "neq", "le", "ge", "lt", "gt"):
        # comparisons used in term position (1-bit boolean result).
        a = lower_term(args[0], blaster, widths, name_map=name_map)
        b = lower_term(args[1], blaster, widths, width=len(a), name_map=name_map)
        if op == "eq":
            return [blaster.blast_eq(a, b)]
        if op == "neq":
            eq = blaster.blast_eq(a, b)
            out = blaster.cnf.new_var()
            blaster.gate_not(out, eq)
            return [out]
        if op == "le":
            return [blaster.blast_ule(a, b)]
        if op == "ge":
            return [blaster.blast_ule(b, a)]
        if op == "lt":
            return [blaster.blast_ult(a, b)]
        return [blaster.blast_ult(b, a)]
    raise ValueError(f"unsupported term op: {op}")


def lower_pred(pred: Union[str, bool, List], blaster: BitBlaster,
               widths: Dict[str, int],
               name_map: Optional[Dict[str, str]] = None) -> int:
    """Lower a predicate S-expression to a 1-bit var."""
    if isinstance(pred, str):
        pred = parse_sexpr(pred)
    if isinstance(pred, bool):
        return blaster.const_true() if pred else blaster.const_false()
    if isinstance(pred, str):
        # a bare 1-bit signal atom used as a predicate
        raw = pred
        name = name_map.get(raw, raw) if name_map else raw
        if raw in widths and widths[raw] == 1:
            return blaster.symbols.intern(name, 1)
        raise ValueError(f"unsupported bare signal predicate: {raw!r}")
    if not isinstance(pred, list) or not pred:
        raise ValueError(f"malformed predicate: {pred!r}")

    op = pred[0]
    args = pred[1:]

    if op == "read":
        # a signal used directly as a predicate: 1-bit is the var; multi-bit is
        # the OR-reduction (nonzero).
        raw = args[0]
        name = name_map.get(raw, raw) if name_map else raw
        w = widths[raw]
        if w == 1:
            return blaster.symbols.intern(name, 1)
        acc = blaster.symbols.intern(name, w)  # first bit
        for i in range(1, w):
            out = blaster.cnf.new_var()
            blaster.gate_or(out, acc, blaster.symbols.intern(name, w) + i)
            acc = out
        return acc
    if op == "and":
        a = lower_pred(args[0], blaster, widths, name_map=name_map)
        b = lower_pred(args[1], blaster, widths, name_map=name_map)
        out = blaster.cnf.new_var()
        blaster.gate_and(out, a, b)
        return out
    if op == "or":
        a = lower_pred(args[0], blaster, widths, name_map=name_map)
        b = lower_pred(args[1], blaster, widths, name_map=name_map)
        out = blaster.cnf.new_var()
        blaster.gate_or(out, a, b)
        return out
    if op == "not":
        a = lower_pred(args[0], blaster, widths, name_map=name_map)
        out = blaster.cnf.new_var()
        blaster.gate_not(out, a)
        return out
    if op == "implies":
        # (implies a b) = (or (not a) b)
        a = lower_pred(args[0], blaster, widths, name_map=name_map)
        b = lower_pred(args[1], blaster, widths, name_map=name_map)
        na = blaster.cnf.new_var()
        blaster.gate_not(na, a)
        out = blaster.cnf.new_var()
        blaster.gate_or(out, na, b)
        return out
    if op in ("eq", "neq"):
        a = lower_term(args[0], blaster, widths, name_map=name_map)
        b = lower_term(args[1], blaster, widths, width=len(a), name_map=name_map)
        eq = blaster.blast_eq(a, b)
        if op == "eq":
            return eq
        out = blaster.cnf.new_var()
        blaster.gate_not(out, eq)
        return out
    if op in ("le", "ge", "lt", "gt"):
        a = lower_term(args[0], blaster, widths, name_map=name_map)
        b = lower_term(args[1], blaster, widths, width=len(a), name_map=name_map)
        if op == "le":
            return blaster.blast_ule(a, b)
        if op == "ge":
            return blaster.blast_ule(b, a)
        if op == "lt":
            return blaster.blast_ult(a, b)
        return blaster.blast_ult(b, a)
    raise ValueError(f"unsupported predicate op: {op}")


def compile_base_entail(init_values: Dict[str, int], inv_pred: Union[str, List],
                        widths: Dict[str, int]) -> BitBlaster:
    """Compile ``Init ∧ ¬Inv`` (BASE_ENTAIL) to a BitBlaster with unit clauses
    fixing the initial values and a negation unit on the invariant."""
    blaster = BitBlaster()
    # intern the init signal vars + fix them
    for name, val in init_values.items():
        w = widths[name]
        base = blaster.symbols.intern(name, w)
        for i in range(w):
            blaster.cnf.add([base + i if (val >> i) & 1 else -(base + i)])
    inv = lower_pred(inv_pred, blaster, widths)
    blaster.cnf.add([-inv])  # ¬Inv
    return blaster


def compile_ind_step(inv_pred: Union[str, List],
                     transitions: Dict[str, Union[str, List]],
                     widths: Dict[str, int]) -> BitBlaster:
    """Compile ``Inv(s) ∧ T(s,s') ∧ ¬Inv(s')`` (IND_STEP).

    ``transitions`` maps each state signal to its next-state S-expression over
    the current state (e.g. ``{"count": "(add (read count) 1)"}``).
    """
    blaster = BitBlaster()

    # 1. Inv(s) — the invariant on the current state.
    inv = lower_pred(inv_pred, blaster, widths)
    blaster.cnf.add([inv])

    # 2. T(s,s') — for each signal, intern the primed var and tie it to the
    #    lowered next-state expression.
    primed_map: Dict[str, str] = {}
    for name, next_expr in transitions.items():
        w = widths[name]
        nxt = lower_term(next_expr, blaster, widths)
        pname = name + "'"
        primed = [blaster.symbols.intern(pname, w) + i for i in range(w)]
        eq = blaster.blast_eq(primed, nxt)
        blaster.cnf.add([eq])  # primed == nxt
        primed_map[name] = pname

    # 3. ¬Inv(s') — the invariant on the next (primed) state, negated.
    inv_prime = lower_pred(inv_pred, blaster, widths, name_map=primed_map)
    blaster.cnf.add([-inv_prime])

    return blaster


def compile_bad_cube_step_with_selectors(
        local_blocks: Sequence[Union[str, List]],
        transitions: Dict[str, Union[str, List]],
        widths: Dict[str, int],
        cube) -> "tuple[BitBlaster, Dict[tuple, int]]":
    """Compile ``BAD_CUBE_STEP(F, cube)`` with a selector literal per cube literal.

    For each cube literal ``(name, value)`` a fresh selector ``a_l`` is attached
    to BOTH the antecedent (``a_l → ¬l(s)``) and the consequent (``a_l → l(s')``).
    Solving under the assumptions ``{a_l}`` and reading the failed core lets the
    caller drop every literal whose selector is unused by the refutation.
    """
    blaster = BitBlaster()
    for block in local_blocks:
        blaster.cnf.add([lower_pred(block, blaster, widths)])

    # Antecedent ¬b(s) = ∨_l ¬l(s) is a SINGLE clause; the selector gates each
    # ¬l(s) via a_l → ¬l(s) = (¬a_l ∨ ¬l(s)).  Under {a_l} the clause is the
    # plain ∨ ¬l(s); with a_l unassigned the solver can drop the disjunct.
    selectors: Dict[tuple, int] = {}
    antecedent: List[int] = []
    for name, value in sorted(cube):
        sel = blaster.cnf.new_var()
        selectors[(name, value)] = sel
        lit_cur = lower_pred(["eq", ["read", name], value], blaster, widths)
        antecedent.extend([-sel, -lit_cur])   # ¬a_l ∨ ¬l(s)
    blaster.cnf.add(antecedent)

    primed_map: Dict[str, str] = {}
    for name, next_expr in transitions.items():
        w = widths[name]
        nxt = lower_term(next_expr, blaster, widths)
        pname = name + "'"
        primed = [blaster.symbols.intern(pname, w) + i for i in range(w)]
        eq = blaster.blast_eq(primed, nxt)
        blaster.cnf.add([eq])
        primed_map[name] = pname

    for name, value in sorted(cube):
        sel = selectors[(name, value)]
        lit_next = lower_pred(["eq", ["read", name], value], blaster, widths,
                              name_map=primed_map)
        blaster.cnf.add([-sel, lit_next])  # a_l -> l(s')

    return blaster, selectors
