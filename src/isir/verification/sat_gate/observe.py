# src/isir/verification/sat_gate/observe.py
#
# Observability metrics. Coverage and firing rate are ALWAYS reported as
# a pair: coverage is the honest number, firing rate is only a plumbing check.

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
    resurrect_lost: int = 0
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

    def firing_rate_flagged(self, threshold: float = 0.01) -> bool:
        """Eligible-but-idle flag: eligible obligations exist but the gate
        (almost) never fires — a silent-no-op wiring symptom, not an honest
        low rate."""
        return self.eligible_pre > 0 and self.firing_rate() < threshold

    def record_park(self) -> None:
        self.park_count += 1

    def record_resurrect(self, provable: bool) -> None:
        """Record a forced-resurrection probe: ``provable`` means the parked
        obligation was still provable (no completeness loss)."""
        self.resurrect_count += 1
        if not provable:
            self.resurrect_lost += 1

    def park_precision(self) -> float:
        """: the fraction of forced-resurrected parks that lost nothing.

        Measured only on the forced-resurrection sample; 1.0 when no sample yet.
        """
        if not self.resurrect_count:
            return 1.0
        return (self.resurrect_count - self.resurrect_lost) / self.resurrect_count


class DisableRegistry:
    """Tracks disabled classes + the re-probe schedule.

    A class disabled on ERROR is completeness-critical (T1) and MUST be
    periodically re-probed; on the first successful re-probe it is re-enabled
    with a loud log and the re-probe count is recorded.
    """

    def __init__(self, reprobe_interval_steps: int) -> None:
        self.reprobe_interval_steps = reprobe_interval_steps
        self._disabled: Dict[str, Dict[str, object]] = {}
        self.count = 0       # disable_class.count
        self.reprobe_count = 0  # disable_class.reprobe_count

    def disable(self, class_id: str, reason: str, current_step: int = 0) -> None:
        self._disabled[class_id] = {
            "reason": reason, "last_probe_step": current_step, "reprobe_count": 0,
        }
        self.count += 1

    def is_disabled(self, class_id: str) -> bool:
        return class_id in self._disabled

    def reprobe_due(self, class_id: str, current_step: int) -> bool:
        if class_id not in self._disabled:
            return False
        d = self._disabled[class_id]
        return (current_step - int(d["last_probe_step"])) >= self.reprobe_interval_steps

    def record_reprobe(self, class_id: str, success: bool, current_step: int) -> bool:
        """Record a re-probe; return True iff the class was re-enabled."""
        d = self._disabled[class_id]
        d["reprobe_count"] = int(d["reprobe_count"]) + 1
        d["last_probe_step"] = current_step
        self.reprobe_count += 1
        if success:
            del self._disabled[class_id]
            return True
        return False
