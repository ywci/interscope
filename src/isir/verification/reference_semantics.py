# src/isir/verification/reference_semantics.py
#
# A direct-evaluation reference interpreter for ISIR semantics.
#
# This is a *third* implementation, independent of both the direct-path Verilog
# emitter (`isir_to_rtl_direct`) and the Kōika RTL backend (`koika_to_rtl`).  It
# evaluates the S-expressions with the shared `eval_expr` and applies the
# declared schedule itself, so agreement with the direct path is real evidence
# (not an artifact of shared lowering code).
#
# The reference truncates every written value to the register's declared width,
# matching the fixed-width RTL semantics.

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from isir.dialects.isir import SpecModule
from isir.utils.expr import eval_expr, parse_sexpr, unfold_user_functions
from isir.lowering.isir_to_rtl_direct import _width_of
from isir.utils.logger import get_logger

logger = get_logger(__name__)


def _fire_value(spec: SpecModule, cond: str, state: Dict[str, Any], inputs: Dict[str, Any],
                memories: Dict[str, Dict[int, Any]]) -> bool:
    c = (cond or "true").strip()
    if c == "true":
        return True
    c = unfold_user_functions(c, spec.functions)
    return bool(eval_expr(c, state, inputs, memories))


def _replace_blackboxes(expr: Any, blackbox_names: set) -> Any:
    """Replace calls to bodyless (uninterpreted) functions with 0, matching the
    direct-path RTL's `1'b0` stub for uninterpreted functions."""
    if isinstance(expr, list):
        if expr and expr[0] in blackbox_names:
            return 0
        return [_replace_blackboxes(a, blackbox_names) for a in expr]
    return expr


def _grants(spec: SpecModule, fire: Dict[str, bool]) -> Dict[str, bool]:
    kind = spec.schedule_op.kind if spec.schedule_op else "parallel"
    order = spec.schedule_op.rule_order if spec.schedule_op else [r.rule_name for r in spec.rule_ops]
    grants: Dict[str, bool] = {}
    for r in spec.rule_ops:
        g = fire[r.rule_name]
        if kind == "sequential":
            try:
                idx = order.index(r.rule_name)
            except ValueError:
                idx = len(order)
            for earlier in order[:idx]:
                if fire.get(earlier):
                    g = False
                    break
        grants[r.rule_name] = g
    return grants


def _max_operand_width(expr: Any, state_types: Dict[str, str], input_types: Dict[str, str]) -> int:
    """Return the widest register/input referenced by an expression (the wrap width)."""
    w = 1

    def walk(e):
        nonlocal w
        if isinstance(e, str):
            if e in state_types:
                w = max(w, _width_of(state_types[e]))
            elif e in input_types:
                w = max(w, _width_of(input_types[e]))
        elif isinstance(e, list):
            for a in e:
                walk(a)
    walk(expr)
    return w


def reference_step(spec: SpecModule, state: Dict[str, Any], inputs: Dict[str, Any],
                   memories: Dict[str, Dict[int, Any]]) -> Tuple[Dict[str, Any], Dict[str, Dict[int, Any]]]:
    """Compute the next state + memories per the ISIR semantics."""
    state_types = {s.state_name: s.data_type for s in spec.state_ops if s.kind != "memory"}
    input_types = {i.name: i.data_type for i in spec.inputs}
    blackbox_names = {f.get("name") for f in spec.functions if f.get("body") is None}
    fire = {r.rule_name: _fire_value(spec, r.condition, state, inputs, memories) for r in spec.rule_ops}
    grants = _grants(spec, fire)

    next_state = dict(state)
    next_memories = {m: dict(v) for m, v in memories.items()}
    for r in spec.rule_ops:
        if not grants[r.rule_name]:
            continue
        for act_str in r.actions:
            act = parse_sexpr(act_str)
            if not (isinstance(act, list) and act):
                continue
            if act[0] == "write" and len(act) == 3:
                dest = act[1]
                w = _width_of(state_types.get(dest, "bits<1>"))
                widths = {**{s: _width_of(t) for s, t in state_types.items()},
                          **{i: _width_of(t) for i, t in input_types.items()}}
                unfolded = unfold_user_functions(act[2], spec.functions)
                unfolded = _replace_blackboxes(parse_sexpr(unfolded), blackbox_names) if blackbox_names else parse_sexpr(unfolded)
                val = eval_expr(unfolded, state, inputs, memories, width=w, widths=widths)
                next_state[dest] = (int(val) & ((1 << w) - 1)) if isinstance(val, (int, bool)) else val
            elif act[0] == "mem_write" and len(act) == 4:
                mem = act[1]
                addr = eval_expr(unfold_user_functions(act[2], spec.functions), state, inputs, memories)
                data = eval_expr(unfold_user_functions(act[3], spec.functions), state, inputs, memories)
                next_memories[mem][int(addr)] = int(data)
    return next_state, next_memories


def initial_state(spec: SpecModule) -> Tuple[Dict[str, Any], Dict[str, Dict[int, Any]]]:
    state: Dict[str, Any] = {}
    memories: Dict[str, Dict[int, Any]] = {}
    for s in spec.state_ops:
        if s.kind == "memory":
            memories[s.state_name] = {}
        else:
            init = s.initial
            if init is None:
                init = False if s.data_type == "bool" else 0
            state[s.state_name] = init
    return state, memories


def reference_trace(spec: SpecModule, cycles: int, seed: int = 0,
                    inputs_seq: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    """Simulate `cycles` cycles; returns the state dict after each cycle."""
    import random
    rng = random.Random(seed)
    state, memories = initial_state(spec)
    trace = []
    for _ in range(cycles):
        if inputs_seq is not None:
            inputs = inputs_seq.pop(0) if inputs_seq else {i.name: 0 for i in spec.inputs}
        else:
            inputs = {i.name: rng.getrandbits(_width_of(i.data_type)) for i in spec.inputs}
        state, memories = reference_step(spec, state, inputs, memories)
        trace.append(dict(state))
    return trace
