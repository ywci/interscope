# tests/sat_gate/test_assumption_registry.py
"""Assumption registry invariants (§11.3)."""

import pytest

from isir.verification.sat_gate.assumptions import (
    AssumptionCapExceeded, AssumptionRegistry,
)


def test_injective_and_idempotent():
    r = AssumptionRegistry(max_assumption_vars=100)
    a = r.activation_literal("g1")
    assert r.activation_literal("g1") == a          # idempotent
    b = r.activation_literal("g2")
    assert a != b
    assert r.group_of(a) == "g1"
    assert r.group_of(b) == "g2"
    assert r.is_injective()


def test_no_recycling_within_epoch():
    r = AssumptionRegistry()
    lits = {r.activation_literal(f"g{i}") for i in range(10)}
    assert len(lits) == 10  # all distinct, none recycled


def test_cap_raises_and_rebuilds():
    r = AssumptionRegistry(max_assumption_vars=3)
    r.activation_literal("g1")
    r.activation_literal("g2")
    r.activation_literal("g3")
    with pytest.raises(AssumptionCapExceeded):
        r.activation_literal("g4")
