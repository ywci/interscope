# src/isir/verification/sat_gate/epoch.py
#
# Epoch hash. Any change to the semantic inputs invalidates activation
# literals, solver state, and epoch-scoped caches.

import hashlib


def compute_epoch_hash(
    canonical_isir_hash: str,
    encoder_version: str,
    f_exact_version: str,
    abstraction_mode: str,
    memory_mode: str,
    reset_mode: str,
    memory_map_threshold_bits: int,
    max_mul_width: int,
    obligation_ir_version: str,
    yosys_version: str = "",
    pass_script_hash: str = "",
    smt_backend_name: str = "",
    smt_backend_version: str = "",
    symbol_map_hash: str = ""
) -> str:
    """Return a stable SHA-256 prefix over the epoch inputs.

    ``bounded_k`` is deliberately EXCLUDED : it changes query depth, not
    approximation strength or operator routing.  ``memory_map_threshold_bits`` and
    ``max_mul_width`` are INCLUDED : both alter over/under-approximation.
    """
    parts = [
        canonical_isir_hash, encoder_version, f_exact_version,
        yosys_version, pass_script_hash,
        smt_backend_name, smt_backend_version,
        abstraction_mode, memory_mode, reset_mode,
        str(memory_map_threshold_bits), str(max_mul_width),
        symbol_map_hash, obligation_ir_version,
    ]
    raw = "\x1f".join(parts).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]
