# tests/sat_gate/test_hint_routing.py

from isir.verification.sat_gate.hint_routing import HintRouter
from isir.verification.sat_gate.lemma_admission import AdmissionEvidence
from isir.verification.sat_gate.lemma_hint import HintProvenance


def _full_evidence():
    return AdmissionEvidence(itp_proved=True, t3_certified=True,
                             exact_translation=True, dual_encoder_agreement=True,
                             shared_library_tests=True)


def test_harvest_and_offer():
    r = HintRouter()
    hints = r.harvest_and_offer(["(le (read count) 8)"], "o1",
                                HintProvenance.ITP_PROPOSED, current_step=0)
    assert len(hints) == 1
    assert r.pool.state_of(hints[0].hint_id) == "offered"


def test_accept_admits_only_with_full_evidence():
    r = HintRouter()
    hints = r.harvest_and_offer(["(le (read count) 8)"], "o1",
                                HintProvenance.ITP_PROPOSED, current_step=0)
    hid = hints[0].hint_id
    assert r.accept(hid) is True
    # the incomplete evidence denies the admission.
    assert r.admit(hid, AdmissionEvidence(itp_proved=True)) is False
    # the full evidence admits.
    assert r.admit(hid, _full_evidence()) is True


def test_mark_used_after_accept():
    r = HintRouter()
    hints = r.harvest_and_offer(["(le (read count) 8)"], "o1",
                                HintProvenance.ITP_PROPOSED, current_step=0)
    hid = hints[0].hint_id
    r.accept(hid)
    assert r.mark_used(hid) is True
    assert r.pool.state_of(hid) == "used_in_final_proof"


def test_suggested_strategy_recorded():
    r = HintRouter()
    hints = r.harvest_and_offer(["(le (read count) 8)"], "o1",
                                HintProvenance.ITP_PROPOSED, current_step=0,
                                suggested_strategy="induct")
    assert hints[0].suggested_strategy == "induct"
