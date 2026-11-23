# src/isir/verification/sat_gate/gate_config.py
#
# Runtime gate configuration: enable flags and the kill switch.

from dataclasses import dataclass


@dataclass
class GateConfig:
    sat_gating_enabled: bool = True
    lemma_hints_enabled: bool = False
    kill_switch: bool = False

    def effective_enabled(self) -> bool:
        """The gate runs only when enabled and the kill switch is not tripped."""
        return self.sat_gating_enabled and not self.kill_switch

    def trip_kill_switch(self) -> None:
        self.kill_switch = True
