# src/specir/verification/perf/perf_diagnostics.py
#
# Human‑readable failure diagnostics for PERF.
#
# This module converts a `PERFStats` object into a concise, actionable
# summary that helps developers understand why a PERF traversal failed.
#
# It reports:
#   - top repeated error signatures,
#   - beam collapse events,
#   - backtracking effectiveness,
#   - on‑demand backtracking triggers,
#   - and provides recommendations based on observed patterns.
#
# The main entry point is `generate_diagnostics(stats)` or
# `print_diagnostics(stats)`.  The CLI can use `print_diagnostics` for
# the `--perf-stats` flag.

from typing import List, Dict, Any
from specir.verification.perf.perf_stats import PERFStats
from specir.utils.logger import get_logger

logger = get_logger(__name__)


def generate_diagnostics(stats: PERFStats) -> str:
    """
    Generate a human‑readable diagnostic report from PERF statistics.

    Args:
        stats: The PERFStats object collected during a traversal.

    Returns:
        A multiline string containing the diagnostic report.
    """
    if stats is None:
        return "No PERF statistics available."

    lines: List[str] = []
    lines.append("=" * 60)
    lines.append("PERF Failure Diagnostics")
    lines.append("=" * 60)
    lines.append("")
    lines.extend(_summarize_top_errors(stats))
    lines.extend(_summarize_beam_collapse(stats))
    lines.extend(_summarize_backtracking(stats))
    lines.extend(_generate_recommendations(stats))
    lines.append("=" * 60)
    return "\n".join(lines)


def print_diagnostics(stats: PERFStats) -> None:
    """Print the diagnostic report to stdout."""
    report = generate_diagnostics(stats)
    print(report)


def _summarize_top_errors(stats: PERFStats) -> List[str]:
    """Summarize the most frequent error signatures."""
    lines: List[str] = []
    top = stats.top_error_signatures
    if not top:
        lines.append("Top errors: none recorded.")
        lines.append("")
        return lines

    lines.append("Top errors:")
    for idx, entry in enumerate(top[:10], start=1):
        sig = entry["signature"]
        count = entry["count"]
        if len(sig) > 120:
            sig = sig[:120] + "..."
        lines.append(f"  {idx}. {sig} ({count} occurrences)")
    lines.append("")
    return lines


def _summarize_beam_collapse(stats: PERFStats) -> List[str]:
    """Summarize beam collapse events."""
    lines: List[str] = []
    if stats.beam_collapse_count > 0:
        lines.append(f"Beam collapse events: {stats.beam_collapse_count}")
        lines.append(
            "  The beam size repeatedly fell below min_beam_size and could "
            "not be restored.  This often indicates a lack of diversity "
            "among candidates or an overly aggressive Pareto filter."
        )
    else:
        lines.append("Beam collapse events: 0")
        lines.append(
            "  The beam size remained above or equal to min_beam_size "
            "throughout the traversal."
        )
    lines.append("")
    return lines


def _summarize_backtracking(stats: PERFStats) -> List[str]:
    """Summarize backtracking effectiveness."""
    lines: List[str] = []
    lines.append(f"Backtracking summary:")
    lines.append(f"  Total backtracks:            {stats.backtrack_count}")
    lines.append(f"  On‑demand backtracks:        {stats.backtrack_on_demand_count}")
    if stats.backtrack_on_demand_reasons:
        reasons = ", ".join(stats.backtrack_on_demand_reasons)
        lines.append(f"  On‑demand reasons:           {reasons}")
    lines.append(f"  Diversity scoring used:      {stats.backtrack_diversity_count} times")
    lines.append(f"  Alternate primary dim used:  {stats.backtrack_alternate_primary_count} times")
    lines.append(f"  Experience penalty used:     {stats.backtrack_experience_penalty_count} times")
    lines.append(f"  Scoring noise used:          {stats.backtrack_noise_count} times")
    lines.append(f"  Forced regeneration used:    {stats.backtrack_force_regeneration_count} times")

    # Reflection quality
    if stats.reflection_quality_history:
        lines.append("")
        lines.append("Reflection quality history:")
        for rec in stats.reflection_quality_history:
            lines.append(
                f"  Backtrack #{rec['backtrack_num']}: "
                f"quality={rec['quality']:.2f}, "
                f"delta={rec['delta']:.2f}, "
                f"pre_best={rec['pre_best_primary']:.3f}, "
                f"post_best={rec['post_best_primary']:.3f}"
            )
    else:
        lines.append("  No reflection quality recorded.")
    lines.append("")
    return lines


def _generate_recommendations(stats: PERFStats) -> List[str]:
    """Generate actionable recommendations based on observed patterns."""
    recs: List[str] = []
    recs.append("Recommendations:")

    # Check top errors for known patterns.
    top_sigs = [entry["signature"] for entry in stats.top_error_signatures[:5]]
    joined = " ".join(top_sigs).lower()

    if "focused, but cannot be unfocused" in joined or "wrong bullet" in joined:
        recs.append(
            "- Focus/bullet errors are prevalent. Ensure all proof templates "
            "use explicit braces `{ ... }` instead of bullets `-`, `+`, `*`. "
            "Enable the structural validator to reject mixed bullet/brace usage."
        )
    if "nat.mod_add" in joined or "deprecated" in joined:
        recs.append(
            "- Deprecated notation `Nat.mod_add` (or similar) is being used. "
            "Replace it with `Div0.mod_add` or avoid it entirely in generated "
            "code and templates."
        )
    if "not a discriminable equality" in joined or "discriminate" in joined:
        recs.append(
            "- `discriminate` is being used on boolean equalities. Use `inversion` "
            "or `destruct` on the boolean condition instead."
        )
    if "unable to unify" in joined:
        recs.append(
            "- Unification errors suggest applying the induction hypothesis too "
            "early or without destructing the opcode condition first. Ensure the "
            "prompt includes explicit destruct patterns."
        )
    if "found no subterm matching" in joined:
        recs.append(
            "- Rewrite failures indicate the expression does not match the goal. "
            "Add `simpl` before rewriting or verify the exact form of the lemma."
        )

    # Beam collapse recommendation.
    if stats.beam_collapse_count > 0:
        recs.append(
            "- Beam collapse occurred. Consider increasing `min_beam_size`, "
            "reducing `scoring_tournament_size` (to avoid too many ties), or "
            "increasing `branches_per_node` for hard obligations."
        )

    # Backtracking effectiveness.
    if stats.backtrack_count > 0 and not stats.reflection_quality_history:
        recs.append(
            "- Backtracking was used but no reflection quality was recorded. "
            "Ensure `backtracking.enabled` and `reflection_quality_window` are "
            "configured correctly so that backtrack effectiveness is evaluated."
        )
    elif stats.backtrack_count > 0 and stats.reflection_quality_history:
        low_quality = [
            rec for rec in stats.reflection_quality_history
            if rec["quality"] < 0.3
        ]
        if low_quality:
            recs.append(
                "- Several backtracks produced low reflection quality. Consider "
                "adjusting `backtracking.max_backtrack_depth`, "
                "`backtracking.diversity_weight`, or enabling "
                "`backtracking.force_strategy_switch`."
            )

    if not recs[1:]:  # Only "Recommendations:" header?
        recs.append("- No specific recommendations. Review the traversal log for details.")

    return recs
