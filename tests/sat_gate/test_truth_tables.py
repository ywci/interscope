# tests/sat_gate/test_truth_tables.py
"""Per-operator truth tables (§20.3): the CNF's semantics match the reference."""

from sat_helper import dpll_sat, vars_of

from isir.verification.sat_gate.bitblast import BitBlaster
from isir.verification.sat_gate.evaluate import evaluate_bitwise, evaluate_not


def _sat_under(blaster, fixed):
    """SAT check of the accumulated CNF plus unit clauses for `fixed` (var->bool)."""
    unit = []
    for v, val in fixed.items():
        unit.append([v if val else -v])
    nvars = vars_of(blaster.cnf.clauses + unit)
    return dpll_sat(blaster.cnf.clauses + unit, nvars) is not None


def _bit_vector(base, width):
    return [base + i for i in range(width)]


def check_bitwise(op, width):
    blaster = BitBlaster()
    a = _bit_vector(blaster.symbols.intern("a", width), width)
    b = _bit_vector(blaster.symbols.intern("b", width), width)
    out = _bit_vector(blaster.symbols.intern("out", width), width)
    blaster.blast_bitwise(op, a, b, out)

    for ai in range(1 << width):
        for bi in range(1 << width):
            expected = evaluate_bitwise(op, ai, bi) & ((1 << width) - 1)
            for oi in range(1 << width):
                fixed = {}
                for i in range(width):
                    fixed[a[i]] = bool(ai >> i & 1)
                    fixed[b[i]] = bool(bi >> i & 1)
                    fixed[out[i]] = bool(oi >> i & 1)
                sat = _sat_under(blaster, fixed)
                if oi == expected:
                    assert sat, (op, width, ai, bi, oi)
                else:
                    assert not sat, (op, width, ai, bi, oi)


def test_and_truth_table():
    check_bitwise("and", 1)
    check_bitwise("and", 4)


def test_or_truth_table():
    check_bitwise("or", 1)
    check_bitwise("or", 4)


def test_xor_truth_table():
    check_bitwise("xor", 1)
    check_bitwise("xor", 4)


def test_not_truth_table():
    width = 4
    blaster = BitBlaster()
    a = _bit_vector(blaster.symbols.intern("a", width), width)
    out = _bit_vector(blaster.symbols.intern("out", width), width)
    blaster.blast_not(a, out)
    for ai in range(1 << width):
        expected = evaluate_not(ai, width)
        for oi in range(1 << width):
            fixed = {a[i]: bool(ai >> i & 1) for i in range(width)}
            fixed.update({out[i]: bool(oi >> i & 1) for i in range(width)})
            sat = _sat_under(blaster, fixed)
            if oi == expected:
                assert sat
            else:
                assert not sat
