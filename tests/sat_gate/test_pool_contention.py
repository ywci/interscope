# tests/sat_gate/test_pool_contention.py
"""Sharded solver pool + contention measurement (§14.4)."""

from isir.verification.sat_gate.pool import SolverPool


def test_shard_is_deterministic_within_process():
    pool = SolverPool(size=4)
    s1 = pool.acquire("g1")
    pool.release("g1")
    s2 = pool.acquire("g1")
    assert s1 is s2
    pool.close()


def test_contention_counted_when_shard_busy():
    pool = SolverPool(size=1)
    s1 = pool.acquire("g1")
    assert s1 is not None
    s2 = pool.acquire("g2")   # same shard, busy
    assert s2 is None
    assert pool.contention_count == 1
    pool.release("g1")
    assert pool.acquire("g2") is not None
    pool.close()


def test_contention_ratio():
    pool = SolverPool(size=1)
    pool.acquire("g1")
    pool.acquire("g2")   # contention
    pool.acquire("g3")   # contention
    assert pool.contention_ratio() == 2 / 3
    pool.close()
