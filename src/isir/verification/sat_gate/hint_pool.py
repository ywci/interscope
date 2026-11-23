# src/isir/verification/sat_gate/hint_pool.py
#
# Lemma hint pool. Hints are offered to the ITP integrator, not added
# as search nodes; they expire, get accepted/rejected, and vanish on epoch change.

from typing import Any, Dict, List


class HintPool:
    def __init__(self, ttl_steps: int) -> None:
        self.ttl_steps = ttl_steps
        self._pool: Dict[str, Dict[str, Any]] = {}

    def offer(self, hint, current_step: int) -> None:
        self._pool[hint.hint_id] = {
            "hint": hint,
            "state": "offered",
            "expires_step": current_step + self.ttl_steps,
        }

    def accept(self, hint_id: str) -> bool:
        e = self._pool.get(hint_id)
        if e is None or e["state"] != "offered":
            return False
        e["state"] = "accepted"
        return True

    def reject(self, hint_id: str) -> bool:
        e = self._pool.get(hint_id)
        if e is None:
            return False
        e["state"] = "rejected"
        return True

    def mark_used(self, hint_id: str) -> bool:
        e = self._pool.get(hint_id)
        if e is None:
            return False
        e["state"] = "used_in_final_proof"
        return True

    def state_of(self, hint_id: str) -> str:
        e = self._pool.get(hint_id)
        return e["state"] if e else "absent"

    def expire(self, current_step: int) -> int:
        dead = [k for k, e in self._pool.items()
                if e["state"] == "offered" and current_step > e["expires_step"]]
        for k in dead:
            del self._pool[k]
        return len(dead)

    def offered(self) -> List[str]:
        return [k for k, e in self._pool.items() if e["state"] == "offered"]

    def invalidate_epoch(self) -> None:
        self._pool.clear()
