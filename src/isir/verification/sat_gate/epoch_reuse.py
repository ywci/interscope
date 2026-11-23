# src/isir/verification/sat_gate/epoch_reuse.py
#
# Invariant reuse across epochs: extract the subset of previously
# T3-certified clauses that remain base-valid and (individually) inductive under
# the new epoch, to pre-seed the hint pool as UNCHECKED candidates.

from typing import Dict, List


def extract_preseed(init_new: Dict[str, int], transitions_new: Dict[str, str],
                    widths: Dict[str, int],
                    certified_clauses: List[str]) -> List[str]:
    """Return the certified clauses base-valid and individually inductive under the new epoch."""
    from isir.verification.sat_gate.smt_encode import (
        solve_smt_base_entail, solve_smt_ind_step,
)

    base_valid = [c for c in certified_clauses
                  if solve_smt_base_entail(init_new, c, widths) == "unsat"]
    return [c for c in base_valid
            if solve_smt_ind_step(c, transitions_new, widths) == "unsat"]
