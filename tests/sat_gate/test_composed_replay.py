# tests/sat_gate/test_composed_replay.py

from isir.verification.sat_gate.replay import composed_replay


def test_composed_replay_genuine_cti():
    widths = {"count": 4}
    transitions = {"count": "(add (read count) 1)"}
    init = {"count": 0}
    inv = "(le (read count) 7)"

    # reachable trace 0 -> 1 -> ... -> 7; CTI at 7; next state 8 violates Inv.
    probe_trace = [{"count": i} for i in range(8)]
    cti = {"count": 7}
    nxt = {"count": 8}
    assert composed_replay(init, transitions, widths, inv, probe_trace, cti, nxt)


def test_composed_replay_rejects_bad_trace():
    widths = {"count": 4}
    transitions = {"count": "(add (read count) 1)"}
    init = {"count": 0}
    inv = "(le (read count) 7)"

    # the transition is broken (0 -> 5 is not T(0)=1).
    probe_trace = [{"count": 0}, {"count": 5}, {"count": 7}]
    cti = {"count": 7}
    nxt = {"count": 8}
    assert not composed_replay(init, transitions, widths, inv, probe_trace, cti, nxt)


def test_composed_replay_rejects_inv_holding_next():
    widths = {"count": 4}
    transitions = {"count": "(add (read count) 1)"}
    init = {"count": 0}
    inv = "(le (read count) 7)"

    # the next state 7 still satisfies Inv -> not a genuine CTI.
    probe_trace = [{"count": i} for i in range(7)]
    cti = {"count": 6}
    nxt = {"count": 7}
    assert not composed_replay(init, transitions, widths, inv, probe_trace, cti, nxt)


def test_composed_replay_rejects_wrong_init():
    widths = {"count": 4}
    transitions = {"count": "(add (read count) 1)"}
    init = {"count": 0}
    inv = "(le (read count) 7)"
    probe_trace = [{"count": 3}, {"count": 4}, {"count": 7}]  # s_0 != init
    cti = {"count": 7}
    nxt = {"count": 8}
    assert not composed_replay(init, transitions, widths, inv, probe_trace, cti, nxt)
