# src/specir/verification/perf/perf_stats.py
#
# PERF statistics collection and reporting.
# Tracks key metrics during a PERF traversal, including node counts,
# verifier calls, depth reached, beam sizes, Pareto pruning,
# token usage, progress‑tracking for early stopping, backtracking
# counts, backtracking scoring enhancements (diversity, alternate
# primary dimension, experience penalty, noise), forced regeneration
# after backtrack, on‑demand backtracking triggers, and reflection
# quality assessment.

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from datetime import datetime


@dataclass
class PERFStats:
    """
    Statistics collected during a PERF traversal.

    Attributes:
        total_nodes: Total number of nodes generated across all depths.
        total_verifier_calls: Total number of verifier (Coq/ACL2) invocations.
        max_depth: Maximum depth reached during the traversal.
        beam_size: Final beam size at the last depth.
        pruned_by_pareto: Number of nodes removed by Pareto dominance filtering.
        successful_depth: Depth at which a successful proof was found, if any.
        node_details: Optional list of per‑node details for debugging.
        total_tokens: Dictionary with prompt and completion tokens from the LLM.
        start_time: Timestamp when the traversal started (ISO format string).
        end_time: Timestamp when the traversal ended (set on finish).
        start_time_epoch: Timestamp as seconds since epoch (used for on‑demand
            backtracking time‑limit checks).
        depth_stats: Optional list of per‑depth statistics (nodes, beam size, etc.).
        best_primary_score: Best observed score on the primary dimension across depths.
        consecutive_no_improvement: Number of consecutive depths where the best
            primary score did not improve by at least *min_improvement*.
        backtrack_count: Total number of backtrack operations performed.
        backtrack_depths: List of depths to which the search backtracked.
        backtrack_diversity_count: Number of backtracks that used diversity scoring.
        backtrack_alternate_primary_count: Number of backtracks that used an
            alternate primary dimension for beam selection.
        backtrack_experience_penalty_count: Number of backtracks that applied
            an experience penalty to node scores.
        backtrack_noise_count: Number of backtracks that added scoring noise.
        backtrack_force_regeneration_count: Number of backtracks that triggered
            forced regeneration of children (bypassing cache, higher temperature).
        backtrack_on_demand_count: Number of on‑demand backtrack operations
            (triggered by depth interval, time limit, or error pattern).
        backtrack_on_demand_reasons: List of strings indicating why each
            on‑demand backtrack was triggered (e.g., "depth_interval",
            "time_limit", "too_many_identical_errors").
        pre_backtrack_best_primary: Best primary score just before the most
            recent backtrack (set by ``record_pre_backtrack_state``).
        pre_backtrack_error_sig: Dominant error signature just before the most
            recent backtrack.
        reflection_quality: Quality score (0.0‑1.0) computed after the
            configured reflection quality window has passed; indicates how
            much the backtrack improved the search.
        reflection_quality_history: List of per‑backtrack quality records,
            each containing ``backtrack_num``, ``pre_best_primary``,
            ``post_best_primary``, ``pre_error_sig``, ``post_error_sig``,
            ``quality``, ``delta``.
        error_signature_counts: Mapping from normalized error signature to
            number of times that signature was recorded during traversal.
        beam_collapse_count: Number of times the selected beam size dropped
            below `min_beam_size` and could not be restored.
    """

    total_nodes: int = 0
    total_verifier_calls: int = 0
    max_depth: int = 0
    beam_size: int = 0
    pruned_by_pareto: int = 0
    successful_depth: Optional[int] = None
    node_details: List[Dict[str, Any]] = field(default_factory=list)
    total_tokens: Dict[str, int] = field(default_factory=lambda: {"prompt": 0, "completion": 0})
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    start_time_epoch: float = 0.0
    depth_stats: List[Dict[str, Any]] = field(default_factory=list)

    # Progress‑tracking fields for early stopping
    best_primary_score: float = 0.0
    consecutive_no_improvement: int = 0

    # Backtracking statistics
    backtrack_count: int = 0
    backtrack_depths: List[int] = field(default_factory=list)

    # Backtracking scoring enhancement usage
    backtrack_diversity_count: int = 0
    backtrack_alternate_primary_count: int = 0
    backtrack_experience_penalty_count: int = 0
    backtrack_noise_count: int = 0

    # Forced regeneration after backtrack
    backtrack_force_regeneration_count: int = 0

    # On‑demand backtracking
    backtrack_on_demand_count: int = 0
    backtrack_on_demand_reasons: List[str] = field(default_factory=list)

    # Reflection quality assessment
    pre_backtrack_best_primary: float = 0.0
    pre_backtrack_error_sig: Optional[str] = None
    reflection_quality: Optional[float] = None
    reflection_quality_history: List[Dict[str, Any]] = field(default_factory=list)
    error_signature_counts: Dict[str, int] = field(default_factory=dict)
    beam_collapse_count: int = 0

    def record_node(self, details: Optional[Dict[str, Any]] = None) -> None:
        """Record that one node was generated."""
        self.total_nodes += 1
        if details:
            self.node_details.append(details)

    def record_verifier_call(self) -> None:
        """Record one verifier call (Coq/ACL2 invocation)."""
        self.total_verifier_calls += 1

    def record_depth(self, depth: int) -> None:
        """Record that we reached a new depth."""
        if depth > self.max_depth:
            self.max_depth = depth

    def record_beam_size(self, size: int) -> None:
        """Record the current beam size (frontier size)."""
        self.beam_size = size

    def record_pareto_pruned(self, count: int) -> None:
        """Record how many nodes were pruned by Pareto dominance."""
        self.pruned_by_pareto += count

    def record_success(self, depth: int) -> None:
        """Record that a successful proof was found at a given depth."""
        self.successful_depth = depth

    def record_tokens(self, prompt_tokens: int, completion_tokens: int) -> None:
        """Accumulate LLM token usage."""
        self.total_tokens["prompt"] += prompt_tokens
        self.total_tokens["completion"] += completion_tokens

    def record_depth_stats(self, depth: int, nodes: int, beam: int, pruned: int) -> None:
        """Store per‑depth statistics for reporting."""
        self.depth_stats.append({
            "depth": depth,
            "nodes": nodes,
            "beam": beam,
            "pruned": pruned
        })

    def record_progress(self, primary_score: float, min_improvement: float) -> None:
        """
        Update progress‑tracking fields.

        If *primary_score* improves the best observed score by at least
        *min_improvement* (relative to the current best), the counter
        ``consecutive_no_improvement`` is reset to 0.  Otherwise it is
        incremented by 1.
        """
        if primary_score >= self.best_primary_score + min_improvement:
            self.best_primary_score = primary_score
            self.consecutive_no_improvement = 0
        else:
            self.consecutive_no_improvement += 1

    def record_error_signature(self, error_signature: str) -> None:
        """
        Record a normalized error signature.

        Args:
            error_signature: A string representing the dominant error of a
                failed proof attempt. It should already be normalized by the
                traversal before calling this method.
        """
        if not error_signature:
            return
        self.error_signature_counts[error_signature] = (
            self.error_signature_counts.get(error_signature, 0) + 1
        )

    @property
    def top_error_signatures(self) -> List[Dict[str, Any]]:
        """
        Return the most frequent error signatures in descending order.

        Each entry is a dictionary with keys:
            signature (str)
            count (int)
        """
        return [
            {"signature": sig, "count": cnt}
            for sig, cnt in sorted(
                self.error_signature_counts.items(),
                key=lambda item: item[1],
                reverse=True
            )
        ]

    def record_beam_collapse(self) -> None:
        """Record that the beam size fell below the minimum and could not be restored."""
        self.beam_collapse_count += 1

    def record_backtrack(self, depth: int) -> None:
        """Record a backtrack event to the given depth."""
        self.backtrack_count += 1
        self.backtrack_depths.append(depth)

    def record_backtrack_details(
        self,
        diversity_used: bool = False,
        alternate_primary_used: bool = False,
        experience_penalty_used: bool = False,
        noise_used: bool = False,
        force_regeneration_used: bool = False,
    ) -> None:
        """
        Record which scoring enhancements were active during the most recent backtrack.

        Args:
            diversity_used: Whether diversity scoring was applied.
            alternate_primary_used: Whether an alternate primary dimension was used.
            experience_penalty_used: Whether an experience penalty was applied.
            noise_used: Whether scoring noise was added.
            force_regeneration_used: Whether forced regeneration was triggered.
        """
        if diversity_used:
            self.backtrack_diversity_count += 1
        if alternate_primary_used:
            self.backtrack_alternate_primary_count += 1
        if experience_penalty_used:
            self.backtrack_experience_penalty_count += 1
        if noise_used:
            self.backtrack_noise_count += 1
        if force_regeneration_used:
            self.backtrack_force_regeneration_count += 1

    def record_on_demand_backtrack(self, reason: str) -> None:
        """
        Record an on‑demand backtrack event.

        Args:
            reason: A short string indicating why the backtrack was triggered
                    (e.g., "depth_interval", "time_limit",
                    "too_many_identical_errors").
        """
        self.backtrack_on_demand_count += 1
        self.backtrack_on_demand_reasons.append(reason)

    def record_pre_backtrack_state(self, best_primary: float, error_sig: Optional[str]) -> None:
        """
        Snapshot the search state just before a backtrack is performed.

        Args:
            best_primary: The current best primary dimension score.
            error_sig: The dominant error signature at this point.
        """
        self.pre_backtrack_best_primary = best_primary
        self.pre_backtrack_error_sig = error_sig

    def evaluate_reflection_quality(self, current_best_primary: float,
                                    current_error_sig: Optional[str]) -> float:
        """
        Compute the quality of a reflection (backtrack) after the window has passed.

        The quality combines:
        - Primary score improvement: if the current best score is higher than the
          pre‑backtrack score, the improvement is captured.  If not, the improvement
          is 0.
        - Error signature shift: 1.0 if the dominant error changed, else 0.0.

        The formula is:  quality = 0.7 * primary_delta + 0.3 * error_shift,
        where primary_delta is min(1.0, (current - pre) / max(0.01, pre)) if
        current > pre else 0.0.

        Args:
            current_best_primary: Best primary score observed after the reflection
                window.
            current_error_sig: Dominant error signature after the window.

        Returns:
            A float between 0.0 and 1.0 indicating the effectiveness of the
            backtrack.
        """
        if self.pre_backtrack_best_primary is None:
            return 0.0

        # Compute primary score improvement
        if current_best_primary > self.pre_backtrack_best_primary:
            delta = (current_best_primary - self.pre_backtrack_best_primary) / max(0.01, self.pre_backtrack_best_primary)
            primary_delta = min(1.0, delta)
        else:
            primary_delta = 0.0

        # Error signature shift
        error_shift = 1.0 if (current_error_sig != self.pre_backtrack_error_sig) else 0.0

        quality = 0.7 * primary_delta + 0.3 * error_shift
        self.reflection_quality = quality

        # Record to history
        self.reflection_quality_history.append({
            "backtrack_num": self.backtrack_count,
            "pre_best_primary": self.pre_backtrack_best_primary,
            "post_best_primary": current_best_primary,
            "pre_error_sig": self.pre_backtrack_error_sig,
            "post_error_sig": current_error_sig,
            "quality": quality,
            "delta": primary_delta,
        })

        # Clear pre‑backtrack state after evaluation (so it's not reused)
        self.pre_backtrack_best_primary = 0.0
        self.pre_backtrack_error_sig = None

        return quality

    def start(self) -> None:
        """Set the start timestamp."""
        now = datetime.now()
        self.start_time = now.isoformat()
        self.start_time_epoch = now.timestamp()

    def finish(self) -> None:
        """Set the end timestamp."""
        self.end_time = datetime.now().isoformat()

    def reset(self) -> None:
        """Reset all statistics to initial values."""
        self.total_nodes = 0
        self.total_verifier_calls = 0
        self.max_depth = 0
        self.beam_size = 0
        self.pruned_by_pareto = 0
        self.successful_depth = None
        self.node_details = []
        self.total_tokens = {"prompt": 0, "completion": 0}
        self.start_time = None
        self.end_time = None
        self.start_time_epoch = 0.0
        self.depth_stats = []
        self.best_primary_score = 0.0
        self.consecutive_no_improvement = 0
        self.backtrack_count = 0
        self.backtrack_depths = []
        self.backtrack_diversity_count = 0
        self.backtrack_alternate_primary_count = 0
        self.backtrack_experience_penalty_count = 0
        self.backtrack_noise_count = 0
        self.backtrack_force_regeneration_count = 0
        self.backtrack_on_demand_count = 0
        self.backtrack_on_demand_reasons = []
        self.pre_backtrack_best_primary = 0.0
        self.pre_backtrack_error_sig = None
        self.reflection_quality = None
        self.reflection_quality_history = []
        self.error_signature_counts = {}
        self.beam_collapse_count = 0

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert statistics to a dictionary for serialization/reporting.

        Returns:
            A dictionary with all relevant fields.
        """
        return {
            "total_nodes": self.total_nodes,
            "total_verifier_calls": self.total_verifier_calls,
            "max_depth": self.max_depth,
            "beam_size": self.beam_size,
            "pruned_by_pareto": self.pruned_by_pareto,
            "successful_depth": self.successful_depth,
            "total_tokens": self.total_tokens,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "depth_stats": self.depth_stats,
            "best_primary_score": self.best_primary_score,
            "consecutive_no_improvement": self.consecutive_no_improvement,
            "backtrack_count": self.backtrack_count,
            "backtrack_depths": self.backtrack_depths,
            "backtrack_diversity_count": self.backtrack_diversity_count,
            "backtrack_alternate_primary_count": self.backtrack_alternate_primary_count,
            "backtrack_experience_penalty_count": self.backtrack_experience_penalty_count,
            "backtrack_noise_count": self.backtrack_noise_count,
            "backtrack_force_regeneration_count": self.backtrack_force_regeneration_count,
            "backtrack_on_demand_count": self.backtrack_on_demand_count,
            "backtrack_on_demand_reasons": self.backtrack_on_demand_reasons,
            "pre_backtrack_best_primary": self.pre_backtrack_best_primary,
            "pre_backtrack_error_sig": self.pre_backtrack_error_sig,
            "reflection_quality": self.reflection_quality,
            "reflection_quality_history": self.reflection_quality_history,
            "error_signature_counts": self.error_signature_counts,
            "top_error_signatures": self.top_error_signatures,
            "beam_collapse_count": self.beam_collapse_count,
        }

    def summary(self) -> str:
        """
        Generate a human‑readable summary string of the statistics.

        Returns:
            A multiline string with key metrics.
        """
        lines = [
            "PERF Traversal Statistics",
            "--------------------------",
            f"Total nodes generated:   {self.total_nodes}",
            f"Total verifier calls:    {self.total_verifier_calls}",
            f"Maximum depth reached:   {self.max_depth}",
            f"Final beam size:         {self.beam_size}",
            f"Nodes pruned by Pareto:  {self.pruned_by_pareto}",
            f"Successful depth:        {self.successful_depth if self.successful_depth is not None else 'None'}",
            f"Prompt tokens used:      {self.total_tokens.get('prompt', 0)}",
            f"Completion tokens used:  {self.total_tokens.get('completion', 0)}",
            f"Best primary score:      {self.best_primary_score:.3f}",
            f"Consecutive no‑improve:  {self.consecutive_no_improvement}",
            f"Backtrack count:         {self.backtrack_count}",
            f"Backtrack depths:        {self.backtrack_depths if self.backtrack_depths else 'None'}",
            f"  Diversity scoring:     {self.backtrack_diversity_count} times",
            f"  Alternate primary dim: {self.backtrack_alternate_primary_count} times",
            f"  Experience penalty:    {self.backtrack_experience_penalty_count} times",
            f"  Scoring noise:         {self.backtrack_noise_count} times",
            f"  Force regeneration:    {self.backtrack_force_regeneration_count} times",
            f"On‑demand backtracks:    {self.backtrack_on_demand_count}",
            f"  Reasons:               {self.backtrack_on_demand_reasons if self.backtrack_on_demand_reasons else 'None'}",
            f"Reflection quality:      {self.reflection_quality if self.reflection_quality is not None else 'N/A'}",
            f"Beam collapse count:     {self.beam_collapse_count}",
            f"Start time:              {self.start_time or 'N/A'}",
            f"End time:                {self.end_time or 'N/A'}",
        ]

        # Top error signatures
        if self.top_error_signatures:
            lines.append("")
            lines.append("Top errors:")
            for idx, entry in enumerate(self.top_error_signatures[:10], start=1):
                sig = entry["signature"]
                cnt = entry["count"]
                # Truncate long signatures
                if len(sig) > 120:
                    sig = sig[:120] + "..."
                lines.append(f"  {idx}. {sig} ({cnt} occurrences)")

        # Reflection quality history
        if self.reflection_quality_history:
            lines.append("")
            lines.append("Reflection quality history:")
            for rec in self.reflection_quality_history:
                lines.append(
                    f"  Backtrack #{rec['backtrack_num']}: quality={rec['quality']:.2f}, "
                    f"delta={rec['delta']:.2f}, pre_best={rec['pre_best_primary']:.3f}, "
                    f"post_best={rec['post_best_primary']:.3f}"
                )

        # Depth breakdown
        if self.depth_stats:
            lines.append("")
            lines.append("Depth breakdown:")
            for ds in self.depth_stats:
                lines.append(
                    f"  Depth {ds['depth']}: {ds['nodes']} nodes, "
                    f"beam {ds['beam']}, pruned {ds['pruned']}"
                )

        return "\n".join(lines)

    def __repr__(self) -> str:
        return f"PERFStats({self.to_dict()})"
