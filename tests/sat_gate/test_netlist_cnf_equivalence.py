# tests/sat_gate/test_netlist_cnf_equivalence.py

from sat_helper import dpll_sat, vars_of
from isir.verification.sat_gate.bitblast import BitBlaster


def _sat_under(blaster, fixed):
    unit = [[v if val else -v] for v, val in fixed.items()]
    nvars = vars_of(blaster.cnf.clauses + unit)
    return dpll_sat(blaster.cnf.clauses + unit, nvars) is not None


def test_two_gate_chain_1bit():
    blaster = BitBlaster()
    a = blaster.symbols.intern("a", 1)
    b = blaster.symbols.intern("b", 1)
    c = blaster.symbols.intern("c", 1)
    x = blaster.cnf.new_var()
    out = blaster.cnf.new_var()
    blaster.gate_and(x, a, b)
    blaster.gate_or(out, x, c)

    for ai in (0, 1):
        for bi in (0, 1):
            for ci in (0, 1):
                expected = (ai & bi) | ci
                for oi in (0, 1):
                    fixed = {a: bool(ai), b: bool(bi), c: bool(ci), out: bool(oi)}
                    assert _sat_under(blaster, fixed) == (oi == expected)


def test_eq_gate_multi_bit():
    width = 4
    blaster = BitBlaster()
    a = [blaster.symbols.intern("a", width) + i for i in range(width)]
    b = [blaster.symbols.intern("b", width) + i for i in range(width)]
    out = blaster.blast_eq(a, b)

    for ai in range(1 << width):
        for bi in range(1 << width):
            expected = 1 if ai == bi else 0
            for oi in (0, 1):
                fixed = {out: bool(oi)}
                for i in range(width):
                    fixed[a[i]] = bool(ai >> i & 1)
                    fixed[b[i]] = bool(bi >> i & 1)
                assert _sat_under(blaster, fixed) == (oi == expected)


def test_ite_gate_1bit():
    blaster = BitBlaster()
    sel = blaster.symbols.intern("sel", 1)
    a = blaster.symbols.intern("a", 1)
    b = blaster.symbols.intern("b", 1)
    out = blaster.symbols.intern("out", 1)
    blaster.blast_ite(sel, [a], [b], [out])

    for si in (0, 1):
        for ai in (0, 1):
            for bi in (0, 1):
                expected = ai if si else bi
                for oi in (0, 1):
                    fixed = {sel: bool(si), a: bool(ai), b: bool(bi), out: bool(oi)}
                    assert _sat_under(blaster, fixed) == (oi == expected)
