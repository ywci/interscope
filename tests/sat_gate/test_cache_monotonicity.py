# tests/sat_gate/test_cache_monotonicity.py

from isir.verification.sat_gate.cache import SatCache


def test_sat_monotonicity():
    c = SatCache()
    c.put("e", "g1", k=3, model_ref="m", replay_ref="r", cert_ref="c")
    # a call at k' >= 3 answers from the stored k=3 entry.
    assert c.lookup("e", "g1", 3) is not None
    assert c.lookup("e", "g1", 5) is not None
    # a call at k' < 3 must NOT answer (monotonic only upward).
    assert c.lookup("e", "g1", 2) is None


def test_maximal_stored_k_is_returned():
    c = SatCache()
    c.put("e", "g1", k=2, model_ref="m2", replay_ref="r2", cert_ref="c2")
    c.put("e", "g1", k=5, model_ref="m5", replay_ref="r5", cert_ref="c5")
    entry = c.lookup("e", "g1", 8)
    assert entry[0] == 5  # the maximal stored k <= 8
