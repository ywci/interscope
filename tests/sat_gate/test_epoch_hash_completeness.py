# tests/sat_gate/test_epoch_hash_completeness.py

import inspect
from isir.verification.sat_gate.epoch import compute_epoch_hash


def test_epoch_hash_has_all_required_fields():
    """: every  field is a parameter of compute_epoch_hash."""
    params = set(inspect.signature(compute_epoch_hash).parameters)
    required = {
        "canonical_isir_hash", "encoder_version", "f_exact_version",
        "yosys_version", "pass_script_hash",
        "smt_backend_name", "smt_backend_version",
        "abstraction_mode", "memory_mode", "reset_mode",
        "memory_map_threshold_bits", "max_mul_width",
        "symbol_map_hash", "obligation_ir_version",
    }
    assert required <= params, required - params


def test_epoch_hash_excludes_bounded_k():
    """bounded_k changes query depth, not approximation/routing."""
    params = inspect.signature(compute_epoch_hash).parameters
    assert "bounded_k" not in params


def test_approximation_fields_change_hash():
    base = dict(canonical_isir_hash="abc", encoder_version="1", f_exact_version="1",
                abstraction_mode="exact", memory_mode="unknown",
                reset_mode="sync", memory_map_threshold_bits=10, max_mul_width=16,
                obligation_ir_version="1")
    h0 = compute_epoch_hash(**base)
    for key in ("memory_map_threshold_bits", "max_mul_width", "abstraction_mode",
                "memory_mode", "reset_mode"):
        changed = dict(base)
        changed[key] = "DIFFERENT"
        assert compute_epoch_hash(**changed) != h0, key
