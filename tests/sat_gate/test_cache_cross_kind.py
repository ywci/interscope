# tests/sat_gate/test_cache_cross_kind.py

from isir.verification.sat_gate.cache import CacheKey


def test_cross_kind_keys_differ():
    base = dict(epoch_hash="e", anchor="free", bound_k=1, abstraction_mode="exact",
                model_approx="EXACT", predicate_exact=True)
    kinds = ["VACUITY", "FALSIFY_INIT", "IND_STEP", "BASE_ENTAIL"]
    keys = [CacheKey(query_kind=k, **base) for k in kinds]
    assert len(set(keys)) == len(kinds)
