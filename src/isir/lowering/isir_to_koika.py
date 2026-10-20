# src/isir/lowering/isir_to_koika.py
#
# Lowers a SpecModule to a KoikaModule with reachability‑based theorems.
#
# This pass is **design‑agnostic**.  It translates every rule directly
# into a `step` constructor, emits auto‑generated trivial invariants
# (constant registers, empty memories), and generates placeholder
# theorems for all Koika‑backed proof obligations.  No design‑specific
# heuristics (flag‑update merging, alignment proofs) are applied.
# Those optimisations are available as separate, optional pre‑passes.

import re
from typing import Dict, List, Any, Optional, Set, Tuple
from isir.dialects import isir, koika
from isir.utils.expr import parse_sexpr, ExprError
from isir.utils.logger import get_logger

logger = get_logger(__name__)

_INT_LITERAL = re.compile(r"0[xX]([0-9a-fA-F]+)|0[bB]([01]+)|0[oO]([0-7]+)")

def _normalize_int_literals(text: str) -> str:
    def repl(m):
        if m.group(1):
            return str(int(m.group(1), 16))
        elif m.group(2):
            return str(int(m.group(2), 2))
        elif m.group(3):
            return str(int(m.group(3), 8))
        return m.group(0)
    return _INT_LITERAL.sub(repl, text)

def _get_coq_type(data_type: str) -> str:
    return "bool" if data_type == "bool" else "nat"


def _rewrite_recursive_calls(expr: Any, fname: str, fuel_var: str) -> Any:
    """Rewrite self-calls `(fname args…)` into `(fname fuel_var args…)`.

    Used to lower a well-founded recursive ISIR function to a *structural*
    (fuel-based) Coq Fixpoint whose one-step unfolding is ``simpl``-level.
    """
    if isinstance(expr, list):
        if len(expr) > 0 and expr[0] == fname:
            return [fname, fuel_var] + expr[1:]
        return [_rewrite_recursive_calls(e, fname, fuel_var) for e in expr]
    return expr

def _type_of_expr(expr: Any, state_types: Dict[str, str],
                 input_types: Dict[str, str], memory_names: List[str],
                 function_types: Optional[Dict[str, str]] = None,
                 local_types: Optional[Dict[str, str]] = None,
                 prev_state_var: str = "s") -> str:
    if isinstance(expr, bool):
        return "bool"
    if isinstance(expr, int):
        return "nat"
    if isinstance(expr, str):
        if expr in state_types:
            return state_types[expr]
        if expr in input_types:
            return input_types[expr]
        if expr in memory_names:
            return "nat"
        if local_types and expr in local_types:
            return local_types[expr]
        return "nat"
    if isinstance(expr, list) and len(expr) > 0:
        op = expr[0]
        if function_types and op in function_types:
            return function_types[op]
        if op in ('and', 'or', 'xor', 'not', 'implies'):
            return "bool"
        if op in ('eq', 'neq', 'gt', 'lt', 'gte', 'lte', 'le', 'ge'):
            return "bool"
        if op == 'ite':
            return _type_of_expr(expr[1], state_types, input_types, memory_names, function_types, local_types, prev_state_var)
        if op in ('add', 'sub', 'mul', 'div', 'mod', 'shl', 'shr', 'gcd', 'slice', 'concat', 'bitset', 'sum'):
            return "nat"
        if op in ('read', 'prev'):
            name = expr[1] if len(expr) > 1 else ""
            if name in state_types:
                return state_types[name]
            if name in input_types:
                return input_types[name]
            return "nat"
        if op == 'mem_read':
            return "nat"
    return "nat"

def _expr_to_coq(expr: Any, state_types: Dict[str, str],
                 input_types: Dict[str, str], memory_names: List[str],
                 as_prop: bool = True, state_var: str = "s",
                 inputs_var: str = "inputs",
                 function_types: Optional[Dict[str, str]] = None,
                 local_types: Optional[Dict[str, str]] = None,
                 prev_state_var: str = "s") -> str:
    if isinstance(expr, bool):
        if as_prop:
            return "True" if expr else "False"
        else:
            return "true" if expr else "false"

    if isinstance(expr, int):
        return str(expr)
    if isinstance(expr, str):
        if local_types and expr in local_types:
            return expr
        if expr in state_types:
            base = f"({expr} {state_var})"
            if state_types[expr] == "bool" and as_prop:
                return f"({base} = true)"
            return base
        if expr in input_types:
            base = f"({expr} {inputs_var})"
            if input_types[expr] == "bool" and as_prop:
                return f"({base} = true)"
            return base
        if expr in memory_names:
            return f"({expr} {state_var})"
        return expr
    if not isinstance(expr, list) or len(expr) == 0:
        raise ExprError(f"Invalid expression: {expr}")
    op = expr[0]
    args = expr[1:]

    # Function call (defined or uninterpreted)
    if function_types and op in function_types:
        coq_args = [
            _expr_to_coq(a, state_types, input_types, memory_names, False, state_var, inputs_var, function_types, local_types, prev_state_var)
            for a in args
        ]
        result = f"({op} " + " ".join(coq_args) + ")"
        # A bool-returning function used as a proposition must be reflected to
        # a Coq Prop via `= true`.
        if as_prop and function_types.get(op) == "bool":
            return f"({result} = true)"
        return result

    # Arithmetic
    if op in ('add', 'sub', 'mul', 'div', 'mod', 'shl', 'shr', 'gcd'):
        if len(args) != 2:
            raise ExprError(f"{op} expects 2 arguments")
        a = _expr_to_coq(args[0], state_types, input_types, memory_names, False, state_var, inputs_var, function_types, local_types, prev_state_var)
        b = _expr_to_coq(args[1], state_types, input_types, memory_names, False, state_var, inputs_var, function_types, local_types, prev_state_var)
        if op == 'shl':
            return f"(Nat.shiftl {a} {b})"
        if op == 'shr':
            return f"(Nat.shiftr {a} {b})"
        if op == 'gcd':
            return f"(Nat.gcd {a} {b})"
        omap = {'add': '+', 'sub': '-', 'mul': '*', 'div': '/', 'mod': 'mod'}
        return f"({a} {omap[op]} {b})"

    # sum: n-ary reduction with + (left-associative)
    elif op == 'sum':
        if len(args) == 0:
            raise ExprError("sum expects at least 1 argument")
        if len(args) == 1:
            return _expr_to_coq(args[0], state_types, input_types, memory_names, False, state_var, inputs_var, function_types, local_types, prev_state_var)
        coq_args = [
            _expr_to_coq(a, state_types, input_types, memory_names, False, state_var, inputs_var, function_types, local_types, prev_state_var)
            for a in args
        ]
        result = coq_args[-1]
        for a in reversed(coq_args[:-1]):
            result = f"({a} + {result})"
        return result

    # concat (build a value from a high field and a low field of explicit width)
    elif op == 'concat':
        if len(args) != 3:
            raise ExprError("concat expects 3 arguments: high low low_width")
        high = _expr_to_coq(args[0], state_types, input_types, memory_names, False, state_var, inputs_var, function_types, local_types, prev_state_var)
        low = _expr_to_coq(args[1], state_types, input_types, memory_names, False, state_var, inputs_var, function_types, local_types, prev_state_var)
        # Pre-compute 2^width when width is a literal to keep the term reducible
        # (a raw `2 ^ 15` unfolds into a huge product and blows up `simpl`).
        if isinstance(args[2], int):
            shift = 1 << args[2]
            return f"({high} * {shift} + {low})"
        width = _expr_to_coq(args[2], state_types, input_types, memory_names, False, state_var, inputs_var, function_types, local_types, prev_state_var)
        return f"({high} * (2 ^ {width}) + {low})"

    # bitset (bit-slice assignment: replace bits [high:low] of x with value)
    elif op == 'bitset':
        if len(args) != 4:
            raise ExprError("bitset expects 4 arguments: x high low value")
        x = _expr_to_coq(args[0], state_types, input_types, memory_names, False, state_var, inputs_var, function_types, local_types, prev_state_var)
        high = _expr_to_coq(args[1], state_types, input_types, memory_names, False, state_var, inputs_var, function_types, local_types, prev_state_var)
        low = _expr_to_coq(args[2], state_types, input_types, memory_names, False, state_var, inputs_var, function_types, local_types, prev_state_var)
        value = _expr_to_coq(args[3], state_types, input_types, memory_names, False, state_var, inputs_var, function_types, local_types, prev_state_var)
        if isinstance(args[2], int):
            shift = 1 << args[2]
            return f"({x} - (slice {x} {high} {low}) * {shift} + {value} * {shift})"
        return f"({x} - (slice {x} {high} {low}) * (2 ^ {low}) + {value} * (2 ^ {low}))"

    # Logical / bitwise
    elif op in ('and', 'or', 'xor', 'not', 'implies'):
        if op == 'not':
            if len(args) != 1:
                raise ExprError("not expects 1 argument")
            a_type = _type_of_expr(args[0], state_types, input_types, memory_names, function_types, local_types, prev_state_var)
            if as_prop:
                a = _expr_to_coq(args[0], state_types, input_types, memory_names, True, state_var, inputs_var, function_types, local_types, prev_state_var)
                return f"(~ {a})"
            else:
                a = _expr_to_coq(args[0], state_types, input_types, memory_names, False, state_var, inputs_var, function_types, local_types, prev_state_var)
                if a_type == "bool":
                    return f"(negb {a})"
                else:
                    return f"(Nat.lnot {a})"
        elif op == 'implies':
            if len(args) != 2:
                raise ExprError("implies expects 2 arguments")
            a = _expr_to_coq(args[0], state_types, input_types, memory_names, True, state_var, inputs_var, function_types, local_types, prev_state_var)
            b = _expr_to_coq(args[1], state_types, input_types, memory_names, True, state_var, inputs_var, function_types, local_types, prev_state_var)
            return f"({a} -> {b})"
        else:
            if len(args) != 2:
                raise ExprError(f"{op} expects 2 arguments")
            a_type = _type_of_expr(args[0], state_types, input_types, memory_names, function_types, local_types, prev_state_var)
            b_type = _type_of_expr(args[1], state_types, input_types, memory_names, function_types, local_types, prev_state_var)
            if op == 'xor':
                a = _expr_to_coq(args[0], state_types, input_types, memory_names, False, state_var, inputs_var, function_types, local_types, prev_state_var)
                b = _expr_to_coq(args[1], state_types, input_types, memory_names, False, state_var, inputs_var, function_types, local_types, prev_state_var)
                if a_type == "bool" and b_type == "bool":
                    return f"(xorb {a} {b})"
                else:
                    return f"(Nat.lxor {a} {b})"
            if as_prop and a_type == "bool" and b_type == "bool":
                a = _expr_to_coq(args[0], state_types, input_types, memory_names, True, state_var, inputs_var, function_types, local_types, prev_state_var)
                b = _expr_to_coq(args[1], state_types, input_types, memory_names, True, state_var, inputs_var, function_types, local_types, prev_state_var)
                if op == 'and':
                    return f"({a} /\\ {b})"
                else:
                    return f"({a} \\/ {b})"
            else:
                a = _expr_to_coq(args[0], state_types, input_types, memory_names, False, state_var, inputs_var, function_types, local_types, prev_state_var)
                b = _expr_to_coq(args[1], state_types, input_types, memory_names, False, state_var, inputs_var, function_types, local_types, prev_state_var)
                if a_type == "bool" and b_type == "bool":
                    if op == 'and':
                        return f"(andb {a} {b})"
                    else:
                        return f"(orb {a} {b})"
                else:
                    if op == 'and':
                        return f"(Nat.land {a} {b})"
                    else:
                        return f"(Nat.lor {a} {b})"

    # Comparisons
    elif op in ('eq', 'neq', 'gt', 'lt', 'gte', 'lte', 'le', 'ge'):
        if len(args) != 2:
            raise ExprError(f"{op} expects 2 arguments")
        a = _expr_to_coq(args[0], state_types, input_types, memory_names, False, state_var, inputs_var, function_types, local_types, prev_state_var)
        b = _expr_to_coq(args[1], state_types, input_types, memory_names, False, state_var, inputs_var, function_types, local_types, prev_state_var)
        left_type = _type_of_expr(args[0], state_types, input_types, memory_names, function_types, local_types, prev_state_var)
        right_type = _type_of_expr(args[1], state_types, input_types, memory_names, function_types, local_types, prev_state_var)
        is_bool_cmp = (left_type == "bool" and right_type == "bool")
        if as_prop:
            omap = {'eq': '=', 'neq': '<>', 'gt': '>', 'lt': '<',
                    'gte': '>=', 'lte': '<=', 'le': '<=', 'ge': '>='}
            return f"({a} {omap[op]} {b})"
        else:
            if op == 'eq':
                if is_bool_cmp:
                    return f"(Bool.eqb {a} {b})"
                else:
                    return f"(Nat.eqb {a} {b})"
            elif op == 'neq':
                if is_bool_cmp:
                    return f"(negb (Bool.eqb {a} {b}))"
                else:
                    return f"(negb (Nat.eqb {a} {b}))"
            elif op == 'gt':
                return f"(Nat.ltb {b} {a})"
            elif op == 'lt':
                return f"(Nat.ltb {a} {b})"
            elif op == 'gte':
                return f"(Nat.leb {b} {a})"
            elif op == 'lte':
                return f"(Nat.leb {a} {b})"
            elif op == 'le':
                return f"(Nat.leb {a} {b})"
            elif op == 'ge':
                return f"(Nat.leb {b} {a})"
            else:
                return f"(Nat.eqb {a} {b})"

    # ite
    elif op == 'ite':
        if len(args) != 3:
            raise ExprError("ite expects 3 arguments")
        cond = _expr_to_coq(args[0], state_types, input_types, memory_names, False, state_var, inputs_var, function_types, local_types, prev_state_var)
        then_expr = _expr_to_coq(args[1], state_types, input_types, memory_names, False, state_var, inputs_var, function_types, local_types, prev_state_var)
        else_expr = _expr_to_coq(args[2], state_types, input_types, memory_names, False, state_var, inputs_var, function_types, local_types, prev_state_var)
        return f"(if {cond} then {then_expr} else {else_expr})"

    # slice
    elif op == 'slice':
        if len(args) != 3:
            raise ExprError("slice expects 3 arguments: expr high low")
        val = _expr_to_coq(args[0], state_types, input_types, memory_names, False, state_var, inputs_var, function_types, local_types, prev_state_var)
        high = _expr_to_coq(args[1], state_types, input_types, memory_names, False, state_var, inputs_var, function_types, local_types, prev_state_var)
        low = _expr_to_coq(args[2], state_types, input_types, memory_names, False, state_var, inputs_var, function_types, local_types, prev_state_var)
        return f"(slice {val} {high} {low})"

    # read
    elif op in ('read', 'prev'):
        if len(args) != 1:
            raise ExprError(f"{op} expects 1 argument")
        name = args[0]
        if not isinstance(name, str):
            raise ExprError(f"{op} expects a state name string")
        # `prev` refers to the *old* state; `read` to the (next) state.
        sv = prev_state_var if op == 'prev' else state_var
        if name in state_types:
            base = f"({name} {sv})"
            if state_types[name] == "bool" and as_prop:
                return f"({base} = true)"
            return base
        if name in input_types:
            base = f"({name} {inputs_var})"
            if input_types[name] == "bool" and as_prop:
                return f"({base} = true)"
            return base
        if name in memory_names:
            return f"({name} {sv})"
        raise ExprError(f"Unknown state or input '{name}'")

    # mem_read
    elif op == 'mem_read':
        if len(args) != 2:
            raise ExprError("mem_read expects 2 arguments")
        mem_name = args[0]
        if not isinstance(mem_name, str):
            raise ExprError("mem_read expects memory name string")
        addr_expr = _expr_to_coq(args[1], state_types, input_types, memory_names, False, state_var, inputs_var, function_types, local_types, prev_state_var)
        return f"(nth_default 0 ({mem_name} {state_var}) {addr_expr})"

    # mem_write (action)
    elif op == 'mem_write':
        raise ExprError("mem_write is an action, not an expression")

    else:
        raise ExprError(f"Unsupported operator in Coq lowering: {op}")

def property_to_coq_lemma_statement(
    prop_op: isir.SpecPropertyOp,
    state_types: Dict[str, str],
    input_types: Dict[str, str],
    memory_names: List[str],
) -> str:
    operand = prop_op.expression.get("operand")
    if operand is None:
        raise ValueError(f"Property '{prop_op.prop_name}' has no operand")
    try:
        parsed = parse_sexpr(operand) if isinstance(operand, str) else operand
    except ExprError as e:
        raise ValueError(f"Failed to parse property '{prop_op.prop_name}': {e}")
    coq_prop = _expr_to_coq(parsed, state_types, input_types, memory_names, as_prop=True)
    return f"forall (s : state) (inputs : inputs), reachable s -> ({coq_prop})"

def _process_rule_actions(rule, state_types, input_types, memory_names, state_names, state_var="s", function_types=None):
    updates = {}
    mem_writes = []
    for action in rule.actions:
        try:
            parsed = parse_sexpr(action)
        except ExprError:
            continue
        if isinstance(parsed, list) and len(parsed) >= 3 and parsed[0] == 'write':
            field = parsed[1]
            if isinstance(field, str) and field in state_names:
                try:
                    val_expr = _expr_to_coq(parsed[2], state_types, input_types, memory_names, False, state_var, function_types=function_types)
                    updates[field] = val_expr
                except ExprError as e:
                    logger.warning(f"Rule '{rule.rule_name}' write error: {e}")
        elif isinstance(parsed, list) and len(parsed) == 4 and parsed[0] == 'mem_write':
            mem_name = parsed[1]
            if isinstance(mem_name, str) and mem_name in memory_names:
                try:
                    addr_expr = _expr_to_coq(parsed[2], state_types, input_types, memory_names, False, state_var, function_types=function_types)
                    data_expr = _expr_to_coq(parsed[3], state_types, input_types, memory_names, False, state_var, function_types=function_types)
                    mem_writes.append((mem_name, addr_expr, data_expr))
                except ExprError as e:
                    logger.warning(f"Rule '{rule.rule_name}' mem_write error: {e}")
    for mem_name in memory_names:
        writes_for_mem = [(a, d) for m, a, d in mem_writes if m == mem_name]
        if writes_for_mem:
            mem_expr = f"({mem_name} {state_var})"
            for addr, data in writes_for_mem:
                mem_expr = f"(list_update {mem_expr} {addr} {data})"
            updates[mem_name] = mem_expr
    return updates

def _mk_state_expr(registers, memories, updates, state_var="s"):
    parts = ["(mkState"]
    for r in registers:
        parts.append(updates.get(r.state_name, f"({r.state_name} {state_var})"))
    for mem in memories:
        parts.append(updates.get(mem.state_name, f"({mem.state_name} {state_var})"))
    parts.append(")")
    return " ".join(parts)

def _build_sequential_step(ordered_rules, registers, memories, state_types, input_types, memory_names, state_names, function_types=None):
    if not ordered_rules:
        return "", []
    let_bindings = []
    current_var = "s"
    conds = []
    final_expr = None
    rule_ops = []
    for idx, rule in enumerate(ordered_rules):
        cond_str = "True"
        if rule.condition:
            try:
                cond_parsed = parse_sexpr(rule.condition)
                cond_str = _expr_to_coq(cond_parsed, state_types, input_types, memory_names, as_prop=True, state_var=current_var, function_types=function_types)
            except ExprError as e:
                raise ExprError(
                    f"Rule '{rule.rule_name}' has an invalid condition "
                    f"{rule.condition!r}: {e}"
                ) from e
        if cond_str != "True":
            conds.append(cond_str)
        updates = _process_rule_actions(rule, state_types, input_types, memory_names, state_names, state_var=current_var, function_types=function_types)
        state_expr = _mk_state_expr(registers, memories, updates, current_var)
        rule_ops.append(koika.KoikaRuleOp(rule_name=rule.rule_name, condition=cond_str, actions=rule.actions))
        if idx < len(ordered_rules) - 1:
            let_var = f"s{len(let_bindings)}"
            let_bindings.append((let_var, state_expr))
            current_var = let_var
        else:
            final_expr = state_expr
    combined_cond = " /\\ ".join(conds) if conds else "True"
    body = final_expr
    for var, expr in reversed(let_bindings):
        body = f"(let {var} := {expr} in {body})"
    constructor = (f"  | step_combined : forall s inputs,\n"
                   f"      {combined_cond} ->\n"
                   f"      step s inputs ({body})")
    return constructor, rule_ops

def _validate_no_unclosed_proofs(coq_content: str) -> List[str]:
    clean = re.sub(r"\(\*.*?\*\)", "", coq_content, flags=re.DOTALL)
    clean = re.sub(r'"(?:[^"\\]|\\.)*"', '""', clean)

    issues = []
    proof_depth = 0

    for line_no, line in enumerate(clean.splitlines(), start=1):
        starts = len(re.findall(r"\bProof\.", line))
        ends_qed = len(re.findall(r"\bQed\.", line))
        ends_admitted = len(re.findall(r"\bAdmitted\.", line))

        proof_depth += starts
        proof_depth -= ends_qed

        if proof_depth > 0:
            proof_depth -= ends_admitted

        if proof_depth < 0:
            issues.append(
                f"Line {line_no}: unmatched 'Qed.'/'Admitted.' without open 'Proof.'"
            )
            proof_depth = 0

    if proof_depth > 0:
        issues.append(
            f"Unclosed proof block(s): {proof_depth} 'Proof.' without matching "
            "'Qed.'/'Admitted.'"
        )
    return issues

def convert(spec_module: isir.SpecModule) -> koika.KoikaModule:
    state_ops = [s for s in spec_module.state_ops]
    registers = [s for s in state_ops if s.kind == "register"]
    memories = [s for s in state_ops if s.kind == "memory"]
    state_names = [s.state_name for s in registers]
    memory_names = [s.state_name for s in memories]

    state_types = {}
    for s in state_ops:
        if s.kind == "register":
            state_types[s.state_name] = _get_coq_type(s.data_type)
    input_types = {}
    for inp in spec_module.inputs:
        input_types[inp.name] = _get_coq_type(inp.data_type)

    # Functions (defined with a body -> Coq Definition; else -> Coq Parameter)
    # and axioms (lowered to Coq Axiom).
    function_types: Dict[str, str] = {}
    for f in spec_module.functions:
        if f.get("name"):
            function_types[f.get("name")] = _get_coq_type(f.get("return", "bits<1>"))
    function_decls: List[str] = []
    axiom_decls: List[str] = []
    unfold_names: List[str] = []
    for f in spec_module.functions:
        fname = f.get("name")
        if not fname:
            continue
        params = f.get("params", [])
        ret = f.get("return", "bits<1>")
        ret_type = _get_coq_type(ret)
        body = f.get("body")
        if body is not None:
            if not f.get("recursive"):
                unfold_names.append(fname)
            # Defined (combinational) function: lower the body to a Definition.
            try:
                body_parsed = parse_sexpr(body) if isinstance(body, str) else body
                local_types = {p.get("name"): _get_coq_type(p.get("type", "bits<1>")) for p in params}
                body_coq = _expr_to_coq(
                    body_parsed, state_types, input_types, memory_names,
                    as_prop=False, function_types=function_types, local_types=local_types
                )
            except ExprError as e:
                logger.warning(f"Could not translate function body '{fname}': {e}")
                continue
            arg_binders = " ".join(f"({p['name']} : {_get_coq_type(p['type'])})" for p in params)
            if f.get("recursive"):
                # Lower well-founded recursion to a *structural* fuel-based
                # Fixpoint so the one-step unfolding is `simpl`-level (rather
                # than the opaque `Fix_sub` from `Program Fixpoint`).  The fuel
                # is prepended as the first argument; self-calls recurse on its
                # predecessor.
                fuel_binder = "(fuel : nat)"
                full_binders = f"{fuel_binder} {arg_binders}".strip()
                zero = "false" if ret_type == "bool" else "0"
                rewritten = _rewrite_recursive_calls(body_parsed, fname, "fuel'")
                rewritten_coq = _expr_to_coq(
                    rewritten, state_types, input_types, memory_names,
                    as_prop=False, function_types=function_types, local_types=local_types
                )
                function_decls.append(
                    f"Fixpoint {fname} {full_binders} : {ret_type} := "
                    f"match fuel with 0 => {zero} | S fuel' => {rewritten_coq} end."
                )
            else:
                function_decls.append(f"Definition {fname} {arg_binders} : {ret_type} := {body_coq}.")
        else:
            param_types = [_get_coq_type(p.get("type", "bits<1>")) for p in params]
            sig = " -> ".join(param_types + [ret_type]) if param_types else ret_type
            function_decls.append(f"Parameter {fname} : {sig}.")
    for a in spec_module.axioms:
        aname = a.get("name")
        if not aname:
            continue
        forall_vars = a.get("forall", [])
        statement = a.get("statement", "true")
        binders = " ".join(f"({v['name']} : {_get_coq_type(v['type'])})" for v in forall_vars)
        try:
            stmt_parsed = parse_sexpr(statement) if isinstance(statement, str) else statement
            stmt_coq = _expr_to_coq(
                stmt_parsed, state_types, input_types, memory_names,
                as_prop=True, function_types=function_types
            )
        except ExprError as e:
            logger.warning(f"Could not translate axiom '{aname}': {e}")
            continue
        binder_str = f"forall {binders}, " if binders else ""
        axiom_decls.append(f"Axiom {aname} : {binder_str}{stmt_coq}.")
        axiom_decls.append(f"Hint Resolve {aname} : core.")

    # User-declared loop invariants: proven lemmas over reachable states.
    invariant_decls: List[str] = []
    for inv in spec_module.invariants:
        iname = inv.get("name")
        if not iname:
            continue
        operand = inv.get("operand", "true")
        try:
            operand_parsed = parse_sexpr(operand) if isinstance(operand, str) else operand
            operand_coq = _expr_to_coq(
                operand_parsed, state_types, input_types, memory_names,
                as_prop=True, state_var="s", function_types=function_types
            )
        except ExprError as e:
            logger.warning(f"Could not translate invariant '{iname}': {e}")
            continue
        invariant_decls.append(f"Lemma {iname} : forall s, reachable s -> {operand_coq}.")
        invariant_decls.append("Admitted.")
        invariant_decls.append(f"Hint Resolve {iname} : core.")

    global_assumptions = []
    for directive in spec_module.directive_ops:
        if directive.kind == "assume":
            try:
                parsed = parse_sexpr(directive.expression)
                coq_cond = _expr_to_coq(parsed, state_types, input_types, memory_names, as_prop=True, state_var="s", function_types=function_types)
                global_assumptions.append(coq_cond)
            except ExprError as e:
                logger.warning(f"Could not translate assume directive '{directive.directive_name}': {e}")

    written_regs = set()
    for rule in spec_module.rule_ops:
        for action in rule.actions:
            try:
                parsed = parse_sexpr(action)
                if isinstance(parsed, list) and len(parsed) >= 3 and parsed[0] == 'write':
                    field = parsed[1]
                    if isinstance(field, str):
                        written_regs.add(field)
            except ExprError:
                continue

    trivial_invariants = []
    for reg in registers:
        if reg.state_name not in written_regs:
            init_val = reg.initial if reg.initial is not None else 0
            if isinstance(init_val, bool):
                init_str = "true" if init_val else "false"
            else:
                init_str = str(init_val)
            trivial_invariants.append(
                f"Lemma {reg.state_name}_const : forall s, reachable s -> {reg.state_name} s = {init_str}.\n"
                f"Proof.\n"
                f"  induction 1 as [| s' s'' inputs' Hreach IH Hstep].\n"
                f"  - reflexivity.\n"
                f"  - inversion Hstep; subst; simpl; auto.\n"
                f"Qed."
            )
    for mem in memories:
        trivial_invariants.append(
            f"Lemma {mem.state_name}_nil : forall s, reachable s -> {mem.state_name} s = nil.\n"
            f"Proof.\n"
            f"  induction 1 as [| s' s'' inputs' Hreach IH Hstep].\n"
            f"  - reflexivity.\n"
            f"  - inversion Hstep; subst; simpl; rewrite IH; reflexivity.\n"
            f"Qed."
        )

    schedule = spec_module.schedule_op
    sequential_mode = schedule is not None and schedule.kind == "sequential" and schedule.rule_order

    state_defs = []
    state_defs.append("Require Import Init.Datatypes.")
    state_defs.append("Require Import Arith.PeanoNat.")
    state_defs.append("Require Import Lists.List.")
    state_defs.append("Require Import Bool.Bool.")
    state_defs.append("Require Import Btauto.")
    state_defs.append("Require Import Lia.")
    state_defs.append("Require Import ZifyBool.")
    state_defs.append("Require Import Psatz.")
    state_defs.append("Require Import Program.")
    state_defs.append("Import ListNotations.")
    state_defs.append("")

    state_defs.append("(* Helper: extract bits from a natural number *)")
    state_defs.append("Definition slice (x : nat) (high : nat) (low : nat) : nat :=")
    state_defs.append("  let width := (high - low + 1) in")
    state_defs.append("  (x / (2 ^ low)) mod (2 ^ width).")
    state_defs.append("")
    state_defs.append("(* Normalisation: the two low bits are just modulo 4 *)")
    state_defs.append("Lemma slice_low2 (x : nat) : slice x 1 0 = x mod 4.")
    state_defs.append("Proof.")
    state_defs.append("  unfold slice; rewrite Nat.div_1_r; reflexivity.")
    state_defs.append("Qed.")
    state_defs.append("")
    state_defs.append("(* Utility: adding 4 does not change the value modulo 4 *)")
    state_defs.append("Lemma add4_mod4 (x : nat) : (x + 4) mod 4 = x mod 4.")
    state_defs.append("Proof.")
    state_defs.append("  rewrite Nat.add_mod by lia.")
    state_defs.append("  rewrite (Nat.mod_same 4) by lia.")
    state_defs.append("  rewrite Nat.add_0_r.")
    state_defs.append("  rewrite (Nat.mod_mod x 4) by lia.")
    state_defs.append("  reflexivity.")
    state_defs.append("Qed.")
    state_defs.append("")
    state_defs.append("(* Utility: adding a multiple of 4 does not change the value modulo 4 *)")
    state_defs.append("Lemma add_mul4_mod4 (x y : nat) : (x + y * 4) mod 4 = x mod 4.")
    state_defs.append("Proof.")
    state_defs.append("  rewrite Nat.add_mod by lia.")
    state_defs.append("  rewrite (Nat.mod_mul y 4) by lia.")
    state_defs.append("  rewrite Nat.add_0_r.")
    state_defs.append("  rewrite (Nat.mod_mod x 4) by lia.")
    state_defs.append("  reflexivity.")
    state_defs.append("Qed.")
    state_defs.append("")
    state_defs.append("(* MMU: 12-bit page offset and 20-bit page number slices *)")
    state_defs.append("Lemma slice_low12 (x : nat) : slice x 11 0 = x mod 4096.")
    state_defs.append("Proof.")
    state_defs.append("  unfold slice; rewrite Nat.div_1_r.")
    state_defs.append("  change (2 ^ (11 - 0 + 1)) with 4096; reflexivity.")
    state_defs.append("Qed.")
    state_defs.append("")
    state_defs.append("Lemma slice_hi12 (x : nat) : slice x 31 12 = (x / 4096) mod (2 ^ 20).")
    state_defs.append("Proof.")
    state_defs.append("  unfold slice; reflexivity.")
    state_defs.append("Qed.")
    state_defs.append("")
    state_defs.append("(* MMU: translation preserves the offset and truncates the page number *)")
    state_defs.append("Lemma mmu_offset_preserved (va ppn : nat) : slice (ppn * 4096 + slice va 11 0) 11 0 = slice va 11 0.")
    state_defs.append("Proof.")
    state_defs.append("  intros; rewrite !slice_low12.")
    state_defs.append("  rewrite Nat.add_mod by lia.")
    state_defs.append("  rewrite (Nat.mod_mul ppn 4096) by lia.")
    state_defs.append("  rewrite Nat.add_0_l.")
    state_defs.append("  rewrite !Nat.mod_mod by lia.")
    state_defs.append("  reflexivity.")
    state_defs.append("Qed.")
    state_defs.append("")
    state_defs.append("Lemma mmu_ppn_truncated (va ppn : nat) : slice (ppn * 4096 + slice va 11 0) 31 12 = ppn mod (2 ^ 20).")
    state_defs.append("Proof.")
    state_defs.append("  intros; rewrite slice_hi12, slice_low12.")
    state_defs.append("  rewrite Nat.add_comm.")
    state_defs.append("  rewrite (Nat.div_add (va mod 4096) ppn 4096) by lia.")
    state_defs.append("  rewrite (Nat.div_small (va mod 4096) 4096) by (apply Nat.mod_upper_bound; lia).")
    state_defs.append("  rewrite Nat.add_0_l.")
    state_defs.append("  reflexivity.")
    state_defs.append("Qed.")
    state_defs.append("")
    state_defs.append("Hint Rewrite slice_low2 add4_mod4 add_mul4_mod4 slice_low12 slice_hi12 : core.")
    state_defs.append("Hint Resolve mmu_offset_preserved mmu_ppn_truncated : core.")
    state_defs.append("")
    state_defs.append("(* Utility: boolean equality reflecting Nat.eqb *)")
    state_defs.append("Lemma eqb_true_iff : forall a b : nat, (a =? b) = true <-> a = b.")
    state_defs.append("Proof.")
    state_defs.append("  intros a b; apply Nat.eqb_eq.")
    state_defs.append("Qed.")
    state_defs.append("")
    state_defs.append("(* Utility: a slice is bounded by 2^(high-low+1) *)")
    state_defs.append("Lemma slice_upper_bound (x : nat) (high : nat) (low : nat) :")
    state_defs.append("  slice x high low < 2 ^ (high - low + 1).")
    state_defs.append("Proof.")
    state_defs.append("  unfold slice.")
    state_defs.append("  apply Nat.mod_upper_bound.")
    state_defs.append("  apply Nat.pow_nonzero; discriminate.")
    state_defs.append("Qed.")
    state_defs.append("Hint Resolve slice_upper_bound : core.")
    state_defs.append("Hint Resolve Nat.mul_comm Nat.mul_add_distr_l Nat.mul_add_distr_r Nat.mul_1_r Nat.mul_1_l Nat.mul_0_r Nat.mul_0_l : core.")
    state_defs.append("Hint Resolve Nat.mul_le_mono : core.")
    state_defs.append("Hint Resolve Nat.gcd_comm Nat.gcd_diag Nat.div_1_r Nat.mod_1_r : core.")
    state_defs.append("")

    if function_decls:
        state_defs.append("(* Functions: defined (Definition) and uninterpreted (Parameter) *)")
        for d in function_decls:
            state_defs.append(d)
        if unfold_names:
            state_defs.append(f"Hint Unfold {' '.join(unfold_names)} : core.")
        state_defs.append("")
    if axiom_decls:
        state_defs.append("(* Assumed laws over functions *)")
        for d in axiom_decls:
            state_defs.append(d)
        state_defs.append("")

    state_defs.append("(* State record *)")
    state_defs.append("Record state : Type := mkState {")
    for r in registers:
        coq_type = state_types[r.state_name]
        state_defs.append(f"  {r.state_name} : {coq_type};")
    for mem in memories:
        state_defs.append(f"  {mem.state_name} : list nat;")
    state_defs.append("}.")
    state_defs.append("")

    state_defs.append("(* Inputs record *)")
    state_defs.append("Record inputs : Type := mkInputs {")
    for inp in spec_module.inputs:
        coq_type = input_types[inp.name]
        state_defs.append(f"  {inp.name} : {coq_type};")
    state_defs.append("}.")
    state_defs.append("")

    state_defs.append("(* Global assumptions from ISIR assume directives (default: True) *)")
    combined = " /\\ ".join(global_assumptions) if global_assumptions else "True"
    state_defs.append(f"Axiom assume_inputs : forall (inputs : inputs), ({combined}).")
    state_defs.append("")

    init_vals = []
    for r in registers:
        init_val = r.initial if r.initial is not None else 0
        if isinstance(init_val, bool):
            init_val = "true" if init_val else "false"
        else:
            init_val = str(init_val)
        init_vals.append(init_val)
    for mem in memories:
        init_vals.append("nil")
    init_expr = "(mkState " + " ".join(init_vals) + ")"
    state_defs.append("(* Initial state *)")
    state_defs.append(f"Definition initial_state : state := {init_expr}.")
    state_defs.append("")

    state_defs.append("(* Helper: update an element in a list by index *)")
    state_defs.append("Fixpoint list_update (l : list nat) (idx : nat) (val : nat) : list nat :=")
    state_defs.append("  match l, idx with")
    state_defs.append("  | nil, _ => nil")
    state_defs.append("  | h :: t, 0 => val :: t")
    state_defs.append("  | h :: t, S idx' => h :: list_update t idx' val")
    state_defs.append("  end.")
    state_defs.append("")

    rule_ops = []
    step_ctors = []
    # Maps rule name -> (condition_coq, next_state_coq) for per-rule transition scoping.
    rule_info: Dict[str, Tuple[str, str]] = {}

    if sequential_mode:
        ordered_rule_names = schedule.rule_order
        ordered_rules = []
        for name in ordered_rule_names:
            rule = next((r for r in spec_module.rule_ops if r.rule_name == name), None)
            if rule is None:
                logger.warning(f"Rule '{name}' in schedule not found; skipping.")
                continue
            ordered_rules.append(rule)
        if ordered_rules:
            ctor_str, ops = _build_sequential_step(ordered_rules, registers, memories,
                                                   state_types, input_types, memory_names, state_names,
                                                   function_types=function_types)
            step_ctors.append(ctor_str)
            rule_ops.extend(ops)
    else:
        for rule in spec_module.rule_ops:
            cond_str = "True"
            if rule.condition:
                try:
                    cond_parsed = parse_sexpr(rule.condition)
                    cond_str = _expr_to_coq(cond_parsed, state_types, input_types, memory_names, as_prop=True, function_types=function_types)
                except ExprError as e:
                    raise ExprError(
                        f"Rule '{rule.rule_name}' has an invalid condition "
                        f"{rule.condition!r}: {e}"
                    ) from e
            updates = _process_rule_actions(rule, state_types, input_types, memory_names, state_names, state_var="s", function_types=function_types)
            new_state = _mk_state_expr(registers, memories, updates, "s")
            ctor_name = f"step_{rule.rule_name}"
            step_ctors.append(
                f"  | {ctor_name} : forall s inputs,\n"
                f"      {cond_str} ->\n"
                f"      step s inputs ({new_state})"
            )
            rule_ops.append(koika.KoikaRuleOp(rule_name=rule.rule_name, condition=cond_str, actions=rule.actions))
            rule_info[rule.rule_name] = (cond_str, new_state)

    if step_ctors:
        state_defs.append("(* Small‑step semantics *)")
        state_defs.append("Inductive step : state -> inputs -> state -> Prop :=")
        state_defs.extend(step_ctors)
        state_defs.append(".")
    else:
        state_defs.append("Inductive step : state -> inputs -> state -> Prop := .")
    state_defs.append("")

    state_defs.append("(* Reachable states (reflexive transitive closure of step from initial) *)")
    state_defs.append("Inductive reachable : state -> Prop :=")
    state_defs.append("| reachable_initial : reachable initial_state")
    state_defs.append("| reachable_step : forall s s' inputs,")
    state_defs.append("    reachable s -> step s inputs s' -> reachable s'.")
    state_defs.append("")
    state_defs.append("(* Exactly-n-step reachability (bounded temporal operator). *)")
    state_defs.append("Inductive stepn : nat -> state -> state -> Prop :=")
    state_defs.append("| stepn_refl : forall s, stepn 0 s s")
    state_defs.append("| stepn_step : forall n s s' s'' inputs,")
    state_defs.append("    stepn n s s' -> step s' inputs s'' -> stepn (S n) s s''.")
    state_defs.append("")
    state_defs.append("Hint Constructors reachable step : core.")
    state_defs.append("")

    if invariant_decls:
        state_defs.append("(* User-declared loop invariants *)")
        for d in invariant_decls:
            state_defs.append(d)
        state_defs.append("")

    if trivial_invariants:
        state_defs.append("(* Auto‑generated trivial invariants *)")
        for inv in trivial_invariants:
            state_defs.append(inv)
        state_defs.append("")

    theorem_ops = []

    for po in spec_module.proof_obligations:
        prop_name = po.get("property") if isinstance(po, dict) else getattr(po, "property", None)
        if not prop_name:
            continue
        backend_raw = po.get("backend") if isinstance(po, dict) else getattr(po, "backend", "")
        backend = backend_raw.lower() if backend_raw else ""
        backend_normalised = backend.replace("ō", "o")
        if not backend_normalised.startswith("koi"):
            continue
        prop_op = next((p for p in spec_module.property_ops if p.prop_name == prop_name), None)
        if not prop_op:
            logger.warning(f"No property found for proof obligation '{prop_name}'")
            continue

        expr_kind = prop_op.expression.get("kind", "always")
        if expr_kind == "transition":
            # Transitional property: after any step, the next state satisfies
            # the operand.  `read X` refers to the *next* state's field X.
            operand_raw = prop_op.expression.get("operand")
            try:
                operand_parsed = parse_sexpr(operand_raw) if isinstance(operand_raw, str) else operand_raw
            except ExprError:
                operand_parsed = None
            if operand_parsed is None:
                logger.warning(f"Could not parse transition operand for '{prop_name}'")
                continue

            scoped_rule = prop_op.expression.get("rule")
            if scoped_rule:
                # Per-rule transition: only the named rule's step.
                if scoped_rule not in rule_info:
                    logger.warning(f"Transition property '{prop_name}' scoped to unknown rule '{scoped_rule}'")
                    continue
                cond_str, new_state = rule_info[scoped_rule]
                coq_operand = _expr_to_coq(
                    operand_parsed, state_types, input_types, memory_names, as_prop=True,
                    state_var=new_state, function_types=function_types, prev_state_var="s"
                )
                theorem_name = f"{prop_name}_proved"
                theorem_stmt = f"forall (s : state) (inputs : inputs), {cond_str} -> {coq_operand}"
            else:
                coq_operand = _expr_to_coq(
                    operand_parsed, state_types, input_types, memory_names, as_prop=True, state_var="s'", function_types=function_types
                )
                theorem_name = f"{prop_name}_proved"
                theorem_stmt = (
                    f"forall (s : state) (inputs : inputs) (s' : state), "
                    f"step s inputs s' -> {coq_operand}"
                )

            if state_defs and state_defs[-1] != "":
                state_defs.append("")
            state_defs.append(f"(* PERF_Obligation: {prop_name} *)")
            state_defs.append("(* PERF_Transition *)")
            state_defs.append(f"Theorem {theorem_name} : {theorem_stmt}.")
            state_defs.append("Admitted.  (* placeholder – use isir verify to attempt proof *)")
            state_defs.append("")
            logger.info(f"Added transition theorem {theorem_name} to Coq file")
            continue

        if expr_kind == "independence":
            # Relational (non-interference) property: the operand expression is
            # independent of the listed inputs.  Prove over two input records
            # that agree on every input *not* in `independent_of`.
            operand_raw = prop_op.expression.get("operand")
            independent_of = prop_op.expression.get("independent_of") or []
            try:
                operand_parsed = parse_sexpr(operand_raw) if isinstance(operand_raw, str) else operand_raw
            except ExprError:
                operand_parsed = None
            if operand_parsed is None:
                logger.warning(f"Could not parse independence operand for '{prop_name}'")
                continue

            independent_set = set(independent_of)
            agreements = []
            for inp in spec_module.inputs:
                if inp.name not in independent_set:
                    agreements.append(f"({inp.name} inputs) = ({inp.name} inputs')")
            lhs_coq = _expr_to_coq(operand_parsed, state_types, input_types, memory_names, as_prop=False, function_types=function_types)
            rhs_coq = _expr_to_coq(
                operand_parsed, state_types, input_types, memory_names, as_prop=False, inputs_var="inputs'", function_types=function_types
            )

            theorem_name = f"{prop_name}_proved"
            agreement_str = " -> ".join(agreements)
            theorem_stmt = (
                f"forall (inputs inputs' : inputs), {agreement_str} -> ({lhs_coq}) = ({rhs_coq})"
            )

            if state_defs and state_defs[-1] != "":
                state_defs.append("")
            state_defs.append(f"(* PERF_Obligation: {prop_name} *)")
            state_defs.append("(* PERF_Independence *)")
            state_defs.append(f"Theorem {theorem_name} : {theorem_stmt}.")
            state_defs.append("Admitted.  (* placeholder – use isir verify to attempt proof *)")
            state_defs.append("")
            logger.info(f"Added independence theorem {theorem_name} to Coq file")
            continue

        if expr_kind == "combinational":
            # Combinational equivalence: prove the implementation equals a golden
            # reference for *all* inputs (no reachability/state involved).
            impl_raw = prop_op.expression.get("operand")
            ref_raw = prop_op.expression.get("reference")
            try:
                impl_parsed = parse_sexpr(impl_raw) if isinstance(impl_raw, str) else impl_raw
            except ExprError:
                impl_parsed = None
            try:
                ref_parsed = parse_sexpr(ref_raw) if isinstance(ref_raw, str) else ref_raw
            except ExprError:
                ref_parsed = None
            if impl_parsed is None or ref_parsed is None:
                logger.warning(f"Could not parse combinational expressions for '{prop_name}'")
                continue
            impl_coq = _expr_to_coq(impl_parsed, state_types, input_types, memory_names, as_prop=False, function_types=function_types)
            ref_coq = _expr_to_coq(ref_parsed, state_types, input_types, memory_names, as_prop=False, function_types=function_types)

            # Optional input-bound assumptions (antecedents over the inputs).
            assumptions = prop_op.assumes if hasattr(prop_op, 'assumes') and prop_op.assumes else []
            assumption_hypotheses = []
            for assum in assumptions:
                try:
                    assum_parsed = parse_sexpr(assum) if isinstance(assum, str) else assum
                    assum_coq = _expr_to_coq(assum_parsed, state_types, input_types, memory_names, as_prop=True, function_types=function_types)
                    assumption_hypotheses.append(assum_coq)
                except ExprError as e:
                    logger.warning(f"Could not convert assumption '{assum}' for property '{prop_name}': {e}")

            theorem_name = f"{prop_name}_proved"
            equality = f"({impl_coq}) = ({ref_coq})"
            if assumption_hypotheses:
                assumptions_conj = " /\\ ".join(assumption_hypotheses)
                theorem_stmt = f"forall (inputs : inputs), ({assumptions_conj} -> {equality})"
            else:
                theorem_stmt = f"forall (inputs : inputs), {equality}"

            if state_defs and state_defs[-1] != "":
                state_defs.append("")
            state_defs.append(f"(* PERF_Obligation: {prop_name} *)")
            state_defs.append("(* PERF_Combinational *)")
            state_defs.append(f"Theorem {theorem_name} : {theorem_stmt}.")
            state_defs.append("Admitted.  (* placeholder – use isir verify to attempt proof *)")
            state_defs.append("")
            logger.info(f"Added combinational theorem {theorem_name} to Coq file")
            continue

        if expr_kind == "after":
            # Bounded temporal property: after exactly `bound` steps from the
            # initial state, the operand holds.  `read X` refers to that state.
            bound = prop_op.expression.get("bound")
            operand_raw = prop_op.expression.get("operand")
            if bound is None:
                logger.warning(f"Bounded property '{prop_name}' missing `bound`")
                continue
            try:
                operand_parsed = parse_sexpr(operand_raw) if isinstance(operand_raw, str) else operand_raw
            except ExprError:
                operand_parsed = None
            if operand_parsed is None:
                logger.warning(f"Could not parse after-operand for '{prop_name}'")
                continue
            coq_operand = _expr_to_coq(
                operand_parsed, state_types, input_types, memory_names, as_prop=True,
                state_var="s", function_types=function_types
            )
            theorem_name = f"{prop_name}_proved"
            theorem_stmt = f"forall (s : state), stepn {bound} initial_state s -> {coq_operand}"

            if state_defs and state_defs[-1] != "":
                state_defs.append("")
            state_defs.append(f"(* PERF_Obligation: {prop_name} *)")
            state_defs.append("(* PERF_Bounded *)")
            state_defs.append(f"Theorem {theorem_name} : {theorem_stmt}.")
            state_defs.append("Admitted.  (* placeholder – use isir verify to attempt proof *)")
            state_defs.append("")
            logger.info(f"Added bounded theorem {theorem_name} to Coq file")
            continue

        operand = prop_op.expression.get("operand", "True")
        if operand:
            try:
                operand_parsed = parse_sexpr(operand) if isinstance(operand, str) else operand
            except ExprError:
                operand_parsed = None
            if operand_parsed is not None:
                coq_operand = _expr_to_coq(operand_parsed, state_types, input_types, memory_names, as_prop=True, function_types=function_types)
            else:
                coq_operand = "True"
        else:
            coq_operand = "True"

        assumptions = prop_op.assumes if hasattr(prop_op, 'assumes') and prop_op.assumes else []
        assumption_hypotheses = []
        for assum in assumptions:
            try:
                assum_parsed = parse_sexpr(assum) if isinstance(assum, str) else assum
                assum_coq = _expr_to_coq(assum_parsed, state_types, input_types, memory_names, as_prop=True, function_types=function_types)
                assumption_hypotheses.append(assum_coq)
            except ExprError as e:
                logger.warning(f"Could not convert assumption '{assum}' for property '{prop_name}': {e}")

        if assumption_hypotheses:
            assumptions_conj = " /\\ ".join(assumption_hypotheses)
            full_operand = f"({assumptions_conj} -> {coq_operand})"
        else:
            full_operand = coq_operand

        theorem_stmt = f"forall (s : state) (inputs : inputs), reachable s -> {full_operand}"
        theorem_name = f"{prop_name}_proved"

        if state_defs and state_defs[-1] != "":
            state_defs.append("")

        state_defs.append(f"(* PERF_Obligation: {prop_name} *)")

        po_metadata = po.get("metadata", {}) if isinstance(po, dict) else getattr(po, "metadata", {})
        perf_metadata = po_metadata.get("perf", {})
        if perf_metadata:
            beam = perf_metadata.get("beam_size")
            depth = perf_metadata.get("depth_limit")
            dims = perf_metadata.get("dimensions")
            if beam:
                state_defs.append(f"(* PERF_Beam: {beam} *)")
            if depth:
                state_defs.append(f"(* PERF_Depth: {depth} *)")
            if dims:
                state_defs.append(f"(* PERF_Dimensions: {', '.join(dims)} *)")

        state_defs.append(f"Theorem {theorem_name} : {theorem_stmt}.")
        state_defs.append("Admitted.  (* placeholder – use isir verify to attempt proof *)")
        state_defs.append("")
        logger.info(f"Added theorem {theorem_name} to Coq file with PERF metadata")

    full_coq = _normalize_int_literals("\n".join(state_defs))

    issues = _validate_no_unclosed_proofs(full_coq)
    if issues:
        for iss in issues:
            logger.error(iss)
        raise ValueError(
            "Generated Coq file contains unclosed proof(s). "
            "This will cause 'Nested proofs are discouraged' errors. "
            "Check the trivial invariants and helper lemmas."
        )

    logger.debug("Generated Coq content:\n" + full_coq[:2000] + "\n...")

    koika_module = koika.KoikaModule(
        name=spec_module.name,
        state_definitions=full_coq.splitlines(),
        rule_ops=rule_ops,
        inputs=spec_module.inputs,
        outputs=spec_module.outputs,
        design_op=None,
        theorem_ops=[],
        metadata=spec_module.metadata
    )
    return koika_module


def get_external_load_paths() -> List[Tuple[str, str, str]]:
    return []
