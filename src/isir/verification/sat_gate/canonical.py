# src/isir/verification/sat_gate/canonical.py
#
# Canonicalization: byte-stable structural form + hash. No solver or
# encoder imports.

import hashlib
from typing import Any, List, Union


def canonical_form(expr: Union[str, int, bool, List]) -> Any:
    """Return a byte-stable canonical structure for an S-expression.

    Lists are recursed; atoms pass through. The returned structure is JSON /
    repr stable for identical inputs (a CI check requirement).
    """
    if isinstance(expr, list):
        return [canonical_form(x) for x in expr]
    if isinstance(expr, bool):
        return expr
    if isinstance(expr, int):
        return expr
    return expr.strip() if isinstance(expr, str) else expr


def canonical_hash(expr: Union[str, int, bool, List]) -> str:
    """Return a stable SHA-256 prefix for the canonical form."""
    c = canonical_form(expr)
    raw = repr(c).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]
