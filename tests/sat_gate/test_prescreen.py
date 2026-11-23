# tests/sat_gate/test_prescreen.py

from isir.verification.sat_gate.lemma_hint import (
    candidate_predicate_from_cube, t0_prescreen,
)


def test_candidate_predicate_is_negated_cube():
    pred = candidate_predicate_from_cube(frozenset({("count", 7)}))
    assert pred == "(not (eq (read count) 7))"


def test_prescreen_passes_for_inductive():
    widths = {"count": 4}
    init = {"count": 0}
    transitions = {"count": "(add (read count) 0)"}  # identity -> inductive
    assert t0_prescreen(init, transitions, widths, "(le (read count) 15)") == "PASS"


def test_prescreen_fails_for_non_inductive():
    widths = {"count": 4}
    init = {"count": 0}
    transitions = {"count": "(add (read count) 1)"}  # increment -> not inductive
    assert t0_prescreen(init, transitions, widths, "(le (read count) 8)") == "FAIL"


def test_prescreen_fails_for_base_invalid():
    widths = {"count": 4}
    init = {"count": 9}  # 9 > 8 -> base invalid
    transitions = {"count": "(add (read count) 0)"}
    assert t0_prescreen(init, transitions, widths, "(le (read count) 8)") == "FAIL"
