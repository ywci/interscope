# src/isir/verification/sat_gate/oracle/replay.py
#
# Independent replay oracle: re-derive named signal values from the
# SAT model via the symbol table and re-execute against the reference
# semantics. This is deliberately a SEPARATE implementation from the lifter,
# so a shared-lifter bug is not invisible to the oracle.

from typing import Callable, Dict
from isir.verification.sat_gate.bitblast import BitBlaster


def extract_signal(blaster: BitBlaster, model: Dict[int, bool],
                   name: str, width: int) -> int:
    """Extract the value of a named signal from a SAT model (LSB-first)."""
    val = 0
    for i in range(width):
        if model.get(blaster.symbols.var(name, i), False):
            val |= 1 << i
    return val


def replay_ind_step(blaster: BitBlaster, model: Dict[int, bool],
                    inv_fn: Callable[[Dict[str, int]], bool],
                    trans_fn: Callable[[Dict[str, int]], Dict[str, int]],
                    widths: Dict[str, int]) -> bool:
    """Confirm an IND_STEP counterexample.

    Re-derive the state from the model, check Inv(s), advance via the reference
    transition, and confirm Inv(s') is violated.  Returns True iff the model is
    a genuine CTI-to-induction.
    """
    state = {name: extract_signal(blaster, model, name, widths[name])
             for name in widths}
    if not inv_fn(state):
        return False
    next_state = trans_fn(state)
    return not inv_fn(next_state)
