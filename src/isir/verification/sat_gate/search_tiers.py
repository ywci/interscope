# src/isir/verification/sat_gate/search_tiers.py
#
# Two-tier beam plus hint pool. Heuristic evidence parks (never deletes);
# on active-tier exhaustion the park is resurrected in score order.

from typing import Any, List, Tuple


class TwoTierBeam:
    def __init__(self) -> None:
        self.active: List[Tuple[float, Any]] = []
        self.park: List[Tuple[float, Any, str, Any]] = []

    def add_active(self, node: Any, score: float) -> None:
        self.active.append((score, node))

    def park_node(self, node: Any, score: float, reason: str, evidence: Any) -> None:
        """Deprioritize a node to the park tier (never delete)."""
        self.active = [x for x in self.active if x[1] is not node]
        self.park.append((score, node, reason, evidence))
        self.park.sort(key=lambda x: x[0], reverse=True)

    def resurrect(self) -> bool:
        """Resurrect the highest-score parked node; False when the park is empty."""
        if not self.park:
            return False
        score, node, _, _ = self.park.pop(0)
        self.active.append((score, node))
        return True

    def park_reasons(self) -> List[str]:
        return [r for _, _, r, _ in self.park]
