# tests/sat_gate/test_bit_manipulation.py
"""Bit-manipulation ops: slice, concat (var re-wiring) + SMT emission."""

from isir.verification.sat_gate.bitblast import BitBlaster
from isir.verification.sat_gate.compile_dyn import lower_term
from isir.verification.sat_gate.smt_encode import _term


def test_slice_selects_bits():
    blaster = BitBlaster()
    widths = {"x": 8}
    a = [blaster.symbols.intern("x", 8) + i for i in range(8)]
    out = lower_term("(slice (read x) 3 1)", blaster, widths)
    assert out == a[1:4]  # the bits [lo..hi] = a[1], a[2], a[3]


def test_concat_orders_lsb_first():
    blaster = BitBlaster()
    widths = {"hi": 2, "lo": 3}
    hi = [blaster.symbols.intern("hi", 2) + i for i in range(2)]
    lo = [blaster.symbols.intern("lo", 3) + i for i in range(3)]
    out = lower_term("(concat (read hi) (read lo))", blaster, widths)
    assert out == lo + hi  # LSB-first: low bits ++ high bits


def test_smt_slice_and_shift_emit():
    widths = {"a": 8, "b": 8}
    env = {"a": "a", "b": "b"}
    assert _term("(slice (read a) 7 4)", widths, env) == "((_ extract 7 4) a)"
    # variable shift: the shift amount is zero-extended to the value width.
    s = _term("(shl (read a) (slice (read b) 2 0))", widths, env)
    assert s == "(bvshl a ((_ zero_extend 5) ((_ extract 2 0) b)))"


def test_smt_mul_div_mod_emit():
    widths = {"a": 4, "b": 4}
    env = {"a": "a", "b": "b"}
    assert _term("(mul (read a) (read b))", widths, env) == "(bvmul a b)"
    assert _term("(div (read a) (read b))", widths, env) == "(bvudiv a b)"
    assert _term("(mod (read a) (read b))", widths, env) == "(bvurem a b)"
