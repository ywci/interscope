# src/isir/verification/sat_gate/gate_runner.py
#
# End-to-end gate runner: obligation -> policy -> compile -> solve -> certify
# -> disposition.  This is the integration point the PERF path would call.
"""Run the SAT gate over the `always` invariants of a SpecModule."""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from isir.verification.sat_gate.isir_bridge import (
    always_operand, initial_values, memories_of, memory_transitions_of,
    transitions_of, widths_of,
)
from isir.verification.sat_gate.function_inliner import (
    functions_of, inline_functions, sexpr_to_string,
)
from isir.verification.sat_gate.compile_dyn import compile_base_entail, compile_ind_step
from isir.verification.sat_gate.solver_oneshot import solve_cnf
from isir.verification.sat_gate.smt_encode import solve_smt_ind_step_with_memory
from isir.verification.sat_gate.obligation import classify_predicate
from isir.verification.sat_gate.observe import GateMetrics
from isir.verification.sat_gate.policy import (
    CertState, CertTier, EvidenceAction, ModelApprox, QueryKind, Status,
    TargetScope, evidence_action,
)


@dataclass
class GateResult:
    property: str
    base_status: str
    step_status: str
    evidence_action: Optional[EvidenceAction]
    reject_reason: Optional[str] = None


def _to_status(s: str) -> Status:
    return {"sat": Status.SAT, "unsat": Status.UNSAT}.get(s, Status.UNKNOWN)


def run_gate(spec_module, metrics: Optional[GateMetrics] = None,
             certify_t3: bool = False) -> Tuple[List[GateResult], GateMetrics]:
    """Run the gate over every `always` invariant of ``spec_module``.

    For each invariant: classify (fail-closed), compile BASE_ENTAIL + IND_STEP,
    solve one-shot, and map the (base, step) result to an evidence action via
    the objective-free policy.
    """
    metrics = metrics or GateMetrics()
    widths = widths_of(spec_module)
    transitions = transitions_of(spec_module)
    memories = memories_of(spec_module)
    mem_transitions = memory_transitions_of(spec_module)
    init = initial_values(spec_module)
    functions = functions_of(spec_module)
    results: List[GateResult] = []

    for prop in (getattr(spec_module, "property_ops", []) or []):
        expr = getattr(prop, "expression", None) or {}
        if expr.get("kind") != "always":
            continue
        inv = expr.get("operand")
        if not inv:
            continue
        metrics.eligible_pre += 1

        # inline functions ALWAYS: built-ins (min/max/clamp8/…) need no
        # user-defined function table.
        inv = inline_functions(inv, functions)
        transitions = {k: inline_functions(v, functions) for k, v in transitions.items()}
        mem_transitions = {k: inline_functions(v, functions) for k, v in mem_transitions.items()}
        inv_str = inv if isinstance(inv, str) else sexpr_to_string(inv)

        reject = classify_predicate(inv_str)
        if reject:
            metrics.record_unknown(reject)
            results.append(GateResult(
                property=getattr(prop, "prop_name", "?"),
                base_status="unknown", step_status="unknown",
                evidence_action=None, reject_reason=reject,
            ))
            continue

        metrics.gateable += 1

        if memories:
            # Path B: memory-bearing design -> IND_STEP only via the SMT arrays.
            try:
                step_status = solve_smt_ind_step_with_memory(
                    inv, transitions, mem_transitions, widths, memories
                )
            except (ValueError, AssertionError) as e:
                metrics.record_unknown("compile")
                results.append(GateResult(
                    property=getattr(prop, "prop_name", "?"),
                    base_status="unknown", step_status="unknown",
                    evidence_action=None, reject_reason=str(e),
                ))
                continue
            metrics.record_call(step_status)
            action = (EvidenceAction.PROVE_STEP if step_status == "unsat"
                      else EvidenceAction.FORWARD)
            if action is not None:
                metrics.hard_actions[action.value] = \
                    metrics.hard_actions.get(action.value, 0) + 1
            results.append(GateResult(
                property=getattr(prop, "prop_name", "?"),
                base_status="unknown", step_status=step_status,
                evidence_action=action,
            ))
            continue

        try:
            base = compile_base_entail(init, inv, widths)
            step = compile_ind_step(inv, transitions, widths)
        except (ValueError, AssertionError) as e:
            # fall back to the SMT route (handles shifts, multiplication, etc.)
            from isir.verification.sat_gate.smt_encode import solve_smt_ind_step
            try:
                step_status = solve_smt_ind_step(inv, transitions, widths)
            except (ValueError, AssertionError) as e2:
                metrics.record_unknown("compile")
                results.append(GateResult(
                    property=getattr(prop, "prop_name", "?"),
                    base_status="unknown", step_status="unknown",
                    evidence_action=None, reject_reason=str(e2),
                ))
                continue
            metrics.record_call(step_status)
            action = (EvidenceAction.PROVE_STEP if step_status == "unsat"
                      else EvidenceAction.FORWARD)
            if action is not None:
                metrics.hard_actions[action.value] = \
                    metrics.hard_actions.get(action.value, 0) + 1
            results.append(GateResult(
                property=getattr(prop, "prop_name", "?"),
                base_status="unknown", step_status=step_status,
                evidence_action=action,
            ))
            continue

        base_r = solve_cnf(base.cnf)
        step_r = solve_cnf(step.cnf)
        metrics.record_call(step_r.status)

        # Map the pair to an evidence action (inductive pair is the T3 case).
        action = _disposition(base_r.status, step_r.status)
        if action is not None:
            metrics.hard_actions[action.value] = \
                metrics.hard_actions.get(action.value, 0) + 1

        results.append(GateResult(
            property=getattr(prop, "prop_name", "?"),
            base_status=base_r.status, step_status=step_r.status,
            evidence_action=action,
        ))
    return results, metrics


def _disposition(base_status: str, step_status: str) -> Optional[EvidenceAction]:
    """Map the (base, step) solve pair to an evidence action."""
    if base_status == "unknown" or step_status == "unknown":
        return EvidenceAction.FORWARD
    if base_status == "sat":
        # the base case is violated -> a real counterexample candidate.
        return EvidenceAction.REJECT_CANDIDATE
    # base UNSAT (holds)
    if step_status == "unsat":
        # the inductive pair holds -> T3 soundness-critical close.
        return EvidenceAction.PROVE_STEP
    # step SAT: a CTI -> forward for strengthening (never prune unsoundly).
    return EvidenceAction.FORWARD
