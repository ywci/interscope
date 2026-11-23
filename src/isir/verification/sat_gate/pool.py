# src/isir/verification/sat_gate/pool.py
#
# Sharded solver pool: a fixed number of resident solver instances,
# sharded by group-id hash. Contention is measured, not hidden.

from typing import Callable, Optional, Set
from isir.verification.sat_gate.solver_cadical import IncrementalSolver


class SolverPool:
    """A fixed-size pool of incremental solvers sharded by group-id.

    ``acquire`` returns the shard's solver, or None if the shard is busy (the
    contention is recorded).  Callers are expected to ``release`` promptly.
    """

    def __init__(self, size: int,
                 factory: Callable[[], IncrementalSolver] = IncrementalSolver) -> None:
        if size < 1:
            raise ValueError("pool size must be >= 1")
        self._size = size
        self._shards = [factory() for _ in range(size)]
        self._in_use: Set[int] = set()
        self.contention_count = 0
        self.acquire_count = 0

    def _shard(self, group_id: str) -> int:
        return hash(group_id) % self._size

    def acquire(self, group_id: str) -> Optional[IncrementalSolver]:
        self.acquire_count += 1
        idx = self._shard(group_id)
        if idx in self._in_use:
            self.contention_count += 1
            return None
        self._in_use.add(idx)
        return self._shards[idx]

    def release(self, group_id: str) -> None:
        self._in_use.discard(self._shard(group_id))

    def contention_ratio(self) -> float:
        return (self.contention_count / self.acquire_count) if self.acquire_count else 0.0

    def close(self) -> None:
        for s in self._shards:
            s.delete()
        self._shards.clear()
        self._in_use.clear()
