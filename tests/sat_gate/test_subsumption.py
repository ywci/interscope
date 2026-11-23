# tests/sat_gate/test_subsumption.py

from isir.verification.sat_gate.cache import SubsumptionCache


def test_subset_core_subsume_superset():
    c = SubsumptionCache()
    c.put({"g1", "g2"})
    assert c.is_subsumed({"g1", "g2", "g3"}) is True


def test_equal_core_subsume():
    c = SubsumptionCache()
    c.put({"g1", "g2"})
    assert c.is_subsumed({"g1", "g2"}) is True


def test_superset_core_does_not_subsume_subset():
    c = SubsumptionCache()
    c.put({"g1", "g2", "g3"})
    assert c.is_subsumed({"g1", "g2"}) is False


def test_lru_eviction():
    c = SubsumptionCache(max_entries=2)
    c.put({"a"})
    c.put({"b"})
    c.put({"c"})  # evicts {"a"}
    assert c.is_subsumed({"a"}) is False
    assert c.is_subsumed({"b", "x"}) is True
