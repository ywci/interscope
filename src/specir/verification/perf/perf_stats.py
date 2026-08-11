# src/specir/verification/perf/perf_stats.py
#
# PERF statistics collection and reporting.
# Tracks key metrics during a PERF traversal, including node counts,
# verifier calls, depth reached, beam sizes, Pareto pruning,
# token usage, and progress‑tracking for early stopping.
# Provides serialization for reporting.

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
        node_details: Optional list of per-node details for debugging.
        total_tokens: Dictionary with prompt and completion tokens from the LLM.
        start_time: Timestamp when the traversal started.
        end_time: Timestamp when the traversal ended (set on finish).
        depth_stats: Optional list of per-depth statistics (nodes, beam size, etc.).
        best_primary_score: Best observed score on the primary dimension across depths.
        consecutive_no_improvement: Number of consecutive depths where the best
            primary score did not improve by at least *min_improvement*.
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
    depth_stats: List[Dict[str, Any]] = field(default_factory=list)

    # Progress‑tracking fields for early stopping
    best_primary_score: float = 0.0
    consecutive_no_improvement: int = 0

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
        """Store per-depth statistics for reporting."""
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

    def start(self) -> None:
        """Set the start timestamp."""
        self.start_time = datetime.now().isoformat()

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
        self.depth_stats = []
        self.best_primary_score = 0.0
        self.consecutive_no_improvement = 0

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
            "consecutive_no_improvement": self.consecutive_no_improvement
        }

    def summary(self) -> str:
        """
        Generate a human-readable summary string of the statistics.

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
            f"Start time:              {self.start_time or 'N/A'}",
            f"End time:                {self.end_time or 'N/A'}",
        ]
        if self.depth_stats:
            lines.append("Depth breakdown:")
            for ds in self.depth_stats:
                lines.append(
                    f"  Depth {ds['depth']}: {ds['nodes']} nodes, "
                    f"beam {ds['beam']}, pruned {ds['pruned']}"
                )
        return "\n".join(lines)

    def __repr__(self) -> str:
        return f"PERFStats({self.to_dict()})"
