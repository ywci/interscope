# src/isir/verification/sat_gate/obligation.py
#
# Obligation IR for SAT-gating. Backend-agnostic: the model encoding
# is a separate concern, and this module MUST NOT import solver or
# encoder modules (architectural invariant).

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class QueryKind(Enum):
    """Typed tag declaring the logical form and anchor of a gate query ."""
    VACUITY = "vacuity"
    FALSIFY_INIT = "falsify_init"
    IND_STEP = "ind_step"
    BASE_ENTAIL = "base_entail"


class Anchor(Enum):
    INIT = "init"      # unroll from Init(s0)
    FREE = "free"      # unroll from a free state


class TargetScope(Enum):
    THEOREM_TARGET = "theorem_target"
    CANDIDATE_LEMMA = "candidate_lemma"


class ModelApprox(Enum):
    EXACT = "exact"
    OVER = "over"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Obligation:
    """A typed gate obligation.

    ``hypotheses`` and ``target`` are predicates (S-expression strings in the
    current slice).  ``group_ids`` are stable semantic group identifiers used
    for activation literals and core feedback.
    """
    kind: QueryKind
    anchor: Anchor
    target_scope: TargetScope
    target: str
    hypotheses: List[str] = field(default_factory=list)
    bound: int = 0
    group_ids: List[str] = field(default_factory=list)

# Operators whose semantics are admitted as exact in this fragment version.
F_EXACT_OPS = frozenset({
    "and", "or", "not", "xor",
    "add", "sub", "neg",
    "eq", "neq", "gt", "lt", "gte", "lte", "le", "ge",
    "ite", "mux",
    "concat", "extract", "bitselect", "slice",
    "read", "write", "const",
})

# Engineering exclusions: exact translation is possible but not yet shipped.
ENGINEERING_EXCLUSIONS = frozenset({
    "div", "rem", "mod",       # division/remainder
    "mul",                     # exact only <= max_mul_width
    "rshift", "lshift",        # variable shift (constant shifts are exact)
})

# Fundamental exclusions: not encodable in this fragment at all.
FUNDAMENTAL_EXCLUSIONS = frozenset({
    "forall", "exists", "rec", "liveness",
})

# Operators the dynamic compiler (compile_dyn.lower_term / lower_pred) actually
# implements. classify_predicate must flag anything else so the coverage number
# is honest (a token outside this set yields UNKNOWN, never SAT/UNSAT).
SUPPORTED_OPS = frozenset({
    "read", "const", "add", "sub", "ite",
    "and", "or", "xor", "not", "implies",
    "eq", "neq", "le", "ge", "lt", "gt",
    "slice", "concat",
    "mul", "div", "mod", "rem",  # SMT-route only (bit-blast falls back)
})


class RejectReason(Enum):
    """Fail-closed reason codes returned when an obligation is not compilable."""
    QUANTIFIER = "quantifier"
    UNBOUNDED_INT = "unbounded_integer"
    DIVISION = "division_or_remainder"
    WIDE_MUL = "wide_multiply"
    VARIABLE_SHIFT = "variable_shift"
    MEMORY_OOB = "memory_out_of_bounds"
    COST_GUARD = "cost_guard_exceeded"
    UNSUPPORTED = "unsupported_construct"


def classify_predicate(pred: str) -> Optional[str]:
    """Return the name of a blocking construct in ``pred``, else None.

    This is the conservative probe: it flags any token that names an excluded
    operator.  It intentionally over-approximates (a ``mul`` token is flagged
    even if its operands are narrow), because over-flagging yields UNKNOWN,
    never a wrong SAT/UNSAT (rejected ⇒ UNKNOWN).
    """
    import re
    tokens = set(re.findall(r"\(([a-zA-Z_][a-zA-Z0-9_]*)\b", pred))
    for tok in tokens:
        if tok in FUNDAMENTAL_EXCLUSIONS:
            return RejectReason.QUANTIFIER.value
        if tok in ("rshift", "lshift"):
            return RejectReason.VARIABLE_SHIFT.value
        if tok not in SUPPORTED_OPS:
            return RejectReason.UNSUPPORTED.value
    return None
