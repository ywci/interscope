# tests/sat_gate/test_symbol_roundtrip.py
"""Symbol round-trip tests (§20.3)."""

from isir.verification.sat_gate.symbols import SymbolTable


def test_roundtrip_multi_bit():
    st = SymbolTable()
    base = st.intern("count", 4)
    for i in range(4):
        v = st.var("count", i)
        assert st.symbol(v) == ("count", i)
    assert st.roundtrip_ok("count", 4)
    assert base == st.var("count", 0)


def test_names_do_not_collide():
    st = SymbolTable()
    st.intern("a", 3)
    st.intern("b", 5)
    assert st.roundtrip_ok("a", 3)
    assert st.roundtrip_ok("b", 5)
    # distinct ranges
    assert set(st.var("a", i) for i in range(3)).isdisjoint(
        set(st.var("b", i) for i in range(5))
    )


def test_intern_is_idempotent():
    st = SymbolTable()
    b1 = st.intern("x", 8)
    b2 = st.intern("x", 8)
    assert b1 == b2
    assert st.width("x") == 8


def test_unknown_var_raises():
    st = SymbolTable()
    st.intern("x", 1)
    try:
        st.symbol(999)
        raise AssertionError("expected KeyError")
    except KeyError:
        pass
