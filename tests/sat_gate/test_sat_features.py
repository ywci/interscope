# tests/sat_gate/test_sat_features.py

from isir.verification.sat_gate.sat_features import (
    gate_evidence_score, promote_ranker, sat_features_vector,
)
from isir.verification.sat_gate.ranker import ObligationFeatures, ShadowRanker


def test_hint_boosts_gate_evidence():
    plain = ObligationFeatures()
    hinted = ObligationFeatures(lemma_hint_generated=True)
    assert gate_evidence_score(hinted) > gate_evidence_score(plain)


def test_gate_evidence_ordering():
    reachable = ObligationFeatures(cti_reachable="reachable")
    unsat = ObligationFeatures(unsat_hit=True)
    assert gate_evidence_score(ObligationFeatures(lemma_hint_generated=True)) \
        > gate_evidence_score(reachable) > gate_evidence_score(unsat)


def test_features_vector_fixed_order():
    f = ObligationFeatures(failed_group_count=2, cert_reuse=True)
    v = sat_features_vector(f)
    assert len(v) == 5
    assert v[1] == 2.0
    assert v[3] == 1.0


def test_promote_ranker_on_improvement():
    r = ShadowRanker()
    assert r.active is False
    assert promote_ranker(r, held_out_improvement=0.05) is True
    assert r.active is True


def test_promote_ranker_withheld_without_improvement():
    r = ShadowRanker()
    assert promote_ranker(r, held_out_improvement=0.0) is False
    assert r.active is False
