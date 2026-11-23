# src/isir/verification/sat_gate/boosters.py
#
# Generation boosters. Each produces soft seed candidates from an
# existing solver result or an external source

from typing import List, Optional
from isir.verification.sat_gate.lemma_hint import (
    HintProvenance, LemmaHint, _cube_to_predicate, candidate_predicate_from_cube,
)


def probe_core_subcube(init_values, transitions, widths, cube,
                       depth: int) -> frozenset:
    """Booster #1: minimize an unreachable cube to a core sub-cube.

    Drops literals while ``Init ∧ T^depth ∧ subcube`` stays UNSAT, yielding a
    minimal unreachable sub-cube (the honest core of the already-run probe).
    """
    from isir.verification.sat_gate.smt_encode import solve_smt_reachability

    c = sorted(cube)
    changed = True
    while changed:
        changed = False
        for lit in c:
            candidate = [x for x in c if x != lit]
            if not candidate:
                break
            pred = _cube_to_predicate(frozenset(candidate))
            if solve_smt_reachability(init_values, transitions, widths,
                                      pred, depth) == "unsat":
                c = candidate
                changed = True
                break
    return frozenset(c)


def harvest_seed_candidates(clauses: List[str], source_obligation_id: str,
                            provenance: HintProvenance) -> List[LemmaHint]:
    """Boosters #3 (ITP-side) and #7 (IC3-mined): wrap already-proved or
    externally mined clauses as soft seeds.

    ``provenance`` is ITP_PROPOSED / ACL2_STEP_IDENTITY (booster #3) or
    IC3_MINED (booster #7).  The seeds are soft and must still earn
    BASE_ENTAIL + IND_STEP + T3 before becoming permanent.
    """
    hints: List[LemmaHint] = []
    for i, clause in enumerate(clauses):
        hints.append(LemmaHint(
            hint_id=f"{source_obligation_id}-seed-{i}",
            source_obligation_id=source_obligation_id,
            source_cti_cube=frozenset(),
            generalized_cube=frozenset(),
            candidate_predicate=clause,
            provenance=provenance,
))
    return hints


def strengthen_retry(candidate_pred, transitions, widths,
                     max_passes: int = 2) -> Optional[str]:
    """Booster #8: strengthen a failing hint from its own IND_STEP CTI.

    Up to ``max_passes`` times: if the candidate's IND_STEP is UNSAT it is
    returned (inductive); otherwise the failing CTI state ``s`` is blocked by
    conjoining ``¬(cube(s))`` and the check is re-run.  No frame data is
    retained.
    """
    from isir.verification.sat_gate.smt_encode import (
        solve_smt_ind_step, solve_smt_ind_step_model,
)

    pred = candidate_pred
    for _ in range(max_passes):
        if solve_smt_ind_step(pred, transitions, widths) == "unsat":
            return pred
        status, s_state, _ = solve_smt_ind_step_model(pred, transitions, widths)
        if status != "sat" or not s_state:
            return None
        ctg_cube = frozenset((n, v) for n, v in s_state.items())
        pred = f"(and {pred} (not {_cube_to_predicate(ctg_cube)}))"
    return None


def rule_localized_hint(cti_cube, rule_name: str, source_obligation_id: str,
                        hint_id: str) -> LemmaHint:
    """Booster #4: a rule-localized CTI hint (records ``source_rule``)."""
    cube = frozenset(cti_cube)
    return LemmaHint(
        hint_id=hint_id,
        source_obligation_id=source_obligation_id,
        source_cti_cube=cube,
        generalized_cube=cube,
        candidate_predicate=candidate_predicate_from_cube(cube),
        provenance=HintProvenance.CTI_PROBE_UNSAT,
        source_rule=rule_name,
)


def diversify_ctis(inv_pred, transitions, widths, max_ctis: int) -> List[dict]:
    """Booster #5: up to ``max_ctis`` distinct CTI models via model blocking."""
    from isir.verification.sat_gate.smt_encode import solve_smt_ind_step_model

    ctis: List[dict] = []
    for _ in range(max_ctis):
        status, s_state, _ = solve_smt_ind_step_model(
            inv_pred, transitions, widths, blocked_cubes=ctis)
        if status != "sat" or not s_state:
            break
        cube = dict(s_state)
        if cube in ctis:
            break
        ctis.append(cube)
    return ctis


def extend_cube(transitions, widths, cube, universe) -> frozenset:
    """Booster #6: upward generalization — add literals back toward a maximal
    blocked cube while ``¬(cube ∪ {lit})`` stays inductive."""
    from isir.verification.sat_gate.smt_encode import solve_smt_bad_cube_step

    c = sorted(cube)
    for lit in sorted(universe):
        if lit in c:
            continue
        candidate = c + [lit]
        pred = _cube_to_predicate(frozenset(candidate))
        if solve_smt_bad_cube_step([], transitions, widths, pred) == "unsat":
            c = candidate
    return frozenset(c)
