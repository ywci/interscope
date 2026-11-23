# tests/sat_gate/test_cti_probe.py

from isir.verification.sat_gate.cti_probe import resolve_cti


def test_unreachable_cti_keeps_invariant():
    # count <= 15 (4-bit wraps) is inductive -> no CTI.
    widths = {"count": 4}
    transitions = {"count": "(add (read count) 1)"}
    init = {"count": 0}
    inv = "(le (read count) 15)"
    cti_reachable, checked = resolve_cti(init, transitions, widths, inv, cti_probe_k=3)
    assert cti_reachable is None


def test_reachable_cti_reports_cex():
    # count <= 7 with count' = count+1: CTI count=7 is reachable (0..7).
    widths = {"count": 4}
    transitions = {"count": "(add (read count) 1)"}
    init = {"count": 0}
    inv = "(le (read count) 7)"
    cti_reachable, checked = resolve_cti(init, transitions, widths, inv, cti_probe_k=10)
    assert cti_reachable is True
    assert checked is True  # the composed replay (T(7)=8, Inv(7), ¬Inv(8))


def test_bounded_unreachable_cti():
    # count=15 is unreachable in 3 steps; probe says unreachable (bounded).
    widths = {"count": 4}
    transitions = {"count": "(add (read count) 1)"}
    init = {"count": 0}
    inv = "(le (read count) 8)"
    # the CTI for count <= 8 is count=8 -> reachable at step 8, but the probe
    # bound of 3 cannot reach it -> cti_reachable is None (unknown) here because
    # the probe uses the CTI cube, not the invariant.
    cti_reachable, _ = resolve_cti(init, transitions, widths, inv, cti_probe_k=3)
    assert cti_reachable in (None, False)
