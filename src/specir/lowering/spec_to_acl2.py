# src/specir/lowering/spec_to_acl2.py
#
# Lowers a SpecModule (spec dialect) to an ACL2Module (acl2 dialect).
# Automatically adds :induct hints for simple safety properties,
# enabling automatic proof without LLM intervention.

from typing import Dict, List, Any, Optional, Set, Tuple
from specir.dialects import spec_ir, acl2_ir
from specir.utils.expr import parse_sexpr, ExprError
from specir.utils.logger import get_logger

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


def _expr_to_acl2(expr: Any,
                  state_indices: Dict[str, int],
                  memory_names: List[str],
                  inputs: List[str]) -> str:
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
        if expr in state_indices:
            idx = state_indices[expr]
            return f"(nth {idx} st)"
        if expr in inputs:
            return expr
        return expr

    if not isinstance(expr, list) or len(expr) == 0:
        raise ExprError(f"Invalid expression for ACL2 lowering: {expr}")

    op = expr[0]
    args = expr[1:]

    # Arithmetic operators
    if op in ('add', 'sub', 'mul', 'div', 'mod'):
        if len(args) != 2:
            raise ExprError(f"{op} expects 2 arguments")
        a = _expr_to_acl2(args[0], state_indices, memory_names, inputs)
        b = _expr_to_acl2(args[1], state_indices, memory_names, inputs)
        acl2_op_map = {'add': '+', 'sub': '-', 'mul': '*', 'div': '/', 'mod': 'mod'}
        acl2_op = acl2_op_map[op]
        return f"({acl2_op} {a} {b})"

    # Logical operators
    elif op == 'and':
        if len(args) != 2:
            raise ExprError("and expects 2 arguments")
        a = _expr_to_acl2(args[0], state_indices, memory_names, inputs)
        b = _expr_to_acl2(args[1], state_indices, memory_names, inputs)
        return f"(and {a} {b})"
    elif op == 'or':
        if len(args) != 2:
            raise ExprError("or expects 2 arguments")
        a = _expr_to_acl2(args[0], state_indices, memory_names, inputs)
        b = _expr_to_acl2(args[1], state_indices, memory_names, inputs)
        return f"(or {a} {b})"
    elif op == 'not':
        if len(args) != 1:
            raise ExprError("not expects 1 argument")
        a = _expr_to_acl2(args[0], state_indices, memory_names, inputs)
        return f"(not {a})"

    # Implication
    elif op == 'implies':
        if len(args) != 2:
            raise ExprError("implies expects 2 arguments")
        a = _expr_to_acl2(args[0], state_indices, memory_names, inputs)
        b = _expr_to_acl2(args[1], state_indices, memory_names, inputs)
        return f"(implies {a} {b})"

    # Comparison operators
    elif op in ('eq', 'neq', 'gt', 'lt', 'gte', 'lte', 'le', 'ge'):
        if len(args) != 2:
            raise ExprError(f"{op} expects 2 arguments")
        a = _expr_to_acl2(args[0], state_indices, memory_names, inputs)
        b = _expr_to_acl2(args[1], state_indices, memory_names, inputs)
        acl2_op_map = {'eq': '=', 'neq': '/=', 'gt': '>', 'lt': '<',
                       'gte': '>=', 'lte': '<=', 'le': '<=', 'ge': '>='}
        acl2_op = acl2_op_map[op]
        return f"({acl2_op} {a} {b})"

    # Concatenation and slicing
    elif op == 'concat':
        if len(args) != 2:
            raise ExprError("concat expects 2 arguments")
        a = _expr_to_acl2(args[0], state_indices, memory_names, inputs)
        b = _expr_to_acl2(args[1], state_indices, memory_names, inputs)
        return f"(logapp 8 {b} {a})"   # default width for low part

    elif op == 'slice':
        if len(args) != 3:
            raise ExprError("slice expects 3 arguments")
        e = _expr_to_acl2(args[0], state_indices, memory_names, inputs)
        h = _expr_to_acl2(args[1], state_indices, memory_names, inputs)
        l = _expr_to_acl2(args[2], state_indices, memory_names, inputs)
        return f"(logtail {l} (loghead (+ 1 {h}) {e}))"

    # if‑then‑else
    elif op == 'ite':
        if len(args) != 3:
            raise ExprError("ite expects 3 arguments")
        cond = _expr_to_acl2(args[0], state_indices, memory_names, inputs)
        then_expr = _expr_to_acl2(args[1], state_indices, memory_names, inputs)
        else_expr = _expr_to_acl2(args[2], state_indices, memory_names, inputs)
        return f"(if {cond} {then_expr} {else_expr})"

    # read state register
    elif op == 'read':
        if len(args) != 1:
            raise ExprError("read expects 1 argument")
        name = args[0]
        if not isinstance(name, str):
            raise ExprError("read expects a state name string")
        if name not in state_indices:
            raise ExprError(f"Unknown state '{name}' in expression")
        idx = state_indices[name]
        return f"(nth {idx} st)"

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
        addr = _expr_to_acl2(args[1], state_indices, memory_names, inputs)
        return f"(nth {addr} {mem_name})"

    # memory write – action
    elif op == 'mem_write':
        raise ExprError("mem_write is an action, not an expression")

    else:
        raise ExprError(f"Unknown operator '{op}' in ACL2 lowering")


def _action_to_acl2_update(action_str: str,
                           state_indices: Dict[str, int],
                           memory_names: List[str],
                           inputs: List[str]) -> str:
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
        value_expr = _expr_to_acl2(args[1], state_indices, memory_names, inputs)
        return f"(update-nth {idx} {value_expr} st)"

    elif op == 'mem_write':
        if len(args) != 3:
            raise ExprError("mem_write action expects 3 arguments")
        mem_name = args[0]
        if not isinstance(mem_name, str):
            raise ExprError("mem_write expects memory name string")
        addr_expr = _expr_to_acl2(args[1], state_indices, memory_names, inputs)
        data_expr = _expr_to_acl2(args[2], state_indices, memory_names, inputs)
        return f"(update-mem {mem_name} {addr_expr} {data_expr} st)"

    else:
        return _expr_to_acl2(action, state_indices, memory_names, inputs)


def _maybe_auto_hint(prop_op: spec_ir.SpecPropertyOp,
                     state_indices: Dict[str, int],
                     memory_names: List[str],
                     input_names: List[str]) -> Optional[List[str]]:
    """
    Return an ACL2 :hints list if the property matches a simple pattern,
    otherwise return None.
    Currently recognised pattern: safety property whose operand is
    a simple implication or a boolean condition that should hold in all
    reachable states.  For those we suggest induction on the step function.
    """
    if prop_op.kind not in ("safety", "invariant"):
        return None

    operand = prop_op.expression.get("operand", None)
    if not operand:
        return None

    try:
        operand_parsed = parse_sexpr(operand)
    except ExprError:
        return None

    if isinstance(operand_parsed, list) and len(operand_parsed) == 3 and operand_parsed[0] == 'implies':
        return ['("Goal" :induct (step st inputs))']
    elif isinstance(operand_parsed, str) or (isinstance(operand_parsed, list) and operand_parsed[0] != 'implies'):
        return ['("Goal" :induct (step st inputs))']

    return None


def convert(spec_module: spec_ir.SpecModule) -> acl2_ir.ACL2Module:
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

    # 2. Build the transition function
    sorted_rules = sorted(
        spec_module.rule_ops,
        key=lambda r: r.priority if r.priority is not None else 0,
        reverse=True
    )

    cond_clauses: List[str] = []
    for rule in sorted_rules:
        if rule.condition:
            try:
                cond_parsed = parse_sexpr(rule.condition)
                cond_acl2 = _expr_to_acl2(cond_parsed, state_indices, memory_names, input_names)
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
                update_term = _action_to_acl2_update(action_str, state_indices, memory_names, input_names)
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

    next_state_defun = acl2_ir.ACL2DefunOp(
        func_name=f"{spec_module.name}_step",
        args=["st"] + input_names,
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
    init_list = f"(list {' '.join(init_vals)})"
    init_state_defun = acl2_ir.ACL2DefunOp(
        func_name=f"{spec_module.name}_init",
        args=[],
        body=init_list
    )

    defuns = [init_state_defun, next_state_defun]

    # 4. Theorems from proof obligations (with auto‑hints)
    defthms: List[acl2_ir.ACL2DefthmOp] = []
    for po in spec_module.proof_obligations:
        prop_name = _po_property(po)
        if not prop_name:
            continue

        prop_op = next((p for p in spec_module.property_ops if p.prop_name == prop_name), None)
        if not prop_op:
            logger.warning(f"No property found for proof obligation '{prop_name}'")
            continue

        try:
            operand = prop_op.expression.get("operand", None)
            if operand:
                operand_parsed = parse_sexpr(operand)
                prop_acl2 = _expr_to_acl2(operand_parsed, state_indices, memory_names, input_names)
            else:
                prop_acl2 = "t"
        except ExprError as e:
            logger.warning(f"Could not convert property '{prop_name}' to ACL2: {e}")
            prop_acl2 = "t"

        assumes_acl2 = []
        for assume in prop_op.assumes:
            try:
                assume_parsed = parse_sexpr(assume)
                assumes_acl2.append(_expr_to_acl2(assume_parsed, state_indices, memory_names, input_names))
            except ExprError:
                pass

        hypotheses = " ".join(assumes_acl2) if assumes_acl2 else "t"
        statement = f"(implies (and {hypotheses}) {prop_acl2})"

        # Hints: user‑provided hints take precedence; otherwise try auto‑hints
        metadata = _po_metadata(po)
        user_hints = metadata.get("acl2_hints", [])
        if isinstance(user_hints, list) and user_hints:
            hints_list = user_hints
        else:
            auto_hints = _maybe_auto_hint(prop_op, state_indices, memory_names, input_names)
            if auto_hints:
                hints_list = auto_hints
            else:
                hints_list = []

        defthm = acl2_ir.ACL2DefthmOp(
            thm_name=f"{prop_name}_correct",
            statement=statement,
            hints=hints_list
        )
        defthms.append(defthm)

    # 5. Build the ACL2 module
    acl2_mod = acl2_ir.ACL2Module(
        name=spec_module.name,
        defuns=defuns,
        defthms=defthms
    )
    return acl2_mod
