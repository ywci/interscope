# src/isir/verification/sat_gate/__init__.py
#
# SAT-gating: ITP-driven bounded-SAT pre-filter. Sibling to perf/ and proof/.

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
from isir.verification.sat_gate.observe import DisableRegistry, GateMetrics
from isir.verification.sat_gate.audit import AuditStore, RunManifest, content_hash
from isir.verification.sat_gate.cache import (
    CacheKey, CertCache, LemmaHintCache, SatCache, SubsumptionCache,
)
from isir.verification.sat_gate.epoch_reuse import extract_preseed
from isir.verification.sat_gate.boosters import (
    diversify_ctis, extend_cube, harvest_seed_candidates, probe_core_subcube,
    rule_localized_hint, strengthen_retry,
)
from isir.verification.sat_gate.array_instantiate import (
    ackermann_constraints, ackermannize, array_instantiate, collect_selects,
)
from isir.verification.sat_gate.rtlil import parse_rtlil, run_yosys_pass, signal_map
from isir.verification.sat_gate.ranker import (
    ObligationFeatures, ShadowRanker, rule_based_score,
)
from isir.verification.sat_gate.lemma_hint import (
    HintProvenance, LemmaHint, PROVENANCE_TIER, bulk_drop_core,
    candidate_predicate_from_cube, concretization_screen, generalize_cube,
    harvest_s_prime_hint, rank_hints, rank_score, t0_prescreen,
)
from isir.verification.sat_gate.lemma_admission import (
    AdmissionEvidence, LemmaAdmissionPolicy,
)
from isir.verification.sat_gate.hint_pool import HintPool
from isir.verification.sat_gate.search_tiers import TwoTierBeam
from isir.verification.sat_gate.gate_config import GateConfig
from isir.verification.sat_gate.live_gate import (
    LiveGate, ObligationAction, ObligationDisposition, Whitelist,
)
from isir.verification.sat_gate.hint_routing import HintRouter
from isir.verification.sat_gate.cti_probe import resolve_cti
from isir.verification.sat_gate.sat_features import (
    gate_evidence_score, promote_ranker, sat_features_vector,
)
from isir.verification.sat_gate.bounded_fallback import bounded_fallback
from isir.verification.sat_gate.economics import (
    gate_cost, is_economic, per_class_verdict, required_pq, saving,
)
from isir.verification.sat_gate.solver_cadical import IncrementalSolver
from isir.verification.sat_gate.pool import SolverPool
from isir.verification.sat_gate.mus import group_mus
from isir.verification.sat_gate.replay import (
    composed_replay, reference_inv, reference_next_state,
)

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
    "DisableRegistry",
    "AuditStore", "RunManifest", "content_hash",
    "CacheKey", "CertCache", "SatCache", "SubsumptionCache", "LemmaHintCache",
    "HintProvenance", "LemmaHint", "PROVENANCE_TIER", "rank_hints", "rank_score",
    "concretization_screen", "generalize_cube",
    "candidate_predicate_from_cube", "t0_prescreen", "harvest_s_prime_hint",
    "bulk_drop_core",
    "gate_cost", "is_economic", "per_class_verdict", "required_pq", "saving",
    "AdmissionEvidence", "LemmaAdmissionPolicy", "HintPool", "TwoTierBeam",
    "GateConfig",
    "LiveGate", "ObligationAction", "ObligationDisposition", "Whitelist",
    "HintRouter",
    "resolve_cti",
    "gate_evidence_score", "promote_ranker", "sat_features_vector",
    "bounded_fallback",
    "extract_preseed",
    "run_yosys_pass", "parse_rtlil", "signal_map",
    "ObligationFeatures", "ShadowRanker", "rule_based_score",
    "array_instantiate", "ackermannize", "collect_selects", "ackermann_constraints",
    "probe_core_subcube", "harvest_seed_candidates", "strengthen_retry",
    "rule_localized_hint", "diversify_ctis", "extend_cube",
    "IncrementalSolver",
    "SolverPool",
    "group_mus",
    "composed_replay", "reference_inv", "reference_next_state",
]
