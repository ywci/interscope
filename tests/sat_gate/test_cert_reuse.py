# tests/sat_gate/test_cert_reuse.py

from isir.verification.sat_gate.cache import CacheKey, CertCache


def _key(**overrides):
    base = dict(epoch_hash="e", query_kind="IND_STEP", anchor="free", bound_k=1,
                abstraction_mode="exact", model_approx="EXACT", predicate_exact=True)
    base.update(overrides)
    return CacheKey(**base)


def test_flag_matched_reuse():
    c = CertCache()
    key = _key()
    c.put(key, "EXACT", True, "cert")
    assert c.reuse(key, "EXACT", True) == "cert"
    assert c.reuse_count == 1


def test_model_approx_mismatch_rejected():
    c = CertCache()
    key = _key()
    c.put(key, "EXACT", True, "cert")
    assert c.reuse(key, "OVER", True) is None
    assert c.flag_mismatch_rejects == 1
    assert c.reuse_count == 0


def test_predicate_exact_mismatch_rejected():
    c = CertCache()
    key = _key()
    c.put(key, "EXACT", True, "cert")
    assert c.reuse(key, "EXACT", False) is None
    assert c.flag_mismatch_rejects == 1
