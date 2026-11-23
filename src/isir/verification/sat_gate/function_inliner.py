# src/isir/verification/sat_gate/function_inliner.py
#
# Function inlining for the gate fragment. User-defined ISIR functions and a
# small set of built-in arithmetic functions are expanded before lowering, so
# the bit-blaster/SMT encoder never sees a bare function call.

from typing import Dict, List, Union
from isir.utils.expr import parse_sexpr


def functions_of(spec_module) -> Dict[str, "dict"]:
    """Return function name -> {'params': [names], 'body': sexpr-string}."""
    out: Dict[str, dict] = {}
    for fn in getattr(spec_module, "functions", []) or []:
        name = fn.get("name")
        if not name or fn.get("recursive"):
            continue  # recursive functions are out of the gate fragment
        params = [p["name"] for p in fn.get("params", []) or []]
        out[name] = {"params": params, "body": fn.get("body") or ""}
    return out


# Built-in arithmetic functions expressed as parsed S-expression constructors.
BUILTIN_BODIES = {
    "min": lambda a, b: ["clamp", "min", a, b],
    "max": lambda a, b: ["clamp", "max", a, b],
    "min3": lambda a, b, c: ["min", ["min", a, b], c],
    "max3": lambda a, b, c: ["max", ["max", a, b], c],
    "clamp8": lambda x: ["clamp", "min", x, 255],
}


def _substitute(expr, subs: Dict[str, str]):
    if isinstance(expr, str):
        return subs.get(expr, expr)
    if isinstance(expr, list):
        return [_substitute(x, subs) for x in expr]
    return expr


def sexpr_to_string(expr) -> str:
    """Render a parsed S-expression (list/atom) back to a string."""
    if isinstance(expr, list):
        return "(" + " ".join(sexpr_to_string(x) for x in expr) + ")"
    return str(expr)


def inline_functions(expr: Union[str, List], functions: Dict[str, dict]) -> Union[str, List]:
    """Recursively inline function calls in an S-expression.

    User-defined functions are substituted (non-recursive only); a small set of
    built-ins (min/max/clamp8) are expanded directly.
    """
    if isinstance(expr, str):
        expr = parse_sexpr(expr)
    if not isinstance(expr, list) or not expr:
        return expr

    op = expr[0]
    args = expr[1:]

    # built-in arithmetic expansions (recurse into the args first so nested
    # built-ins like (min (max ...) ...) are inlined, then re-inline the result
    # so min3/max3 expand to their ite chains).
    if op in BUILTIN_BODIES:
        inlined_args = [inline_functions(a, functions) for a in args]
        return inline_functions(BUILTIN_BODIES[op](*inlined_args), functions)

    # user-defined function call (non-recursive, with a body to inline)
    if op in functions:
        fn = functions[op]
        if fn.get("body") and not fn.get("recursive") and len(args) == len(fn["params"]):
            body = parse_sexpr(fn["body"])
            subs = dict(zip(fn["params"], args))
            return inline_functions(_substitute(body, subs), functions)

    # ordinary compound: recurse into the args
    return [op] + [inline_functions(a, functions) for a in args]
