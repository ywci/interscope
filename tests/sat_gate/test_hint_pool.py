# tests/sat_gate/test_hint_pool.py

from isir.verification.sat_gate.hint_pool import HintPool
from isir.verification.sat_gate.lemma_hint import HintProvenance, LemmaHint


def _hint(hint_id):
    return LemmaHint(hint_id=hint_id, source_obligation_id="o1",
                     source_cti_cube=frozenset(), generalized_cube=frozenset(),
                     candidate_predicate="(le (read count) 8)",
                     provenance=HintProvenance.CTI_PROBE_UNSAT)


def test_hint_pool_lifecycle():
    pool = HintPool(ttl_steps=10)
    pool.offer(_hint("h1"), current_step=0)
    assert pool.state_of("h1") == "offered"
    assert pool.accept("h1")
    assert pool.state_of("h1") == "accepted"
    assert pool.mark_used("h1")
    assert pool.state_of("h1") == "used_in_final_proof"


def test_hint_pool_expiry():
    pool = HintPool(ttl_steps=10)
    pool.offer(_hint("h1"), current_step=0)
    assert pool.expire(current_step=11) == 1
    assert pool.state_of("h1") == "absent"


def test_hint_pool_reject():
    pool = HintPool(ttl_steps=10)
    pool.offer(_hint("h1"), current_step=0)
    assert pool.reject("h1")
    assert pool.state_of("h1") == "rejected"


def test_hint_pool_epoch_invalidation():
    pool = HintPool(ttl_steps=100)
    pool.offer(_hint("h1"), current_step=0)
    pool.invalidate_epoch()
    assert pool.state_of("h1") == "absent"
