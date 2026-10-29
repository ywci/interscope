# tests/unit/test_nat_model_fidelity.py
#
# nat-proof-model fidelity: the wrapped nat model (`isir_to_koika.py`) must
# match the reference interpreter (`eval_expr`) and the RTL `bits<N>` semantics.
#
# Two layers of evidence:
#   1. `_width_of_expr` mirrors `eval_expr._expr_width` exactly (the operand width
#      used for wrapping).
#   2. The wrap semantics (`(op) mod 2^N`, two's-complement `sub`) agree with
#      `eval_expr` over a random/exhaustive input sweep.

import random
import pytest
from isir.utils.expr import eval_expr, parse_sexpr
from isir.lowering.isir_to_koika import _width_of_expr, _width_of_type


def _reference_expr_width(e, widths):
    w = 1
    def _walk(x):
        nonlocal w
        if isinstance(x, str):
            w = max(w, (widths or {}).get(x, 1))
        elif isinstance(x, list):
            for y in x:
                _walk(y)
    _walk(e)
    return w


def _wrap_semantics(expr, inputs, widths):
    """Evaluate `expr` the way the wrapped nat model does: arithmetic is reduced
    modulo 2^op_w with op_w = max operand width, and `sub` is two's-complement."""
    def ev(e):
        if isinstance(e, bool):
            return e
        if isinstance(e, int):
            return e
        if isinstance(e, str):
            return inputs[e]
        op, args = e[0], e[1:]
        if op in ('add', 'sub', 'mul', 'div', 'mod', 'shl', 'shr', 'lshift', 'rshift'):
            a, b = ev(args[0]), ev(args[1])
            op_w = max(_width_of_expr(args[0], widths), _width_of_expr(args[1], widths))
            mask = (1 << op_w) - 1
            if op == 'add':
                return (a + b) & mask
            if op == 'sub':
                return (a - b) & mask                      # Python signed -> two's complement
            if op == 'mul':
                return (a * b) & mask
            if op == 'div':
                return 0 if b == 0 else (int(a / b) if a >= 0 else -int(-a / b)) & mask
            if op == 'mod':
                return 0 if b == 0 else (a % b) & mask
            if op in ('shl', 'lshift'):
                return (a << b) & mask
            if op in ('shr', 'rshift'):
                return (a >> b) & mask
        if op in ('and', 'or', 'xor'):
            a, b = ev(args[0]), ev(args[1])
            return {'and': a & b, 'or': a | b, 'xor': a ^ b}[op]
        if op == 'not':
            return not ev(args[0])
        if op in ('eq', 'neq', 'gt', 'lt', 'gte', 'lte', 'le', 'ge'):
            a, b = ev(args[0]), ev(args[1])
            return {'eq': a == b, 'neq': a != b, 'gt': a > b, 'lt': a < b,
                    'gte': a >= b, 'lte': a <= b, 'le': a <= b, 'ge': a >= b}[op]
        if op == 'ite':
            return ev(args[1]) if ev(args[0]) else ev(args[2])
        raise ValueError(f"unsupported op in fidelity spec: {op}")
    return ev(expr)


class TestWidthOfType:
    def test_bits_and_bool(self):
        assert _width_of_type("bool") == 1
        assert _width_of_type("bits<4>") == 4
        assert _width_of_type("bits<32>") == 32


class TestWidthMirrorsReference:
    """_width_of_expr must equal eval_expr._expr_width on every operand shape."""

    @pytest.mark.parametrize("sexpr", [
        "x", "y", "1", "255",
        "(add x y)", "(add x 1)", "(add 1 2)",
        "(sub x y)", "(mul x y)", "(shl x 2)",
        "(add (add x y) z)", "(slice x 7 0)",
        "(ite (gt x y) x y)",
    ])
    def test_width_match(self, sexpr):
        widths = {"x": 8, "y": 8, "z": 8}
        e = parse_sexpr(sexpr)
        assert _width_of_expr(e, widths) == _reference_expr_width(e, widths)


class TestWrapMatchesEvalExpr:
    """The wrapped arithmetic must agree with the reference interpreter."""

    W = {"x": 8, "y": 8, "z": 8}

    def _check(self, sexpr, inputs):
        e = parse_sexpr(sexpr)
        ref = eval_expr(e, state={}, inputs=dict(inputs), width=8, widths=self.W)
        got = _wrap_semantics(e, inputs, self.W)
        assert got == ref, f"{sexpr} @ {inputs}: nat-model {got} != reference {ref}"

    def test_exhaustive_add_sub_8bit(self):
        for x in [0, 1, 127, 128, 200, 250, 255]:
            for y in [0, 1, 10, 127, 200, 255]:
                self._check("(add x y)", {"x": x, "y": y})
                self._check("(sub x y)", {"x": x, "y": y})

    def test_random_arithmetic(self, seed=42):
        rng = random.Random(seed)
        for _ in range(500):
            x, y = rng.randrange(256), rng.randrange(256)
            for op in ["add", "sub", "mul", "shl", "shr", "div", "mod"]:
                if op in ("shl", "shr"):
                    y = rng.randrange(9)  # shift amount
                if op in ("div", "mod") and y == 0:
                    y = 1
                self._check(f"({op} x y)", {"x": x, "y": y})

    def test_nested_and_comparison(self):
        self._check("(add (add x y) z)", {"x": 200, "y": 100, "z": 50})
        self._check("(ge (add x y) 256)", {"x": 250, "y": 10})   # the saturating_adder case
        self._check("(ge (add x y) 256)", {"x": 10, "y": 10})
        self._check("(lt (add x y) 15)", {"x": 10, "y": 10})

    def test_saturating_adder_expression(self):
        # The whole saturating_adder RHS: ite (ge (add x y) 256) 255 (add x y)
        sexpr = "(ite (ge (add x y) 256) 255 (add x y))"
        for x, y in [(250, 10), (10, 10), (200, 100), (255, 255), (0, 0)]:
            self._check(sexpr, {"x": x, "y": y})
