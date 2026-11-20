# src/isir/verification/sat_gate/epoch.py
#
# Epoch hash (§11.5).  Any change to the semantic inputs invalidates activation
# literals, solver state, and epoch-scoped caches.
"""Epoch hash composition."""

import hashlib
from typing import Optional


def compute_epoch_hash(
    canonical_isir_hash: str,
    encoder_version: str,
    f_exact_version: str,
    bounded_k: int,
    abstraction_mode: str,
    memory_mode: str,
    reset_mode: str,
    obligation_ir_version: str,
    yosys_version: str = "",
    pass_script_hash: str = "",
    smt_backend_name: str = "",
    smt_backend_version: str = "",
    symbol_map_hash: str = "",
) -> str:
    """Return a stable SHA-256 prefix over the epoch inputs (§11.5)."""
    parts = [
        canonical_isir_hash, encoder_version, f_exact_version,
        str(bounded_k), abstraction_mode, memory_mode, reset_mode,
        obligation_ir_version, yosys_version, pass_script_hash,
        smt_backend_name, smt_backend_version, symbol_map_hash,
    ]
    raw = "\x1f".join(parts).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]
