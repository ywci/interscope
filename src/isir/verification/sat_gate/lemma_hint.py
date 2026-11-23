# src/isir/verification/sat_gate/lemma_hint.py
#
# Lemma hints. A lemma hint is a SOFT output: it never alters
# evidence_action, never enters the permanent database, and carries no
# certification weight. Architectural invariant: this module MUST NOT
# import or call `evidence_action` or `disposition`.

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class HintProvenance(Enum):
    CTI_PROBE_UNSAT = "CTI_probe_UNSAT"
    EPOCH_REUSE = "epoch_reuse"
    PROBE_CORE = "probe_core"
    ITP_PROPOSED = "itp_proposed"
    ACL2_STEP_IDENTITY = "acl2_step_identity"
    IC3_MINED = "ic3_mined"
    PERF_SCRIPT_MINED = "perf_script_mined"


# provenance tier (offer order, never soundness): already-ITP-proved
# sources rank above mined/CTI-derived sources.
PROVENANCE_TIER = {
    HintProvenance.ITP_PROPOSED: 0,
    HintProvenance.ACL2_STEP_IDENTITY: 0,
    HintProvenance.EPOCH_REUSE: 1,
    HintProvenance.PROBE_CORE: 2,
    HintProvenance.IC3_MINED: 3,
    HintProvenance.CTI_PROBE_UNSAT: 4,
    HintProvenance.PERF_SCRIPT_MINED: 5,
}


@dataclass
class LemmaHint:
    """A soft lemma-hint candidate ."""
    hint_id: str
    source_obligation_id: str
    source_cti_cube: frozenset
    generalized_cube: frozenset
    candidate_predicate: str
    provenance: HintProvenance
    cti_side: str = "s"
    source_rule: Optional[str] = None
    generalization_basis: str = "relative_induction_under_F"
    hypotheses: List[str] = field(default_factory=list)
    bounded_unreachable_depth: int = 0
    generalization_steps: List[str] = field(default_factory=list)
    t0_prescreen: str = "SKIPPED"
    suggested_strategy: Optional[str] = None
    concretization_screen: str = "SKIPPED"
    rank_score: float = 0.0
    cert_state: str = "UNCHECKED"
    epoch_hash: str = ""
    timestamp: str = ""
    suggested_action: str = "offer_to_ITP_as_strengthening_hint"


def rank_score(hint: LemmaHint) -> float:
    """Soft ranking : smaller cubes + higher provenance rank first.

    Ranking determines offer order only, never soundness.
    """
    tier = PROVENANCE_TIER.get(hint.provenance, 99)
    size = len(hint.generalized_cube)
    return float(tier) * 1000.0 + float(size)


def rank_hints(hints: List[LemmaHint]) -> List[LemmaHint]:
    """Return hints sorted by offer order (provenance tier, then size)."""
    return sorted(hints, key=rank_score)


def _cube_to_predicate(cube) -> str:
    """A cube of (name, value) pairs -> a right-nested (and (eq …) (and …)) S-expr."""
    if not cube:
        return "true"
    parts = [f"(eq (read {name}) {value})" for name, value in sorted(cube)]
    result = parts[0]
    for p in parts[1:]:
        result = f"(and {result} {p})"
    return result


def concretization_screen(init_values, transitions, widths, cube,
                          depth: int) -> str:
    """Bounded concretization screen: Init ∧ T^depth ∧ cube.

    SAT means the generalized cube excludes a reachable state → "FAIL" (discard
    with provenance).  UNSAT means unreachable up to the bound → "PASS".  The
    screen is sound as a rejection mechanism only; it cannot accept a bad
    candidate (bounded unreachability ≠ unreachability).
    """
    from isir.verification.sat_gate.smt_encode import solve_smt_reachability

    target = _cube_to_predicate(cube)
    result = solve_smt_reachability(init_values, transitions, widths, target, depth)
    if result == "sat":
        return "FAIL"
    if result == "unsat":
        return "PASS"
    return "SKIPPED"


def bulk_drop_core(local_blocks, transitions, widths, cube) -> frozenset:
    """Core-driven bulk dropping via selector assumptions.

    Attaches a fresh selector to each cube literal in BOTH the antecedent
    (``¬l(s)``) and consequent (``l(s')``) encodings, solves
    ``BAD_CUBE_STEP(local_blocks, cube)`` under the selector assumptions, and
    drops every literal whose selector is absent from the failed-assumption core.
    """
    from isir.verification.sat_gate.compile_dyn import (
        compile_bad_cube_step_with_selectors,
)
    from isir.verification.sat_gate.solver_cadical import IncrementalSolver

    if not cube:
        return frozenset()
    blaster, selectors = compile_bad_cube_step_with_selectors(
        list(local_blocks or []), transitions, widths, frozenset(cube))
    solver = IncrementalSolver(clauses=blaster.cnf.clauses)
    assumptions = [sel for _, sel in selectors.items()]
    try:
        if solver.solve(assumptions=assumptions) is not False:
            return frozenset(cube)  # ¬cube is NOT inductive -> no drop
        core = set(solver.get_core())
        return frozenset(lit for lit, sel in selectors.items() if sel in core)
    finally:
        solver.delete()


def generalize_cube(transitions, widths, cube, local_blocks=None,
                    generalization_depth: int = 0, init_values=None,
                    cti_probe_k: int = 0) -> frozenset:
    """Generalize a CTI cube by literal dropping + CTG predecessor blocking."""
    from isir.verification.sat_gate.smt_encode import (
        solve_smt_bad_cube_step, solve_smt_bad_cube_step_model,
        solve_smt_reachability,
)

    blocks = list(local_blocks or [])
    c = sorted(bulk_drop_core(blocks, transitions, widths, frozenset(cube)))
    ctg_depth = 0
    changed = True
    while changed:
        changed = False
        for lit in c:
            candidate = [x for x in c if x != lit]
            if not candidate:
                break
            pred = _cube_to_predicate(frozenset(candidate))
            status, model = solve_smt_bad_cube_step_model(
                blocks, transitions, widths, pred)
            if status == "unsat":
                c = candidate
                changed = True
                break
            if status == "sat" and model is not None and ctg_depth < generalization_depth:
                pred_cube = frozenset((n, v) for n, v in model.items())
                pred_pred = _cube_to_predicate(pred_cube)
                if (solve_smt_bad_cube_step(blocks, transitions, widths, pred_pred) == "unsat"
                        and (init_values is None
                             or solve_smt_reachability(init_values, transitions, widths,
                                                       pred_pred, cti_probe_k) == "unsat")):
                    blocks.append(f"(not {pred_pred})")
                    ctg_depth += 1
                    if solve_smt_bad_cube_step(blocks, transitions, widths, pred) == "unsat":
                        c = candidate
                        changed = True
                        break
    return frozenset(c)


def candidate_predicate_from_cube(cube) -> str:
    """The hinted predicate ¬c' (``candidate_predicate``)."""
    return f"(not {_cube_to_predicate(cube)})"


def t0_prescreen(init_values, transitions, widths, candidate_pred) -> str:
    """T0 pre-screen: uncertified BASE_ENTAIL + IND_STEP before any T3 cost."""
    from isir.verification.sat_gate.smt_encode import (
        solve_smt_base_entail, solve_smt_ind_step,
)

    if solve_smt_base_entail(init_values, candidate_pred, widths) != "unsat":
        return "FAIL"
    if solve_smt_ind_step(candidate_pred, transitions, widths) != "unsat":
        return "FAIL"
    return "PASS"


def harvest_s_prime_hint(inv_pred, transitions, widths, source_obligation_id,
                         hint_id: str) -> Optional["LemmaHint"]:
    """The post-state (s′) cube from the IND_STEP model."""
    from isir.verification.sat_gate.smt_encode import solve_smt_ind_step_model

    status, _, s_prime = solve_smt_ind_step_model(inv_pred, transitions, widths)
    if status != "sat" or not s_prime:
        return None
    cube = frozenset((n, v) for n, v in s_prime.items())
    generalized = generalize_cube(transitions, widths, cube)
    return LemmaHint(
        hint_id=hint_id,
        source_obligation_id=source_obligation_id,
        source_cti_cube=cube,
        generalized_cube=generalized,
        candidate_predicate=candidate_predicate_from_cube(generalized),
        provenance=HintProvenance.CTI_PROBE_UNSAT,
        cti_side="s'",
)
