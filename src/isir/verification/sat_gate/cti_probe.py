# src/isir/verification/sat_gate/cti_probe.py
#
# CTI reachability probe + composed replay: resolve an IND_STEP SAT result into
# the (cti_reachable, composed_replay_checked) pair that licenses the hard
# action. Unreachable CTIs keep the invariant and yield a lemma hint; reachable
# CTIs become CEX claims only after the composed replay co-check.

from typing import Tuple


def resolve_cti(init_values, transitions, widths, inv_pred,
                cti_probe_k: int) -> Tuple[object, bool]:
    """Resolve an IND_STEP SAT into ``(cti_reachable, composed_replay_checked)``.

    ``cti_reachable`` is True (reachable, probe SAT + step replay), False
    (unreachable up to ``cti_probe_k``), or None (unknown / not a SAT CTI).
    The composed replay is the step co-check: ``T(s)=s'`` plus ``Inv(s)``
    and ``¬Inv(s')`` against the reference semantics.
    """
    from isir.verification.sat_gate.smt_encode import (
        solve_smt_ind_step_model, solve_smt_reachability,
    )
    from isir.verification.sat_gate.replay import (
        reference_inv, reference_next_state,
    )
    from isir.verification.sat_gate.lemma_hint import _cube_to_predicate

    status, s_state, s_prime = solve_smt_ind_step_model(inv_pred, transitions, widths)
    if status != "sat" or not s_state or not s_prime:
        return None, False  # UNSAT or unknown -> no CTI to probe

    cube = frozenset((n, v) for n, v in s_state.items())
    pred = _cube_to_predicate(cube)
    probe = solve_smt_reachability(init_values, transitions, widths, pred, cti_probe_k)
    if probe == "unsat":
        return False, False  # unreachable -> keep the invariant + lemma hint
    if probe == "sat":
        # The composed replay: the step replay T(s)=s' + Inv(s) + ¬Inv(s').
        # Input-dependent transitions cannot be replayed without the input
        # sequence, so the check fails closed (no hard action) rather than crash.
        try:
            checked = (reference_next_state(s_state, transitions, widths) == s_prime
                       and reference_inv(s_state, inv_pred, widths)
                       and not reference_inv(s_prime, inv_pred, widths))
        except Exception:  # noqa: BLE001
            checked = False
        return True, checked
    return None, False  # unknown
