# src/isir/verification/sat_gate/smt_encode.py
#
# Independent second encoder: lower a predicate to SMT-LIB QF_BV and solve via
# the z3 binary. This is a DIFFERENT encoding route from the bit-blaster, so
# dual-encoder agreement can catch cross-route divergence.

import re
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional
from isir.utils.expr import parse_sexpr


def _term_width(term, widths: Dict[str, int],
                memories: Optional[Dict[str, "tuple[int, int]"]] = None) -> int:
    """Return the bit width of a term S-expression."""
    if isinstance(term, str):
        term = parse_sexpr(term)
        if isinstance(term, str):
            # a bare signal atom
            if term in widths:
                return widths[term]
            if memories and term in memories:
                return memories[term][0]
            return 1
    if isinstance(term, int):
        return max(1, term.bit_length())
    if isinstance(term, list) and term:
        op = term[0]
        if op == "read":
            return widths[term[1]]
        if op == "mem_read" and memories and term[1] in memories:
            return memories[term[1]][0]
        if op == "slice":
            # structure: ['slice', term, hi, lo]
            return int(term[2]) - int(term[3]) + 1
        if op == "concat":
            return _term_width(term[1], widths, memories) + _term_width(term[2], widths, memories)
        if op == "ite":
            return max(_term_width(term[2], widths, memories),
                       _term_width(term[3], widths, memories))
        if op == "clamp":
            # structure: ['clamp', mode, a, b]
            return min(_term_width(term[2], widths, memories),
                       _term_width(term[3], widths, memories))
        if op == "mul_full":
            return _term_width(term[1], widths, memories) + _term_width(term[2], widths, memories)
        if op in ("add", "sub", "and", "or", "xor", "mul", "div", "mod", "rem"):
            return max(_term_width(term[1], widths, memories),
                       _term_width(term[2], widths, memories))
        if op in ("not", "shl", "shr", "rshift", "lshift"):
            return _term_width(term[1], widths, memories)
    return 1


def _is_memory_term(term, memories) -> bool:
    """True if the term is a memory (array) reference."""
    if not memories:
        return False
    if isinstance(term, str):
        term = parse_sexpr(term)
    if isinstance(term, list) and term:
        op = term[0]
        if op == "read" and term[1] in memories:
            return True
        if op in ("mem_read", "mem_write") and term[1] in memories:
            return True
    return False


def _term(term, widths: Dict[str, int], env: Dict[str, str],
          width: Optional[int] = None,
          memories: Optional[Dict[str, "tuple[int, int]"]] = None) -> str:
    """S-expression term -> SMT-LIB QF_ABV expression string."""
    if isinstance(term, str):
        term = parse_sexpr(term)
    if isinstance(term, bool):
        # a boolean literal in term position is a 1-bit constant.
        return "#b1" if term else "#b0"
    if isinstance(term, int):
        w = width or max(1, term.bit_length())
        return f"(_ bv{term} {w})"
    if isinstance(term, str):
        if term in widths:
            return env[term]
        if memories and term in memories:
            return env[term]
        raise ValueError(f"unknown signal {term!r}")
    if not isinstance(term, list):
        raise ValueError(f"malformed term {term!r}")

    op, args = term[0], term[1:]
    if op == "read":
        return env[args[0]]
    if op == "mem_read":
        mem = args[0]
        idx = _term(args[1], widths, env, memories=memories)
        return f"(select {env[mem]} {idx})"
    if op == "mem_write":
        mem = args[0]
        idx = _term(args[1], widths, env, memories=memories)
        val = _term(args[2], widths, env, memories=memories)
        return f"(store {env[mem]} {idx} {val})"
    if op == "slice":
        a = _term(args[0], widths, env, memories=memories)
        hi, lo = int(args[1]), int(args[2])
        return f"((_ extract {hi} {lo}) {a})"
    if op == "concat":
        a = _term(args[0], widths, env, memories=memories)
        b = _term(args[1], widths, env, memories=memories)
        return f"(concat {a} {b})"
    if op in ("shl", "shr", "rshift", "lshift"):
        a = _term(args[0], widths, env, memories=memories)
        aw = _term_width(args[0], widths, memories)
        n = _term(args[1], widths, env, memories=memories)
        nw = _term_width(args[1], widths, memories)
        if nw < aw:
            n = f"((_ zero_extend {aw - nw}) {n})"
        f = "bvshl" if op in ("shl", "lshift") else "bvlshr"
        return f"({f} {a} {n})"
    if op == "clamp":
        # min/max clamp: result width is the NARROWER operand (the clamp bound).
        mode, a, b = args[0], args[1], args[2]
        wa, wb = _term_width(a, widths, memories), _term_width(b, widths, memories)
        w = min(wa, wb)
        at = _term(a, widths, env, memories=memories)
        bt = _term(b, widths, env, memories=memories)
        if wa > w:
            at = f"((_ extract {w - 1} 0) {at})"
        elif wa < w:
            at = f"((_ zero_extend {w - wa}) {at})"
        if wb > w:
            bt = f"((_ extract {w - 1} 0) {bt})"
        elif wb < w:
            bt = f"((_ zero_extend {w - wb}) {bt})"
        f = "bvule" if mode == "min" else "bvuge"
        return f"(ite ({f} {at} {bt}) {at} {bt})"
    if op == "mul_full":
        # full-width multiply: zero-extend both operands to wa+wb bits.
        wa, wb = _term_width(args[0], widths, memories), _term_width(args[1], widths, memories)
        a = _term(args[0], widths, env, memories=memories)
        b = _term(args[1], widths, env, memories=memories)
        return f"(bvmul ((_ zero_extend {wb}) {a}) ((_ zero_extend {wa}) {b}))"
    if op in ("mul", "div", "mod", "rem"):
        wa, wb = _term_width(args[0], widths, memories), _term_width(args[1], widths, memories)
        w = max(wa, wb)
        a = _term(args[0], widths, env, memories=memories)
        b = _term(args[1], widths, env, memories=memories)
        if wa < w:
            a = f"((_ zero_extend {w - wa}) {a})"
        if wb < w:
            b = f"((_ zero_extend {w - wb}) {b})"
        f = {"mul": "bvmul", "div": "bvudiv", "mod": "bvurem", "rem": "bvurem"}[op]
        return f"({f} {a} {b})"
    if op in ("add", "sub", "and", "or", "xor"):
        # Masking: `and`/`or` with a narrower constant operand truncates the
        # wider operand to the constant's width (e.g. `(and x 255)` -> 8-bit).
        if op in ("and", "or") and isinstance(args[1], int):
            wc = _term_width(args[1], widths, memories)
            ww = _term_width(args[0], widths, memories)
            if wc < ww:
                a = _term(args[0], widths, env, memories=memories)
                b = _term(args[1], widths, env, memories=memories)
                a = f"((_ extract {wc - 1} 0) {a})"
                f = "bvand" if op == "and" else "bvor"
                return f"({f} {a} {b})"
        wa, wb = _term_width(args[0], widths, memories), _term_width(args[1], widths, memories)
        w = max(wa, wb)
        a = _term(args[0], widths, env, memories=memories)
        b = _term(args[1], widths, env, memories=memories)
        if wa < w:
            a = f"((_ zero_extend {w - wa}) {a})"
        if wb < w:
            b = f"((_ zero_extend {w - wb}) {b})"
        f = {"add": "bvadd", "sub": "bvsub", "and": "bvand", "or": "bvor", "xor": "bvxor"}[op]
        return f"({f} {a} {b})"
    if op == "not":
        a = _term(args[0], widths, env, memories=memories)
        return f"(bvnot {a})"
    if op == "ite":
        s = _pred(args[0], widths, env, memories=memories)
        if _is_memory_term(args[1], memories) or _is_memory_term(args[2], memories):
            a = _term(args[1], widths, env, memories=memories)
            b = _term(args[2], widths, env, memories=memories)
            return f"(ite {s} {a} {b})"
        wa, wb = _term_width(args[1], widths, memories), _term_width(args[2], widths, memories)
        w = max(wa, wb)
        a = _term(args[1], widths, env, memories=memories)
        b = _term(args[2], widths, env, memories=memories)
        if wa < w:
            a = f"((_ zero_extend {w - wa}) {a})"
        if wb < w:
            b = f"((_ zero_extend {w - wb}) {b})"
        return f"(ite {s} {a} {b})"
    if op in ("eq", "neq", "le", "ge", "lt", "gt"):
        # comparisons in term position: a 1-bit boolean result.
        wa, wb = _term_width(args[0], widths, memories), _term_width(args[1], widths, memories)
        w = max(wa, wb)
        a = _term(args[0], widths, env, memories=memories)
        b = _term(args[1], widths, env, memories=memories)
        if wa < w:
            a = f"((_ zero_extend {w - wa}) {a})"
        if wb < w:
            b = f"((_ zero_extend {w - wb}) {b})"
        if op == "eq":
            return f"(ite (= {a} {b}) #b1 #b0)"
        if op == "neq":
            return f"(ite (not (= {a} {b})) #b1 #b0)"
        f = {"le": "bvule", "ge": "bvuge", "lt": "bvult", "gt": "bvugt"}[op]
        return f"(ite ({f} {a} {b}) #b1 #b0)"
    raise ValueError(f"unsupported term op {op}")


def _pred(pred, widths: Dict[str, int], env: Dict[str, str],
          memories: Optional[Dict[str, "tuple[int, int]"]] = None) -> str:
    """S-expression predicate -> SMT-LIB Bool expression string."""
    if isinstance(pred, str):
        pred = parse_sexpr(pred)
    if isinstance(pred, bool):
        return "true" if pred else "false"
    if isinstance(pred, str):
        if pred in widths and widths[pred] == 1:
            return f"(= {env[pred]} #b1)"
        raise ValueError(f"unsupported bare predicate {pred!r}")
    if not isinstance(pred, list):
        raise ValueError(f"malformed predicate {pred!r}")

    op, args = pred[0], pred[1:]
    if op == "read":
        # a signal as a predicate: 1-bit equality to #b1.
        return f"(= {env[args[0]]} #b1)"
    if op in ("and", "or"):
        a = _pred(args[0], widths, env, memories=memories)
        b = _pred(args[1], widths, env, memories=memories)
        return f"({op} {a} {b})"
    if op == "not":
        a = _pred(args[0], widths, env, memories=memories)
        return f"(not {a})"
    if op == "implies":
        a = _pred(args[0], widths, env, memories=memories)
        b = _pred(args[1], widths, env, memories=memories)
        return f"(=> {a} {b})"
    if op in ("eq", "neq", "le", "ge", "lt", "gt"):
        # comparison: coerce both operands to the max width (a wider constant,
        # e.g. `(lt count 16)` with a 4-bit count, widens the operand).
        wa, wb = _term_width(args[0], widths, memories), _term_width(args[1], widths, memories)
        w = max(wa, wb)
        a = _term(args[0], widths, env, memories=memories)
        b = _term(args[1], widths, env, memories=memories)
        if wa < w:
            a = f"((_ zero_extend {w - wa}) {a})"
        if wb < w:
            b = f"((_ zero_extend {w - wb}) {b})"
        if op == "eq":
            return f"(= {a} {b})"
        if op == "neq":
            return f"(not (= {a} {b}))"
        f = {"le": "bvule", "ge": "bvuge", "lt": "bvult", "gt": "bvugt"}[op]
        return f"({f} {a} {b})"
    raise ValueError(f"unsupported predicate op {op}")


def _declare(env: Dict[str, str], widths: Dict[str, int],
             memories: Optional[Dict[str, "tuple[int, int]"]] = None) -> List[str]:
    lines = []
    for name, w in widths.items():
        v = name.replace("'", "_p")
        env[name] = v
        lines.append(f"(declare-const {v} (_ BitVec {w}))")
    for name, (elem_w, addr_w) in (memories or {}).items():
        v = name.replace("'", "_p")
        env[name] = v
        lines.append(f"(declare-const {v} (Array (_ BitVec {addr_w}) (_ BitVec {elem_w})))")
    return lines


def solve_smt_ind_step_with_memory(inv_pred, transitions: Dict[str, str],
                                   mem_transitions: Dict[str, str],
                                   widths, memories) -> str:
    """IND_STEP for a memory-bearing design (QF_ABV): Inv ∧ T ∧ ¬Inv'."""
    env: Dict[str, str] = {}
    decls = _declare(env, widths, memories)
    asserts = [f"(assert {_pred(inv_pred, widths, env, memories)})"]
    primed: Dict[str, str] = dict(env)  # inputs map to themselves
    for name, nxt in transitions.items():
        w = widths[name]
        p = name.replace("'", "_p") + "n"
        primed[name] = p
        decls.append(f"(declare-const {p} (_ BitVec {w}))")
        asserts.append(f"(assert (= {p} {_term(nxt, widths, env, memories=memories)}))")
    for mem, nxt in mem_transitions.items():
        elem_w, addr_w = memories[mem]
        p = mem.replace("'", "_p") + "n"
        primed[mem] = p
        decls.append(f"(declare-const {p} (Array (_ BitVec {addr_w}) (_ BitVec {elem_w})))")
        asserts.append(f"(assert (= {p} {_term(nxt, widths, env, memories=memories)}))")
    inv2 = _pred(inv_pred, widths, primed, memories)
    asserts.append(f"(assert (not {inv2}))")
    return _run_smt(decls + asserts)


def solve_smt_base_entail(init_values: Dict[str, int], inv_pred, widths) -> str:
    env: Dict[str, str] = {}
    decls = _declare(env, widths)
    asserts = []
    for name, val in init_values.items():
        w = widths[name]
        asserts.append(f"(assert (= {env[name]} (_ bv{val} {w})))")
    asserts.append(f"(assert (not {_pred(inv_pred, widths, env)}))")
    return _run_smt(decls + asserts)


def solve_smt_ind_step(inv_pred, transitions: Dict[str, str], widths) -> str:
    env: Dict[str, str] = {}
    decls = _declare(env, widths)
    asserts = [f"(assert {_pred(inv_pred, widths, env)})"]
    primed: Dict[str, str] = dict(env)  # inputs map to themselves
    for name, nxt in transitions.items():
        w = widths[name]
        p = name.replace("'", "_p") + "n"
        primed[name] = p
        decls.append(f"(declare-const {p} (_ BitVec {w}))")
        asserts.append(f"(assert (= {p} {_term(nxt, widths, env)}))")
    inv2 = _pred(inv_pred, widths, primed)
    asserts.append(f"(assert (not {inv2}))")
    return _run_smt(decls + asserts)


def solve_smt_ind_step_model(inv_pred, transitions: Dict[str, str], widths,
                             blocked_cubes=None):
    """IND_STEP with the (s, s') models.

    Returns ``(status, s_state, s_prime_state)``; when SAT, both states are
    ``{name: int}`` mappings from the model; otherwise they are None.
    ``blocked_cubes`` (optional) is a list of ``{name: int}`` cubes whose
    conjunctions are asserted false (model blocking for multi-CTI seeding).
    """
    env: Dict[str, str] = {}
    decls = _declare(env, widths)
    asserts = [f"(assert {_pred(inv_pred, widths, env)})"]
    primed: Dict[str, str] = dict(env)
    for name, nxt in transitions.items():
        w = widths[name]
        p = name.replace("'", "_p") + "n"
        primed[name] = p
        decls.append(f"(declare-const {p} (_ BitVec {w}))")
        asserts.append(f"(assert (= {p} {_term(nxt, widths, env)}))")
    asserts.append(f"(assert (not {_pred(inv_pred, widths, primed)}))")
    for cube in (blocked_cubes or []):
        parts = [f"(eq (read {n}) {v})" for n, v in sorted(cube.items())]
        conj = parts[0]
        for p in parts[1:]:
            conj = f"(and {conj} {p})"
        asserts.append(f"(assert (not {conj}))")

    names = " ".join(f"{env[n]} {primed[n]}" for n in widths)
    body = ("(set-logic QF_ABV)\n" + "\n".join(decls + asserts) +
            "\n(check-sat)\n(get-value (" + names + "))\n")
    with tempfile.NamedTemporaryFile("w", suffix=".smt2", delete=False) as f:
        f.write(body)
        path = Path(f.name)
    try:
        proc = subprocess.run(["z3", str(path)], capture_output=True, text=True, timeout=60)
    except FileNotFoundError:
        return ("unknown", None, None)
    out = proc.stdout
    if out.startswith("unsat"):
        return ("unsat", None, None)
    if out.startswith("sat"):
        s_state: Dict[str, int] = {}
        s_prime: Dict[str, int] = {}
        for name, w in widths.items():
            m = re.search(r"\(\(?" + re.escape(env[name]) + r"\s+#x([0-9a-f]+)\)", out)
            if m:
                s_state[name] = int(m.group(1), 16)
            m = re.search(r"\(\(?" + re.escape(primed[name]) + r"\s+#x([0-9a-f]+)\)", out)
            if m:
                s_prime[name] = int(m.group(1), 16)
        return ("sat", s_state, s_prime)
    return ("unknown", None, None)


def solve_smt_reachability(init_values: Dict[str, int], transitions: Dict[str, str],
                           widths, target_pred, depth: int) -> str:
    """Bounded reachability: Init ∧ (∃ j ≤ depth: target(s_j)).

    SAT means ``target_pred`` is reachable within ``depth`` steps; UNSAT means it
    is unreachable up to that bound (bounded, not unbounded, unreachability).
    """
    env: Dict[str, str] = {}
    decls = _declare(env, widths)
    asserts = []
    for name, val in init_values.items():
        w = widths[name]
        asserts.append(f"(assert (= {env[name]} (_ bv{val} {w})))")

    target_at_steps = [f"{_pred(target_pred, widths, env)}"]  # step 0
    cur: Dict[str, str] = dict(env)
    for step in range(depth):
        nxt: Dict[str, str] = {}
        for name in widths:
            var = f"{name}_{step}"
            nxt[name] = var
            decls.append(f"(declare-const {var} (_ BitVec {widths[name]}))")
        for name, nxt_expr in transitions.items():
            asserts.append(f"(assert (= {nxt[name]} {_term(nxt_expr, widths, cur)}))")
        cur = nxt
        target_at_steps.append(f"{_pred(target_pred, widths, cur)}")

    # the target is reachable at some step j <= depth.
    asserts.append(f"(assert (or {' '.join(target_at_steps)}))")
    return _run_smt(decls + asserts)


def solve_smt_bad_cube_step(local_blocks, transitions: Dict[str, str],
                            widths, cube_pred: str) -> str:
    """BAD_CUBE_STEP(F, b) = F(s) ∧ ¬b(s) ∧ T(s, s') ∧ b(s').

    UNSAT means ``¬b`` is inductive relative to the local blocking clauses F.
    ``local_blocks`` are S-expression predicates over the current state.
    """
    env: Dict[str, str] = {}
    decls = _declare(env, widths)
    asserts = []
    for block in local_blocks:
        asserts.append(f"(assert {_pred(block, widths, env)})")
    asserts.append(f"(assert (not {_pred(cube_pred, widths, env)}))")

    primed: Dict[str, str] = dict(env)
    for name, nxt in transitions.items():
        w = widths[name]
        p = name.replace("'", "_p") + "n"
        primed[name] = p
        decls.append(f"(declare-const {p} (_ BitVec {w}))")
        asserts.append(f"(assert (= {p} {_term(nxt, widths, env)}))")

    asserts.append(f"(assert {_pred(cube_pred, widths, primed)})")
    return _run_smt(decls + asserts)


def solve_smt_bad_cube_step_model(local_blocks, transitions: Dict[str, str],
                                  widths, cube_pred: str):
    """BAD_CUBE_STEP with the predecessor-state model.

    Returns ``(status, state)``: when SAT, ``state`` is a ``{name: int}`` mapping
    of the predecessor state ``s`` from the model; otherwise ``state`` is None.
    """
    env: Dict[str, str] = {}
    decls = _declare(env, widths)
    asserts = []
    for block in local_blocks:
        asserts.append(f"(assert {_pred(block, widths, env)})")
    asserts.append(f"(assert (not {_pred(cube_pred, widths, env)}))")

    primed: Dict[str, str] = dict(env)
    for name, nxt in transitions.items():
        w = widths[name]
        p = name.replace("'", "_p") + "n"
        primed[name] = p
        decls.append(f"(declare-const {p} (_ BitVec {w}))")
        asserts.append(f"(assert (= {p} {_term(nxt, widths, env)}))")

    asserts.append(f"(assert {_pred(cube_pred, widths, primed)})")

    names = " ".join(f"{env[n]}" for n in widths)
    body = ("(set-logic QF_ABV)\n" + "\n".join(decls + asserts) +
            "\n(check-sat)\n(get-value (" + names + "))\n")
    with tempfile.NamedTemporaryFile("w", suffix=".smt2", delete=False) as f:
        f.write(body)
        path = Path(f.name)
    try:
        proc = subprocess.run(["z3", str(path)], capture_output=True, text=True, timeout=60)
    except FileNotFoundError:
        return ("unknown", None)
    out = proc.stdout
    if out.startswith("unsat"):
        return ("unsat", None)
    if out.startswith("sat"):
        state: Dict[str, int] = {}
        for name, w in widths.items():
            m = re.search(r"\(\(?" + re.escape(env[name]) + r"\s+#x([0-9a-f]+)\)", out)
            if m:
                state[name] = int(m.group(1), 16)
        return ("sat", state)
    return ("unknown", None)


def _run_smt(decls_and_asserts: List[str]) -> str:
    body = "(set-logic QF_ABV)\n" + "\n".join(decls_and_asserts) + "\n(check-sat)\n"
    with tempfile.NamedTemporaryFile("w", suffix=".smt2", delete=False) as f:
        f.write(body)
        path = Path(f.name)
    try:
        proc = subprocess.run(["z3", str(path)], capture_output=True, text=True, timeout=60)
    except FileNotFoundError:
        return "unknown"
    out = proc.stdout.strip()
    if out == "sat":
        return "sat"
    if out == "unsat":
        return "unsat"
    return "unknown"
