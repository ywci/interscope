# src/isir/cli/refine_check.py
#
# CLI subcommand `refine-check` – lowering-refinement evidence.
#
# Default: runs the per-item bounded SMT refinement check, attaches
# evidence records, caches results, and (with --differential) cross-checks the
# refinement status against the behavioral differential harness
# (`rtl_differential.py`).  An item whose lowering diverges (`bounded_fail`)
# blocks the pipeline (non-zero exit).
#
#   --trace            run the raw multi-cycle trace unrolling
#   --evidence         write `lowering_refinement`/`lowering_refinement_proof`
#                      records to the SQLite evidence registry
#   --differential     cross-check against the behavioral differential
#   --cache-dir DIR    where to persist the refinement cache
#   --cycles N         differential cycle count (default 8)

import argparse
import sys
from pathlib import Path

from isir.parser.parser import parse_isir
from isir.lowering.ast_to_isir import convert_ast_to_isir_module
from isir.lowering.smt_refine import refine_trace
from isir.verification.lowering_refinement import run_lowering_refinement


def main() -> int:
    parser = argparse.ArgumentParser(prog="isir refine-check",
                                     description="Lowering-refinement evidence.")
    parser.add_argument("input", type=str, help="Path to the .isir file")
    parser.add_argument("--trace", action="store_true",
                        help="Run the raw multi-cycle trace unrolling")
    parser.add_argument("--cycles", type=int, default=8,
                        help="Differential/trace cycle count (default: 8)")
    parser.add_argument("--evidence", action="store_true",
                        help="Write refinement evidence records to the registry")
    parser.add_argument("--differential", action="store_true",
                        help="Cross-check the refinement status against rtl_differential.py")
    parser.add_argument("--cache-dir", type=str, default=None,
                        help="Directory for the refinement cache")
    args = parser.parse_args()

    spec = convert_ast_to_isir_module(parse_isir(Path(args.input).resolve()).module)

    if args.trace:
        r = refine_trace(spec, cycles=args.cycles)
        print(f"{spec.name}: {r['status']} (cycles={args.cycles})")
        return 0 if r["status"] == "unsat" else 1

    registry = None
    if args.evidence:
        from isir.evidence.registry import EvidenceRegistry
        registry = EvidenceRegistry()

    report = run_lowering_refinement(
        spec,
        cycles=args.cycles,
        cache_dir=Path(args.cache_dir) if args.cache_dir else None,
        registry=registry,
        run_differential=args.differential,
    )

    for it in report.items:
        mark = {"bounded_pass": "OK", "bounded_fail": "DIV", "proof_pass": "PROOF",
                "proof_out_of_scope": "SKIP"}[it.status.value]
        print(f"[{mark:5}] {it.item_id:40} {it.status.value}")

    from isir.verification.attribution import attribute_report
    ar = attribute_report(report, spec)
    failing = [a for a in ar.attributions if a.category.value != "none"]
    for a in failing:
        print(f"       -> {a.category.value} ({a.route or '-'})")

    if report.differential_status is not None:
        verdict = ("consistent" if report.differential_consistent else "INCONSISTENT")
        print(f"\n{spec.name}: differential={report.differential_status} ({verdict})"
              f", cache_hits={report.cache_hits}")
    else:
        print(f"\n{spec.name}: cache_hits={report.cache_hits}")

    # Gate: a bounded_fail item blocks the pipeline.
    return 1 if report.has_bounded_fail else 0


if __name__ == "__main__":
    sys.exit(main())
