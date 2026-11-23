# tests/sat_gate/test_bounded_fallback.py

from isir.verification.sat_gate.bounded_fallback import bounded_fallback
from isir.verification.sat_gate.lemma_hint import _cube_to_predicate


def test_bounded_cex_within_depth():
    widths = {"count": 4}
    transitions = {"count": "(add (read count) 1)"}
    init = {"count": 0}
    pred = _cube_to_predicate(frozenset({("count", 2)}))
    assert bounded_fallback(init, transitions, widths, pred, max_depth=3) == "bounded_cex"


def test_bounded_safe_within_depth():
    widths = {"count": 4}
    transitions = {"count": "(add (read count) 1)"}
    init = {"count": 0}
    pred = _cube_to_predicate(frozenset({("count", 15)}))
    assert bounded_fallback(init, transitions, widths, pred, max_depth=2) == "bounded_safe"
