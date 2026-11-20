# tests/sat_gate/test_epoch_rebuild.py
"""Epoch hash stability + change sensitivity (§11.5)."""

from isir.verification.sat_gate.epoch import compute_epoch_hash


def test_epoch_hash_is_stable():
    args = dict(canonical_isir_hash="abc", encoder_version="1", f_exact_version="1",
                bounded_k=1, abstraction_mode="exact", memory_mode="unknown",
                reset_mode="sync", obligation_ir_version="1")
    assert compute_epoch_hash(**args) == compute_epoch_hash(**args)


def test_epoch_hash_changes_on_each_input():
    base = dict(canonical_isir_hash="abc", encoder_version="1", f_exact_version="1",
                bounded_k=1, abstraction_mode="exact", memory_mode="unknown",
                reset_mode="sync", obligation_ir_version="1")
    h0 = compute_epoch_hash(**base)
    for key in base:
        changed = dict(base)
        changed[key] = "DIFFERENT"
        assert compute_epoch_hash(**changed) != h0, key
