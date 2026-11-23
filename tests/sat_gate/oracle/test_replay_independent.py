# tests/sat_gate/oracle/test_replay_independent.py

from isir.verification.sat_gate.replay import (
    composed_replay, reference_inv, reference_next_state,
)


def test_reference_next_state_is_independent():
    # the reference transition uses eval_expr, not the bit-blaster.
    widths = {"count": 4}
    transitions = {"count": "(add (read count) 1)"}
    assert reference_next_state({"count": 7}, transitions, widths) == {"count": 8}


def test_reference_inv_is_independent():
    widths = {"count": 4}
    assert reference_inv({"count": 7}, "(le (read count) 7)", widths) is True
    assert reference_inv({"count": 8}, "(le (read count) 7)", widths) is False


def test_composed_replay_independent_of_solver():
    # a genuine CTI reachable by the reference semantics.
    widths = {"count": 4}
    transitions = {"count": "(add (read count) 1)"}
    init = {"count": 0}
    inv = "(le (read count) 7)"
    trace = [{"count": i} for i in range(8)]
    assert composed_replay(init, transitions, widths, inv, trace,
                           {"count": 7}, {"count": 8})


def test_composed_replay_rejects_solver_only_artifact():
    # a state the solver could produce but the reference transition forbids.
    widths = {"count": 4}
    transitions = {"count": "(add (read count) 1)"}
    init = {"count": 0}
    inv = "(le (read count) 7)"
    bad_trace = [{"count": 0}, {"count": 3}, {"count": 7}]
    assert not composed_replay(init, transitions, widths, inv, bad_trace,
                               {"count": 7}, {"count": 8})
