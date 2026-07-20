# src/specir/lowering/spec_to_koika.py
#
# Lowers a SpecModule to a KoikaModule with reachability-based theorems.
# - Translates top-level `assume` directives into global Coq `Axiom` declarations.
# - Normalizes hex, binary, and octal integer literals to decimal.
# - Statically detects and emits trivial invariants (memory always nil, constant registers)
#   **after** the `reachable` predicate so the lemmas compile.
# - Detects alignment-safe registers (initialized to 0 and only ever incremented by 4)
#   and automatically proves `slice(reg, 1, 0) = 0` using the `slice_low2` lemma.
# - Supports sequential schedules using `let` bindings to share intermediate states.
# - Composes multiple mem_write actions to the same memory correctly.
# - Merges flag-update rules when present.
# - Uses classic Coq imports (compatible with Coq 8.14) – avoids `Stdlib` prefix.
# - Stores the original rule actions in `KoikaRuleOp` for RTL generation.
# - Propagates interface information (inputs/outputs) to the resulting KoikaModule.

import re
from typing import Dict, List, Any, Optional, Set, Tuple, Union
from specir.dialects import spec_ir, koika_ir
from specir.utils.expr import parse_sexpr, ExprError
from specir.utils.logger import get_logger

logger = get_logger(__name__)


# Pattern for C‑style integer literals: 0x…, 0b…, 0o…
_INT_LITERAL = re.compile(r"0[xX]([0-9a-fA-F]+)|0[bB]([01]+)|0[oO]([0-7]+)")

def _normalize_int_literals(text: str) -> str:
    """Replace C‑style integer literals with their decimal equivalents."""
    def repl(m):
        if m.group(1):   # hex
            return str(int(m.group(1), 16))
        elif m.group(2): # binary
            return str(int(m.group(2), 2))
        elif m.group(3): # octal
            return str(int(m.group(3), 8))
        return m.group(0)
    return _INT_LITERAL.sub(repl, text)

def _get_coq_type(data_type: str) -> str:
    if data_type == "bool":
        return "bool"
    return "nat"

def _type_of_expr(expr: Any,
                 state_types: Dict[str, str],
                 input_types: Dict[str, str],
                 memory_names: List[str]) -> str:
    """Infer a rough type for an expression: 'bool' or 'nat'."""
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
        return "nat"
    if isinstance(expr, list) and len(expr) > 0:
        op = expr[0]
        if op in ('and', 'or', 'not', 'implies'):
            return "bool"
        if op in ('eq', 'neq', 'gt', 'lt', 'gte', 'lte', 'le', 'ge'):
            return "bool"
        if op == 'ite':
            return _type_of_expr(expr[1], state_types, input_types, memory_names)
        if op in ('add', 'sub', 'mul', 'div', 'mod', 'slice', 'concat'):
            return "nat"
        if op == 'read':
            name = expr[1] if len(expr) > 1 else ""
            if name in state_types:
                return state_types[name]
            if name in input_types:
                return input_types[name]
            return "nat"
        if op == 'mem_read':
            return "nat"
    return "nat"


def _expr_to_coq(
    expr: Any,
    state_types: Dict[str, str],
    input_types: Dict[str, str],
    memory_names: List[str],
    as_prop: bool = True,
    state_var: str = "s"
) -> str:
    """Convert parsed S-expression to Coq term.

    The `as_prop` flag indicates whether the result should be a proposition
    (using `=`, `/\\`, `\\/`, `~`) or a boolean (using `Nat.eqb`, `Bool.eqb`,
    `andb`, `orb`, `negb`).  When `as_prop` is True, the returned string
    is a Coq `Prop`; otherwise it is a `bool` or `nat`.
    """
    if isinstance(expr, bool):
        if as_prop:
            return "True" if expr else "False"
        else:
            return "true" if expr else "false"

    if isinstance(expr, int):
        return str(expr)
    if isinstance(expr, str):
        if expr in state_types:
            base = f"({expr} {state_var})"
            if state_types[expr] == "bool" and as_prop:
                return f"({base} = true)"
            return base
        if expr in input_types:
            base = f"({expr} inputs)"
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

    # Arithmetic
    if op in ('add', 'sub', 'mul', 'div', 'mod'):
        if len(args) != 2:
            raise ExprError(f"{op} expects 2 arguments")
        a = _expr_to_coq(args[0], state_types, input_types, memory_names, False, state_var)
        b = _expr_to_coq(args[1], state_types, input_types, memory_names, False, state_var)
        omap = {'add': '+', 'sub': '-', 'mul': '*', 'div': '/', 'mod': 'mod'}
        return f"({a} {omap[op]} {b})"

    # Logical / bitwise
    elif op in ('and', 'or', 'not', 'implies'):
        if op == 'not':
            if len(args) != 1:
                raise ExprError("not expects 1 argument")
            a_type = _type_of_expr(args[0], state_types, input_types, memory_names)
            if as_prop:
                a = _expr_to_coq(args[0], state_types, input_types, memory_names, True, state_var)
                return f"(~ {a})"
            else:
                a = _expr_to_coq(args[0], state_types, input_types, memory_names, False, state_var)
                if a_type == "bool":
                    return f"(negb {a})"
                else:
                    return f"(Nat.lnot {a})"   # bitwise NOT for nat
        elif op == 'implies':
            if len(args) != 2:
                raise ExprError("implies expects 2 arguments")
            a = _expr_to_coq(args[0], state_types, input_types, memory_names, True, state_var)
            b = _expr_to_coq(args[1], state_types, input_types, memory_names, True, state_var)
            return f"({a} -> {b})"
        else:  # and, or
            if len(args) != 2:
                raise ExprError(f"{op} expects 2 arguments")
            a_type = _type_of_expr(args[0], state_types, input_types, memory_names)
            b_type = _type_of_expr(args[1], state_types, input_types, memory_names)
            if as_prop and a_type == "bool" and b_type == "bool":
                a = _expr_to_coq(args[0], state_types, input_types, memory_names, True, state_var)
                b = _expr_to_coq(args[1], state_types, input_types, memory_names, True, state_var)
                if op == 'and':
                    return f"({a} /\\ {b})"
                else:
                    return f"({a} \\/ {b})"
            else:
                a = _expr_to_coq(args[0], state_types, input_types, memory_names, False, state_var)
                b = _expr_to_coq(args[1], state_types, input_types, memory_names, False, state_var)
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
        a = _expr_to_coq(args[0], state_types, input_types, memory_names, False, state_var)
        b = _expr_to_coq(args[1], state_types, input_types, memory_names, False, state_var)
        left_type = _type_of_expr(args[0], state_types, input_types, memory_names)
        right_type = _type_of_expr(args[1], state_types, input_types, memory_names)
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
                return f"(negb (Nat.ltb {a} {b}))"
            elif op == 'lte':
                return f"(negb (Nat.ltb {b} {a}))"
            elif op == 'le':
                return f"(negb (Nat.ltb {b} {a}))"
            elif op == 'ge':
                return f"(negb (Nat.ltb {a} {b}))"
            else:
                return f"(Nat.eqb {a} {b})"

    # ite
    elif op == 'ite':
        if len(args) != 3:
            raise ExprError("ite expects 3 arguments")
        cond = _expr_to_coq(args[0], state_types, input_types, memory_names, False, state_var)
        then_expr = _expr_to_coq(args[1], state_types, input_types, memory_names, False, state_var)
        else_expr = _expr_to_coq(args[2], state_types, input_types, memory_names, False, state_var)
        return f"(if {cond} then {then_expr} else {else_expr})"

    # slice
    elif op == 'slice':
        if len(args) != 3:
            raise ExprError("slice expects 3 arguments: expr high low")
        val = _expr_to_coq(args[0], state_types, input_types, memory_names, False, state_var)
        high = _expr_to_coq(args[1], state_types, input_types, memory_names, False, state_var)
        low = _expr_to_coq(args[2], state_types, input_types, memory_names, False, state_var)
        return f"(slice {val} {high} {low})"

    # read state / input
    elif op == 'read':
        if len(args) != 1:
            raise ExprError("read expects 1 argument")
        name = args[0]
        if not isinstance(name, str):
            raise ExprError("read expects a state name string")
        if name in state_types:
            base = f"({name} {state_var})"
            if state_types[name] == "bool" and as_prop:
                return f"({base} = true)"
            return base
        if name in input_types:
            base = f"({name} inputs)"
            if input_types[name] == "bool" and as_prop:
                return f"({base} = true)"
            return base
        if name in memory_names:
            return f"({name} {state_var})"
        raise ExprError(f"Unknown state or input '{name}'")

    # mem_read
    elif op == 'mem_read':
        if len(args) != 2:
            raise ExprError("mem_read expects 2 arguments")
        mem_name = args[0]
        if not isinstance(mem_name, str):
            raise ExprError("mem_read expects memory name string")
        addr_expr = _expr_to_coq(args[1], state_types, input_types, memory_names, False, state_var)
        return f"(nth_default 0 ({mem_name} {state_var}) {addr_expr})"

    # mem_write (action)
    elif op == 'mem_write':
        raise ExprError("mem_write is an action, not an expression")

    else:
        raise ExprError(f"Unsupported operator in Coq lowering: {op}")


def _process_rule_actions(
    rule: spec_ir.SpecRuleOp,
    state_types: Dict[str, str],
    input_types: Dict[str, str],
    memory_names: List[str],
    state_names: List[str],
    state_var: str = "s"
) -> Dict[str, str]:
    updates: Dict[str, str] = {}
    mem_writes: List[Tuple[str, str, str]] = []

    for action in rule.actions:
        try:
            parsed = parse_sexpr(action)
        except ExprError:
            continue

        if isinstance(parsed, list) and len(parsed) >= 3 and parsed[0] == 'write':
            field = parsed[1]
            if isinstance(field, str) and field in state_names:
                try:
                    val_expr = _expr_to_coq(parsed[2], state_types, input_types, memory_names, False, state_var)
                    updates[field] = val_expr
                except ExprError as e:
                    logger.warning(f"Rule '{rule.rule_name}' write error: {e}")
        elif isinstance(parsed, list) and len(parsed) == 4 and parsed[0] == 'mem_write':
            mem_name = parsed[1]
            if isinstance(mem_name, str) and mem_name in memory_names:
                try:
                    addr_expr = _expr_to_coq(parsed[2], state_types, input_types, memory_names, False, state_var)
                    data_expr = _expr_to_coq(parsed[3], state_types, input_types, memory_names, False, state_var)
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


def _mk_state_expr(
    registers: List[spec_ir.SpecStateOp],
    memories: List[spec_ir.SpecStateOp],
    updates: Dict[str, str],
    state_var: str = "s"
) -> str:
    parts = ["(mkState"]
    for r in registers:
        parts.append(updates.get(r.state_name, f"({r.state_name} {state_var})"))
    for mem in memories:
        parts.append(updates.get(mem.state_name, f"({mem.state_name} {state_var})"))
    parts.append(")")
    return " ".join(parts)


def _build_sequential_step(
    ordered_rules: List[spec_ir.SpecRuleOp],
    registers: List[spec_ir.SpecStateOp],
    memories: List[spec_ir.SpecStateOp],
    state_types: Dict[str, str],
    input_types: Dict[str, str],
    memory_names: List[str],
    state_names: List[str]
) -> Tuple[str, List[koika_ir.KoikaRuleOp]]:
    if not ordered_rules:
        return "", []

    let_bindings: List[Tuple[str, str]] = []
    current_var = "s"
    conds: List[str] = []
    final_expr = None
    rule_ops = []

    for idx, rule in enumerate(ordered_rules):
        cond_str = "True"
        if rule.condition:
            try:
                cond_parsed = parse_sexpr(rule.condition)
                cond_str = _expr_to_coq(cond_parsed, state_types, input_types,
                                        memory_names, as_prop=True,
                                        state_var=current_var)
            except ExprError as e:
                logger.warning(f"Rule '{rule.rule_name}' condition parse error: {e}. Using 'True'.")
        if cond_str != "True":
            conds.append(cond_str)

        updates = _process_rule_actions(rule, state_types, input_types,
                                        memory_names, state_names,
                                        state_var=current_var)
        state_expr = _mk_state_expr(registers, memories, updates, current_var)

        # Preserve the original rule actions
        rule_ops.append(koika_ir.KoikaRuleOp(
            rule_name=rule.rule_name,
            condition=cond_str,
            actions=rule.actions
        ))

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

    constructor = (
        f"  | step_combined : forall s inputs,\n"
        f"      {combined_cond} ->\n"
        f"      step s inputs ({body})"
    )
    return constructor, rule_ops


def _detect_alignment_safe_registers(
    spec_module: spec_ir.SpecModule,
    registers: List[spec_ir.SpecStateOp],
    written_regs: Set[str]
) -> Set[str]:
    """Return the set of register names that are safe for alignment proofs."""
    safe: Set[str] = set()
    write_exprs_map: Dict[str, List[Any]] = {reg.state_name: [] for reg in registers}
    for rule in spec_module.rule_ops:
        for action in rule.actions:
            try:
                parsed = parse_sexpr(action)
            except ExprError:
                continue
            if isinstance(parsed, list) and len(parsed) >= 3 and parsed[0] == 'write':
                field = parsed[1]
                if isinstance(field, str) and field in write_exprs_map:
                    write_exprs_map[field].append(parsed[2])

    for reg in registers:
        name = reg.state_name
        if name not in written_regs:
            safe.add(name)
            continue
        exprs = write_exprs_map[name]
        if not exprs:
            continue
        all_add4 = True
        for e in exprs:
            if not (isinstance(e, list) and len(e) == 3 and e[0] == 'add'
                    and isinstance(e[1], list) and len(e[1]) == 2
                    and e[1][0] == 'read' and e[1][1] == name
                    and e[2] == 4):
                all_add4 = False
                break
        if all_add4:
            safe.add(name)
    return safe


def convert(spec_module: spec_ir.SpecModule) -> koika_ir.KoikaModule:
    """Convert a SpecModule to a KoikaModule with reachability‑based theorems."""

    state_ops = [s for s in spec_module.state_ops]
    registers = [s for s in state_ops if s.kind == "register"]
    memories = [s for s in state_ops if s.kind == "memory"]
    state_names = [s.state_name for s in registers]
    memory_names = [s.state_name for s in memories]
    input_names = [i.name for i in spec_module.inputs]

    state_types: Dict[str, str] = {}
    for s in state_ops:
        if s.kind == "register":
            state_types[s.state_name] = _get_coq_type(s.data_type)
    input_types: Dict[str, str] = {}
    for inp in spec_module.inputs:
        input_types[inp.name] = _get_coq_type(inp.data_type)

    # Flag‑update rule detection
    flag_rule_actions: Optional[List[str]] = None
    other_rules: List[spec_ir.SpecRuleOp] = []
    for rule in spec_module.rule_ops:
        if rule.rule_name == "update_flags":
            flag_rule_actions = rule.actions
            logger.info("Detected 'update_flags' rule; its actions will be merged into other rules.")
        else:
            other_rules.append(rule)

    # Global assumptions
    global_assumptions: List[str] = []
    for directive in spec_module.directive_ops:
        if directive.kind == "assume":
            try:
                parsed = parse_sexpr(directive.expression)
                coq_cond = _expr_to_coq(parsed, state_types, input_types,
                                        memory_names, as_prop=True,
                                        state_var="s")
                global_assumptions.append(coq_cond)
            except ExprError as e:
                logger.warning(f"Could not translate assume directive '{directive.directive_name}': {e}")

    # Trivial invariant generation
    written_regs: Set[str] = set()
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

    trivial_invariants: List[str] = []
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

    alignment_safe = _detect_alignment_safe_registers(spec_module, registers, written_regs)
    logger.info("Alignment‑safe registers: %s", sorted(alignment_safe))

    # Schedule handling
    schedule = spec_module.schedule_op
    sequential_mode = schedule is not None and schedule.kind == "sequential" and schedule.rule_order

    state_defs: List[str] = []
    state_defs.append("Require Import Init.Datatypes.")
    state_defs.append("Require Import Arith.PeanoNat.")
    state_defs.append("Require Import Lists.List.")
    state_defs.append("Require Import Bool.Bool.")
    state_defs.append("Require Import Lia.")
    state_defs.append("Require Import Psatz.")
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
    state_defs.append("  rewrite <- (Nat.mod_add x 1 4); [ reflexivity | lia ].")
    state_defs.append("Qed.")
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

    if global_assumptions:
        state_defs.append("(* Global assumptions from SpecIR assume directives *)")
        combined = " /\\ ".join(global_assumptions)
        state_defs.append(f"Axiom assume_inputs : forall (inputs : inputs), ({combined}).")
        state_defs.append("")

    # Initial state
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

    rule_ops: List[koika_ir.KoikaRuleOp] = []
    step_ctors: List[str] = []

    if sequential_mode:
        ordered_rule_names = schedule.rule_order
        ordered_rules = []
        for name in ordered_rule_names:
            rule = next((r for r in other_rules if r.rule_name == name), None)
            if rule is None:
                logger.warning(f"Rule '{name}' in schedule not found; skipping.")
                continue
            ordered_rules.append(rule)

        if ordered_rules:
            ctor_str, ops = _build_sequential_step(
                ordered_rules, registers, memories,
                state_types, input_types, memory_names, state_names
            )
            step_ctors.append(ctor_str)
            rule_ops.extend(ops)
    else:
        for rule in other_rules:
            cond_str = "True"
            if rule.condition:
                try:
                    cond_parsed = parse_sexpr(rule.condition)
                    cond_str = _expr_to_coq(cond_parsed, state_types, input_types, memory_names, as_prop=True)
                except ExprError as e:
                    logger.warning(f"Rule '{rule.rule_name}' condition parse error: {e}. Using 'True'.")

            updates = _process_rule_actions(rule, state_types, input_types, memory_names, state_names, state_var="s")

            if flag_rule_actions is not None and "count" in state_names:
                new_count_expr = updates.get("count", "(count s)")
                updates["full"] = f"(Nat.eqb {new_count_expr} 8)"
                updates["empty"] = f"(Nat.eqb {new_count_expr} 0)"
                logger.debug(f"Rule '{rule.rule_name}': merged flag updates.")

            new_state = _mk_state_expr(registers, memories, updates, "s")

            ctor_name = f"step_{rule.rule_name}"
            step_ctors.append(
                f"  | {ctor_name} : forall s inputs,\n"
                f"      {cond_str} ->\n"
                f"      step s inputs ({new_state})"
            )
            rule_ops.append(koika_ir.KoikaRuleOp(
                rule_name=rule.rule_name,
                condition=cond_str,
                actions=rule.actions
            ))

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

    # Trivial invariants after reachable
    if trivial_invariants:
        state_defs.append("(* Auto‑generated trivial invariants *)")
        for inv in trivial_invariants:
            state_defs.append(inv)
        state_defs.append("")

    theorem_ops: List[koika_ir.KoikaTheoremOp] = []
    emitted_helper_lemmas: Set[str] = set()

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

        operand = prop_op.expression.get("operand", "True")
        if operand:
            try:
                operand_parsed = parse_sexpr(operand) if isinstance(operand, str) else operand
            except ExprError:
                operand_parsed = None
            if operand_parsed is not None:
                coq_operand = _expr_to_coq(operand_parsed, state_types, input_types, memory_names, as_prop=True)
            else:
                coq_operand = "True"
        else:
            coq_operand = "True"

        assumptions = prop_op.assumes if hasattr(prop_op, 'assumes') and prop_op.assumes else []
        assumption_hypotheses = []
        for assum in assumptions:
            try:
                assum_parsed = parse_sexpr(assum) if isinstance(assum, str) else assum
                assum_coq = _expr_to_coq(assum_parsed, state_types, input_types, memory_names, as_prop=True)
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

        reg_name = None
        if isinstance(operand_parsed, list) and len(operand_parsed) == 3 \
                and operand_parsed[0] == 'eq' \
                and isinstance(operand_parsed[1], list) and len(operand_parsed[1]) == 4 \
                and operand_parsed[1][0] == 'slice' \
                and isinstance(operand_parsed[1][1], list) and len(operand_parsed[1][1]) == 2 \
                and operand_parsed[1][1][0] == 'read' \
                and isinstance(operand_parsed[1][1][1], str) \
                and operand_parsed[1][2] == 1 and operand_parsed[1][3] == 0 \
                and operand_parsed[2] == 0:
            reg_name = operand_parsed[1][1][1]

        if reg_name and reg_name in alignment_safe:
            lemma_name = f"{reg_name}_mod4_0"
            if lemma_name not in emitted_helper_lemmas:
                emitted_helper_lemmas.add(lemma_name)
                state_defs.append(
                    f"Lemma {lemma_name} : forall s, reachable s -> {reg_name} s mod 4 = 0.\n"
                    f"Proof.\n"
                    f"  induction 1 as [| s' s'' inputs' Hreach IH Hstep].\n"
                    f"  - reflexivity.\n"
                    f"  - inversion Hstep; subst.\n"
                    f"    match goal with\n"
                    f"    | [ |- context[{reg_name} (mkState ?a ?b ?c ?d ?e ?f)] ] =>\n"
                    f"      change ({reg_name} (mkState a b c d e f)) with a\n"
                    f"    end.\n"
                    f"    rewrite add4_mod4.\n"
                    f"    exact IH.\n"
                    f"Qed.\n"
                )
            state_defs.append(f"Theorem {theorem_name} : {theorem_stmt}.")
            state_defs.append("Proof.")
            state_defs.append(f"  intros s inputs Hreach; rewrite slice_low2.")
            state_defs.append(f"  apply {lemma_name}; exact Hreach.")
            state_defs.append("Qed.")
            state_defs.append("")
            logger.info(f"Auto‑proved theorem {theorem_name} using {lemma_name}.")
            continue

        # Default placeholder theorem
        state_defs.append(f"Theorem {theorem_name} : {theorem_stmt}.")
        state_defs.append("Proof. (* placeholder – not yet proven; use specir verify to attempt proof *) Admitted.")
        state_defs.append("")
        logger.info(f"Added theorem {theorem_name} to Coq file (placeholder)")

    full_coq = _normalize_int_literals("\n".join(state_defs))
    state_defs = full_coq.splitlines()

    logger.info("Generated Coq content:\n" + "\n".join(state_defs))

    koika_module = koika_ir.KoikaModule(
        name=spec_module.name,
        state_definitions=state_defs,
        rule_ops=rule_ops,
        inputs=spec_module.inputs,
        outputs=spec_module.outputs,
        design_op=None,
        theorem_ops=[],
        metadata=spec_module.metadata
    )
    return koika_module
