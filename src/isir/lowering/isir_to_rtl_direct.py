# src/isir/lowering/isir_to_rtl_direct.py
#
# Independent ISIR → RTL lowering path.
#
# This path emits synthesizable Verilog directly from the Spec dialect, WITHOUT
# invoking the Kōika lowering (`isir_to_koika.py`).  It is a *differential*
# and *replay* reference, not a golden model: the trusted reference RTL remains
# the long path (ISIR → Kōika → RTL).
#
# Independence requirements (see the development plan):
#   * Shared, syntactic only: `parse_isir`, `convert_ast_to_isir_module`,
#     `parse_sexpr` (S-expression tokenization — no desugaring, no coercion).
#   * Independent here: expression lowering, scheduling derivation, state
#     encoding, and Verilog emission.  We do NOT reuse `isir_to_koika.py`'s
#     `_type_of_expr` / `_expr_to_coq` / `_build_sequential_step`.

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from isir.dialects.isir import SpecModule
from isir.utils.expr import ExprError, parse_sexpr
from isir.utils.logger import get_logger

logger = get_logger(__name__)

# Width policy for the unparameterised `int` type (documented; the long path
# maps it to unbounded `nat`, so a fixed width is required for synthesis).
INT_WIDTH = 32

_BIN_BITWISE = {"and": "&", "or": "|", "xor": "^"}
_BIN_ARITH = {
    "add": "+", "sub": "-", "mul": "*", "div": "/", "mod": "%",
    "shl": "<<", "shr": ">>", "lshift": "<<", "rshift": ">>",
}
_BIN_CMP = {"eq": "==", "neq": "!=", "gt": ">", "lt": "<",
            "gte": ">=", "lte": "<=", "ge": ">=", "le": "<="}

_VERILOG_KEYWORDS = {
    "always", "assign", "begin", "end", "if", "else", "case", "endcase",
    "for", "while", "repeat", "forever", "function", "endfunction", "task",
    "endtask", "module", "endmodule", "input", "output", "inout", "wire",
    "reg", "logic", "integer", "parameter", "localparam", "generate",
    "endgenerate", "genvar", "signed", "unsigned", "posedge", "negedge",
    "or", "and", "not", "xor", "xnor", "nor", "nand", "buf", "release",
    "disable", "deassign", "force", "wait", "fork", "join", "initial",
    "event", "supply0", "supply1", "tri", "tri0", "tri1", "wand", "wor",
    "real", "realtime", "time", "specify", "endspecify", "specparam",
    "table", "endtable", "primitive", "endprimitive", "pmos", "nmos",
    "cmos", "rcmos", "pullup", "pulldown", "tran", "tranif0", "tranif1",
}


def _parse_type(data_type: str) -> Tuple[str, Optional[int], Optional[int]]:
    """Parse a canonical type string → (kind, width, depth)."""
    t = (data_type or "").strip()
    if t == "bool":
        return ("bits", 1, None)
    if t == "int":
        return ("int", INT_WIDTH, None)
    if t.startswith("bits<"):
        try:
            return ("bits", int(t[5:-1]), None)
        except ValueError:
            pass
    if t.startswith("memory("):
        inner = t[len("memory("):-1]
        parts = [p.strip() for p in inner.split(",")]
        elem = parts[0] if parts else "bits<8>"
        depth = int(parts[1]) if len(parts) > 1 and parts[1].lstrip("-").isdigit() else 1
        _, ew, _ = _parse_type(elem)
        return ("memory", ew or 8, depth)
    if t.startswith("enum("):
        inner = t[len("enum("):-1]
        values = [v.strip() for v in inner.split(",") if v.strip()]
        w = max(1, (len(values) - 1).bit_length()) if values else 1
        return ("bits", w, None)
    if t.startswith("array("):
        inner = t[len("array("):-1]
        parts = [p.strip() for p in inner.split(",")]
        elem = parts[0] if parts else "bits<8>"
        size = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1
        _, ew, _ = _parse_type(elem)
        return ("memory", ew or 8, size)
    return ("bits", 1, None)


def _width_of(data_type: str) -> int:
    _, w, _ = _parse_type(data_type)
    return w or 1


class RtlDirectEmitter:
    """Emit synthesizable Verilog + a source-mapping file from a SpecModule."""

    def __init__(self, spec: SpecModule, int_width: int = INT_WIDTH) -> None:
        self.spec = spec
        self.int_width = int_width
        self.state_types: Dict[str, str] = {s.state_name: s.data_type for s in spec.state_ops}
        self.input_types: Dict[str, str] = {i.name: i.data_type for i in spec.inputs}
        self.output_names: set = {o.name for o in spec.outputs}
        self.memory_names: List[str] = [s.state_name for s in spec.state_ops if s.kind == "memory"]
        self.reg_names: set = {s.state_name for s in spec.state_ops if s.kind != "memory"}
        self.functions: Dict[str, Dict[str, Any]] = {f["name"]: f for f in spec.functions}
        self.schedule = spec.schedule_op
        self.reset = spec.resets[0] if spec.resets else None
        self.clock = spec.clocks[0] if spec.clocks else None

    @staticmethod
    def _sig(name: str) -> str:
        """Escape a Verilog reserved keyword as an escaped identifier."""
        return f"\\{name} " if name in _VERILOG_KEYWORDS else name

    def _type_of_name(self, name: str) -> str:
        if name in self.state_types:
            return self.state_types[name]
        for o in self.spec.outputs:
            if o.name == name:
                return o.data_type
        return "bits<1>"

    def _initial_of(self, name: str) -> str:
        for s in self.spec.state_ops:
            if s.state_name == name and s.kind != "memory":
                if s.initial is None:
                    return "0"
                if s.initial is True:
                    return "1'b1"
                if s.initial is False:
                    return "1'b0"
                return str(s.initial)
        return "0"

    def _decl(self, data_type: str) -> str:
        kind, w, _ = _parse_type(data_type)
        if kind == "int":
            return f"logic signed [{w - 1}:0]"
        return "logic" if w == 1 else f"logic [{w - 1}:0]"

    def _operand_width(self, expr: Any) -> Optional[int]:
        """Max width of the registers/inputs referenced by an expression."""
        w = None

        def walk(e):
            nonlocal w
            if isinstance(e, str):
                if e in self.state_types:
                    w = max(w or 1, _width_of(self.state_types[e]))
                elif e in self.input_types:
                    w = max(w or 1, _width_of(self.input_types[e]))
            elif isinstance(e, list):
                for a in e:
                    walk(a)
        walk(expr)
        return w

    def _lower(self, expr: Any, width: Optional[int] = None) -> str:
        if isinstance(expr, bool):
            return "1'b1" if expr else "1'b0"
        if isinstance(expr, int):
            return str(expr)
        if isinstance(expr, str):
            if expr.startswith(("0b", "0x", "0o")):
                try:
                    return str(int(expr, 0))
                except ValueError:
                    pass
            return self._sig(expr)
        if not isinstance(expr, list) or not expr:
            raise ExprError(f"Invalid expression: {expr!r}")

        op = expr[0]
        args = expr[1:]

        if op in self.functions:
            fn = self.functions[op]
            body = fn.get("body")
            params = [p["name"] for p in fn.get("params", [])]
            if body is not None and params:
                sub = dict(zip(params, args))
                return self._lower(self._subst(parse_sexpr(body), sub), width)
            return "1'b0"  # uninterpreted-function stub

        if op == "read":
            return str(args[0]) if args else "1'b0"
        if op == "prev":
            return f"prev_{args[0]}" if args else "1'b0"
        if op == "mem_read":
            return f"{args[0]}[{self._lower(args[1])}]" if len(args) >= 2 else "1'b0"
        if op == "ite":
            return f"({self._lower(args[0], 1)} ? {self._lower(args[1], width)} : {self._lower(args[2], width)})"
        if op in _BIN_BITWISE:
            return f"({self._lower(args[0], width)} {_BIN_BITWISE[op]} {self._lower(args[1], width)})"
        if op == "not":
            return f"(~ {self._lower(args[0], width)})"
        if op == "implies":
            return f"((! {self._lower(args[0], 1)}) || {self._lower(args[1], 1)})"
        if op in _BIN_CMP:
            return f"({self._lower(args[0], width)} {_BIN_CMP[op]} {self._lower(args[1], width)})"
        if op in _BIN_ARITH:
            a = self._lower(args[0], width)
            b = self._lower(args[1], width)
            result = f"({a} {_BIN_ARITH[op]} {b})"
            # Truncate to the operand width so the arithmetic matches the ISIR
            # bits<N> wrapping semantics (Verilog mul/add widen before assignment).
            op_w = self._operand_width(expr)
            if op_w:
                result = f"({result} & {op_w}'d{(1 << op_w) - 1})"
            return result
        if op == "min":
            return f"(({self._lower(args[0], width)} < {self._lower(args[1], width)}) ? {self._lower(args[0], width)} : {self._lower(args[1], width)})"
        if op == "max":
            return f"(({self._lower(args[0], width)} > {self._lower(args[1], width)}) ? {self._lower(args[0], width)} : {self._lower(args[1], width)})"
        if op == "sum":
            return "(" + " + ".join(self._lower(a, width) for a in args) + ")"
        if op == "slice":
            v = self._lower(args[0], width)
            h = args[1] if isinstance(args[1], int) else self._lower(args[1])
            l = args[2] if isinstance(args[2], int) else self._lower(args[2])
            if isinstance(h, int) and isinstance(l, int):
                w = h - l + 1
                # Sized cast forces the exact slice width; a bare `>> ... & mask`
                # would keep the operand width and widen enclosing concats.
                return f"{w}'( ({v}) >> {l} )"
            return f"{v}[{h}:{l}]"
        if op == "concat":
            high = self._lower(args[0], width)
            low = self._lower(args[1], width)
            lw = args[2] if isinstance(args[2], int) else self._lower(args[2])
            if isinstance(lw, int):
                # Size the low field to exactly `lw` bits so the concat width is
                # width(high) + lw rather than widening from the low operand.
                return f"{{{high}, {lw}'( {low} )}}"
            return f"{{{high}, {low}}}"
        raise ExprError(f"Unsupported operator '{op}' in direct lowering: {expr!r}")

    @staticmethod
    def _subst(expr: Any, sub: Dict[str, Any]) -> Any:
        if isinstance(expr, list):
            return [RtlDirectEmitter._subst(c, sub) for c in expr]
        if isinstance(expr, str) and expr in sub:
            return sub[expr]
        return expr

    def _grant_expr(self) -> List[str]:
        rules = self.spec.rule_ops
        lines: List[str] = []
        if not rules:
            return lines
        kind = self.schedule.kind if self.schedule else "parallel"
        order = self.schedule.rule_order if self.schedule else [r.rule_name for r in rules]
        for r in rules:
            fire = f"fire_{r.rule_name}"
            if kind == "sequential":
                try:
                    idx = order.index(r.rule_name)
                except ValueError:
                    idx = len(order)
                mask = "".join(f" && ! fire_{e}" for e in order[:idx])
                lines.append(f"  assign grant_{r.rule_name} = {fire}{mask};")
            else:
                lines.append(f"  assign grant_{r.rule_name} = {fire};")
        return lines

    def emit_module(self, module_name: Optional[str] = None) -> str:
        name = module_name or self.spec.name or "design"
        ports = self._ports()
        return (
            f"module {name} (\n" + ",\n".join(f"  {p}" for p in ports) + "\n);\n"
            f"\n{self._state_decls()}\n"
            f"\n{self._combinational()}\n"
            f"\n{self._sequential()}\n"
            f"\n{self._mem_sequential()}\n"
            f"\nendmodule\n"
        )

    def _ports(self) -> List[str]:
        ports: List[str] = []
        if self.clock:
            ports.append(f"input  logic {self.clock['name']}")
        if self.reset:
            ports.append(f"input  logic {self.reset['name']}")
        for i in self.spec.inputs:
            ports.append(f"input  {self._decl(i.data_type)} {self._sig(i.name)}")
        for o in self.spec.outputs:
            ports.append(f"output {self._decl(o.data_type)} {self._sig(o.name)}")
        return ports

    def _state_decls(self) -> str:
        lines: List[str] = []
        for s in self.spec.state_ops:
            if s.kind == "memory":
                _, w, depth = _parse_type(s.data_type)
                lines.append(f"  {self._decl(s.data_type)} {s.state_name} [0:{depth - 1}];")
            else:
                if s.state_name not in self.output_names:
                    lines.append(f"  {self._decl(s.data_type)} {s.state_name};")
                lines.append(f"  {self._decl(s.data_type)} next_{s.state_name};")
        for r in self.spec.rule_ops:
            lines.append(f"  logic fire_{r.rule_name};")
            lines.append(f"  logic grant_{r.rule_name};")
        return "\n".join(lines)

    def _combinational(self) -> str:
        lines: List[str] = ["  // Combinational: rule conditions, grants, next-state shadows."]
        for r in self.spec.rule_ops:
            cond = self._lower(parse_sexpr(r.condition or "true"), 1)
            lines.append(f"  assign fire_{r.rule_name} = {cond};")
        lines.extend(self._grant_expr())
        lines.append("  always_comb begin")
        for name in sorted(self.reg_names):
            lines.append(f"    next_{name} = {name};")
        for r in self.spec.rule_ops:
            actions = self._reg_actions(r)
            if not actions:
                continue
            lines.append(f"    if (grant_{r.rule_name}) begin")
            for state, v in actions:
                lines.append(f"      next_{state} = {v};")
            lines.append("    end")
        lines.append("  end")
        # Combinational outputs written by a rule: `output = (grant ? expr : 0)`.
        for r in self.spec.rule_ops:
            for name, v in self._comb_actions(r):
                lines.append(f"  assign {self._sig(name)} = (grant_{r.rule_name} ? {v} : '0);")
        # Unconnected outputs (declared but not a state nor driven) — leave them
        # undriven; they are spec-visible dead outputs.
        return "\n".join(lines)

    def _sequential(self) -> str:
        clk = self.clock["name"] if self.clock else "clk"
        lines: List[str] = [f"  // Sequential commit of registers.", f"  always_ff @(posedge {clk}) begin"]
        if self.reset:
            active_high = self.reset.get("polarity", "active_high") == "active_high"
            rst = self.reset["name"]
            lines.append(f"    if ({'' if active_high else '!'}{rst}) begin")
            for name in sorted(self.reg_names):
                lines.append(f"      {name} <= {self._initial_of(name)};")
            lines.append("    end else begin")
            for name in sorted(self.reg_names):
                lines.append(f"      {name} <= next_{name};")
            lines.append("    end")
        else:
            for name in sorted(self.reg_names):
                lines.append(f"    {name} <= next_{name};")
        lines.append("  end")
        return "\n".join(lines)

    def _mem_sequential(self) -> str:
        """Memory writes (mem_write) committed on the clock."""
        clk = self.clock["name"] if self.clock else "clk"
        writes = [(r, w) for r in self.spec.rule_ops for w in self._mem_writes(r)]
        if not writes:
            return ""
        lines: List[str] = [f"  // Memory writes.", f"  always_ff @(posedge {clk}) begin"]
        for r, (mem, addr, data) in writes:
            lines.append(f"    if (grant_{r.rule_name}) {mem}[{addr}] <= {data};")
        lines.append("  end")
        return "\n".join(lines)

    def _initial(self, s) -> str:
        if s.initial is None:
            return "0"
        if s.initial is True:
            return "1'b1"
        if s.initial is False:
            return "1'b0"
        return str(s.initial)

    def _reg_actions(self, rule) -> List[Tuple[str, str]]:
        """[(state, verilog_expr)] for `(write state expr)` on registers."""
        out: List[Tuple[str, str]] = []
        for act in rule.actions:
            e = parse_sexpr(act)
            if isinstance(e, list) and e and e[0] == "write" and len(e) == 3:
                state = e[1]
                if state in self.memory_names or state not in self.state_types:
                    continue
                val = self._lower(e[2], _width_of(self.state_types.get(state, "bits<1>")))
                out.append((state, val))
        return out

    def _comb_actions(self, rule) -> List[Tuple[str, str]]:
        """[(output, verilog_expr)] for `(write output expr)` on outputs (combinational)."""
        out: List[Tuple[str, str]] = []
        for act in rule.actions:
            e = parse_sexpr(act)
            if isinstance(e, list) and e and e[0] == "write" and len(e) == 3:
                name = e[1]
                if name in self.output_names and name not in self.state_types:
                    val = self._lower(e[2], _width_of(self._type_of_name(name)))
                    out.append((name, val))
        return out

    def _mem_writes(self, rule) -> List[Tuple[str, str, str]]:
        """[(mem, addr_expr, data_expr)] for `(mem_write mem addr data)`."""
        out: List[Tuple[str, str, str]] = []
        for act in rule.actions:
            e = parse_sexpr(act)
            if isinstance(e, list) and e and e[0] == "mem_write" and len(e) == 4:
                mem = e[1]
                addr = self._lower(e[2])
                data = self._lower(e[3])
                out.append((mem, addr, data))
        return out

    def emit_mapping(self, rtl_file: str, isir_source: str) -> str:
        items: List[Dict[str, Any]] = []
        for s in self.spec.state_ops:
            sigs = [s.state_name] + ([] if s.kind == "memory" else [f"next_{s.state_name}"])
            items.append({"spec_item_id": s.state_name, "rtl_signals": sigs, "rtl_lines": [], "kind": "state"})
        for r in self.spec.rule_ops:
            items.append({"spec_item_id": r.rule_name,
                          "rtl_signals": [f"fire_{r.rule_name}", f"grant_{r.rule_name}"],
                          "rtl_lines": [], "kind": "rule"})
        reset = {}
        if self.reset:
            reset = {"signal": self.reset["name"], "polarity": self.reset.get("polarity", "active_high"),
                     "initial_cycle": 0}
        doc = {
            "design": self.spec.name,
            "isir_source": isir_source,
            "rtl_file": rtl_file,
            "reset": reset,
            "items": items,
            "observables": [o.name for o in self.spec.outputs],
            "partial_spec_policy": "nondeterministic",
            "memory_policy": "assume_initialized",
            "int_width": self.int_width,
        }
        return json.dumps(doc, indent=2)


def emit(spec: SpecModule, out_dir: Path, policy: str = "sim",
         int_width: int = INT_WIDTH) -> Tuple[Path, Path]:
    """Emit the direct-path Verilog + source mapping. Returns (rtl, mapping)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    emitter = RtlDirectEmitter(spec, int_width=int_width)
    rtl_path = out_dir / f"{spec.name}_direct.v"
    rtl_path.write_text(emitter.emit_module(), encoding="utf-8")
    mapping_path = out_dir / f"{spec.name}_direct.mapping.json"
    mapping_path.write_text(emitter.emit_mapping(rtl_path.name, f"{spec.name}.isir"), encoding="utf-8")
    logger.info("Direct RTL emitted to %s (mapping %s)", rtl_path, mapping_path)
    return rtl_path, mapping_path
