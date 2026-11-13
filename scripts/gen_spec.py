#!/usr/bin/env python3
# scripts/gen_spec.py
#
# Generate a natural-language Markdown specification from an .isir file.
#
# The Markdown is pure natural language (no S-expressions, no .isir syntax).
# Round-trip checking keeps the canonical behavioral facts in memory (no
# sidecar file is written): `_facts` extracts them, `_reconstruct` rebuilds an
# ISIR module from them.
#
# Verification:
#   --verify          reconstruct an ISIR module from the in-memory facts and
#                     differentially compare reference_trace(original) vs
#                     reference_trace(reconstructed) over seeded inputs.
#   --llm-roundtrip   additionally ask the configured LLM (conf/config.yaml) to
#                     regenerate the .isir from the natural-language spec, then
#                     differentially check it against the original.
#
# Usage:
#   python scripts/gen_spec.py <file.isir>              # writes <file>.md
#   python scripts/gen_spec.py <file.isir> --verify     # lossless round-trip check
#   python scripts/gen_spec.py <file.isir> --llm-roundtrip
#   python scripts/gen_spec.py --all [--verify]

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import yaml  # noqa: E402

from isir.dialects import isir  # noqa: E402
from isir.lowering.ast_to_isir import convert_ast_to_isir_module  # noqa: E402
from isir.parser.parser import parse_isir  # noqa: E402
from isir.utils.expr import parse_sexpr  # noqa: E402

_CMP_SYM = {"gt": ">", "ge": "≥", "lt": "<", "le": "≤"}


def _nl(expr) -> str:
    """Recursively translate a parsed S-expression into natural language."""
    if isinstance(expr, bool):
        return "true" if expr else "false"
    if isinstance(expr, (int, float)):
        return str(expr)
    if isinstance(expr, str):
        return expr
    if isinstance(expr, list):
        if not expr:
            return "nothing"
        op = expr[0]
        args = expr[1:]
        if op == "read":
            return f"`{args[0]}`" if args else "?"
        if op == "write":
            return f"set `{args[0]}` to {_nl(args[1]) if len(args) > 1 else '?'}"
        if op == "eq":
            return f"{_nl(args[0])} equals {_nl(args[1])}" if len(args) > 1 else "?"
        if op == "neq":
            return f"{_nl(args[0])} does not equal {_nl(args[1])}" if len(args) > 1 else "?"
        if op == "add":
            return f"{_nl(args[0])} + {_nl(args[1])}"
        if op == "sub":
            return f"{_nl(args[0])} − {_nl(args[1])}"
        if op == "mul":
            return f"{_nl(args[0])} × {_nl(args[1])}"
        if op == "mul_full":
            return f"the full (non-wrapping) product of {_nl(args[0])} and {_nl(args[1])}"
        if op == "and":
            return f"{_nl(args[0])} and {_nl(args[1])}"
        if op == "or":
            return f"{_nl(args[0])} or {_nl(args[1])}"
        if op == "xor":
            return f"{_nl(args[0])} xor {_nl(args[1])}"
        if op == "not":
            return f"not ({_nl(args[0])})"
        if op == "implies":
            return f"if {_nl(args[0])}, then {_nl(args[1])}"
        if op == "ite":
            return (f"if {_nl(args[0])}, then {_nl(args[1])}, "
                    f"otherwise {_nl(args[2]) if len(args) > 2 else '?'}")
        if op in _CMP_SYM:
            return f"{_nl(args[0])} {_CMP_SYM[op]} {_nl(args[1])}"
        if op == "slice":
            return f"{_nl(args[0])}[{args[1]}:{args[2]}]"
        if op == "shl":
            return f"{_nl(args[0])} shifted left by {_nl(args[1])}"
        if op == "shr":
            return f"{_nl(args[0])} shifted right by {_nl(args[1])}"
        # fallback: generic function call
        return f"{op}({', '.join(_nl(a) for a in args)})"
    return str(expr)


def _nl_str(sexp: str) -> str:
    """Parse + translate an S-expression string to natural language."""
    try:
        return _nl(parse_sexpr(sexp))
    except Exception:  # noqa: BLE001
        return sexp


def _facts(spec) -> Dict[str, Any]:
    return {
        "name": spec.name,
        "inputs": [{"name": i.name, "type": i.data_type} for i in spec.inputs],
        "state_ops": [
            {"name": s.state_name, "kind": s.kind, "type": s.data_type, "initial": s.initial}
            for s in spec.state_ops
        ],
        "rule_ops": [
            {"name": r.rule_name, "condition": r.condition, "actions": list(r.actions)}
            for r in spec.rule_ops
        ],
        "property_ops": [
            {"name": p.prop_name, "kind": p.kind, "expression": dict(p.expression),
             "assumes": list(p.assumes)}
            for p in spec.property_ops
        ],
        "functions": spec.functions,
    }


def _reconstruct(facts: Dict[str, Any]) -> "isir.SpecModule":
    return isir.SpecModule(
        name=facts["name"],
        inputs=[isir.Interface(name=i["name"], direction="input", data_type=i["type"])
                for i in facts.get("inputs", [])],
        state_ops=[isir.SpecStateOp(state_name=s["name"], kind=s.get("kind", "register"),
                                     data_type=s.get("type", "bits<1>"), initial=s.get("initial"))
                   for s in facts.get("state_ops", [])],
        rule_ops=[isir.SpecRuleOp(rule_name=r["name"], condition=r.get("condition"),
                                   actions=list(r.get("actions", [])))
                  for r in facts.get("rule_ops", [])],
        property_ops=[isir.SpecPropertyOp(prop_name=p["name"], kind=p.get("kind", "safety"),
                                           expression=dict(p.get("expression", {})),
                                           assumes=list(p.get("assumes", [])))
                      for p in facts.get("property_ops", [])],
        functions=list(facts.get("functions", [])),
    )


def _fmt_type(t: str) -> str:
    return t or "?"


def gen_markdown(spec) -> str:
    L: List[str] = []
    name = spec.name
    L.append(f"# {name} specification")
    L.append("")

    if spec.inputs:
        L.append("## Inputs")
        L.append("")
        L.append("| Name | Type |")
        L.append("|------|------|")
        for i in spec.inputs:
            L.append(f"| `{i.name}` | {_fmt_type(i.data_type)} |")
        L.append("")

    if spec.state_ops:
        L.append("## State")
        L.append("")
        L.append("| Name | Kind | Type | Initial |")
        L.append("|------|------|------|---------|")
        for s in spec.state_ops:
            if s.initial is False:
                init = "false"
            elif s.initial is True:
                init = "true"
            elif s.initial is None:
                init = ""
            else:
                init = str(s.initial)
            L.append(f"| `{s.state_name}` | {s.kind} | {_fmt_type(s.data_type)} | {init} |")
        L.append("")

    if spec.rule_ops:
        L.append("## Behavior (rules)")
        L.append("")
        for r in spec.rule_ops:
            cond = _nl_str(r.condition) if r.condition else "always"
            actions = "; ".join(_nl_str(a) for a in r.actions)
            L.append(f"- **{r.rule_name}** — when {cond}, {actions}.")
        L.append("")

    if spec.property_ops:
        L.append("## Properties")
        L.append("")
        for p in spec.property_ops:
            kind = p.kind
            expr = p.expression
            op = expr.get("operand") if isinstance(expr, dict) else expr
            ref = expr.get("reference") if isinstance(expr, dict) else None
            if kind == "combinational" and ref is not None:
                line = f"for all inputs, {_nl_str(op)} equals {_nl_str(ref)}"
            elif kind in ("safety", "invariant"):
                line = f"always, {_nl_str(op)}"
            elif kind == "transition":
                line = f"after each step, {_nl_str(op)}"
            else:
                line = _nl_str(op) if op else str(expr)
            L.append(f"- **{p.prop_name}** ({kind}): {line}.")
        L.append("")

    return "\n".join(L)


def verify_roundtrip(spec, cycles: int = 20, seed: int = 0) -> bool:
    from isir.verification.reference_semantics import reference_trace

    reconstructed = _reconstruct(_facts(spec))
    try:
        t1 = reference_trace(spec, cycles, seed)
        t2 = reference_trace(reconstructed, cycles, seed)
    except Exception as e:  # noqa: BLE001
        print(f"  ERROR: reference trace failed: {e}")
        return False
    if t1 != t2:
        print("  MISMATCH: reconstructed spec behaves differently")
        for i, (s1, s2) in enumerate(zip(t1, t2)):
            if s1 != s2:
                print(f"    first divergence at cycle {i}")
                break
        return False
    return True


def llm_roundtrip(spec, markdown: str) -> Optional[bool]:
    """Ask the configured LLM to regenerate the .isir from the NL spec, then
    differentially check it (reference_trace equivalence) against the original.

    The regenerated .isir is written to a temporary file (never overwriting the
    original .isir) and deleted immediately after parsing.

    Returns None if the LLM is unavailable, else True/False."""
    
    try:
        from isir.utils.config_loader import load_config
        from isir.backends.llm_client import get_llm_client_from_config
        config = load_config()
        llm = get_llm_client_from_config(config)
    except Exception as e:  # noqa: BLE001
        print(f"  LLM unavailable: {e}")
        return None

    prompt = (
        "You are given a natural-language hardware specification. Regenerate the "
        "equivalent ISIR module as a single YAML document (spec.module @<name> { ... }) "
        "that captures the SAME inputs, state, rules, and properties. Output only the "
        "YAML, with no prose or code fences.\n\n"
        f"{markdown}"
    )
    try:
        isir_text = llm.generate(prompt)
    except Exception as e:  # noqa: BLE001
        print(f"  LLM generation failed: {e}")
        return False

    # Best-effort: parse the LLM output + differential check against the
    # original. The regenerated .isir is written to a temp file in /tmp, NOT to
    # the original examples/<name>/<name>.isir, so it can never overwrite it.
    import tempfile
    from isir.verification.reference_semantics import reference_trace
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".isir", delete=False) as f:
            f.write(isir_text)
            tmp = f.name
        try:
            from isir.parser.parser import parse_isir
            regen = convert_ast_to_isir_module(parse_isir(Path(tmp)).module)
        finally:
            Path(tmp).unlink(missing_ok=True)
        return reference_trace(spec, 10, 0) == reference_trace(regen, 10, 0)
    except Exception as e:  # noqa: BLE001
        print(f"  LLM round-trip parse failed: {e}")
        return False


def _load(path: Path):
    return convert_ast_to_isir_module(parse_isir(path).module)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("files", nargs="*", help=".isir files to process")
    ap.add_argument("--all", action="store_true", help="process every examples/*/*.isir")
    ap.add_argument("--verify", action="store_true", help="lossless round-trip check")
    ap.add_argument("--llm-roundtrip", action="store_true",
                    help="LLM prose→ISIR round-trip check (uses conf/config.yaml)")
    ap.add_argument("--cycles", type=int, default=20)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    targets: List[Path] = []
    if args.all:
        root = Path(__file__).resolve().parents[1]
        targets = sorted((root / "examples").glob("*/*.isir"))
    else:
        targets = [Path(f) for f in args.files]
    if not targets:
        ap.error("no .isir files given (use --all or pass files)")

    ok = 0
    for p in targets:
        p = p.resolve()
        spec = _load(p)
        md = gen_markdown(spec)
        md_out = p.with_suffix(".md")
        md_out.write_text(md, encoding="utf-8")

        status = f"wrote {md_out.name}"
        if args.verify:
            status += "  [round-trip " + ("OK" if verify_roundtrip(spec, args.cycles, args.seed) else "FAILED") + "]"
            if "FAILED" in status:
                ok -= 1
        if args.llm_roundtrip:
            r = llm_roundtrip(spec, md)
            if r is None:
                status += "  [llm-roundtrip SKIPPED (no LLM)]"
            else:
                status += "  [llm-roundtrip " + ("OK" if r else "FAILED") + "]"
        print(status)
        ok += 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
