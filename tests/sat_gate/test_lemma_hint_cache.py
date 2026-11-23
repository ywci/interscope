# tests/sat_gate/test_lemma_hint_cache.py

from isir.verification.sat_gate.cache import LemmaHintCache


def test_put_and_get_within_ttl():
    c = LemmaHintCache(ttl_steps=10)
    c.put("e", "o1", "cube1", "hint1", current_step=0)
    assert c.get("e", "o1", "cube1", current_step=5) == "hint1"


def test_ttl_expiry():
    c = LemmaHintCache(ttl_steps=10)
    c.put("e", "o1", "cube1", "hint1", current_step=0)
    assert c.get("e", "o1", "cube1", current_step=11) is None


def test_epoch_invalidation():
    c = LemmaHintCache(ttl_steps=100)
    c.put("e1", "o1", "cube1", "hint1", current_step=0)
    c.put("e2", "o1", "cube1", "hint2", current_step=0)
    assert c.invalidate_epoch("e1") == 1
    assert c.get("e1", "o1", "cube1", current_step=0) is None
    assert c.get("e2", "o1", "cube1", current_step=0) == "hint2"


def test_distinct_keys_are_independent():
    c = LemmaHintCache(ttl_steps=10)
    c.put("e", "o1", "cube1", "hint1", current_step=0)
    c.put("e", "o1", "cube2", "hint2", current_step=0)
    assert c.get("e", "o1", "cube1", current_step=0) == "hint1"
    assert c.get("e", "o1", "cube2", current_step=0) == "hint2"
