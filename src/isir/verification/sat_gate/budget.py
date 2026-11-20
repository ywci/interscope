# src/isir/verification/sat_gate/budget.py
#
# Conflict budgets calibrated to wall-clock (§14.2).  The terminator sets the
# solver's conflict limit; a budget hit yields None (unknown), never a wrong
# SAT/UNSAT.
"""Wall-clock-calibrated conflict budgets + terminator."""

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from isir.verification.sat_gate.solver_cadical import IncrementalSolver


@dataclass(frozen=True)
class ConflictBudget:
    k_conf: int
    target_ms: float


def _linear_fit(samples: Sequence[Tuple[float, float]]) -> Tuple[float, float]:
    """Least-squares fit of wall_ms = slope * conflicts + intercept."""
    n = len(samples)
    if n == 0:
        return 0.0, 0.0
    mx = sum(s[0] for s in samples) / n
    my = sum(s[1] for s in samples) / n
    num = sum((s[0] - mx) * (s[1] - my) for s in samples)
    den = sum((s[0] - mx) ** 2 for s in samples)
    slope = (num / den) if den else 0.0
    intercept = my - slope * mx
    return slope, intercept


def calibrate_budget(samples: Sequence[Tuple[float, float]],
                     target_ms: float) -> ConflictBudget:
    """Fit (conflicts, wall_ms) samples and pick K_conf for ``target_ms``.

    ``samples`` are (conflict_count, wall_ms) from the unlimited-budget warmup.
    """
    slope, intercept = _linear_fit(samples)
    if slope <= 0:
        k_conf = 1
    else:
        k_conf = max(1, int((target_ms - intercept) / slope))
    return ConflictBudget(k_conf=k_conf, target_ms=target_ms)


def solve_with_budget(solver: IncrementalSolver,
                      assumptions: Optional[List[int]],
                      budget: ConflictBudget) -> Optional[bool]:
    """Solve under ``assumptions`` with the conflict budget set.

    Returns True/False, or None when the budget is hit (unknown — the caller
    must treat this as UNKNOWN, never SAT/UNSAT).
    """
    solver._solver.conf_budget = budget.k_conf
    return solver.solve(assumptions=assumptions)
