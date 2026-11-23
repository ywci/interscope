# tests/sat_gate/test_s_prime_hint.py

from isir.verification.sat_gate.lemma_hint import harvest_s_prime_hint


def test_harvest_s_prime_hint_from_ind_step_model():
    # count <= 7 with count' = count+1: the IND_STEP SAT has s=7, s'=8.
    widths = {"count": 4}
    transitions = {"count": "(add (read count) 1)"}
    inv = "(le (read count) 7)"
    hint = harvest_s_prime_hint(inv, transitions, widths, "o1", "h1")
    assert hint is not None
    assert hint.cti_side == "s'"
    assert ("count", 8) in hint.source_cti_cube


def test_harvest_s_prime_hint_none_when_inductive():
    # count <= 15 with count' = count+1 (4-bit wraps): the IND_STEP is UNSAT.
    widths = {"count": 4}
    transitions = {"count": "(add (read count) 1)"}
    inv = "(le (read count) 15)"
    assert harvest_s_prime_hint(inv, transitions, widths, "o1", "h1") is None
