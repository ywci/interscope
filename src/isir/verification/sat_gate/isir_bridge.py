# src/isir/verification/sat_gate/isir_bridge.py
#
# Thin ISIR -> SAT-gating bridge: extract signal widths, the combined
# next-state transition, and the `always` invariant operand from a parsed
# SpecModule.  No solver/encoder imports beyond the backend-agnostic core.
"""ISIR frontend: SpecModule -> widths / transitions / invariants."""

import re
from typing import Dict, List, Optional, Tuple


def _extract_width(data_type: str) -> Optional[int]:
    if data_type == "bool":
        return 1
    if isinstance(data_type, str) and data_type.startswith("bits<"):
        try:
            return int(data_type[5:-1])
        except ValueError:
            return None
    return None


def widths_of(spec_module) -> Dict[str, int]:
    """Return signal name -> bit width for state + inputs + resets."""
    widths: Dict[str, int] = {}
    for s in getattr(spec_module, "state_ops", []) or []:
        w = _extract_width(getattr(s, "data_type", "") or "")
        if w is not None:
            widths[getattr(s, "state_name", "")] = w
    for i in getattr(spec_module, "inputs", []) or []:
        w = _extract_width(getattr(i, "data_type", "") or "")
        if w is not None:
            widths[getattr(i, "name", "")] = w
    for r in getattr(spec_module, "resets", []) or []:
        name = r.get("name") if isinstance(r, dict) else getattr(r, "name", None)
        if name:
            widths[name] = 1  # reset signals are 1-bit
    return widths


def transitions_of(spec_module) -> Dict[str, str]:
    """Return register -> combined next-state S-expression.

    Multiple rules writing the same register are merged into a nested
    ``(ite cond expr (ite … (read reg)))``, first rule wins.
    """
    writes: Dict[str, List[Tuple[str, str]]] = {}
    for rule in getattr(spec_module, "rule_ops", []) or []:
        cond = getattr(rule, "condition", None) or "true"
        for action in getattr(rule, "actions", []) or []:
            m = re.match(r"\(write\s+(\w+)\s+(.+)\)\s*$", action.strip())
            if m:
                reg, expr = m.group(1), m.group(2).strip()
                writes.setdefault(reg, []).append((cond, expr))

    transitions: Dict[str, str] = {}
    for reg, entries in writes.items():
        expr = f"(read {reg})"
        for cond, e in reversed(entries):
            expr = f"(ite {cond} {e} {expr})"
        transitions[reg] = expr
    return transitions


def always_operand(spec_module, prop_name: str) -> Optional[str]:
    """Return the operand S-expression of an `always` property by name."""
    for p in getattr(spec_module, "property_ops", []) or []:
        expr = getattr(p, "expression", None) or {}
        pn = getattr(p, "prop_name", None) or getattr(p, "name", None)
        if pn == prop_name and expr.get("kind") == "always":
            return expr.get("operand")
    return None


def initial_values(spec_module) -> Dict[str, int]:
    """Return register -> initial value."""
    init: Dict[str, int] = {}
    for s in getattr(spec_module, "state_ops", []) or []:
        if getattr(s, "kind", "") == "register":
            init[getattr(s, "state_name", "")] = int(getattr(s, "initial", 0) or 0)
    return init


def memories_of(spec_module) -> Dict[str, "tuple[int, int]"]:
    """Return memory name -> (elem_width, addr_width)."""
    import math
    mems: Dict[str, "tuple[int, int]"] = {}
    for s in getattr(spec_module, "state_ops", []) or []:
        if getattr(s, "kind", "") != "memory":
            continue
        dt = getattr(s, "data_type", "") or ""
        m = re.match(r"memory\(bits<(\d+)>,\s*(\d+)\)", dt)
        if m:
            elem_w = int(m.group(1))
            depth = int(m.group(2))
            addr_w = max(1, (depth - 1).bit_length())
            mems[getattr(s, "state_name", "")] = (elem_w, addr_w)
    return mems


def memory_transitions_of(spec_module) -> Dict[str, str]:
    """Return memory name -> combined next-state S-expression over SMT arrays.

    The ``(mem_write mem idx val)`` actions become nested
    ``(ite cond (store mem idx val) …)`` chains, first rule wins.
    """
    writes: Dict[str, List[Tuple[str, str, str, str]]] = {}
    for rule in getattr(spec_module, "rule_ops", []) or []:
        cond = getattr(rule, "condition", None) or "true"
        for action in getattr(rule, "actions", []) or []:
            m = re.match(r"\(mem_write\s+(\w+)\s+(.+?)\s+(.+)\)\s*$", action.strip())
            if m:
                mem, idx, val = m.group(1), m.group(2), m.group(3)
                writes.setdefault(mem, []).append((cond, idx, val, mem))

    out: Dict[str, str] = {}
    for mem, entries in writes.items():
        expr = f"(read {mem})"
        for cond, idx, val, _ in reversed(entries):
            expr = f"(ite {cond} (mem_write {mem} {idx} {val}) {expr})"
        out[mem] = expr
    return out
