# src/isir/verification/sat_gate/replay.py
#
# Runtime model replay against reference semantics. This is the
# independent re-execution path used by the REPLAY certificate and, crucially,
# by the composed replay that licenses hard actions derived from an
# IND_STEP counterexample. It uses the ITP-side expression evaluator, NOT the
# bit-blaster/SMT encoder, so a shared-lifter bug is visible here.

from typing import Dict, List, Optional, Sequence
from isir.utils.expr import eval_expr


def reference_next_state(state: Dict[str, int], transitions: Dict[str, str],
                         widths: Dict[str, int]) -> Dict[str, int]:
    """Advance ``state`` via the reference semantics of ``transitions``.

    ``transitions`` map each register to its next-state S-expression over the
    current state (e.g. ``{"count": "(add (read count) 1)"}``).  The result is
    the full next-state mapping.
    """
    nxt = dict(state)
    for name, expr in transitions.items():
        nxt[name] = eval_expr(expr, state, widths=widths)
    return nxt


def reference_inv(state: Dict[str, int], inv_pred: str,
                  widths: Dict[str, int]) -> bool:
    """Evaluate an invariant predicate against the reference semantics."""
    return bool(eval_expr(inv_pred, state, widths=widths))


def _state_matches(trace_state: Dict[str, int], state: Dict[str, int],
                   names: Sequence[str]) -> bool:
    return all(trace_state.get(n) == state.get(n) for n in names)


def composed_replay(
    init_values: Dict[str, int],
    transitions: Dict[str, str],
    widths: Dict[str, int],
    inv_pred: str,
    probe_trace: Sequence[Dict[str, int]],
    cti_state: Dict[str, int],
    next_state: Dict[str, int],
    names: Optional[Sequence[str]] = None,
) -> bool:
    """Composed replay: probe replay + step replay on the same lifted state.

    ``probe_trace`` is ``[s_0, ..., s_j]`` from the bounded reachability probe.
    Returns True iff, against the reference semantics:

    * ``s_0`` matches the initial values,
    * ``T(s_i, s_{i+1})`` holds for every ``i < j`` (probe replay),
    * ``s_j`` matches the CTI state,
    * ``T(s_j, s_{j+1})`` yields ``next_state`` (step replay),
    * ``Inv(s_j)`` holds and ``¬Inv(s_{j+1})`` holds.

    A False result means the model is NOT a genuine CTI-to-induction and no
    hard action may be derived from it (bug per  step 5).
    """
    if not probe_trace:
        return False
    names = list(names) if names is not None else list(widths)

    # Probe replay: the trace must start at Init and follow T step by step.
    if not _state_matches(probe_trace[0], init_values, names):
        return False
    for i in range(len(probe_trace) - 1):
        expected = reference_next_state(probe_trace[i], transitions, widths)
        if not _state_matches(probe_trace[i + 1], expected, names):
            return False

    # The final trace state must be the CTI state.
    if not _state_matches(probe_trace[-1], cti_state, names):
        return False

    # Step replay: T(cti) -> next_state, Inv(cti), ¬Inv(next_state).
    if not _state_matches(reference_next_state(cti_state, transitions, widths),
                          next_state, names):
        return False
    if not reference_inv(cti_state, inv_pred, widths):
        return False
    if reference_inv(next_state, inv_pred, widths):
        return False  # Inv(s_{j+1}) must be false for a genuine CTI
    return True
