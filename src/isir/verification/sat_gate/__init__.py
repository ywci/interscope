# src/isir/verification/sat_gate/__init__.py
#
# SAT-gating: ITP-driven bounded-SAT pre-filter.  Sibling to perf/ and proof/.
"""SAT-gating package (Phase 1: backend-agnostic core)."""

from isir.verification.sat_gate.obligation import (
    Anchor, ModelApprox, Obligation, QueryKind, TargetScope,
    classify_predicate,
)
from isir.verification.sat_gate.policy import (
    CertState, CertTier, EvidenceAction, Objective, SearchAction, Status,
    disposition, evidence_action, is_hard,
)
from isir.verification.sat_gate.certificate import (
    Certificate, RiskClass, min_tier_for, risk_class_of,
)
from isir.verification.sat_gate.assumptions import gate_clause, gate_clause_set
from isir.verification.sat_gate.symbols import SymbolTable
from isir.verification.sat_gate.bitblast import BitBlaster, CNF
from isir.verification.sat_gate.evaluate import (
    evaluate_bitwise, evaluate_not, evaluate_eq, evaluate_ite,
)
from isir.verification.sat_gate.canonical import canonical_form, canonical_hash
from isir.verification.sat_gate.compile_dyn import (
    compile_base_entail, compile_ind_step, const_vector, lower_pred, lower_term,
)
from isir.verification.sat_gate.epoch import compute_epoch_hash
from isir.verification.sat_gate.assumptions import (
    AssumptionCapExceeded, AssumptionRegistry,
)
from isir.verification.sat_gate.observe import GateMetrics
from isir.verification.sat_gate.solver_cadical import IncrementalSolver
from isir.verification.sat_gate.pool import SolverPool
from isir.verification.sat_gate.mus import group_mus

__all__ = [
    "Anchor", "ModelApprox", "Obligation", "QueryKind", "TargetScope",
    "classify_predicate",
    "CertState", "CertTier", "EvidenceAction", "Objective", "SearchAction",
    "Status", "disposition", "evidence_action", "is_hard",
    "Certificate", "RiskClass", "min_tier_for", "risk_class_of",
    "gate_clause", "gate_clause_set",
    "SymbolTable", "BitBlaster", "CNF",
    "evaluate_bitwise", "evaluate_not", "evaluate_eq", "evaluate_ite",
    "canonical_form", "canonical_hash",
    "compile_base_entail", "compile_ind_step", "const_vector", "lower_pred", "lower_term",
    "compute_epoch_hash",
    "AssumptionCapExceeded", "AssumptionRegistry",
    "GateMetrics",
    "IncrementalSolver",
    "SolverPool",
    "group_mus",
]
