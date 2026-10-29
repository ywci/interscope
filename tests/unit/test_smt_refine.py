# tests/unit/test_smt_refine.py
#
# Unit tests for the bounded SMT refinement checker (smt_refine.py).

import random
import pytest
from isir.lowering.smt_refine import (
    expr_to_smt, refine_write, validate_encoder, smt_eval,
    coq_dsl_to_smt, refine_isir_vs_koika,
)
from isir.utils.expr import parse_sexpr


WIDTHS = {"a": 8, "b": 8, "x": 8, "y": 8}


def _samples(n=20):
    rng = random.Random(0)
    return [{k: rng.getrandbits(8) for k in ("a", "b", "x", "y")} for _ in range(n)]


class TestEncoder:
    @pytest.mark.parametrize("sexpr", [
        "(add a b)", "(sub a b)", "(and a b)", "(or a b)", "(xor a b)", "(not a)",
        "(eq a b)", "(neq a b)", "(lt a b)", "(ge a b)",
        "(shl a b)", "(shr a b)",
        "(slice a 7 4)", "(slice a 3 0)",
        "(ite (lt a b) a b)",
        "(ge (add x y) 256)", "(le (add x y) 255)",
    ])
    def test_matches_eval_expr(self, sexpr):
        e = parse_sexpr(sexpr)
        # validate at both the operand width and a 1-bit (bool) destination
        assert validate_encoder(e, 8, WIDTHS, _samples())
        assert validate_encoder(e, 1, WIDTHS, _samples())

    def test_ge_add_widens_comparison_literal(self):
        # `ge (add x y) 256` must zero-extend the 8-bit sum and emit 256 at 9 bits.
        decls = set()
        term = expr_to_smt(parse_sexpr("(ge (add x y) 256)"), 8, WIDTHS, decls)
        assert "zero_extend" in term and "256" in term

    def test_smt_eval_matches(self):
        e = parse_sexpr("(add a b)")
        assert smt_eval(e, 8, WIDTHS, {"a": 250, "b": 10}) == 4  # wraps mod 256


class TestRefineWrite:
    def test_same_is_unsat(self):
        r = refine_write("r", parse_sexpr("(add a b)"), parse_sexpr("(add a b)"), 8, WIDTHS)
        assert r["status"] == "unsat"

    def test_diverge_is_sat(self):
        r = refine_write("r", parse_sexpr("(add a b)"), parse_sexpr("(sub a b)"), 8, WIDTHS)
        assert r["status"] == "sat"

    def test_comparison_literal_bug_is_sat(self):
        # Correct `ge (add x y) 256` vs the historical width-buggy `ge (add x y) 0`.
        r = refine_write("r", parse_sexpr("(ge (add x y) 256)"),
                         parse_sexpr("(ge (add x y) 0)"), 1, WIDTHS)
        assert r["status"] == "sat"


class TestCoqDslEncoder:
    def test_roundtrip_simple(self):
        term, decls = coq_dsl_to_smt("(read0(A_reg) + read0(B_reg))",
                                     {"a_reg": 8, "b_reg": 8})
        assert term == "(bvadd a_reg b_reg)"
        assert ("a_reg", 8) in decls and ("b_reg", 8) in decls

    def test_zeroextend_target_width(self):
        # zeroExtend(a, 9) extends to width 9 (delta 1), not by 9.
        term, _ = coq_dsl_to_smt("zeroExtend((read0(X) + read0(Y)), 9)", {"x": 8, "y": 8})
        assert "(_ zero_extend 1)" in term

    def test_partial_spec_fresh_variable(self):
        # A bodyless function (partial_spec) is non-deterministic, not 0.
        decls = set()
        term = expr_to_smt(parse_sexpr("(sigmoid (read x))"), 8, {"x": 8}, decls,
                           blackboxes={"sigmoid"})
        assert term == "sigmoid"
        assert ("sigmoid", 8) in decls

    def test_extcall_fresh_variable(self):
        term, decls = coq_dsl_to_smt("extcall Sigmoid(read0(X))", {"x": 8, "sigmoid": 8})
        assert term == "sigmoid"
        assert ("sigmoid", 8) in decls


class TestRefineIsirVsKoika:
    def test_known_good_is_unsat(self):
        # The reference `(ge (add x y) 256)` and the Kōika DSL agree.
        r = refine_isir_vs_koika("r", parse_sexpr("(ge (add x y) 256)"),
                                 "(! (zeroExtend((read0(X) + read0(Y)), 9) < |9`d256|))",
                                 1, WIDTHS)
        assert r["status"] == "unsat"

    def test_injected_bug_is_sat(self):
        # A wrong Kōika DSL (the buggy `|8'd256|` == 0) must be caught.
        r = refine_isir_vs_koika("r", parse_sexpr("(ge (add x y) 256)"),
                                 "(! ((read0(X) + read0(Y)) < |8`d0|))",
                                 1, WIDTHS)
        assert r["status"] == "sat"


class TestRefineTrace:
    def test_counter_unsat(self):
        from pathlib import Path
        from isir.parser.parser import parse_isir
        from isir.lowering.ast_to_isir import convert_ast_to_isir_module
        from isir.lowering.smt_refine import refine_trace
        spec = convert_ast_to_isir_module(parse_isir(Path("examples/counter/counter.isir")).module)
        assert refine_trace(spec, cycles=3)["status"] == "unsat"

    def test_gcd_unsat(self):
        from pathlib import Path
        from isir.parser.parser import parse_isir
        from isir.lowering.ast_to_isir import convert_ast_to_isir_module
        from isir.lowering.smt_refine import refine_trace
        spec = convert_ast_to_isir_module(parse_isir(Path("examples/gcd/gcd.isir")).module)
        assert refine_trace(spec, cycles=3)["status"] == "unsat"
