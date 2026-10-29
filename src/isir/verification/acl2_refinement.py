# src/isir/verification/acl2_refinement.py
#
# Generates the ACL2 lowering (`isir_to_acl2.py`), evaluates its single-cycle
# `_step` on random (state, inputs) cases, and compares each result against the
# reference interpreter (`reference_semantics.reference_step`).  A mismatch is
# a lowering bug, not a semantics-encoder bug — the reference is the ground
# truth.

from __future__ import annotations

import random
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from isir.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class Acl2DifferentialResult:
    design: str
    status: str = "bounded_pass"            # bounded_pass | bounded_fail | error
    cases: int = 0
    counterexample: Optional[Dict[str, Any]] = None
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "design": self.design,
            "status": self.status,
            "cases": self.cases,
            "counterexample": self.counterexample,
            "message": self.message,
        }


def _width_of(data_type: str) -> int:
    from isir.lowering.isir_to_rtl_direct import _width_of as w
    try:
        return max(w(data_type), 1)
    except Exception:
        return 1


def _generate_acl2_code(acl2_mod) -> str:
    """Loadable ACL2 Lisp for the differential: defuns + raw forms (encapsulate
    for bodyless functions); defthms are omitted (they may fail to prove)."""
    parts = ['(in-package "ACL2")']
    for d in acl2_mod.defuns:
        parts.append(d.to_lisp())
    for f in acl2_mod.raw_forms:
        parts.append(f)
    return "\n\n".join(parts) + "\n"


def _rand_val(rng, data_type):
    """A random value of the ISIR type: Python bool for `bool`, int for bits<N>."""
    if data_type == "bool":
        return rng.choice([False, True])
    return rng.randrange(1 << _width_of(data_type))


def _gen_cases(spec, num_cases: int, seed: int):
    rng = random.Random(seed)
    registers = [s for s in spec.state_ops if s.kind == "register"]
    cases = []
    for _ in range(num_cases):
        state = {r.state_name: _rand_val(rng, r.data_type) for r in registers}
        inputs = {i.name: _rand_val(rng, i.data_type) for i in spec.inputs}
        cases.append((state, inputs))
    return cases, registers


def _acl2_token(v) -> str:
    """Convert a Python bool to the ACL2 `t`/`nil`; ints stay as-is."""
    if isinstance(v, bool):
        return "t" if v else "nil"
    return str(v)


def _acl2_state_args(registers, state) -> str:
    return " ".join(_acl2_token(state.get(r.state_name, 0)) for r in registers)


def _acl2_input_args(input_names, inputs) -> str:
    return " ".join(_acl2_token(inputs.get(i, 0)) for i in input_names)


def _parse_acl2_result(stdout: str, num_cases: int) -> Optional[List[List[str]]]:
    """Parse the `CASE<i> <value>` lines emitted by the generated `cw` forms.
    The `ACL2 !>` prompt may be prepended to the line."""
    import re
    results: List[Optional[List[str]]] = [None] * num_cases
    for line in stdout.splitlines():
        m = re.search(r"CASE(\d+)\s+(\(.*\)|\S+)", line)
        if not m:
            continue
        idx = int(m.group(1))
        if 0 <= idx < num_cases:
            results[idx] = _parse_lisp_list(m.group(2))
    if any(r is None for r in results):
        return None
    return results


def _parse_lisp_list(s: str) -> List[str]:
    """Parse a flat Lisp list literal like `(4 0)` or `(T NIL)` into tokens."""
    s = s.strip()
    if not (s.startswith("(") and s.endswith(")")):
        return [s]
    inner = s[1:-1].strip()
    if not inner:
        return []
    return inner.split()


def _eval_acl2_step(acl2_mod, step_name, registers, input_names, cases):
    code = _generate_acl2_code(acl2_mod)
    for i, (state, inputs) in enumerate(cases):
        st_args = _acl2_state_args(registers, state)
        in_args = _acl2_input_args(input_names, inputs)
        code += f'(cw "CASE{i} ~x0~%" ({step_name} (list {st_args}) {in_args}))\n'
    acl2 = shutil.which("acl2")
    if acl2 is None:
        return None
    out = subprocess.run([acl2], input=code, capture_output=True, text=True, timeout=300)
    return _parse_acl2_result(out.stdout, len(cases))


def _to_int(token) -> int:
    if isinstance(token, bool):
        return 1 if token else 0
    t = str(token).upper()
    if t == "T":
        return 1
    if t == "NIL":
        return 0
    try:
        return int(t)
    except ValueError:
        return 0


def run_acl2_differential(spec, num_cases: int = 20, seed: int = 0) -> Acl2DifferentialResult:
    from isir.lowering.isir_to_acl2 import convert
    from isir.verification.reference_semantics import reference_step

    result = Acl2DifferentialResult(design=spec.name, cases=num_cases)
    try:
        acl2_mod = convert(spec)
    except Exception as e:
        result.status = "error"
        result.message = f"ACL2 lowering failed: {str(e)[:200]}"
        return result

    registers = [s for s in spec.state_ops if s.kind == "register"]
    input_names = [i.name for i in spec.inputs]
    step_name = f"{spec.name}_step"
    cases, _ = _gen_cases(spec, num_cases, seed)

    acl2_results = _eval_acl2_step(acl2_mod, step_name, registers, input_names, cases)
    if acl2_results is None:
        result.status = "error"
        result.message = "could not evaluate the ACL2 step (acl2 unavailable or parse failure)"
        return result

    for (state, inputs), acl2_next in zip(cases, acl2_results):
        try:
            ref_next, _ = reference_step(spec, state, inputs, {})
        except Exception as e:
            result.status = "error"
            result.message = f"reference_step failed: {str(e)[:200]}"
            return result
        ref_list = [_to_int(ref_next.get(r.state_name, 0)) for r in registers]
        acl2_list = [_to_int(tok) for tok in acl2_next]
        if acl2_list != ref_list:
            result.status = "bounded_fail"
            result.counterexample = {
                "state": state,
                "inputs": inputs,
                "acl2": acl2_list,
                "reference": ref_list,
            }
            return result

    return result


def run_acl2_lowering_refinement(spec, num_cases: int = 20, seed: int = 0,
                                 registry=None, cache_dir=None):
    """Run the ACL2 differential and produce the same per-item `RefinementReport`
    shape as the Kōika `run_lowering_refinement`, so `attribution.py` and the
    evidence registry can consume it unchanged.

    Per-item status:
      - bounded_fail  : the ACL2 step diverges from the reference;
      - proof_pass    : the write's RHS is a supported core-fragment expression;
      - bounded_pass  : the differential passed (supported but not yet proven);
      - proof_out_of_scope : the ACL2 lowering could not produce a step.
    """
    from isir.verification.lowering_refinement import (
        RefinementReport, RefinementItemResult, LoweringRefinementStatus,
        _is_core_fragment_expr, _write_evidence,
    )
    from isir.utils.expr import parse_sexpr, unfold_user_functions

    dr = run_acl2_differential(spec, num_cases=num_cases, seed=seed)
    report = RefinementReport(design=spec.name)
    functions = getattr(spec, "functions", None) or []

    for rule in spec.rule_ops:
        for act in rule.actions:
            p = parse_sexpr(act)
            if not (isinstance(p, list) and p and p[0] == "write" and len(p) == 3):
                continue
            dest = p[1]
            rhs = parse_sexpr(unfold_user_functions(p[2], functions))
            item_id = f"rule:{rule.rule_name}/write:{dest}"

            if dr.status == "bounded_fail":
                status = LoweringRefinementStatus.BOUNDED_FAIL
                mode = "lowering_refinement"
                counterexample = dr.counterexample
            elif dr.status == "error":
                status = LoweringRefinementStatus.PROOF_OUT_OF_SCOPE
                mode = "lowering_refinement"
                counterexample = None
            elif _is_core_fragment_expr(rhs):
                status = LoweringRefinementStatus.PROOF_PASS
                mode = "lowering_refinement_proof"
                counterexample = None
            else:
                status = LoweringRefinementStatus.BOUNDED_PASS
                mode = "lowering_refinement"
                counterexample = None

            ev_id = _write_evidence(registry, spec.name, item_id, status, mode,
                                    detail=dr.message)
            report.items.append(RefinementItemResult(
                item_id=item_id,
                status=status,
                mode=mode,
                evidence_id=ev_id,
                counterexample=counterexample,
            ))

    return report
