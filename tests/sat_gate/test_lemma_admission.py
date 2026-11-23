# tests/sat_gate/test_lemma_admission.py

from isir.verification.sat_gate.lemma_admission import (
    AdmissionEvidence, LemmaAdmissionPolicy,
)


def _full_evidence(**overrides):
    base = dict(itp_proved=True, t3_certified=True, exact_translation=True,
                dual_encoder_agreement=True, shared_library_tests=True)
    base.update(overrides)
    return AdmissionEvidence(**base)


def test_admission_requires_full_evidence():
    p = LemmaAdmissionPolicy(max_lemmas_per_epoch=10)
    assert p.admit("h1", _full_evidence()) is True
    # missing any one evidence -> deny.
    assert p.admit("h2", _full_evidence(shared_library_tests=False)) is False


def test_admission_rate_limited():
    p = LemmaAdmissionPolicy(max_lemmas_per_epoch=2)
    assert p.admit("h1", _full_evidence()) and p.admit("h2", _full_evidence())
    assert p.admit("h3", _full_evidence()) is False  # the rate limit


def test_admission_epoch_bump_resets_limit():
    p = LemmaAdmissionPolicy(max_lemmas_per_epoch=1)
    assert p.admit("h1", _full_evidence()) and not p.admit("h2", _full_evidence())
    p.bump_epoch()
    assert p.admit("h2", _full_evidence())
