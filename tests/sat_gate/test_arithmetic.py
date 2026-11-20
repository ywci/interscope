# tests/sat_gate/test_arithmetic.py
"""Arithmetic truth tables: add/sub/ult/ule match the reference."""

from sat_helper import dpll_sat, vars_of

from isir.verification.sat_gate.bitblast import BitBlaster


def _sat_under(blaster, fixed):
    unit = [[v if val else -v] for v, val in fixed.items()]
    nvars = vars_of(blaster.cnf.clauses + unit)
    return dpll_sat(blaster.cnf.clauses + unit, nvars) is not None


def _vec(blaster, name, width):
    return [blaster.symbols.intern(name, width) + i for i in range(width)]


def test_add_truth_table():
    width = 4
    blaster = BitBlaster()
    a = _vec(blaster, "a", width)
    b = _vec(blaster, "b", width)
    out = _vec(blaster, "out", width)
    blaster.blast_add(a, b, out)
    for ai in range(1 << width):
        for bi in range(1 << width):
            expected = (ai + bi) & ((1 << width) - 1)
            for oi in range(1 << width):
                fixed = {a[i]: bool(ai >> i & 1) for i in range(width)}
                fixed.update({b[i]: bool(bi >> i & 1) for i in range(width)})
                fixed.update({out[i]: bool(oi >> i & 1) for i in range(width)})
                assert _sat_under(blaster, fixed) == (oi == expected), (ai, bi, oi)


def test_sub_truth_table():
    width = 4
    blaster = BitBlaster()
    a = _vec(blaster, "a", width)
    b = _vec(blaster, "b", width)
    out = _vec(blaster, "out", width)
    blaster.blast_sub(a, b, out)
    for ai in range(1 << width):
        for bi in range(1 << width):
            expected = (ai - bi) & ((1 << width) - 1)
            for oi in range(1 << width):
                fixed = {a[i]: bool(ai >> i & 1) for i in range(width)}
                fixed.update({b[i]: bool(bi >> i & 1) for i in range(width)})
                fixed.update({out[i]: bool(oi >> i & 1) for i in range(width)})
                assert _sat_under(blaster, fixed) == (oi == expected), (ai, bi, oi)


def test_ule_truth_table():
    width = 4
    blaster = BitBlaster()
    a = _vec(blaster, "a", width)
    b = _vec(blaster, "b", width)
    out = blaster.blast_ule(a, b)
    for ai in range(1 << width):
        for bi in range(1 << width):
            expected = 1 if ai <= bi else 0
            for oi in (0, 1):
                fixed = {out: bool(oi)}
                for i in range(width):
                    fixed[a[i]] = bool(ai >> i & 1)
                    fixed[b[i]] = bool(bi >> i & 1)
                assert _sat_under(blaster, fixed) == (oi == expected), (ai, bi, oi)


def test_ult_truth_table():
    width = 4
    blaster = BitBlaster()
    a = _vec(blaster, "a", width)
    b = _vec(blaster, "b", width)
    out = blaster.blast_ult(a, b)
    for ai in range(1 << width):
        for bi in range(1 << width):
            expected = 1 if ai < bi else 0
            for oi in (0, 1):
                fixed = {out: bool(oi)}
                for i in range(width):
                    fixed[a[i]] = bool(ai >> i & 1)
                    fixed[b[i]] = bool(bi >> i & 1)
                assert _sat_under(blaster, fixed) == (oi == expected), (ai, bi, oi)
