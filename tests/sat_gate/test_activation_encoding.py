# tests/sat_gate/test_activation_encoding.py
"""Activation encoding shape tests (§11.2): one clause per group, never the
unit conjunction."""

from isir.verification.sat_gate.assumptions import gate_clause, gate_clause_set


def test_single_multi_literal_clause():
    c = gate_clause(7, [1, 2, 3])
    assert c == [-7, 1, 2, 3]
    # exactly one clause, and it is not the banned unit conjunction
    assert len(c) == 4


def test_unit_literal_clause():
    assert gate_clause(7, [1]) == [-7, 1]


def test_clause_set_one_clause_per_group():
    clauses = gate_clause_set(7, [[1, 2], [3], [4, 5, 6]])
    assert clauses == [[-7, 1, 2], [-7, 3], [-7, 4, 5, 6]]
    assert len(clauses) == 3  # one per C_i, not one per literal


def test_banned_form_is_never_emitted():
    """The banned form (¬a∨l1)∧(¬a∨l2)… would be multiple clauses with the
    same activation; we must emit exactly one for a multi-literal group."""
    c = gate_clause(7, [1, 2, 3, 4])
    assert c.count(-7) == 1
    assert len(c) == 1 + 4
