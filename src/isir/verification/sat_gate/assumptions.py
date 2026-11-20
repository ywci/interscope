# src/isir/verification/sat_gate/assumptions.py
#
# Activation-literal clause gating (§11.2).  The correct encoding gates a
# multi-literal clause under activation ``a`` as ONE clause
# ``(¬a ∨ l1 ∨ … ∨ ln)`` — never the unit conjunction ``(¬a∨l1) ∧ …``.
"""Activation-literal clause gating."""

from typing import List, Sequence


def gate_clause(activation: int, literals: Sequence[int]) -> List[int]:
    """Return the single gated clause ``(¬a ∨ l1 ∨ … ∨ ln)``.

    ``activation`` is a positive literal id; the returned clause starts with its
    negation.  Exactly one clause is produced regardless of ``len(literals)``.
    """
    return [-activation, *list(literals)]


def gate_clause_set(activation: int, clauses: Sequence[Sequence[int]]) -> List[List[int]]:
    """One gated clause per ``C_i`` (never a unit conjunction per literal)."""
    return [gate_clause(activation, c) for c in clauses]


class AssumptionCapExceeded(Exception):
    """Raised when the activation-literal cap is reached (§11.3: rebuild epoch)."""


class AssumptionRegistry:
    """Injective, immutable group-id -> activation-literal map within an epoch.

    Activation literals are positive integers allocated in order and NEVER
    recycled within an epoch.  On reaching ``max_assumption_vars`` the caller
    rebuilds the epoch (raising :class:`AssumptionCapExceeded` first).
    """

    def __init__(self, max_assumption_vars: int = 65536) -> None:
        self.max_assumption_vars = max_assumption_vars
        self._group_to_lit: "dict[str, int]" = {}
        self._lit_to_group: "dict[int, str]" = {}
        self._next_lit = 1
        self.epoch_rebuilds = 0

    def activation_literal(self, group_id: str) -> int:
        """Return (allocating if new) the activation literal for ``group_id``."""
        if group_id in self._group_to_lit:
            return self._group_to_lit[group_id]
        if self._next_lit > self.max_assumption_vars:
            raise AssumptionCapExceeded(
                f"activation-literal cap {self.max_assumption_vars} reached; "
                f"rebuild epoch"
            )
        lit = self._next_lit
        self._next_lit += 1
        self._group_to_lit[group_id] = lit
        self._lit_to_group[lit] = group_id
        return lit

    def group_of(self, lit: int) -> str:
        return self._lit_to_group[lit]

    def is_injective(self) -> bool:
        return len(self._group_to_lit) == len(self._lit_to_group)

    def __len__(self) -> int:
        return len(self._group_to_lit)
