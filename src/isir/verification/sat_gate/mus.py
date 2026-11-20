# src/isir/verification/sat_gate/mus.py
#
# Group-MUS on certification intent (§14.5): shrink the failed-assumption core
# to a minimal set of group activation literals (deletion-based MUS).
"""Deletion-based Group-MUS over activation literals."""

from typing import List, Sequence

from isir.verification.sat_gate.assumptions import AssumptionRegistry
from isir.verification.sat_gate.solver_cadical import IncrementalSolver


def group_mus(group_ids: Sequence[str], registry: AssumptionRegistry,
              solver: IncrementalSolver) -> List[str]:
    """Return a minimal subset of ``group_ids`` still UNSAT under the solver.

    Uses deletion-based shrinking: each candidate removal that keeps the
    formula UNSAT is dropped.  The result is a MUS (every proper subset is
    satisfiable).
    """
    core = list(group_ids)
    i = 0
    while i < len(core):
        candidate = core[:i] + core[i + 1:]
        lits = [registry.activation_literal(g) for g in candidate]
        if solver.solve(assumptions=lits) is False:
            core = candidate
        else:
            i += 1
    return core
