# src/isir/lowering/isir_to_acl2.py
#
# Lowers a SpecModule (spec dialect) to a loadable ACL2Module (acl2 dialect):
# defun/defthm/defaxiom/defun-sk/encapsulate forms covering the single-cycle,
# temporal, and liveness subset of ISIR.  Generated defthms carry kind-aware
# best-effort hints and are admitted with skip-proofs so the output always
# loads; the prover (proof/acl2/prover.py) discharges them.

import re
from typing import Dict, List, Any, Optional, Set, Tuple
from isir.dialects import isir, acl2
from isir.utils.expr import parse_sexpr, ExprError, unfold_user_functions, expr_to_string
from isir.utils.logger import get_logger

logger = get_logger(__name__)


def _po_property(po) -> Optional[str]:
    """Return the property name stored in a proof obligation (dict or object)."""
    if isinstance(po, dict):
        return po.get("property")
    return getattr(po, "property", None)


def _po_backend(po) -> Optional[str]:
    """Return the backend stored in a proof obligation (dict or object)."""
    if isinstance(po, dict):
        return po.get("backend")
    return getattr(po, "backend", None)


def _po_metadata(po) -> Dict[str, Any]:
    """Return the metadata dict of a proof obligation."""
    if isinstance(po, dict):
        return po.get("metadata", {})
    return getattr(po, "metadata", {})


def _width_of_type(data_type: str) -> int:
    """Bit width of an ISIR data type (bool -> 1, bits<N> -> N, else 1)."""
    if data_type == "bool":
        return 1
    m = re.match(r"bits<(\d+)>", (data_type or "").strip())
    if m:
        return int(m.group(1))
    return 1


def _width_of_expr(expr: Any, widths: Optional[Dict[str, int]],
                   default: int = 1) -> int:
    """Mirror eval_expr._expr_width: the max bit width of the state/input names
    appearing in `expr` (the operand width used for wrapping)."""
    w = default
    def walk(x):
        nonlocal w
        if isinstance(x, str):
            w = max(w, (widths or {}).get(x, default))
        elif isinstance(x, list):
            for y in x:
                walk(y)
    walk(expr)
    return w


def _type_of_expr(expr: Any, state_types: Optional[Dict[str, str]],
                  input_types: Optional[Dict[str, str]]) -> str:
    """Return "bool" for a boolean-typed expression, else "bits<N>".  Used to
    decide whether and/or/xor are logical (bool) or bitwise (bits)."""
    if isinstance(expr, bool):
        return "bool"
    if isinstance(expr, int):
        return "bits<1>"
    if isinstance(expr, str):
        if state_types and expr in state_types:
            return state_types[expr]
        if input_types and expr in input_types:
            return input_types[expr]
        return "bits<1>"
    op = expr[0]
    args = expr[1:]
    if op in ("and", "or", "xor", "not", "implies",
              "eq", "neq", "gt", "lt", "gte", "lte", "le", "ge",
              "rose", "fell", "stable"):
        return "bool"
    if op == "ite" and len(args) >= 3:
        return _type_of_expr(args[1], state_types, input_types)
    if op in ("next", "prev") and args:
        return _type_of_expr(args[0], state_types, input_types)
    if op in ("read", "prev") and args:
        name = args[0]
        if isinstance(name, str):
            if state_types and name in state_types:
                return state_types[name]
            if input_types and name in input_types:
                return input_types[name]
        return "bits<1>"
    return "bits<1>"


def _subst_sexpr(node, subst):
    """Recursively replace string leaves via `subst` (used for independence
    primed-input copies)."""
    if isinstance(node, str):
        return subst.get(node, node)
    if isinstance(node, list):
        return [_subst_sexpr(x, subst) for x in node]
    return node


def _rewrite_recursive_calls(expr: Any, fname: str, fuel_term: str) -> Any:
    """Rewrite self-calls `(fname args...)` into `(fname fuel_term args...)`
    for a fuel-based ACL2 defun (structural recursion on fuel)."""
    if isinstance(expr, list):
        if len(expr) > 0 and expr[0] == fname:
            return [fname, fuel_term] + expr[1:]
        return [_rewrite_recursive_calls(e, fname, fuel_term) for e in expr]
    return expr


def _contains_temporal(sexpr: Any) -> bool:
    """True if the sexpr mentions a temporal operator (needs a trace model)."""
    if isinstance(sexpr, str):
        return False
    if isinstance(sexpr, list):
        if sexpr and isinstance(sexpr[0], str) and sexpr[0] in ("next", "prev", "rose", "fell", "stable"):
            return True
        return any(_contains_temporal(x) for x in sexpr)
    return False


def _state_access(idx: int, state_var: str, trace_stepn: Optional[str],
                  trace_ct: Optional[str], inputs_str: str,
                  mem_var: Optional[str] = None) -> str:
    """State access: `(nth idx st)` in single-cycle mode, or
    `(nth idx (stepn <ct> st <inputs> [mem]))` in trace (temporal) mode."""
    if trace_stepn:
        mem_arg = f" {mem_var}" if mem_var else ""
        stepn_call = f"({trace_stepn} {trace_ct} {state_var} {inputs_str}{mem_arg})"
        if mem_var:
            # Memory design: stepn returns (cons st mem); the state is the car.
            stepn_call = f"(car {stepn_call})"
        return f"(nth {idx} {stepn_call})"
    return f"(nth {idx} {state_var})"


def _expr_to_acl2(expr: Any,
                  state_indices: Dict[str, int],
                  memory_names: List[str],
                  inputs: List[str],
                  widths: Optional[Dict[str, int]] = None,
                  state_types: Optional[Dict[str, str]] = None,
                  input_types: Optional[Dict[str, str]] = None,
                  state_var: str = "st",
                  function_info: Optional[Set[str]] = None,
                  local_names: Optional[Set[str]] = None,
                  trace_stepn: Optional[str] = None,
                  trace_ct: Optional[str] = None,
                  mem_var: str = "mem") -> str:
    """
    Convert a parsed S‑expression into an ACL2 term string.
    The state is represented as a list (st) where registers are accessed
    via (nth idx st) and updated via (update‑nth idx val st).
    Memories are accessed via (nth addr mem) and updated via a helper.
    """
    if isinstance(expr, bool):
        return "t" if expr else "nil"
    if isinstance(expr, int):
        return str(expr)
    if isinstance(expr, str):
        if local_names and expr in local_names:
            return expr
        if expr in state_indices:
            idx = state_indices[expr]
            return _state_access(idx, state_var, trace_stepn, trace_ct, " ".join(inputs))
        if expr in inputs:
            return expr
        return expr

    if not isinstance(expr, list) or len(expr) == 0:
        raise ExprError(f"Invalid expression for ACL2 lowering: {expr}")

    op = expr[0]
    args = expr[1:]

    # Arithmetic operators
    if op in ('add', 'sub', 'mul', 'div', 'mod', 'shl', 'shr', 'lshift', 'rshift', 'gcd', 'min', 'max'):
        if len(args) != 2:
            raise ExprError(f"{op} expects 2 arguments")
        a = _expr_to_acl2(args[0], state_indices, memory_names, inputs, widths, state_types, input_types, state_var, function_info, local_names, trace_stepn, trace_ct, mem_var)
        b = _expr_to_acl2(args[1], state_indices, memory_names, inputs, widths, state_types, input_types, state_var, function_info, local_names, trace_stepn, trace_ct, mem_var)
        if op in ('shl', 'lshift'):
            if widths is not None:
                op_w = max(_width_of_expr(args[0], widths), _width_of_expr(args[1], widths))
                return f"(mod (ash {a} {b}) (expt 2 {op_w}))"
            return f"(ash {a} {b})"
        if op in ('shr', 'rshift'):
            if widths is not None:
                op_w = max(_width_of_expr(args[0], widths), _width_of_expr(args[1], widths))
                return f"(mod (ash {a} (- {b})) (expt 2 {op_w}))"
            return f"(ash {a} (- {b}))"
        if op == 'gcd':
            return f"(isir-gcd {a} {b})"
        if op == 'min':
            return f"(min {a} {b})"
        if op == 'max':
            return f"(max {a} {b})"
        if op == 'div':
            op_w = max(_width_of_expr(args[0], widths), _width_of_expr(args[1], widths)) if widths else None
            return f"(mod (truncate {a} {b}) (expt 2 {op_w}))" if op_w else f"(truncate {a} {b})"
        acl2_op_map = {'add': '+', 'sub': '-', 'mul': '*', 'mod': 'mod'}
        acl2_op = acl2_op_map[op]
        if widths is not None:
            op_w = max(_width_of_expr(args[0], widths), _width_of_expr(args[1], widths))
            return f"(mod ({acl2_op} {a} {b}) (expt 2 {op_w}))"
        return f"({acl2_op} {a} {b})"

    # sum: n-ary reduction with +
    if op == 'sum':
        if len(args) == 0:
            raise ExprError("sum expects at least 1 argument")
        if len(args) == 1:
            return _expr_to_acl2(args[0], state_indices, memory_names, inputs, widths, state_types, input_types, state_var, function_info, local_names, trace_stepn, trace_ct, mem_var)
        acl2_args = [_expr_to_acl2(a, state_indices, memory_names, inputs, widths, state_types, input_types, state_var, function_info, local_names, trace_stepn, trace_ct, mem_var) for a in args]
        result = acl2_args[-1]
        for a in reversed(acl2_args[:-1]):
            result = f"(+ {a} {result})"
        return result

    # concat (high field, low field of explicit width)
    elif op == 'concat':
        if len(args) != 3:
            raise ExprError("concat expects 3 arguments: high low low_width")
        high = _expr_to_acl2(args[0], state_indices, memory_names, inputs, widths, state_types, input_types, state_var, function_info, local_names, trace_stepn, trace_ct, mem_var)
        low = _expr_to_acl2(args[1], state_indices, memory_names, inputs, widths, state_types, input_types, state_var, function_info, local_names, trace_stepn, trace_ct, mem_var)
        width = _expr_to_acl2(args[2], state_indices, memory_names, inputs, widths, state_types, input_types, state_var, function_info, local_names, trace_stepn, trace_ct, mem_var)
        return f"(+ (mod {low} (expt 2 {width})) (* {high} (expt 2 {width})))"

    # Logical operators
    elif op in ('and', 'or', 'xor'):
        if len(args) != 2:
            raise ExprError(f"{op} expects 2 arguments")
        a = _expr_to_acl2(args[0], state_indices, memory_names, inputs, widths, state_types, input_types, state_var, function_info, local_names, trace_stepn, trace_ct, mem_var)
        b = _expr_to_acl2(args[1], state_indices, memory_names, inputs, widths, state_types, input_types, state_var, function_info, local_names, trace_stepn, trace_ct, mem_var)
        # logical for boolean operands (conditions), bitwise for bits<N> data.
        if (_type_of_expr(args[0], state_types, input_types) == "bool" and
                _type_of_expr(args[1], state_types, input_types) == "bool"):
            return f"({op} {a} {b})"
        return f"({'logand' if op == 'and' else 'logior' if op == 'or' else 'logxor'} {a} {b})"
    elif op == 'not':
        if len(args) != 1:
            raise ExprError("not expects 1 argument")
        a = _expr_to_acl2(args[0], state_indices, memory_names, inputs, widths, state_types, input_types, state_var, function_info, local_names, trace_stepn, trace_ct, mem_var)
        return f"(not {a})"

    # Implication
    elif op == 'implies':
        if len(args) != 2:
            raise ExprError("implies expects 2 arguments")
        a = _expr_to_acl2(args[0], state_indices, memory_names, inputs, widths, state_types, input_types, state_var, function_info, local_names, trace_stepn, trace_ct, mem_var)
        b = _expr_to_acl2(args[1], state_indices, memory_names, inputs, widths, state_types, input_types, state_var, function_info, local_names, trace_stepn, trace_ct, mem_var)
        return f"(implies {a} {b})"

    # Comparison operators
    elif op in ('eq', 'neq', 'gt', 'lt', 'gte', 'lte', 'le', 'ge'):
        if len(args) != 2:
            raise ExprError(f"{op} expects 2 arguments")
        a = _expr_to_acl2(args[0], state_indices, memory_names, inputs, widths, state_types, input_types, state_var, function_info, local_names, trace_stepn, trace_ct, mem_var)
        b = _expr_to_acl2(args[1], state_indices, memory_names, inputs, widths, state_types, input_types, state_var, function_info, local_names, trace_stepn, trace_ct, mem_var)
        acl2_op_map = {'eq': '=', 'neq': '/=', 'gt': '>', 'lt': '<',
                       'gte': '>=', 'lte': '<=', 'le': '<=', 'ge': '>='}
        acl2_op = acl2_op_map[op]
        return f"({acl2_op} {a} {b})"

    # Concatenation and slicing
    elif op == 'concat':
        if len(args) != 2:
            raise ExprError("concat expects 2 arguments")
        a = _expr_to_acl2(args[0], state_indices, memory_names, inputs, widths, state_types, input_types, state_var, function_info, local_names, trace_stepn, trace_ct, mem_var)
        b = _expr_to_acl2(args[1], state_indices, memory_names, inputs, widths, state_types, input_types, state_var, function_info, local_names, trace_stepn, trace_ct, mem_var)
        return f"(+ {b} (* {a} 256))"   # default width for low part

    elif op == 'slice':
        if len(args) != 3:
            raise ExprError("slice expects 3 arguments")
        e = _expr_to_acl2(args[0], state_indices, memory_names, inputs, widths, state_types, input_types, state_var, function_info, local_names, trace_stepn, trace_ct, mem_var)
        h = _expr_to_acl2(args[1], state_indices, memory_names, inputs, widths, state_types, input_types, state_var, function_info, local_names, trace_stepn, trace_ct, mem_var)
        l = _expr_to_acl2(args[2], state_indices, memory_names, inputs, widths, state_types, input_types, state_var, function_info, local_names, trace_stepn, trace_ct, mem_var)
        return f"(mod (floor {e} (expt 2 {l})) (expt 2 (+ 1 (- {h} {l}))))"

    # if‑then‑else
    elif op == 'ite':
        if len(args) != 3:
            raise ExprError("ite expects 3 arguments")
        cond = _expr_to_acl2(args[0], state_indices, memory_names, inputs, widths, state_types, input_types, state_var, function_info, local_names, trace_stepn, trace_ct, mem_var)
        then_expr = _expr_to_acl2(args[1], state_indices, memory_names, inputs, widths, state_types, input_types, state_var, function_info, local_names, trace_stepn, trace_ct, mem_var)
        else_expr = _expr_to_acl2(args[2], state_indices, memory_names, inputs, widths, state_types, input_types, state_var, function_info, local_names, trace_stepn, trace_ct, mem_var)
        return f"(if {cond} {then_expr} {else_expr})"

    # read state register (or input: eval_expr looks up state first, then inputs)
    elif op == 'read':
        if len(args) != 1:
            raise ExprError("read expects 1 argument")
        name = args[0]
        if not isinstance(name, str):
            raise ExprError("read expects a state name string")
        if name in state_indices:
            idx = state_indices[name]
            return _state_access(idx, state_var, trace_stepn, trace_ct, " ".join(inputs), mem_var if memory_names else None)
        if name in inputs:
            return name
        raise ExprError(f"Unknown state or input '{name}' in expression")

    # write action – not an expression
    elif op == 'write':
        raise ExprError("write is an action, not an expression")

    # memory read
    elif op == 'mem_read':
        if len(args) != 2:
            raise ExprError("mem_read expects 2 arguments")
        mem_name = args[0]
        if not isinstance(mem_name, str):
            raise ExprError("mem_read expects memory name string")
        addr = _expr_to_acl2(args[1], state_indices, memory_names, inputs, widths, state_types, input_types, state_var, function_info, local_names, trace_stepn, trace_ct, mem_var)
        midx = memory_names.index(mem_name) if mem_name in memory_names else 0
        return f"(nth {addr} (nth {midx} {mem_var}))"

    # memory write – action
    elif op == 'mem_write':
        raise ExprError("mem_write is an action, not an expression")

    # Temporal operators: evaluated relative to a trace cycle (trace_ct).
    elif op in ('next', 'prev', 'rose', 'fell', 'stable'):
        if len(args) != 1:
            raise ExprError(f"{op} expects 1 argument")
        if not trace_stepn:
            raise ExprError(f"'{op}' requires a temporal (trace) context")
        sub = args[0]
        ct = trace_ct or "t"
        prev_ct = f"(nfix (1- {ct}))"
        next_ct = f"(1+ {ct})"
        if op == 'next':
            return _expr_to_acl2(sub, state_indices, memory_names, inputs, widths, state_types, input_types, state_var, function_info, local_names, trace_stepn, next_ct)
        if op == 'prev':
            return _expr_to_acl2(sub, state_indices, memory_names, inputs, widths, state_types, input_types, state_var, function_info, local_names, trace_stepn, prev_ct)
        cur = _expr_to_acl2(sub, state_indices, memory_names, inputs, widths, state_types, input_types, state_var, function_info, local_names, trace_stepn, ct)
        prv = _expr_to_acl2(sub, state_indices, memory_names, inputs, widths, state_types, input_types, state_var, function_info, local_names, trace_stepn, prev_ct)
        if op == 'rose':
            return f"(and {cur} (not {prv}))"
        if op == 'fell':
            return f"(and (not {cur}) {prv})"
        return f"(equal {cur} {prv})"

    else:
        # Unknown operator: treat as a user function call (bodyless function,
        # e.g. partial_spec).  Defined functions are inlined before lowering.
        acl2_args = [_expr_to_acl2(a, state_indices, memory_names, inputs, widths, state_types, input_types, state_var, function_info, local_names, trace_stepn, trace_ct, mem_var) for a in args]
        if function_info and op in function_info:
            # Recursive function: fuel-based defun `(op fuel a b ...)`.  Use the
            # declared measure (with arguments substituted, evaluated as a
            # natural) as a SUFFICIENT fuel so exact-value properties are sound;
            # fall back to a free fuel when no measure is declared.
            params, measure_expr = _RECURSIVE_MEASURES.get(op, ([], None))
            if measure_expr is not None:
                sub = {params[i]: args[i] for i in range(min(len(params), len(args)))}
                fuel = _expr_to_acl2(_subst_sexpr(measure_expr, sub), state_indices, memory_names, inputs, None, None, None, state_var, function_info, local_names, trace_stepn, trace_ct, mem_var)
            else:
                fuel = "fuel"
            return f"({op} {fuel} {' '.join(acl2_args)})"
        return f"({op} {' '.join(acl2_args)})"


def _action_to_acl2_update(action_str: str,
                           state_indices: Dict[str, int],
                           memory_names: List[str],
                           inputs: List[str],
                           widths: Optional[Dict[str, int]] = None,
                           state_types: Optional[Dict[str, str]] = None,
                           input_types: Optional[Dict[str, str]] = None,
                           state_var: str = "st",
                           function_info: Optional[Set[str]] = None,
                           local_names: Optional[Set[str]] = None,
                           trace_stepn: Optional[str] = None,
                           trace_ct: Optional[str] = None,
                           mem_var: str = "mem") -> str:
    """
    Convert a single action S‑expression into an ACL2 state update term.
    Returns (update‑nth idx val st) for registers or
    (update‑mem mem addr val st) for memories.
    """
    try:
        action = parse_sexpr(action_str)
    except ExprError:
        return action_str

    if not isinstance(action, list):
        return str(action)

    op = action[0]
    args = action[1:]

    if op == 'write':
        if len(args) != 2:
            raise ExprError("write action expects 2 arguments")
        reg_name = args[0]
        if not isinstance(reg_name, str):
            raise ExprError("write expects register name string")
        if reg_name not in state_indices:
            raise ExprError(f"Unknown register '{reg_name}' in write action")
        idx = state_indices[reg_name]
        value_expr = _expr_to_acl2(args[1], state_indices, memory_names, inputs, widths, state_types, input_types, state_var, function_info, local_names, trace_stepn, trace_ct, mem_var)
        return f"(update-nth {idx} {value_expr} {state_var})"

    elif op == 'mem_write':
        if len(args) != 3:
            raise ExprError("mem_write action expects 3 arguments")
        mem_name = args[0]
        if not isinstance(mem_name, str):
            raise ExprError("mem_write expects memory name string")
        addr_expr = _expr_to_acl2(args[1], state_indices, memory_names, inputs, widths, state_types, input_types, state_var, function_info, local_names, trace_stepn, trace_ct, mem_var)
        data_expr = _expr_to_acl2(args[2], state_indices, memory_names, inputs, widths, state_types, input_types, state_var, function_info, local_names, trace_stepn, trace_ct, mem_var)
        midx = memory_names.index(mem_name) if mem_name in memory_names else 0
        return f"(update-nth {midx} (update-nth {addr_expr} {data_expr} (nth {midx} {mem_var})) {mem_var})"

    else:
        return _expr_to_acl2(action, state_indices, memory_names, inputs, widths, state_types, input_types, state_var, function_info, local_names, trace_stepn, trace_ct, mem_var)


def _maybe_auto_hint(prop_op: isir.SpecPropertyOp,
                     state_indices: Dict[str, int],
                     memory_names: List[str],
                     input_names: List[str],
                     step_name: str = "step") -> Optional[List[str]]:
    """
    Best-effort ACL2 :hints by property kind:

    - safety/invariant/transition : induct on the n-cycle step (stepn);
    - bounded eventually/until     : induct on the cycle bound n;
    - combinational                : disable generalization (arithmetic-5).
    """
    expr_kind = prop_op.expression.get("kind", "always")
    in_args = " ".join(input_names)

    if prop_op.kind in ("safety", "invariant") or expr_kind == "transition":
        # Self-identity (eq A A) is a reflexivity: no induction needed.
        operand_raw = prop_op.expression.get("operand")
        if operand_raw:
            try:
                op_parsed = parse_sexpr(operand_raw)
                if (isinstance(op_parsed, list) and len(op_parsed) == 3
                        and op_parsed[0] == "eq" and op_parsed[1] == op_parsed[2]):
                    return None
            except ExprError:
                pass
        # Otherwise: induct on the invariant-preservation trace from init.
        mem_arg = " mem" if memory_names else ""
        init_name = step_name[:-4] + "init" if step_name.endswith("_step") else "init_state"
        return [f'("Goal" :induct ({step_name}n t {init_name} {in_args}{mem_arg}))']
    if expr_kind in ("eventually", "until") and prop_op.expression.get("bound") is not None:
        return ['("Goal" :induct n)']
    if expr_kind == "combinational":
        return ['(\"Goal\" :do-not \'(generalize))']
    return None


def convert(spec_module: isir.SpecModule) -> acl2.ACL2Module:
    """
    Convert a SpecModule to an ACL2Module with functional definitions and theorems.
    """

    # 1. Collect state registers and assign indices for list representation
    registers = [s for s in spec_module.state_ops if s.kind == "register"]
    state_indices: Dict[str, int] = {}
    for i, reg in enumerate(registers):
        state_indices[reg.state_name] = i

    memory_names = [s.state_name for s in spec_module.state_ops if s.kind == "memory"]
    input_names = [i.name for i in spec_module.inputs]
    output_names = [o.name for o in spec_module.outputs]

    # Bit widths of state registers and inputs (bool -> 1, bits<N> -> N), used to
    # wrap arithmetic at the operand width so the ACL2 model matches the
    # reference `eval_expr` / the wrapped `bits<N>` semantics.
    widths: Dict[str, int] = {}
    for s in spec_module.state_ops:
        if s.kind == "register":
            widths[s.state_name] = _width_of_type(s.data_type)
    for inp in spec_module.inputs:
        widths[inp.name] = _width_of_type(inp.data_type)

    # Data types (bool vs bits<N>) so and/or/xor lower to logical vs bitwise.
    state_types: Dict[str, str] = {}
    for s in spec_module.state_ops:
        if s.kind == "register":
            state_types[s.state_name] = s.data_type
    input_types: Dict[str, str] = {inp.name: inp.data_type for inp in spec_module.inputs}

    # User functions: defined (with body) are inlined via unfold_user_functions;
    # bodyless (partial_spec) are left as calls and encapsulated below.
    functions = spec_module.functions or []

    def _unfold(expr_str):
        if not functions or not expr_str:
            return expr_str
        inline_fns = [f for f in functions if f.get("body") is not None and not f.get("recursive")]
        if not inline_fns:
            return expr_str
        try:
            return unfold_user_functions(expr_str, inline_fns)
        except Exception:
            return expr_str

    # Recursive functions: lowered to fuel-based defuns; calls take a `fuel`
    # argument (a free variable in property statements, universally quantified).
    recursive_names: Set[str] = {
        f.get("name") for f in functions if f.get("body") is not None and f.get("recursive") and f.get("name")
    }
    global _RECURSIVE_MEASURES
    _RECURSIVE_MEASURES = {}
    for f in functions:
        fname = f.get("name")
        if fname and f.get("body") is not None and f.get("recursive") and f.get("measure"):
            params = [pp.get("name") for pp in (f.get("params") or [])]
            measure_raw = f.get("measure")
            try:
                measure_parsed = parse_sexpr(measure_raw) if isinstance(measure_raw, str) else measure_raw
                _RECURSIVE_MEASURES[fname] = (params, measure_parsed)
            except ExprError:
                pass

    # 2. Build the transition function
    schedule_kind = spec_module.schedule_op.kind if spec_module.schedule_op else "parallel"
    sorted_rules = sorted(
        spec_module.rule_ops,
        key=lambda r: r.priority if r.priority is not None else 0,
        reverse=True
    )

    has_mem = bool(memory_names)

    if schedule_kind == "parallel":
        if has_mem:
            # track (cons st mem) pairs; every RHS reads the ORIGINAL st0/mem0
            bindings = [("acc0", "(cons st mem)")]
            acc = "acc0"
            for i, rule in enumerate(sorted_rules, 1):
                cond_acl2 = "t"
                if rule.condition:
                    try:
                        cond_acl2 = _expr_to_acl2(parse_sexpr(_unfold(rule.condition)), state_indices, memory_names, input_names, widths, state_types, input_types, function_info=recursive_names)
                    except ExprError as e:
                        logger.warning(f"Rule '{rule.rule_name}' condition error: {e}")
                update = acc
                for action_str in reversed(rule.actions):
                    try:
                        act = parse_sexpr(action_str)
                        if isinstance(act, list) and act and act[0] == "write" and len(act) == 3 and act[1] in state_indices:
                            idx = state_indices[act[1]]
                            val = _expr_to_acl2(parse_sexpr(_unfold(act[2])), state_indices, memory_names, input_names, widths, state_types, input_types, state_var="(car acc0)", function_info=recursive_names, mem_var="(cdr acc0)")
                            update = f"(cons (update-nth {idx} {val} (car {acc})) (cdr {acc}))"
                        elif isinstance(act, list) and act and act[0] == "mem_write" and len(act) == 4 and act[1] in memory_names:
                            midx = memory_names.index(act[1])
                            addr = _expr_to_acl2(parse_sexpr(_unfold(act[2])), state_indices, memory_names, input_names, widths, state_types, input_types, state_var="(car acc0)", function_info=recursive_names, mem_var="(cdr acc0)")
                            data = _expr_to_acl2(parse_sexpr(_unfold(act[3])), state_indices, memory_names, input_names, widths, state_types, input_types, state_var="(car acc0)", function_info=recursive_names, mem_var="(cdr acc0)")
                            update = f"(cons (car {acc}) (update-nth {midx} (update-nth {addr} {data} (nth {midx} (cdr {acc}))) (cdr {acc})))"
                    except ExprError as e:
                        logger.warning(f"Rule '{rule.rule_name}' action error: {e}")
                bindings.append((f"acc{i}", f"(if {cond_acl2} {update} {acc})"))
                acc = f"acc{i}"
            body = "(let* (\n" + "\n".join(f"       ({v} {e})" for v, e in bindings) + f")\n       {acc})"
        else:
            # All enabled rules fire simultaneously: every RHS reads the ORIGINAL
            # `st`, and the writes accumulate (later rules override earlier).
            bindings = [("st0", "st")]
            acc = "st0"
            for i, rule in enumerate(sorted_rules, 1):
                cond_acl2 = "t"
                if rule.condition:
                    try:
                        cond_acl2 = _expr_to_acl2(parse_sexpr(_unfold(rule.condition)), state_indices, memory_names, input_names, widths, state_types, input_types, function_info=recursive_names)
                    except ExprError as e:
                        logger.warning(f"Rule '{rule.rule_name}' condition error: {e}")
                update = acc
                for action_str in reversed(rule.actions):
                    try:
                        act = parse_sexpr(action_str)
                        if isinstance(act, list) and act and act[0] == "write" and len(act) == 3:
                            if act[1] in state_indices:
                                idx = state_indices[act[1]]
                                val = _expr_to_acl2(parse_sexpr(_unfold(act[2])), state_indices, memory_names, input_names, widths, state_types, input_types, state_var="st", function_info=recursive_names)
                                update = f"(update-nth {idx} {val} {update})"
                    except ExprError as e:
                        logger.warning(f"Rule '{rule.rule_name}' action error: {e}")
                bindings.append((f"st{i}", f"(if {cond_acl2} {update} {acc})"))
                acc = f"st{i}"
            body = "(let* (\n" + "\n".join(f"       ({v} {e})" for v, e in bindings) + f")\n       {acc})"
    else:
        # sequential: first-match cond (first enabled rule wins)
        cond_clauses: List[str] = []
        for rule in sorted_rules:
            if rule.condition:
                try:
                    cond_acl2 = _expr_to_acl2(parse_sexpr(_unfold(rule.condition)), state_indices, memory_names, input_names, widths, state_types, input_types, function_info=recursive_names)
                except ExprError as e:
                    logger.warning(f"Rule '{rule.rule_name}' condition parse error: {e}. Skipping.")
                    continue
            else:
                cond_acl2 = "t"

            if not rule.actions:
                continue

            state_update = "st"
            for action_str in reversed(rule.actions):
                try:
                    update_term = _action_to_acl2_update(_unfold(action_str), state_indices, memory_names, input_names, widths, state_types, input_types, function_info=recursive_names)
                    if update_term.endswith(" st)"):
                        prefix = update_term[:-4]
                        state_update = f"{prefix} {state_update})"
                    else:
                        state_update = f"(let ((st {state_update})) {update_term})"
                except ExprError as e:
                    logger.warning(f"Rule '{rule.rule_name}' action error: {e}. Skipping action.")
                    continue
            cond_clauses.append(f"({cond_acl2} {state_update})")

        if not cond_clauses:
            body = "st"
        else:
            body = "(cond\n" + "\n".join(f"       {c}" for c in cond_clauses) + "\n       (t st))"

    if input_names:
        body = f"(declare (ignorable {' '.join(input_names)}))\n  {body}"
    next_state_defun = acl2.ACL2DefunOp(
        func_name=f"{spec_module.name}_step",
        args=["st"] + input_names + (["mem"] if has_mem else []),
        body=body
    )

    # 3. Generate initial state definition
    init_vals = []
    for reg in registers:
        init = reg.initial if reg.initial is not None else 0
        if isinstance(init, bool):
            init_vals.append("t" if init else "nil")
        else:
            init_vals.append(str(init))
    if has_mem:
        mem_inits = " ".join("nil" for _ in memory_names)
        init_list = f"(cons (list {' '.join(init_vals)}) (list {mem_inits}))"
    else:
        init_list = f"(list {' '.join(init_vals)})"
    init_state_defun = acl2.ACL2DefunOp(
        func_name=f"{spec_module.name}_init",
        args=[],
        body=init_list
    )

    defuns = [init_state_defun, next_state_defun]

    # Recursive functions: fuel-based defuns (structural recursion on fuel).
    for f in functions:
        fname = f.get("name")
        if not fname or f.get("body") is None or not f.get("recursive"):
            continue
        params = f.get("params") or []
        pnames = [pp.get("name") for pp in params]
        ret = f.get("return", "bits<1>")
        zero = "nil" if ret == "bool" else "0"
        try:
            body_parsed = parse_sexpr(f.get("body"))
            rewritten = _rewrite_recursive_calls(body_parsed, fname, "(1- fuel)")
            local_widths = dict(widths)
            local_types = dict(state_types)
            for pp in params:
                nm = pp.get("name")
                if nm:
                    local_widths[nm] = _width_of_type(pp.get("type", "bits<1>"))
                    local_types[nm] = pp.get("type", "bits<1>")
            body_acl2 = _expr_to_acl2(rewritten, state_indices, memory_names, input_names, local_widths, local_types, input_types, state_var="st", local_names=set(pnames))
        except ExprError as e:
            logger.warning(f"Could not lower recursive function '{fname}': {e}")
            continue
        defuns.append(acl2.ACL2DefunOp(
            func_name=fname,
            args=["fuel"] + pnames,
            body=f"(if (zp fuel) {zero}\n    {body_acl2})"
        ))

    # 3b. n-cycle step (clocked trace model for temporal properties).
    inputs_str = " ".join(input_names)
    if has_mem:
        stepn_body = (f"(if (zp n) (cons st mem)\n"
                      f"    (let ((nxt ({spec_module.name}_step st {inputs_str} mem)))\n"
                      f"      ({spec_module.name}_stepn (1- n) (car nxt) {inputs_str} (cdr nxt))))")
    else:
        stepn_body = f"(if (zp n) st\n    ({spec_module.name}_stepn (1- n) ({spec_module.name}_step st {inputs_str}) {inputs_str}))"
    if input_names:
        stepn_body = f"(declare (ignorable {' '.join(input_names)}))\n  {stepn_body}"
    stepn_defun = acl2.ACL2DefunOp(
        func_name=f"{spec_module.name}_stepn",
        args=["n", "st"] + input_names + (["mem"] if has_mem else []),
        body=stepn_body
    )
    defuns.append(stepn_defun)

    # 4. Theorems from proof obligations (with auto‑hints)
    defthms: List[acl2.ACL2DefthmOp] = []
    temporal_defuns: List[acl2.ACL2DefunOp] = []
    defun_sk_ops: List[acl2.ACL2DefunSkOp] = []
    for po in spec_module.proof_obligations:
        # Honor the `backend` field (mirror isir_to_koika): only obligations
        # explicitly tagged `acl2` are lowered to ACL2 theorems.
        backend = (_po_backend(po) or "").lower().replace("ō", "o")
        if backend != "acl2":
            continue
        prop_name = _po_property(po)
        if not prop_name:
            continue

        prop_op = next((p for p in spec_module.property_ops if p.prop_name == prop_name), None)
        if not prop_op:
            logger.warning(f"No property found for proof obligation '{prop_name}'")
            continue

        expr_kind = prop_op.expression.get("kind", "always")

        # Liveness (unbounded eventually/until) is handled below via defun-sk
        # (existential quantification over the trace).

        operand = prop_op.expression.get("operand", None)
        assumes_acl2 = []
        for assume in prop_op.assumes:
            try:
                assume_parsed = parse_sexpr(_unfold(assume))
                assumes_acl2.append(_expr_to_acl2(assume_parsed, state_indices, memory_names, input_names, widths, state_types, input_types, function_info=recursive_names))
            except ExprError:
                pass

        try:
            if expr_kind == "combinational":
                # functional identity: (equal impl reference)
                impl = _expr_to_acl2(parse_sexpr(_unfold(operand)), state_indices, memory_names, input_names, widths, state_types, input_types, function_info=recursive_names)
                ref = prop_op.expression.get("reference", None)
                ref_acl2 = _expr_to_acl2(parse_sexpr(_unfold(ref)), state_indices, memory_names, input_names, widths, state_types, input_types, function_info=recursive_names) if (ref is not None and ref != "") else "t"
                # Inputs are bounded to their bit width (matches the reference).
                for inp in spec_module.inputs:
                    w = widths.get(inp.name)
                    if w:
                        assumes_acl2.append(f"(natp {inp.name})")
                        assumes_acl2.append(f"(< {inp.name} (expt 2 {w}))")
                prop_acl2 = f"(equal {impl} {ref_acl2})"
            elif expr_kind == "transition":
                # operand holds when the scoped rule fires; add the rule's
                # condition to the hypotheses.  `prev` refers to the pre-cycle
                # state, so a temporal operand uses the trace model.
                t_parsed = parse_sexpr(_unfold(operand))
                if _contains_temporal(t_parsed):
                    prop_acl2 = _expr_to_acl2(t_parsed, state_indices, memory_names, input_names, widths, state_types, input_types, function_info=recursive_names, trace_stepn=f"{spec_module.name}_stepn", trace_ct="t")
                    assumes_acl2.insert(0, "(natp t)")
                else:
                    prop_acl2 = _expr_to_acl2(t_parsed, state_indices, memory_names, input_names, widths, state_types, input_types, function_info=recursive_names)
                rule_name = prop_op.expression.get("rule")
                rule = next((r for r in spec_module.rule_ops if r.rule_name == rule_name), None)
                if rule is not None and rule.condition:
                    try:
                        assumes_acl2.append(_expr_to_acl2(parse_sexpr(_unfold(rule.condition)), state_indices, memory_names, input_names, widths, state_types, input_types, function_info=recursive_names))
                    except ExprError:
                        pass
            elif expr_kind == "independence":
                # operand independent of the listed inputs: compare against a
                # primed copy of those inputs (a free variable per input).
                independent_of = prop_op.expression.get("independent_of", []) or []
                primed = {}
                for x in independent_of:
                    xp = f"{x}_prime"
                    primed[x] = xp
                    if x in input_types:
                        input_types[xp] = input_types[x]
                    if x in widths:
                        widths[xp] = widths[x]
                    if xp not in input_names:
                        input_names.append(xp)
                operand_parsed = parse_sexpr(_unfold(operand))
                operand_prime = _subst_sexpr(operand_parsed, primed)
                impl = _expr_to_acl2(operand_parsed, state_indices, memory_names, input_names, widths, state_types, input_types, function_info=recursive_names)
                impl_prime = _expr_to_acl2(operand_prime, state_indices, memory_names, input_names, widths, state_types, input_types, function_info=recursive_names)
                prop_acl2 = f"(equal {impl} {impl_prime})"
            elif expr_kind == "after":
                # after n: the operand holds at cycle n of the trace.
                bound = prop_op.expression.get("bound", 0)
                operand_parsed = parse_sexpr(_unfold(operand))
                prop_acl2 = _expr_to_acl2(operand_parsed, state_indices, memory_names, input_names, widths, state_types, input_types, function_info=recursive_names, trace_stepn=f"{spec_module.name}_stepn", trace_ct=str(bound))
            elif expr_kind in ("eventually", "until"):
                # temporal quantifier: bounded -> recursive defun over n;
                # unbounded -> defun-sk (exists / exists+forall over the trace).
                bound = prop_op.expression.get("bound")
                if bound is None:
                    if expr_kind == "eventually":
                        op_parsed = parse_sexpr(_unfold(operand))
                        op_acl2 = _expr_to_acl2(op_parsed, state_indices, memory_names, input_names, widths, state_types, input_types, function_info=recursive_names, trace_stepn=f"{spec_module.name}_stepn", trace_ct="i")
                        pred_fn = f"{prop_name}_operand"
                        defuns.append(acl2.ACL2DefunOp(func_name=pred_fn, args=["i", "st"] + input_names, body=op_acl2))
                        sk = f"{prop_name}_eventually"
                        defun_sk_ops.append(acl2.ACL2DefunSkOp(
                            pred_name=sk, free_args=["st"] + input_names, exists_vars=["i"],
                            body=f"(and (natp i) ({pred_fn} i st {inputs_str}))",
                            quantifier="exists", skolem_name=f"{sk}_witness"))
                        prop_acl2 = f"({sk} st {inputs_str})"
                    else:
                        left = prop_op.expression.get("left")
                        right = prop_op.expression.get("right")
                        phi_acl2 = _expr_to_acl2(parse_sexpr(_unfold(left)), state_indices, memory_names, input_names, widths, state_types, input_types, function_info=recursive_names, trace_stepn=f"{spec_module.name}_stepn", trace_ct="i")
                        psi_acl2 = _expr_to_acl2(parse_sexpr(_unfold(right)), state_indices, memory_names, input_names, widths, state_types, input_types, function_info=recursive_names, trace_stepn=f"{spec_module.name}_stepn", trace_ct="i")
                        phi_fn = f"{prop_name}_left"
                        psi_fn = f"{prop_name}_right"
                        defuns.append(acl2.ACL2DefunOp(func_name=phi_fn, args=["i", "st"] + input_names, body=phi_acl2))
                        defuns.append(acl2.ACL2DefunOp(func_name=psi_fn, args=["i", "st"] + input_names, body=psi_acl2))
                        before_fn = f"{prop_name}_before"
                        defun_sk_ops.append(acl2.ACL2DefunSkOp(
                            pred_name=before_fn, free_args=["k", "st"] + input_names, exists_vars=["j"],
                            body=f"(implies (< j k) ({phi_fn} j st {inputs_str}))",
                            quantifier="forall"))
                        until_fn = f"{prop_name}_until"
                        defun_sk_ops.append(acl2.ACL2DefunSkOp(
                            pred_name=until_fn, free_args=["st"] + input_names, exists_vars=["k"],
                            body=f"(and (natp k) ({psi_fn} k st {inputs_str}) ({before_fn} k st {inputs_str}))",
                            quantifier="exists", skolem_name=f"{until_fn}_witness"))
                        prop_acl2 = f"({until_fn} st {inputs_str})"
                else:
                    if expr_kind == "eventually":
                        op_parsed = parse_sexpr(_unfold(operand))
                        op_acl2 = _expr_to_acl2(op_parsed, state_indices, memory_names, input_names, widths, state_types, input_types, function_info=recursive_names, trace_stepn=f"{spec_module.name}_stepn", trace_ct="n")
                        fn = f"{prop_name}_eventually"
                        temporal_defuns.append(acl2.ACL2DefunOp(
                            func_name=fn, args=["n", "st"] + input_names,
                            body=f"(if (zp n)\n    {op_acl2}\n  (or {op_acl2} ({fn} (1- n) st {inputs_str})))"
                        ))
                        prop_acl2 = f"({fn} n st {inputs_str})"
                    else:
                        left = prop_op.expression.get("left")
                        right = prop_op.expression.get("right")
                        phi_acl2 = _expr_to_acl2(parse_sexpr(_unfold(left)), state_indices, memory_names, input_names, widths, state_types, input_types, function_info=recursive_names, trace_stepn=f"{spec_module.name}_stepn", trace_ct="n")
                        psi_acl2 = _expr_to_acl2(parse_sexpr(_unfold(right)), state_indices, memory_names, input_names, widths, state_types, input_types, function_info=recursive_names, trace_stepn=f"{spec_module.name}_stepn", trace_ct="n")
                        fn = f"{prop_name}_until"
                        temporal_defuns.append(acl2.ACL2DefunOp(
                            func_name=fn, args=["n", "st"] + input_names,
                            body=f"(if (zp n)\n    {psi_acl2}\n  (or {psi_acl2} (and {phi_acl2} ({fn} (1- n) st {inputs_str}))))"
                        ))
                        prop_acl2 = f"({fn} n st {inputs_str})"
            else:
                # safety / invariant / always: the operand holds in every
                # reachable state, i.e. at every cycle t of the trace from the
                # initial state (sound — mirrors Koika's `reachable s -> P`).
                if operand:
                    operand_parsed = parse_sexpr(_unfold(operand))
                    tr = f"{spec_module.name}_stepn"
                    init = f"{spec_module.name}_init"
                    prop_acl2 = _expr_to_acl2(operand_parsed, state_indices, memory_names, input_names, widths, state_types, input_types, function_info=recursive_names, trace_stepn=tr, trace_ct="t", state_var=init)
                    # Re-lower the assumes over the same trace state.
                    assumes_acl2 = []
                    for assume in prop_op.assumes:
                        try:
                            assume_parsed = parse_sexpr(_unfold(assume))
                            assumes_acl2.append(_expr_to_acl2(assume_parsed, state_indices, memory_names, input_names, widths, state_types, input_types, function_info=recursive_names, trace_stepn=tr, trace_ct="t", state_var=init))
                        except ExprError:
                            pass
                    assumes_acl2.insert(0, "(natp t)")
                else:
                    prop_acl2 = "t"
        except ExprError as e:
            logger.warning(f"Could not convert property '{prop_name}' to ACL2: {e}")
            continue

        hypotheses = " ".join(assumes_acl2) if assumes_acl2 else "t"
        statement = f"(implies (and {hypotheses}) {prop_acl2})"

        metadata = _po_metadata(po)
        user_hints = metadata.get("acl2_hints", [])
        if isinstance(user_hints, list) and user_hints:
            hints_list = user_hints
        else:
            auto_hints = _maybe_auto_hint(prop_op, state_indices, memory_names, input_names, step_name=f"{spec_module.name}_step")
            hints_list = auto_hints or []

        # Proof automation: emit the correct statement + a best-effort hint,
        # and admit (skip-proofs) so the generated file always loads.  The
        # prover (proof/acl2/prover.py) removes the skip-proofs and uses the
        # hint to discharge the proof.
        defthm = acl2.ACL2DefthmOp(
            thm_name=f"{prop_name}_correct",
            statement=statement,
            hints=hints_list,
            skip_proofs=True,
            rule_classes_nil=True,
        )
        defthms.append(defthm)

    # 4b. Axioms (unproved assumptions): defaxiom.
    for a in spec_module.axioms:
        aname = a.get("name")
        if not aname:
            continue
        statement = a.get("statement", "true")
        try:
            stmt_parsed = parse_sexpr(_unfold(statement))
            stmt_acl2 = _expr_to_acl2(stmt_parsed, state_indices, memory_names, input_names, widths, state_types, input_types, function_info=recursive_names)
        except ExprError as e:
            logger.warning(f"Could not translate axiom '{aname}': {e}")
            continue
        # Axiom `forall` binders stay free variables: `_expr_to_acl2` returns
        # unknown names bare, so the defaxiom keeps them universally quantified.
        defthms.append(acl2.ACL2DefthmOp(thm_name=aname, statement=stmt_acl2, axiom=True))

    # 4c. Directives: assume -> hypothesis (added to every property below);
    #     assert/cover -> a theorem of the directive expression.
    global_assumes = []
    for directive in spec_module.directive_ops:
        try:
            d_acl2 = _expr_to_acl2(parse_sexpr(_unfold(directive.expression)), state_indices, memory_names, input_names, widths, state_types, input_types, function_info=recursive_names)
        except ExprError as e:
            logger.warning(f"Could not translate directive '{directive.directive_name}': {e}")
            continue
        if directive.kind == "assume":
            global_assumes.append(d_acl2)
        elif directive.kind in ("assert", "cover"):
            defthms.append(acl2.ACL2DefthmOp(
                thm_name=f"{directive.directive_name}_holds",
                statement=d_acl2,
            ))

    # Fold global assume directives into the property hypotheses.
    if global_assumes:
        for t in defthms:
            if t.axiom:
                continue
            t.statement = f"(implies (and {' '.join(global_assumes)}) {t.statement})"

    # 4c-bis. Fairness constraints: liveness assumptions (weak -> eventually;
    # strong -> always eventually, here approximated as eventually).
    for f in spec_module.fairness:
        fname = f.get("name")
        fcond = f.get("condition")
        if not fname or not fcond:
            continue
        try:
            cond_parsed = parse_sexpr(_unfold(fcond))
            cond_acl2 = _expr_to_acl2(cond_parsed, state_indices, memory_names, input_names, widths, state_types, input_types, function_info=recursive_names, trace_stepn=f"{spec_module.name}_stepn", trace_ct="i")
            pred_fn = f"{fname}_cond"
            defuns.append(acl2.ACL2DefunOp(func_name=pred_fn, args=["i", "st"] + input_names, body=cond_acl2))
            ev_fn = f"{fname}_eventually"
            defun_sk_ops.append(acl2.ACL2DefunSkOp(
                pred_name=ev_fn, free_args=["st"] + input_names, exists_vars=["i"],
                body=f"(and (natp i) ({pred_fn} i st {inputs_str}))",
                quantifier="exists", skolem_name=f"{ev_fn}_witness"))
            defthms.append(acl2.ACL2DefthmOp(thm_name=fname, statement=f"({ev_fn} st {inputs_str})", axiom=True))
        except ExprError as e:
            logger.warning(f"Could not lower fairness '{fname}': {e}")

    # 4d. Bodyless functions (partial_spec): encapsulate as uninterpreted.
    raw_forms: List[str] = [
        "(defun isir-gcd (a b)\n"
        "  (declare (xargs :measure (nfix b)))\n"
        "  (if (zp b) (nfix a) (isir-gcd b (mod a b))))"
    ]
    for f in functions:
        fname = f.get("name")
        if not fname or f.get("body") is not None:
            continue
        pnames = [pp.get("name") for pp in (f.get("params") or [])]
        args_str = " ".join(pnames)
        ignore = f"(declare (ignore {' '.join(pnames)}))" if pnames else ""
        stars = " ".join("*" for _ in pnames)
        formals = " ".join(pnames)
        raw_forms.append(
            "(encapsulate\n"
            f"  ((({fname} {stars}) => *\n"
            f"    :formals ({formals})))\n"
            f"  (local (defun {fname} ({args_str}) {ignore} 0)))"
        )

    defuns.extend(temporal_defuns)

    # 4c. Domain lemmas used by the proof obligations (mod bounds).
    domain_lemmas = [
        acl2.ACL2DefthmOp(
            thm_name="isir-mod-<=-x",
            statement="(implies (and (integerp x) (integerp y) (<= 0 x) (< 0 y)) (<= (mod x y) x))",
            hints=['("Goal" :in-theory (enable mod))'],
            rule_classes=[":linear"],
        ),
        acl2.ACL2DefthmOp(
            thm_name="isir-mod-x-y-x",
            statement="(implies (and (integerp x) (integerp y) (<= 0 x) (< x y)) (equal (mod x y) x))",
            hints=['("Goal" :in-theory (enable mod))'],
            rule_classes=[":rewrite"],
        ),
        acl2.ACL2DefthmOp(
            thm_name="isir-natp-mod",
            statement="(implies (and (integerp x) (integerp y) (< 0 y)) (natp (mod x y)))",
            hints=['("Goal" :in-theory (enable mod))'],
            rule_classes=[":rewrite", ":type-prescription"],
        ),
    ]
    for lemma in domain_lemmas:
        raw_forms.append(lemma.to_lisp())

    # 5. Build the ACL2 module
    acl2_mod = acl2.ACL2Module(
        name=spec_module.name,
        defuns=defuns,
        defthms=defthms,
        defun_sk_ops=defun_sk_ops,
        raw_forms=raw_forms
    )
    return acl2_mod
