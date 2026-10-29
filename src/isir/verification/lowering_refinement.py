# src/isir/verification/lowering_refinement.py
#
# Wires the bounded SMT checker and the machine-checked proofs into the
# `compile --backend koika` lowering so that every lowering run produces
# per-item refinement evidence:
#
#   * evidence records  `verification_mode: lowering_refinement` (bounded)
#     and `lowering_refinement_proof` (machine-checked) in the SQLite registry;
#   * a `lowering_refinement_status ∈ {bounded_pass, bounded_fail, proof_pass,
#     proof_out_of_scope}` per item;
#   * a cache keyed by `(spec_item_hash, lowering_version, bound_config)`;
#   * a cross-check against the behavioral differential (`rtl_differential.py`):
#     a `bounded_pass` that diverges behaviorally (or a `bounded_fail` that
#     agrees) is a harness/encoding defect, not a silent discrepancy.

from __future__ import annotations

import hashlib
import inspect
import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from isir.utils.logger import get_logger

logger = get_logger(__name__)


def _compute_lowering_version() -> str:
    try:
        from isir.lowering import koika_to_rtl, smt_refine
        src = inspect.getsource(koika_to_rtl) + inspect.getsource(smt_refine)
        return hashlib.sha256(src.encode("utf-8")).hexdigest()[:12]
    except Exception as e:
        logger.warning("Could not compute lowering version: %s", e)
        return "unknown"


LOWERING_VERSION = _compute_lowering_version()


class LoweringRefinementStatus(str, Enum):
    BOUNDED_PASS = "bounded_pass"
    BOUNDED_FAIL = "bounded_fail"
    PROOF_PASS = "proof_pass"
    PROOF_OUT_OF_SCOPE = "proof_out_of_scope"


@dataclass
class RefinementItemResult:
    item_id: str
    status: LoweringRefinementStatus
    mode: str                      # "lowering_refinement" | "lowering_refinement_proof"
    evidence_id: Optional[int] = None
    counterexample: Optional[Dict[str, Any]] = None
    detail: str = ""
    category: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "item_id": self.item_id,
            "lowering_refinement_status": self.status.value,
            "verification_mode": self.mode,
            "evidence_id": self.evidence_id,
            "counterexample": self.counterexample,
            "detail": self.detail,
            "category": self.category,
        }


@dataclass
class RefinementReport:
    design: str
    items: List[RefinementItemResult] = field(default_factory=list)
    differential_status: Optional[str] = None
    differential_consistent: Optional[bool] = None
    cache_hits: int = 0

    @property
    def has_bounded_fail(self) -> bool:
        return any(i.status == LoweringRefinementStatus.BOUNDED_FAIL for i in self.items)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "design": self.design,
            "items": [i.to_dict() for i in self.items],
            "differential_status": self.differential_status,
            "differential_consistent": self.differential_consistent,
            "cache_hits": self.cache_hits,
            "blocked": self.has_bounded_fail,
        }


def _cache_path(cache_dir: Optional[Path]) -> Path:
    return (Path(cache_dir) if cache_dir else Path("build") / "refinement_cache") / "cache.json"


def _load_cache(cache_dir: Optional[Path]) -> Dict[str, Any]:
    p = _cache_path(cache_dir)
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            logger.warning("Could not parse refinement cache %s; ignoring.", p)
    return {}


def _save_cache(cache_dir: Optional[Path], cache: Dict[str, Any]) -> None:
    p = _cache_path(cache_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cache, indent=2, sort_keys=True))


def _item_hash(design: str, rule_name: str, cond: Any, dest: str, rhs: Any,
               widths: Dict[str, int]) -> str:
    payload = json.dumps(
        {
            "design": design,
            "rule": rule_name,
            "cond": cond,
            "dest": dest,
            "rhs": rhs,
            "widths": {k: v for k, v in sorted(widths.items())},
            "lowering_version": LOWERING_VERSION,
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


_SUPPORTED_BINOPS = frozenset({
    "add", "sub", "and", "or", "xor",
    "eq", "neq", "lt", "gt", "le", "ge",
})


def _is_core_fragment_expr(e: Any) -> bool:
    if isinstance(e, (int, bool)):
        return True
    if isinstance(e, str):
        return True  # register/input name
    if isinstance(e, list) and e:
        op = e[0]
        if op in ("read", "prev"):
            return len(e) == 2 and isinstance(e[1], str)
        if op == "not":
            return len(e) == 2 and _is_core_fragment_expr(e[1])
        if op == "ite":
            return len(e) == 4 and all(_is_core_fragment_expr(a) for a in e[1:])
        if op in _SUPPORTED_BINOPS:
            return len(e) == 3 and all(_is_core_fragment_expr(a) for a in e[1:])
    return False


def _matches_core_fragment_proof(rhs: Any) -> bool:
    """A write action is `proof_pass` when its RHS is a supported core-fragment
    expression — every such operator has a machine-checked value-correspondence
    lemma in `ISIR.koika.RefinementProofs`, and the single-write `refines` template
    (`counter_refines` and its `sub`/`ite` siblings) composes them."""
    return _is_core_fragment_expr(rhs)


def _write_evidence(registry, design: str, item_id: str,
                    status: LoweringRefinementStatus, mode: str,
                    detail: str = "") -> Optional[int]:
    if registry is None:
        return None
    try:
        ev_type = ("lowering_refinement_proof" if mode == "lowering_refinement_proof"
                   else "lowering_refinement")
        return registry.add_evidence(
            evidence_type=ev_type,
            ref_type="local_id",
            ref_value=f"local:{item_id}",
            engine="lowering_refinement",
            status=status.value,
            property_name=item_id,
            design_name=design,
        )
    except Exception as e:
        logger.warning("Could not write evidence for %s: %s", item_id, e)
        return None


def run_lowering_refinement(spec: Any, cycles: int = 3, seed: int = 0,
                            cache_dir: Optional[Path] = None,
                            registry=None,
                            run_differential: bool = False) -> RefinementReport:
    """Run the bounded per-item refinement check, attach evidence, cache, and
    (optionally) cross-check against the behavioral differential.

    `run_differential` defaults to False because it invokes the Kōika compiler
    and iverilog; the pipeline cross-check is an explicit opt-in."""
    from isir.lowering.koika_to_rtl import (
        _coq_bits_expr, _capitalize, _internalize_inputs, _has_unsupported_ops,
    )
    from isir.lowering.isir_to_rtl_direct import _width_of
    from isir.lowering.smt_refine import refine_isir_vs_koika
    from isir.utils.expr import parse_sexpr, unfold_user_functions

    report = RefinementReport(design=spec.name)
    cache = _load_cache(cache_dir)

    int_spec = _internalize_inputs(spec)
    widths = {s.state_name: _width_of(s.data_type) for s in int_spec.state_ops}
    reg_widths = {_capitalize(k): v for k, v in widths.items()}
    functions = getattr(spec, "functions", None) or []

    for rule in spec.rule_ops:
        cond = parse_sexpr(unfold_user_functions(rule.condition or "true", functions))
        for act in rule.actions:
            p = parse_sexpr(act)
            if not (isinstance(p, list) and p and p[0] == "write" and len(p) == 3):
                continue
            dest = p[1]
            rhs = parse_sexpr(unfold_user_functions(p[2], functions))
            dw = widths.get(dest, 1)
            item_id = f"rule:{rule.rule_name}/write:{dest}"

            if _has_unsupported_ops(rhs) or _has_unsupported_ops(cond):
                report.items.append(RefinementItemResult(
                    item_id=item_id,
                    status=LoweringRefinementStatus.PROOF_OUT_OF_SCOPE,
                    mode="lowering_refinement",
                    detail="unsupported operator (slice/mul/div/mod/mem_*)",
                    category="koika_modeling_gap",
                ))
                continue

            key = _item_hash(spec.name, rule.rule_name, cond, dest, rhs, widths)
            if key in cache:
                report.cache_hits += 1
                status = LoweringRefinementStatus(cache[key]["status"])
                counterexample = cache[key].get("counterexample")
                category = cache[key].get("category")
            else:
                try:
                    dsl = _coq_bits_expr(rhs, reg_widths, dw)
                    r = refine_isir_vs_koika(dest, rhs, dsl, dw, widths)
                except Exception as e:
                    logger.warning("refine check failed for %s: %s", item_id, e)
                    report.items.append(RefinementItemResult(
                        item_id=item_id,
                        status=LoweringRefinementStatus.PROOF_OUT_OF_SCOPE,
                        mode="lowering_refinement",
                        detail=f"koika DSL cannot lower: {str(e)[:200]}",
                        category="koika_modeling_gap",
                    ))
                    continue

                if r["status"] == "unsat":
                    status = LoweringRefinementStatus.BOUNDED_PASS
                    counterexample = None
                    category = None
                elif r["status"] == "sat":
                    status = LoweringRefinementStatus.BOUNDED_FAIL
                    counterexample = {"model": r.get("model", "")}
                    category = None  # refined to lowering_bug/spec_ambiguity by attribution
                else:
                    status = LoweringRefinementStatus.PROOF_OUT_OF_SCOPE
                    counterexample = None
                    category = "bound_exhausted"

                cache[key] = {"status": status.value, "counterexample": counterexample,
                              "category": category}

            # Upgrade bounded_pass to proof_pass when the RHS is a supported
            mode = "lowering_refinement"
            if status == LoweringRefinementStatus.BOUNDED_PASS and \
                    _matches_core_fragment_proof(rhs):
                status = LoweringRefinementStatus.PROOF_PASS
                mode = "lowering_refinement_proof"

            ev_id = _write_evidence(registry, spec.name, item_id, status, mode,
                                    detail=(counterexample or {}).get("model", "")[:200] if counterexample else "")

            report.items.append(RefinementItemResult(
                item_id=item_id,
                status=status,
                mode=mode,
                evidence_id=ev_id,
                counterexample=counterexample,
                category=category,
            ))

    _save_cache(cache_dir, cache)

    # Cross-check against the behavioral differential (opt-in: it runs the
    # Kōika compiler + iverilog).
    if run_differential:
        report.differential_status, report.differential_consistent = \
            _cross_check_differential(spec, report, seed)

    return report


def _cross_check_differential(spec: Any, report: RefinementReport,
                              seed: int) -> tuple[Optional[str], Optional[bool]]:
    """Run rtl_differential and check agreement with the refinement status.

    Consistency rule:
      * bounded_fail (any sat item)  <-> divergent_long_short
      * bounded_pass (all unsat)     <-> agreed_long_short
    `long_path_unsupported`/`error` are not comparable to a per-item verdict.
    """
    from isir.lowering.rtl_differential import diff_design
    from isir.parser.parser import parse_isir  # noqa: F401 (kept for symmetry)

    try:
        import tempfile
        with tempfile.TemporaryDirectory(prefix="wp6_diff_") as td:
            r = diff_design(spec, Path(td) / "short", Path(td) / "long", cycles=8, seed=seed)
        dstatus = r.status
    except Exception as e:
        logger.warning("Differential cross-check failed: %s", e)
        return None, None

    if dstatus not in ("agreed_long_short", "divergent_long_short"):
        # long_path_unsupported / error: not comparable to a per-item verdict.
        return dstatus, None

    behavioral_diverges = (dstatus == "divergent_long_short")
    refinement_fails = report.has_bounded_fail
    consistent = (behavioral_diverges == refinement_fails)
    return dstatus, consistent
