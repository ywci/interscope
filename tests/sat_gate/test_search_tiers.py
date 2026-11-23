# tests/sat_gate/test_search_tiers.py

from isir.verification.sat_gate.search_tiers import TwoTierBeam


def test_park_moves_out_of_active():
    beam = TwoTierBeam()
    a = object()
    b = object()
    beam.add_active(a, 0.9)
    beam.add_active(b, 0.5)
    beam.park_node(b, 0.5, "heuristic", evidence={"x": 1})
    assert b not in [n for _, n in beam.active]
    assert beam.park_reasons() == ["heuristic"]


def test_resurrect_highest_score_first():
    beam = TwoTierBeam()
    low = object()
    high = object()
    beam.park_node(low, 0.3, "low", None)
    beam.park_node(high, 0.8, "high", None)
    assert beam.resurrect() is True
    assert beam.active[0][1] is high  # the highest score resurrected first


def test_resurrect_empty_park():
    beam = TwoTierBeam()
    assert beam.resurrect() is False
