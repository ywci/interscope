# tests/sat_gate/test_fail_closed.py

import pytest
from isir.verification.sat_gate.obligation import classify_predicate
from isir.verification.sat_gate.compile_dyn import lower_pred, lower_term
from isir.verification.sat_gate.bitblast import BitBlaster


def test_classify_flags_excluded_ops():
    assert classify_predicate("(rshift a 2)") == "variable_shift"
    assert classify_predicate("(forall x p)") == "quantifier"
    assert classify_predicate("(add a b)") is None
    assert classify_predicate("(mul a b)") is None
    assert classify_predicate("(div a b)") is None
    assert classify_predicate("(mod a b)") is None


def test_lower_rejects_unsupported_pred():
    blaster = BitBlaster()
    with pytest.raises(ValueError):
        lower_pred("(rshift a 2)", blaster, {"a": 4, "b": 4})


def test_lower_rejects_unsupported_term():
    blaster = BitBlaster()
    with pytest.raises(ValueError):
        lower_term("(rshift a 2)", blaster, {"a": 4})
