# src/isir/verification/sat_gate/bounded_fallback.py
#
# Bounded BMC fallback (k <= 2). When the gate cannot resolve an obligation
# (IND_STEP SAT with an unresolved CTI), the bounded fallback runs the bounded
# reachability of the CTI cube at depth <= max_depth and reports bounded_safe,
# bounded_cex, or unknown. This is the S-O+R+F arm.

def bounded_fallback(init_values, transitions, widths, target_pred,
                     max_depth: int = 2) -> str:
    """Run the bounded reachability of ``target_pred`` at depth <= ``max_depth``.

    Returns ``bounded_safe`` (unreachable up to the bound), ``bounded_cex``
    (reachable within the bound), or ``unknown``.
    """
    from isir.verification.sat_gate.smt_encode import solve_smt_reachability

    result = solve_smt_reachability(init_values, transitions, widths,
                                    target_pred, max_depth)
    if result == "sat":
        return "bounded_cex"
    if result == "unsat":
        return "bounded_safe"
    return "unknown"
