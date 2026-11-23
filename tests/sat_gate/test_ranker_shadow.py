# tests/sat_gate/test_ranker_shadow.py

from isir.verification.sat_gate.ranker import (
    ObligationFeatures, ShadowRanker, rule_based_score,
)


def test_rule_based_score_is_deterministic():
    f = ObligationFeatures(lemma_hint_generated=True, unsat_hit=True)
    assert rule_based_score(f) == rule_based_score(f)


def test_hint_boosts_rule_score():
    plain = ObligationFeatures()
    hinted = ObligationFeatures(lemma_hint_generated=True)
    assert rule_based_score(hinted) > rule_based_score(plain)


def test_shadow_rank_orders_without_side_effects():
    r = ShadowRanker()
    a = ObligationFeatures(lemma_hint_generated=True)
    b = ObligationFeatures()
    ordered = r.rank([b, a])
    assert ordered[0] is a  # the hinted obligation ranks first
    assert r.log == []       # ranking alone does not log
    assert not r.active      # still shadow


def test_observe_logs_off_policy():
    r = ShadowRanker()
    f = ObligationFeatures(bound_k=2)
    r.observe(f, closed=True)
    r.observe(f, closed=False)
    assert len(r.log) == 2
    assert r.log[0] == (f.vector(), True)
    assert r.log[1] == (f.vector(), False)


def test_activate_promotes_shadow():
    r = ShadowRanker()
    assert not r.active
    r.activate()
    assert r.active
