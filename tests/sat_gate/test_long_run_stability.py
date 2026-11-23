# tests/sat_gate/test_long_run_stability.py

from isir.verification.sat_gate.audit import AuditStore
from isir.verification.sat_gate.hint_pool import HintPool
from isir.verification.sat_gate.lemma_admission import (
    AdmissionEvidence, LemmaAdmissionPolicy,
)
from isir.verification.sat_gate.lemma_hint import HintProvenance, LemmaHint


def _hint(hint_id):
    return LemmaHint(hint_id=hint_id, source_obligation_id="o1",
                     source_cti_cube=frozenset(), generalized_cube=frozenset(),
                     candidate_predicate="(le (read count) 8)",
                     provenance=HintProvenance.CTI_PROBE_UNSAT)


def _full_evidence():
    return AdmissionEvidence(itp_proved=True, t3_certified=True,
                             exact_translation=True, dual_encoder_agreement=True,
                             shared_library_tests=True)


def test_audit_store_bounded_under_epoch_churn():
    store = AuditStore()
    for epoch in range(50):
        for i in range(100):
            store.put({"i": i}, epoch_hash=f"e{epoch}")
        store.invalidate_epoch(f"e{epoch}")
    # every epoch is invalidated -> no unbounded growth across epochs.
    assert store.for_epoch("e0") == []


def test_hint_pool_bounded_by_ttl():
    pool = HintPool(ttl_steps=10)
    for step in range(200):
        pool.offer(_hint(f"h{step}"), current_step=step)
        pool.expire(current_step=step)
    assert len(pool.offered()) <= pool.ttl_steps + 1


def test_admission_rate_limited_under_volume():
    p = LemmaAdmissionPolicy(max_lemmas_per_epoch=5)
    for _ in range(1000):
        p.admit("h", _full_evidence())
    assert p.admitted_this_epoch <= p.max_lemmas_per_epoch
    assert len(p.log) <= p.max_lemmas_per_epoch


def test_epoch_bump_resets_admission_volume():
    p = LemmaAdmissionPolicy(max_lemmas_per_epoch=5)
    for epoch in range(100):
        for _ in range(100):
            p.admit("h", _full_evidence())
        p.bump_epoch()
    # the rate limit resets each epoch -> the admitted count stays bounded.
    assert p.admitted_this_epoch <= p.max_lemmas_per_epoch
