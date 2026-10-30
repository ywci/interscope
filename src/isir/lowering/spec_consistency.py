# src/isir/lowering/spec_consistency.py
#
# Self-Consistency verification (Section 3 of the Evolving Specification plan):
# checks the Confirmed specification itself — is it internally consistent and
# satisfiable? — by asking z3 whether a model exists, rather than whether the
# negation is UNSAT (which is what smt_refine.py does for refinement).
#
#   property satisfiability : exists a state/inputs where every safety/invariant
#                             operand holds  (unsat => contradictory / over-constrained)
#   rule fireability        : exists a state/inputs where each rule's condition
#                             is true        (unsat => dead rule)
#
# This is distinct from `smt_refine.py`, which proves *refinement* (spec-vs-RTL
# divergence) by checking the NEGATION for satisfiability.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from isir.dialects.isir import SpecModule
from isir.lowering.isir_to_rtl_direct import _width_of
from isir.lowering.smt_refine import expr_to_smt, run_z3
from isir.utils.expr import parse_sexpr, unfold_user_functions


def _widths(spec: SpecModule) -> Dict[str, int]:
    w: Dict[str, int] = {}
    for s in spec.state_ops:
        if s.kind == "register":
            w[s.state_name] = _width_of(s.data_type)
    for i in spec.inputs:
        w[i.name] = _width_of(i.data_type)
    return w


def _blackboxes(spec: SpecModule) -> Set[str]:
    return {f.get("name") for f in (getattr(spec, "functions", None) or [])
            if f.get("body") is None}


def _decl_lines(decls: Set[Tuple[str, int]]) -> List[str]:
    return [f"(declare-const {name} (_ BitVec {w}))" for name, w in sorted(decls)]


def _satisfiable(term: str, decls: Set[Tuple[str, int]], z3_bin: str) -> Tuple[str, str]:
    """Check satisfiability of `term` (a 1-bit boolean).  Returns (status, model)."""
    lines = ["(set-logic QF_BV)", *_decl_lines(decls),
             f"(assert (= {term} (_ bv1 1)))", "(check-sat)", "(get-model)"]
    status, out = run_z3("\n".join(lines) + "\n", z3_bin)
    model = "\n".join(l for l in out.splitlines() if l.startswith("  ") or "->" in l) if status == "sat" else ""
    return status, model


@dataclass
class PropertyConsistency:
    prop_name: str
    status: str = "sat"          # sat = satisfiable, unsat = contradictory
    model: str = ""


@dataclass
class RuleFireability:
    rule_name: str
    status: str = "sat"          # sat = can fire, unsat = dead rule
    model: str = ""


@dataclass
class SpecConsistencyResult:
    design: str
    status: str = "consistent"   # consistent | inconsistent | error
    properties: List[PropertyConsistency] = field(default_factory=list)
    rules: List[RuleFireability] = field(default_factory=list)
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "design": self.design,
            "status": self.status,
            "properties": [{"prop_name": p.prop_name, "status": p.status} for p in self.properties],
            "rules": [{"rule_name": r.rule_name, "status": r.status} for r in self.rules],
            "message": self.message,
        }


def _operand_sexpr(prop_op) -> Optional[Any]:
    operand = prop_op.expression.get("operand")
    if not operand:
        return None
    try:
        return parse_sexpr(operand)
    except Exception:
        return None


def check_self_consistency(spec: SpecModule, z3_bin: str = "z3") -> SpecConsistencyResult:
    """Check the specification's own properties for satisfiability, and each
    rule for fireability.  `unsat` on any property is a contradiction; `unsat`
    on a rule is a dead rule (its condition is never satisfiable).
    """
    result = SpecConsistencyResult(design=spec.name)
    widths = _widths(spec)
    blackboxes = _blackboxes(spec)
    functions = getattr(spec, "functions", None) or []

    try:
        # 1. Property satisfiability (the spec's own assertions).
        for p in spec.property_ops:
            if p.kind not in ("safety", "invariant"):
                continue
            sexpr = _operand_sexpr(p)
            if sexpr is None:
                continue
            sexpr = parse_sexpr(unfold_user_functions(sexpr, functions))
            decls: Set[Tuple[str, int]] = set()
            try:
                term = expr_to_smt(sexpr, 1, widths, decls, blackboxes)
            except (ValueError, NotImplementedError) as e:
                result.properties.append(PropertyConsistency(p.prop_name, "error", str(e)[:120]))
                continue
            status, model = _satisfiable(term, decls, z3_bin)
            result.properties.append(PropertyConsistency(p.prop_name, status, model))

        # 2. Rule fireability (each rule can fire under some state/inputs).
        for r in spec.rule_ops:
            cond = r.condition or "true"
            try:
                sexpr = parse_sexpr(unfold_user_functions(cond, functions))
                decls = set()
                term = expr_to_smt(sexpr, 1, widths, decls, blackboxes)
            except (ValueError, NotImplementedError) as e:
                result.rules.append(RuleFireability(r.rule_name, "error", str(e)[:120]))
                continue
            status, model = _satisfiable(term, decls, z3_bin)
            result.rules.append(RuleFireability(r.rule_name, status, model))

        inconsistent = ([p for p in result.properties if p.status == "unsat"]
                        + [r for r in result.rules if r.status == "unsat"])
        if any(p.status == "error" for p in result.properties) or any(r.status == "error" for r in result.rules):
            result.status = "error"
            result.message = "some checks could not be encoded"
        elif inconsistent:
            result.status = "inconsistent"
            result.message = "contradiction: " + ", ".join(
                [f"property {p.prop_name}" for p in result.properties if p.status == "unsat"]
                + [f"rule {r.rule_name}" for r in result.rules if r.status == "unsat"])
    except Exception as e:  # noqa: BLE001
        result.status = "error"
        result.message = str(e)[:200]

    return result


def check_rtl_conformance(spec: SpecModule, trace: List[Dict[str, Any]],
                          evidence_prefix: str = "rtl") -> List[Any]:
    """RTL Conformance verification (Section 3, Mode B): check the Confirmed
    specification's safety/invariant properties against a Candidate-RTL trace
    (a list of `{"state": ..., "inputs": ..., "memories": ...}` cycles).

    Each failing property yields a RawEvidenceRecord tagged
    `verification_mode == rtl_conformance` with `error_class == counterexample`
    (which `annotation.record_to_finding` then attributes to
    `rtl_implementation_error` / `repair_rtl`).
    """
    from isir.dialects.evolving_spec import (
        ErrorClass, EvidenceSource, ProofStatus, RawEvidenceRecord, VerificationMode,
    )
    from isir.utils.expr import eval_expr, parse_sexpr

    records: List[Any] = []
    state_types = {s.state_name: s.data_type for s in spec.state_ops if s.kind != "memory"}
    input_types = {i.name: i.data_type for i in spec.inputs}
    widths = {**{n: _width_of(t) for n, t in state_types.items()},
              **{n: _width_of(t) for n, t in input_types.items()}}

    for prop in spec.property_ops:
        if prop.kind not in ("safety", "invariant"):
            continue
        operand = prop.expression.get("operand")
        if not operand:
            continue
        parsed = parse_sexpr(operand)
        for cycle, cyc in enumerate(trace):
            state = cyc.get("state", {}) if isinstance(cyc, dict) else {}
            inputs = cyc.get("inputs", {}) if isinstance(cyc, dict) else {}
            memories = cyc.get("memories", {}) if isinstance(cyc, dict) else {}
            try:
                val = eval_expr(parsed, state, inputs, memories, width=1, widths=widths)
            except Exception as e:  # noqa: BLE001
                val = False
            if not val:
                records.append(RawEvidenceRecord(
                    evidence_ref=f"{evidence_prefix}:{prop.prop_name}",
                    primary_spec_item_id=prop.prop_name,
                    verification_mode=VerificationMode.RTL_CONFORMANCE,
                    evidence_source=EvidenceSource.SIMULATION,
                    proof_status=ProofStatus.DISPROVED,
                    error_class=ErrorClass.COUNTEREXAMPLE,
                    counterexample={"cycle": cycle},
                ))
                break  # one record per property
    return records
