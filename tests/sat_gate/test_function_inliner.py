# tests/sat_gate/test_function_inliner.py

from isir.verification.sat_gate.function_inliner import (
    functions_of, inline_functions, sexpr_to_string,
)


def test_builtin_min_max_clamp():
    fns = {}
    assert sexpr_to_string(inline_functions("(min (read a) (read b))", fns)) == \
        "(clamp min (read a) (read b))"
    assert sexpr_to_string(inline_functions("(max (read a) (read b))", fns)) == \
        "(clamp max (read a) (read b))"
    assert sexpr_to_string(inline_functions("(clamp8 (read x))", fns)) == \
        "(clamp min (read x) 255)"


def test_user_defined_function_substitution():
    fns = {"l1i_has_line": {"params": ["s", "a", "ra"],
                            "body": "(and (neq s 0) (eq a ra))"}}
    out = inline_functions("(l1i_has_line (read st) (read addr) (read req))", fns)
    assert sexpr_to_string(out) == \
        "(and (neq (read st) 0) (eq (read addr) (read req)))"


def test_recursive_function_is_skipped():
    fns = {"f": {"params": ["x"], "body": "(f x)", "recursive": True}}
    # functions_of would have skipped it; here the inline must leave the call.
    assert sexpr_to_string(inline_functions("(f a)", fns)) == "(f a)"
