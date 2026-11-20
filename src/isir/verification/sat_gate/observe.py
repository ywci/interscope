# src/isir/verification/sat_gate/observe.py
#
# Observability metrics (§18).  Coverage and firing rate are ALWAYS reported as
# a pair: coverage is the honest number, firing rate is only a plumbing check.
"""Gate observability: coverage + firing rate + counters."""

from dataclasses import dataclass, field
from typing import Dict, Tuple


@dataclass
class GateMetrics:
    eligible_pre: int = 0       # obligations at the hook, before filtering
    gateable: int = 0           # passed IR parse + fragment + cost guards
    calls: int = 0              # gate invocations
    status_histogram: Dict[str, int] = field(default_factory=dict)
    unknown_reasons: Dict[str, int] = field(default_factory=dict)
    hard_actions: Dict[str, int] = field(default_factory=dict)
    park_count: int = 0
    resurrect_count: int = 0
    cert_pending: int = 0
    cert_reuse_count: int = 0
    backpressure: int = 0

    def coverage(self) -> float:
        return (self.gateable / self.eligible_pre) if self.eligible_pre else 0.0

    def firing_rate(self) -> float:
        return (self.calls / self.gateable) if self.gateable else 0.0

    def coverage_firing_pair(self) -> Tuple[float, float]:
        """The honest pair: (coverage, firing_rate)."""
        return (self.coverage(), self.firing_rate())

    def record_call(self, status: str) -> None:
        self.calls += 1
        self.status_histogram[status] = self.status_histogram.get(status, 0) + 1

    def record_unknown(self, reason: str) -> None:
        self.unknown_reasons[reason] = self.unknown_reasons.get(reason, 0) + 1
