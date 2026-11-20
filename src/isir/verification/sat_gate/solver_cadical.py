# src/isir/verification/sat_gate/solver_cadical.py
#
# Resident (incremental) solver wrapper (§12.1, §12.2): persistent clauses,
# assumption-based solving, model + failed-assumption extraction.
#
# pysat's bundled CaDiCaL is one-shot only (its wrapper rejects incr=True), so
# the incremental capability uses Glucose (a §12.1 secondary solver).  The
# one-shot CaDiCaL path with DRAT tracing lives in solver_oneshot.py.
"""Incremental solver wrapper (Glucose: assumptions + failed core)."""

from typing import List, Optional


class IncrementalSolver:
    """Persistent-clause solver with assumptions + failed-assumption core."""

    def __init__(self, clauses: Optional[List[List[int]]] = None) -> None:
        from pysat.solvers import Glucose4
        self._solver = Glucose4(bootstrap_with=list(clauses or []), incr=True)

    def add_clause(self, clause: List[int]) -> None:
        self._solver.add_clause(clause)

    def solve(self, assumptions: Optional[List[int]] = None) -> Optional[bool]:
        """Solve under ``assumptions``; returns True/False or None (unknown)."""
        return self._solver.solve(assumptions=assumptions or [])

    def get_model(self) -> List[int]:
        return self._solver.get_model()

    def get_core(self) -> List[int]:
        """The failed-assumption set (a valid, possibly non-minimal superset)."""
        return self._solver.get_core()

    def delete(self) -> None:
        self._solver.delete()
