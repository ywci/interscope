# src/specir/utils/expr.py
#
# S-expression parser, evaluator, and type checker for SpecIR expressions.
# Supports all operators defined in the specification (add, sub, and, or, not,
# eq, neq, gt, lt, gte, lte, le, ge, mul, div, mod, concat, slice, ite, read,
# write, mem_read, mem_write, next, prev, rose, fell, stable, implies).
# Also provides functions to convert an expression to a string and type-check it.

import re
from typing import Any, Dict, List, Optional, Union


class ExprError(Exception):
    """Exception raised for expression parsing or evaluation errors."""
    pass


def parse_sexpr(s: Union[str, List, int, bool]) -> Any:
    """
    Parse a string S-expression into a nested list structure.

    Args:
        s: String like "(add (read head) 1)", an already‑parsed list,
           or an atomic value (int, bool).

    Returns:
        Nested list representation, or the atom itself for non‑string atoms.

    Raises:
        ExprError: On malformed expressions or empty input.
    """
    if isinstance(s, list):
        return s[:]

    if isinstance(s, (int, bool)):
        return s

    if not isinstance(s, str):
        raise ExprError(f"Cannot parse expression of type {type(s)}")

    s = s.strip()
    if not s:
        raise ExprError("Empty expression string")

    if not s.startswith('('):
        try:
            return int(s)
        except ValueError:
            if s.lower() == 'true':
                return True
            if s.lower() == 'false':
                return False
            return s

    tokens = []
    i = 0
    n = len(s)
    while i < n:
        ch = s[i]
        if ch == '(':
            tokens.append('(')
            i += 1
        elif ch == ')':
            tokens.append(')')
            i += 1
        elif ch.isspace():
            i += 1
        else:
            start = i
            while i < n and not s[i].isspace() and s[i] not in '()':
                i += 1
            token = s[start:i]
            try:
                tokens.append(int(token))
            except ValueError:
                if token.lower() == 'true':
                    tokens.append(True)
                elif token.lower() == 'false':
                    tokens.append(False)
                else:
                    tokens.append(token)

    stack = [[]]
    for tok in tokens:
        if tok == '(':
            stack.append([])
        elif tok == ')':
            if len(stack) == 1:
                raise ExprError("Unbalanced parentheses: unexpected ')'")
            expr = stack.pop()
            stack[-1].append(expr)
        else:
            stack[-1].append(tok)

    if len(stack) != 1:
        raise ExprError("Unbalanced parentheses: missing ')'")

    result = stack[0]
    if not result:
        raise ExprError("Empty expression")

    if isinstance(result, list) and len(result) == 1 and isinstance(result[0], list) and not result[0]:
        raise ExprError("Empty expression")

    def _check_empty(expr):
        if isinstance(expr, list):
            if not expr:
                raise ExprError("Empty expression")
            for e in expr:
                _check_empty(e)
    _check_empty(result)

    return result[0] if len(result) == 1 else result


def eval_expr(expr: Union[str, List],
              state: Dict[str, Any],
              inputs: Optional[Dict[str, Any]] = None,
              memories: Optional[Dict[str, Dict[int, Any]]] = None,
              previous_state: Optional[Dict[str, Any]] = None,
              next_state: Optional[Dict[str, Any]] = None) -> Any:
    """
    Evaluate a SpecIR expression in the context of current state, inputs, and memories.

    Args:
        expr: S-expression (string or nested list) to evaluate.
        state: Mapping from register names to current values (int or bool).
        inputs: Mapping from input signal names to current values.
        memories: Mapping from memory names to dictionaries (address -> value).
        previous_state: Optional previous cycle state (for temporal operators).
        next_state: Optional next cycle state (for temporal operators).

    Returns:
        Evaluated value (int, bool, or None for unknown/unused).

    Raises:
        ExprError on unsupported operator or type mismatch.
    """
    if inputs is None:
        inputs = {}
    if memories is None:
        memories = {}

    parsed = parse_sexpr(expr)
    return _eval_internal(parsed, state, inputs, memories, previous_state, next_state)


def _eval_internal(expr: Any,
                   state: Dict[str, Any],
                   inputs: Dict[str, Any],
                   memories: Dict[str, Dict[int, Any]],
                   previous_state: Optional[Dict[str, Any]],
                   next_state: Optional[Dict[str, Any]]) -> Any:
    """Internal recursive evaluator."""
    if isinstance(expr, bool):
        return expr
    if isinstance(expr, int):
        return expr
    if isinstance(expr, str):
        if expr in state:
            return state[expr]
        if inputs is not None and expr in inputs:
            return inputs[expr]
        raise ExprError(f"Unknown variable '{expr}' — not in state or inputs")

    if not isinstance(expr, list) or len(expr) == 0:
        raise ExprError(f"Invalid expression: {expr}")

    op = expr[0]
    if not isinstance(op, str):
        raise ExprError(f"Operator must be a string, got {type(op)}")

    args = expr[1:]

    # Arithmetic
    if op in ('add', 'sub', 'mul', 'div', 'mod'):
        if len(args) != 2:
            raise ExprError(f"{op} expects 2 arguments, got {len(args)}")
        a = _eval_internal(args[0], state, inputs, memories, previous_state, next_state)
        b = _eval_internal(args[1], state, inputs, memories, previous_state, next_state)
        if op == 'add':
            return a + b
        elif op == 'sub':
            return a - b
        elif op == 'mul':
            return a * b
        elif op == 'div':
            if b == 0:
                raise ExprError("Division by zero")
            # Integer division (truncates toward zero for positive; hardware usually truncates)
            return int(a / b) if a >= 0 else -int(-a / b)
        elif op == 'mod':
            if b == 0:
                raise ExprError("Modulo by zero")
            return a % b

    # Logical
    elif op in ('and', 'or'):
        if len(args) != 2:
            raise ExprError(f"{op} expects 2 arguments, got {len(args)}")
        a = _eval_internal(args[0], state, inputs, memories, previous_state, next_state)
        b = _eval_internal(args[1], state, inputs, memories, previous_state, next_state)
        if op == 'and':
            return a and b
        else:
            return a or b

    elif op == 'not':
        if len(args) != 1:
            raise ExprError("not expects 1 argument")
        a = _eval_internal(args[0], state, inputs, memories, previous_state, next_state)
        return not a

    elif op == 'implies':
        if len(args) != 2:
            raise ExprError("implies expects 2 arguments")
        a = _eval_internal(args[0], state, inputs, memories, previous_state, next_state)
        b = _eval_internal(args[1], state, inputs, memories, previous_state, next_state)
        # classical implication: (not a) or b
        return (not a) or b

    # Comparisons
    elif op in ('eq', 'neq', 'gt', 'lt', 'gte', 'lte', 'le', 'ge'):
        if len(args) != 2:
            raise ExprError(f"{op} expects 2 arguments, got {len(args)}")
        a = _eval_internal(args[0], state, inputs, memories, previous_state, next_state)
        b = _eval_internal(args[1], state, inputs, memories, previous_state, next_state)
        if op == 'eq':
            return a == b
        elif op == 'neq':
            return a != b
        elif op == 'gt':
            return a > b
        elif op == 'lt':
            return a < b
        elif op == 'gte':
            return a >= b
        elif op == 'lte':
            return a <= b
        elif op == 'le':
            return a <= b
        elif op == 'ge':
            return a >= b

    # Bit‑vector operations
    elif op == 'concat':
        if len(args) != 2:
            raise ExprError("concat expects 2 arguments")
        high = _eval_internal(args[0], state, inputs, memories, previous_state, next_state)
        low = _eval_internal(args[1], state, inputs, memories, previous_state, next_state)
        # Width assumption: default width of low is 8 bits
        try:
            return (high << 8) | low
        except TypeError:
            raise ExprError("concat requires integer operands")

    elif op == 'slice':
        if len(args) != 3:
            raise ExprError("slice expects 3 arguments: expr high low")
        val = _eval_internal(args[0], state, inputs, memories, previous_state, next_state)
        high = _eval_internal(args[1], state, inputs, memories, previous_state, next_state)
        low = _eval_internal(args[2], state, inputs, memories, previous_state, next_state)
        if not isinstance(high, int) or not isinstance(low, int):
            raise ExprError("slice bounds must be integers")
        if high < low:
            raise ExprError(f"slice: high ({high}) must be >= low ({low})")
        mask = (1 << (high - low + 1)) - 1
        return (val >> low) & mask

    # if‑then‑else
    elif op == 'ite':
        if len(args) != 3:
            raise ExprError("ite expects 3 arguments: cond then else")
        cond = _eval_internal(args[0], state, inputs, memories, previous_state, next_state)
        if cond:
            return _eval_internal(args[1], state, inputs, memories, previous_state, next_state)
        else:
            return _eval_internal(args[2], state, inputs, memories, previous_state, next_state)

    # State / memory access
    elif op == 'read':
        if len(args) != 1:
            raise ExprError("read expects 1 argument (state name)")
        name = args[0]
        if not isinstance(name, str):
            raise ExprError(f"read expects a state name as literal string, got {type(name)}")
        # Look up in state first, then inputs
        if name in state:
            return state[name]
        if inputs is not None and name in inputs:
            return inputs[name]
        raise ExprError(f"read: unknown state or input '{name}'")

    elif op == 'write':
        raise ExprError("write is not an expression, it's an action")

    elif op == 'mem_read':
        if len(args) != 2:
            raise ExprError("mem_read expects 2 arguments: mem_name address")
        mem_name = args[0]
        if not isinstance(mem_name, str):
            raise ExprError(f"mem_read expects memory name as literal string, got {type(mem_name)}")
        addr = _eval_internal(args[1], state, inputs, memories, previous_state, next_state)
        if mem_name not in memories:
            raise ExprError(f"Unknown memory '{mem_name}'")
        # Python booleans are a subclass of int; reject them explicitly
        if isinstance(addr, bool) or not isinstance(addr, int):
            raise ExprError(f"Memory address must be integer, got {type(addr)}")
        return memories[mem_name].get(addr, 0)

    elif op == 'mem_write':
        raise ExprError("mem_write is an action, not an expression")

    # Temporal operators – require trace context
    elif op == 'next':
        if len(args) != 1:
            raise ExprError("next expects 1 argument")
        if next_state is None:
            raise ExprError("'next' operator requires next_state context (evaluate within a trace)")
        return _eval_internal(args[0], next_state, inputs, memories, previous_state, next_state)

    elif op == 'prev':
        if len(args) != 1:
            raise ExprError("prev expects 1 argument")
        if previous_state is None:
            raise ExprError("'prev' operator requires previous_state context (evaluate within a trace)")
        return _eval_internal(args[0], previous_state, inputs, memories, previous_state, next_state)

    elif op == 'rose':
        if len(args) != 1:
            raise ExprError("rose expects 1 argument")
        if previous_state is None:
            raise ExprError("'rose' operator requires previous_state context")
        curr = _eval_internal(args[0], state, inputs, memories, previous_state, next_state)
        prev = _eval_internal(args[0], previous_state, inputs, memories, previous_state, next_state)
        return bool(curr) and not bool(prev)

    elif op == 'fell':
        if len(args) != 1:
            raise ExprError("fell expects 1 argument")
        if previous_state is None:
            raise ExprError("'fell' operator requires previous_state context")
        curr = _eval_internal(args[0], state, inputs, memories, previous_state, next_state)
        prev = _eval_internal(args[0], previous_state, inputs, memories, previous_state, next_state)
        return not bool(curr) and bool(prev)

    elif op == 'stable':
        if len(args) != 1:
            raise ExprError("stable expects 1 argument")
        if previous_state is None:
            raise ExprError("'stable' operator requires previous_state context")
        curr = _eval_internal(args[0], state, inputs, memories, previous_state, next_state)
        prev = _eval_internal(args[0], previous_state, inputs, memories, previous_state, next_state)
        return curr == prev

    else:
        raise ExprError(f"Unknown operator: {op}")


def expr_to_string(expr: Union[str, List, int, bool]) -> str:
    """
    Convert an S-expression to a human-readable string (e.g., for debugging).
    Accepts atoms and nested lists.
    """
    parsed = parse_sexpr(expr)
    return _expr_to_str(parsed)


def _expr_to_str(expr: Any) -> str:
    """Recursive string converter."""
    if isinstance(expr, bool):
        return 'true' if expr else 'false'
    if isinstance(expr, (int, str)):
        return str(expr)
    if isinstance(expr, list):
        return "(" + " ".join(_expr_to_str(e) for e in expr) + ")"
    return str(expr)


def type_check_expr(expr: Union[str, List, int, bool], context: Dict[str, str]) -> str:
    """
    Perform simple type checking on an expression given a context mapping
    identifiers to types ('bits<n>', 'bool', 'int').

    Returns a type string or raises ExprError.
    """
    parsed = parse_sexpr(expr)
    return _type_check_internal(parsed, context)


def _type_check_internal(expr: Any, context: Dict[str, str]) -> str:
    if isinstance(expr, bool):
        return "bool"
    if isinstance(expr, int):
        return "int"
    if isinstance(expr, str):
        if expr in context:
            return context[expr]
        raise ExprError(f"Unknown identifier '{expr}' in type context. Available: {list(context.keys())}")
    if not isinstance(expr, list) or len(expr) == 0:
        raise ExprError(f"Invalid expression for type check: {expr}")

    op = expr[0]
    if not isinstance(op, str):
        raise ExprError(f"Operator must be a string, got {type(op)}")
    args = expr[1:]

    if op in ('add', 'sub', 'mul', 'div', 'mod'):
        for arg in args:
            t = _type_check_internal(arg, context)
            if t not in ('int', 'any', 'bits'):
                raise ExprError(f"Arithmetic operator {op} requires int, got {t}")
        return "int"

    elif op in ('and', 'or', 'not', 'implies'):
        for arg in args:
            t = _type_check_internal(arg, context)
            if t != "bool":
                raise ExprError(f"Logical operator {op} requires bool, got {t}")
        return "bool"

    elif op in ('eq', 'neq', 'gt', 'lt', 'gte', 'lte', 'le', 'ge'):
        for arg in args:
            _type_check_internal(arg, context)
        return "bool"

    elif op == 'concat':
        return "bits"
    elif op == 'slice':
        return "bits"

    elif op == 'ite':
        if len(args) != 3:
            raise ExprError("ite expects 3 arguments")
        cond_type = _type_check_internal(args[0], context)
        then_type = _type_check_internal(args[1], context)
        else_type = _type_check_internal(args[2], context)
        if cond_type != "bool":
            raise ExprError("ite condition must be bool")
        if then_type != else_type:
            raise ExprError(f"ite branches must have same type, got {then_type} and {else_type}")
        return then_type

    elif op == 'read':
        if len(args) != 1:
            raise ExprError("read expects 1 argument (state name)")
        name = args[0]
        if not isinstance(name, str):
            raise ExprError("read expects a literal state name")
        if name not in context:
            raise ExprError(f"Unknown state '{name}' in read")
        return context[name]

    elif op == 'mem_read':
        return "bits"

    elif op in ('next', 'prev', 'rose', 'fell', 'stable'):
        if len(args) != 1:
            raise ExprError(f"{op} expects 1 argument")
        return _type_check_internal(args[0], context)

    else:
        raise ExprError(f"Type checking not implemented for operator '{op}'")
