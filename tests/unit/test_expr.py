# tests/unit/test_expr.py
#
# Comprehensive unit tests for the SpecIR expression engine
# (src/specir/utils/expr.py). Covers parsing, evaluation,
# type checking, and error handling.

import pytest
from specir.utils.expr import (
    parse_sexpr,
    eval_expr,
    type_check_expr,
    expr_to_string,
    ExprError,
)


class TestParseSexpr:
    def test_atom_int(self):
        assert parse_sexpr("42") == 42

    def test_atom_string(self):
        assert parse_sexpr("foo") == "foo"

    def test_atom_true(self):
        assert parse_sexpr("true") is True

    def test_atom_false(self):
        assert parse_sexpr("false") is False

    def test_atom_bool_direct(self):
        assert parse_sexpr(True) is True
        assert parse_sexpr(False) is False

    def test_atom_int_direct(self):
        assert parse_sexpr(42) == 42

    def test_simple_list(self):
        assert parse_sexpr("(add 1 2)") == ["add", 1, 2]

    def test_nested_list(self):
        assert parse_sexpr("(and (not a) b)") == ["and", ["not", "a"], "b"]

    def test_already_list(self):
        # Should return a copy, not the same object
        original = ["add", 1, 2]
        result = parse_sexpr(original)
        assert result == original
        assert result is not original

    def test_empty_string_error(self):
        with pytest.raises(ExprError, match="Empty expression"):
            parse_sexpr("")

    def test_whitespace_only(self):
        with pytest.raises(ExprError, match="Empty expression"):
            parse_sexpr("   ")

    def test_unbalanced_open(self):
        with pytest.raises(ExprError, match="Unbalanced parentheses"):
            parse_sexpr("(and a b")

    def test_unbalanced_close(self):
        with pytest.raises(ExprError, match="Unbalanced parentheses"):
            parse_sexpr("(and a b))")

    def test_empty_parens(self):
        with pytest.raises(ExprError, match="Empty expression"):
            parse_sexpr("()")

    def test_nested_empty(self):
        with pytest.raises(ExprError, match="Empty expression"):
            parse_sexpr("(and ())")


class TestEvalExpr:
    def test_add(self):
        assert eval_expr("(add 3 5)", {}) == 8

    def test_sub(self):
        assert eval_expr("(sub 10 4)", {}) == 6

    def test_mul(self):
        assert eval_expr("(mul 3 7)", {}) == 21

    def test_div(self):
        assert eval_expr("(div 10 3)", {}) == 3   # integer truncation toward zero
        assert eval_expr("(div -10 3)", {}) == -3

    def test_mod(self):
        assert eval_expr("(mod 10 3)", {}) == 1

    def test_div_by_zero(self):
        with pytest.raises(ExprError, match="Division by zero"):
            eval_expr("(div 1 0)", {})

    def test_mod_by_zero(self):
        with pytest.raises(ExprError, match="Modulo by zero"):
            eval_expr("(mod 1 0)", {})

    def test_and(self):
        assert eval_expr("(and true true)", {}) is True
        assert eval_expr("(and true false)", {}) is False

    def test_or(self):
        assert eval_expr("(or false true)", {}) is True
        assert eval_expr("(or false false)", {}) is False

    def test_not(self):
        assert eval_expr("(not true)", {}) is False
        assert eval_expr("(not false)", {}) is True

    def test_implies(self):
        assert eval_expr("(implies true true)", {}) is True
        assert eval_expr("(implies true false)", {}) is False
        assert eval_expr("(implies false true)", {}) is True
        assert eval_expr("(implies false false)", {}) is True

    def test_eq(self):
        assert eval_expr("(eq 5 5)", {}) is True
        assert eval_expr("(eq 5 6)", {}) is False

    def test_neq(self):
        assert eval_expr("(neq 5 5)", {}) is False
        assert eval_expr("(neq 5 6)", {}) is True

    def test_gt(self):
        assert eval_expr("(gt 7 3)", {}) is True

    def test_lt(self):
        assert eval_expr("(lt 3 7)", {}) is True

    def test_gte(self):
        assert eval_expr("(gte 5 5)", {}) is True

    def test_lte(self):
        assert eval_expr("(lte 3 5)", {}) is True

    def test_le(self):
        assert eval_expr("(le 5 5)", {}) is True
        assert eval_expr("(le 6 5)", {}) is False

    def test_ge(self):
        assert eval_expr("(ge 5 5)", {}) is True
        assert eval_expr("(ge 4 5)", {}) is False

    def test_ite_true(self):
        assert eval_expr("(ite true 42 0)", {}) == 42

    def test_ite_false(self):
        assert eval_expr("(ite false 42 0)", {}) == 0

    def test_ite_nested(self):
        assert eval_expr("(ite (gt 3 1) (add 2 2) 0)", {}) == 4

    def test_read_state(self):
        assert eval_expr("(read head)", {"head": 5}) == 5

    def test_read_input(self):
        assert eval_expr("(read enq)", {}, inputs={"enq": True}) is True

    def test_read_unknown(self):
        with pytest.raises(ExprError, match="unknown state or input"):
            eval_expr("(read unknown)", {})

    def test_read_not_string(self):
        with pytest.raises(ExprError, match="read expects a state name as literal string"):
            eval_expr("(read (add 1 2))", {})

    def test_mem_read(self):
        memories = {"mem": {0: 10, 1: 20}}
        assert eval_expr("(mem_read mem 0)", {}, memories=memories) == 10
        assert eval_expr("(mem_read mem 1)", {}, memories=memories) == 20
        # Missing address defaults to 0
        assert eval_expr("(mem_read mem 99)", {}, memories=memories) == 0

    def test_mem_read_unknown_memory(self):
        with pytest.raises(ExprError, match="Unknown memory"):
            eval_expr("(mem_read bad 0)", {})

    def test_mem_read_non_int_addr(self):
        # Use a boolean value as address to trigger type error
        with pytest.raises(ExprError, match="Memory address must be integer"):
            eval_expr("(mem_read mem true)", {}, memories={"mem": {}})

    def test_concat(self):
        # Default width of low is 8 bits; shift high by 8
        assert eval_expr("(concat 1 2)", {}) == (1 << 8) | 2

    def test_slice(self):
        # (slice val high low)
        val = 0b110101
        # bits 5 down to 3 -> 110 = 6
        assert eval_expr(f"(slice {val} 5 3)", {}) == 6

    def test_slice_bounds_error(self):
        with pytest.raises(ExprError, match="high.*must be >= low"):
            eval_expr("(slice 10 3 5)", {})

    def test_write_action_fails(self):
        with pytest.raises(ExprError, match="write is not an expression"):
            eval_expr("(write head 5)", {"head": 0})

    def test_mem_write_action_fails(self):
        with pytest.raises(ExprError, match="mem_write is an action"):
            eval_expr("(mem_write mem 0 5)", {}, memories={"mem": {}})

    def test_next_operator(self):
        state = {"a": 1}
        next_state = {"a": 2}
        assert eval_expr("(next (read a))", state, next_state=next_state) == 2

    def test_prev_operator(self):
        state = {"a": 2}
        prev_state = {"a": 1}
        assert eval_expr("(prev (read a))", state, previous_state=prev_state) == 1

    def test_rose_true(self):
        prev = {"sig": 0}
        curr = {"sig": 1}
        assert eval_expr("(rose (read sig))", curr, previous_state=prev) is True

    def test_rose_false(self):
        prev = {"sig": 1}
        curr = {"sig": 0}
        assert eval_expr("(rose (read sig))", curr, previous_state=prev) is False

    def test_fell_true(self):
        prev = {"sig": 1}
        curr = {"sig": 0}
        assert eval_expr("(fell (read sig))", curr, previous_state=prev) is True

    def test_fell_false(self):
        prev = {"sig": 0}
        curr = {"sig": 1}
        assert eval_expr("(fell (read sig))", curr, previous_state=prev) is False

    def test_stable(self):
        prev = {"sig": 3}
        curr = {"sig": 3}
        assert eval_expr("(stable (read sig))", curr, previous_state=prev) is True
        curr2 = {"sig": 4}
        assert eval_expr("(stable (read sig))", curr2, previous_state=prev) is False

    def test_next_without_context(self):
        with pytest.raises(ExprError, match="requires next_state"):
            eval_expr("(next (read a))", {"a": 0})

    def test_prev_without_context(self):
        with pytest.raises(ExprError, match="requires previous_state"):
            eval_expr("(prev (read a))", {"a": 0})

    def test_rose_without_context(self):
        with pytest.raises(ExprError, match="requires previous_state"):
            eval_expr("(rose (read a))", {"a": 1})

    def test_unknown_operator(self):
        with pytest.raises(ExprError, match="Unknown operator"):
            eval_expr("(bogus 1 2)", {})


class TestExprToString:
    def test_int(self):
        assert expr_to_string(42) == "42"

    def test_bool(self):
        assert expr_to_string(True) == "true"

    def test_list(self):
        assert expr_to_string(["add", 1, 2]) == "(add 1 2)"

    def test_string_input(self):
        assert expr_to_string("(add 1 2)") == "(add 1 2)"


class TestTypeCheckExpr:
    def setup_method(self):
        self.context = {"a": "bool", "b": "bool", "x": "int", "y": "int"}

    def test_int_constant(self):
        assert type_check_expr(42, self.context) == "int"

    def test_bool_constant(self):
        assert type_check_expr("true", self.context) == "bool"

    def test_variable(self):
        assert type_check_expr("a", self.context) == "bool"

    def test_unknown_variable(self):
        with pytest.raises(ExprError, match="Unknown identifier"):
            type_check_expr("z", self.context)

    def test_arithmetic(self):
        assert type_check_expr("(add x y)", self.context) == "int"
        assert type_check_expr("(sub x 1)", self.context) == "int"

    def test_arithmetic_bad_type(self):
        with pytest.raises(ExprError, match="requires int"):
            type_check_expr("(add a b)", self.context)

    def test_logical(self):
        assert type_check_expr("(and a b)", self.context) == "bool"
        assert type_check_expr("(not a)", self.context) == "bool"
        assert type_check_expr("(implies a b)", self.context) == "bool"

    def test_logical_bad_type(self):
        with pytest.raises(ExprError, match="requires bool"):
            type_check_expr("(and x y)", self.context)

    def test_comparison(self):
        # eq/neq produce bool regardless of operand types
        assert type_check_expr("(eq x y)", self.context) == "bool"
        assert type_check_expr("(neq a b)", self.context) == "bool"
        assert type_check_expr("(le x y)", self.context) == "bool"
        assert type_check_expr("(ge a b)", self.context) == "bool"

    def test_ite(self):
        assert type_check_expr("(ite a x y)", self.context) == "int"

    def test_ite_cond_not_bool(self):
        with pytest.raises(ExprError, match="condition must be bool"):
            type_check_expr("(ite x a b)", self.context)

    def test_ite_branch_type_mismatch(self):
        with pytest.raises(ExprError, match="branches must have same type"):
            type_check_expr("(ite a x b)", self.context)

    def test_read(self):
        # read of a variable in context returns its type
        assert type_check_expr("(read x)", self.context) == "int"

    def test_read_unknown(self):
        with pytest.raises(ExprError, match="Unknown state"):
            type_check_expr("(read z)", self.context)

    def test_concat_slice(self):
        assert type_check_expr("(concat x y)", self.context) == "bits"

    def test_mem_read(self):
        assert type_check_expr("(mem_read mem addr)", {}) == "bits"

    def test_temporal_operators(self):
        # temporal operators propagate the type of their operand
        assert type_check_expr("(next (read x))", self.context) == "int"
        assert type_check_expr("(rose (read a))", self.context) == "bool"
