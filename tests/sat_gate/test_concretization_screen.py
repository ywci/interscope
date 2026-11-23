# tests/sat_gate/test_concretization_screen.py

from isir.verification.sat_gate.lemma_hint import concretization_screen


def test_reachable_cube_fails_screen():
    # count=3 is reachable from 0 in 3 steps -> the screen rejects it.
    widths = {"count": 4}
    transitions = {"count": "(add (read count) 1)"}
    init = {"count": 0}
    cube = frozenset({("count", 3)})
    assert concretization_screen(init, transitions, widths, cube, depth=5) == "FAIL"


def test_unreachable_cube_passes_screen():
    # count=15 is unreachable in 3 steps -> the screen passes (bounded).
    widths = {"count": 4}
    transitions = {"count": "(add (read count) 1)"}
    init = {"count": 0}
    cube = frozenset({("count", 15)})
    assert concretization_screen(init, transitions, widths, cube, depth=3) == "PASS"


def test_multi_literal_cube_screen():
    widths = {"count": 4, "overflow_flag": 1}
    transitions = {"count": "(add (read count) 1)",
                   "overflow_flag": "(eq (read count) 15)"}
    init = {"count": 0, "overflow_flag": 0}
    # count=1 and flag=0 is reachable (after 1 step) -> FAIL.
    cube = frozenset({("count", 1), ("overflow_flag", 0)})
    assert concretization_screen(init, transitions, widths, cube, depth=2) == "FAIL"
