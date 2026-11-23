# tests/sat_gate/test_epoch_rebuild.py

from isir.verification.sat_gate.epoch import compute_epoch_hash


def _base():
    return dict(canonical_isir_hash="abc", encoder_version="1", f_exact_version="1",
                abstraction_mode="exact", memory_mode="unknown",
                reset_mode="sync", memory_map_threshold_bits=10, max_mul_width=16,
                obligation_ir_version="1")


def test_epoch_hash_is_stable():
    args = _base()
    assert compute_epoch_hash(**args) == compute_epoch_hash(**args)


def test_epoch_hash_changes_on_each_input():
    base = _base()
    h0 = compute_epoch_hash(**base)
    for key in base:
        changed = dict(base)
        changed[key] = "DIFFERENT"
        assert compute_epoch_hash(**changed) != h0, key
