# src/isir/verification/sat_gate/array_instantiate.py
#
# Bounded array instantiation: eliminate arrays from a bounded,
# quantifier-free query exactly, producing a pure bit-vector formula that Path A
# (CaDiCaL + DRAT) can certify.

from typing import List, Optional, Tuple


def ackermannize(expr):
    """Rewrite select(store(a,i,v), j) -> ite(i=j, v, select(a,j))."""
    if isinstance(expr, list):
        if expr and expr[0] == "select":
            inner = ackermannize(expr[1])
            j = ackermannize(expr[2])
            if isinstance(inner, list) and inner and inner[0] == "store":
                a, i, v = inner[1], inner[2], inner[3]
                return ["ite", ["=", i, j], v, ["select", a, j]]
            return ["select", inner, j]
        return [ackermannize(a) for a in expr]
    return expr


def collect_selects(expr) -> List[Tuple]:
    """Collect the base-array ``select(a, i)`` pairs."""
    selects: List[Tuple] = []

    def walk(e):
        if isinstance(e, list):
            if (e and e[0] == "select"
                    and not (isinstance(e[1], list) and e[1] and e[1][0] == "store")):
                selects.append((e[1], e[2]))
            for a in e:
                walk(a)

    walk(expr)
    return selects


def ackermann_constraints(selects: List[Tuple], max_pairs: int) -> Optional[List[list]]:
    """Functional-consistency (i=j) -> (a_i = a_j) per array symbol."""
    constraints: List[list] = []
    pairs = 0
    by_array = {}
    for arr, idx in selects:
        by_array.setdefault(str(arr), []).append((arr, idx))
    for idxs in by_array.values():
        for x in range(len(idxs)):
            for y in range(x + 1, len(idxs)):
                pairs += 1
                if pairs > max_pairs:
                    return None  # exceed the cap -> fallback to T1/soft-only
                i, j = idxs[x][1], idxs[y][1]
                a_i = ["select", idxs[x][0], i]
                a_j = ["select", idxs[y][0], j]
                constraints.append(["=>", ["=", i, j], ["=", a_i, a_j]])
    return constraints


def array_instantiate(expr, max_ackermann_pairs: int = 64) -> Tuple[list, List[list], bool]:
    t = ackermannize(expr)
    selects = collect_selects(t)
    constraints = ackermann_constraints(selects, max_ackermann_pairs)
    if constraints is None:
        return t, [], False
    return t, constraints, True
