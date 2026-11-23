# src/isir/verification/sat_gate/economics.py
#
# Certification-inclusive economics. The gate is economic only when the
# expected prover-cost saving is ≥3× the certification-inclusive gate cost.


def gate_cost(C_triage: float, h_hard: float = 0.0,
              h_t1_hard: float = 0.0, C_T1: float = 0.0,
              h_t3_hard: float = 0.0, C_T3: float = 0.0,
              h_sat_hard: float = 0.0, C_REPLAY: float = 0.0,
              r_audit: float = 0.0, C_audit: float = 0.0,
              ramp_amort: float = 0.0) -> float:
    """The per-call certification-inclusive gate cost."""
    cert = (h_t1_hard * C_T1 + h_t3_hard * C_T3 + h_sat_hard * C_REPLAY)
    return C_triage + h_hard * cert + r_audit * C_audit + ramp_amort


def saving(p: float, q: float, E_avoid: float) -> float:
    """The expected avoided prover cost."""
    return p * q * E_avoid


def is_economic(C_g_avg: float, E_avoid: float, p: float = 1.0,
                q: float = 1.0, margin: float = 3.0) -> bool:
    """Economic gate: ``saving ≥ margin · C_g_avg``."""
    return p * q * E_avoid >= margin * C_g_avg


def required_pq(C_g_avg: float, E_avoid: float, margin: float = 3.0) -> float:
    """The ``p·q`` required for the per-class break-even."""
    return margin * C_g_avg / E_avoid


def per_class_verdict(C_g_avg: float, E_avoid: float, margin: float = 3.0) -> str:
    """'gate' when the required p·q ≤ 1, else 'do-not-gate'."""
    return "gate" if required_pq(C_g_avg, E_avoid, margin) <= 1.0 else "do_not_gate"
