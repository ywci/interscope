# src/isir/verification/sat_gate/drat.py
#
# Minimal independent DRAT proof checker (RUP + RAT), used to certify UNSAT at
# T3 without depending on an external drat-trim.  This is the checker the
# certificate points at; it is deliberately simple and auditable.
"""DRAT proof checking (RUP + RAT)."""

from typing import Iterable, List, Sequence, Set


def _unit_propagation_conflict(clauses: Sequence[Sequence[int]],
                               units: Sequence[int]) -> bool:
    """True iff unit propagation from ``units`` derives the empty clause."""
    assign = {abs(u): (u > 0) for u in units}
    changed = True
    while changed:
        changed = False
        for c in clauses:
            sat = False
            unassigned: List[int] = []
            for lit in c:
                v = assign.get(abs(lit))
                if v is None:
                    unassigned.append(lit)
                elif v == (lit > 0):
                    sat = True
                    break
            if sat:
                continue
            if not unassigned:
                return True  # conflict
            if len(unassigned) == 1:
                lit = unassigned[0]
                assign[abs(lit)] = lit > 0
                changed = True
    return False


def _check_rup(clauses: Sequence[Sequence[int]], clause: Sequence[int]) -> bool:
    # RUP: unit propagation from ¬clause reaches a conflict.
    return _unit_propagation_conflict(clauses, [-l for l in clause])


def _check_rat(clauses: Sequence[Sequence[int]], clause: Sequence[int]) -> bool:
    # RAT: for some pivot literal l, every clause D containing ¬l has
    # (C ∪ D \ {¬l}) as a RUP.
    for pivot in clause:
        ok = True
        for d in clauses:
            if -pivot not in d:
                continue
            resolvent = list(set(clause) | (set(d) - {-pivot}))
            if not _check_rup(clauses, resolvent):
                ok = False
                break
        if ok:
            return True
    return False


def check_drat(formula: Sequence[Sequence[int]],
               proof_lines: Iterable[str]) -> bool:
    """Check a DRAT proof; True iff it derives the empty clause.

    ``proof_lines`` are DIMACS-style lines: ``<lits> 0`` (add) or
    ``d <lits> 0`` (delete).  Each added non-empty clause must be a RUP or RAT
    w.r.t. the current clause database.
    """
    db: List[Set[int]] = [set(c) for c in formula]
    for line in proof_lines:
        line = line.strip()
        if not line:
            continue
        toks = line.split()
        if toks[0] == "d":
            c = {int(t) for t in toks[1:] if t != "0"}
            db = [d for d in db if d != c]
            continue
        c = [int(t) for t in toks if t != "0"]
        if not c:
            # empty clause: the refutation; it must itself be a RUP.
            return _check_rup(db, [])
        if not (_check_rup(db, c) or _check_rat(db, c)):
            return False
        db.append(set(c))
    return False
