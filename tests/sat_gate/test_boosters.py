# tests/sat_gate/test_boosters.py

from isir.verification.sat_gate.boosters import (
    diversify_ctis, extend_cube, harvest_seed_candidates, probe_core_subcube,
    rule_localized_hint, strengthen_retry,
)
from isir.verification.sat_gate.lemma_hint import HintProvenance


def test_probe_core_subcube_minimizes_unreachable_cube():
    # count=15 is unreachable in 3 steps but flag=1 is reachable at step 0, so
    # a (count=15, flag=1) cube minimizes to (count, 15).
    widths = {"count": 4, "flag": 1}
    transitions = {"count": "(add (read count) 1)", "flag": "(read flag)"}
    init = {"count": 0, "flag": 1}
    cube = frozenset({("count", 15), ("flag", 1)})
    core = probe_core_subcube(init, transitions, widths, cube, depth=3)
    assert core <= cube
    assert ("count", 15) in core  # the essential unreachable literal stays


def test_harvest_seed_candidates_wraps_clauses():
    clauses = ["(le (read count) 8)"]
    hints = harvest_seed_candidates(clauses, "o1", HintProvenance.ITP_PROPOSED)
    assert len(hints) == 1
    assert hints[0].provenance is HintProvenance.ITP_PROPOSED
    assert hints[0].candidate_predicate == "(le (read count) 8)"


def test_strengthen_retry_reaches_inductive():
    # count <= 15 is already inductive -> returned as-is.
    widths = {"count": 4}
    transitions = {"count": "(add (read count) 1)"}
    r = strengthen_retry("(le (read count) 15)", transitions, widths)
    assert r == "(le (read count) 15)"


def test_strengthen_retry_returns_none_when_stuck():
    # a predicate that keeps failing its IND_STEP within the pass budget.
    widths = {"count": 4}
    transitions = {"count": "(add (read count) 1)"}
    r = strengthen_retry("(le (read count) 8)", transitions, widths, max_passes=2)
    assert r is None


def test_rule_localized_hint_records_source_rule():
    h = rule_localized_hint({("count", 7)}, "r1", "o1", "h1")
    assert h.source_rule == "r1"
    assert h.source_cti_cube == frozenset({("count", 7)})


def test_diversify_ctis_returns_distinct_models():
    widths = {"count": 4}
    transitions = {"count": "(add (read count) 1)"}
    inv = "(le (read count) 7)"
    ctis = diversify_ctis(inv, transitions, widths, max_ctis=3)
    assert ctis  # at least one CTI
    keys = [tuple(sorted(c.items())) for c in ctis]
    assert len(keys) == len(set(keys))  # distinct


def test_extend_cube_adds_literals():
    widths = {"count": 4}
    transitions = {"count": "(add (read count) 0)"}  # identity -> ¬cube inductive
    cube = frozenset({("count", 3)})
    universe = frozenset({("count", 3), ("count", 4)})
    extended = extend_cube(transitions, widths, cube, universe)
    assert extended == frozenset({("count", 3), ("count", 4)})
