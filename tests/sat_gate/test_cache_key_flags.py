# tests/sat_gate/test_cache_key_flags.py

from isir.verification.sat_gate.cache import CacheKey


def test_model_approx_in_key():
    k1 = CacheKey("e", "IND_STEP", "free", 1, "exact", "EXACT", True)
    k2 = CacheKey("e", "IND_STEP", "free", 1, "exact", "OVER", True)
    assert k1 != k2


def test_predicate_exact_in_key():
    k1 = CacheKey("e", "IND_STEP", "free", 1, "exact", "EXACT", True)
    k2 = CacheKey("e", "IND_STEP", "free", 1, "exact", "EXACT", False)
    assert k1 != k2


def test_epoch_and_kind_in_key():
    k = CacheKey("e", "IND_STEP", "free", 1, "exact", "EXACT", True)
    assert k.epoch_hash == "e"
    assert k.query_kind == "IND_STEP"
    assert k.bound_k == 1
