# tests/sat_gate/test_hint_acceptance.py

from isir.verification.sat_gate.lemma_hint import (
    HintProvenance, LemmaHint, rank_hints, rank_score,
)


def _hint(hint_id, provenance, cube):
    return LemmaHint(
        hint_id=hint_id,
        source_obligation_id="o1",
        source_cti_cube=frozenset(cube),
        generalized_cube=frozenset(cube),
        candidate_predicate="candidate",
        provenance=provenance,
)


def test_provenance_tier_orders_first():
    itp = _hint("itp", HintProvenance.ITP_PROPOSED, {"a", "b"})
    cti = _hint("cti", HintProvenance.CTI_PROBE_UNSAT, {"a", "b"})
    assert rank_score(itp) < rank_score(cti)


def test_smaller_cube_orders_first_within_tier():
    small = _hint("small", HintProvenance.CTI_PROBE_UNSAT, {"a"})
    large = _hint("large", HintProvenance.CTI_PROBE_UNSAT, {"a", "b", "c"})
    assert rank_score(small) < rank_score(large)


def test_rank_hints_sorts_by_offer_order():
    hints = [
        _hint("cti_big", HintProvenance.CTI_PROBE_UNSAT, {"a", "b", "c"}),
        _hint("itp", HintProvenance.ITP_PROPOSED, {"x", "y"}),
        _hint("cti_small", HintProvenance.CTI_PROBE_UNSAT, {"a"}),
    ]
    ordered = rank_hints(hints)
    assert ordered[0].hint_id == "itp"
    assert ordered[1].hint_id == "cti_small"
    assert ordered[2].hint_id == "cti_big"


def test_hint_is_soft_by_default():
    h = _hint("h", HintProvenance.CTI_PROBE_UNSAT, {"a"})
    assert h.cert_state == "UNCHECKED"
    assert h.suggested_action == "offer_to_ITP_as_strengthening_hint"
