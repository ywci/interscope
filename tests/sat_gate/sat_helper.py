# tests/sat_gate/sat_helper.py

from typing import Dict, Optional, Sequence


def dpll_sat(clauses: Sequence[Sequence[int]], nvars: int) -> Optional[Dict[int, bool]]:
    """Return a satisfying assignment (var -> bool) or None.

    Simple DPLL: unit propagation + pure-literal elimination is omitted (the
    test formulas are tiny, so plain backtracking suffices).
    """
    clauses = [list(c) for c in clauses]

    def assign_lit(assign, lit):
        assign[abs(lit)] = lit > 0

    def clause_status(c, assign):
        has_unassigned = False
        for lit in c:
            v = assign.get(abs(lit))
            if v is None:
                has_unassigned = True
            elif v == (lit > 0):
                return "sat"
        return "unit" if has_unassigned else "unsat"

    def search(assign):
        # unit propagation
        changed = True
        while changed:
            changed = False
            for c in clauses:
                st = clause_status(c, assign)
                if st == "unsat":
                    return None
                if st == "unit":
                    # find the sole unassigned literal
                    unassigned = [l for l in c if abs(l) not in assign]
                    if len(unassigned) == 1:
                        assign_lit(assign, unassigned[0])
                        changed = True
        # all clauses sat?
        if all(clause_status(c, assign) == "sat" for c in clauses):
            return assign
        # pick an unassigned var
        var = next((v for v in range(1, nvars + 1) if v not in assign), None)
        if var is None:
            return assign if all(clause_status(c, assign) == "sat" for c in clauses) else None
        for val in (True, False):
            nxt = dict(assign)
            nxt[var] = val
            r = search(nxt)
            if r is not None:
                return r
        return None

    return search({})


def vars_of(clauses: Sequence[Sequence[int]]) -> int:
    if not clauses:
        return 0
    return max(abs(l) for c in clauses for l in c)
