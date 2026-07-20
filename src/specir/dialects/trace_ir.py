# src/specir/dialects/trace_ir.py
#
# Trace dialect – captures cycle-by-cycle simulation data (VCD, etc.)
# and supports lifting back to abstract SpecIR events.
# Provides operations: trace.module, trace.clock, trace.signal, trace.cycle,
# trace.value, trace.annotation.

from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

from specir.dialects.spec_ir import Dialect, Operation, Type


class TraceDialect(Dialect):
    name = "trace"


class TraceSignalType(Type):
    pass


class TraceCycleType(Type):
    pass


@dataclass
class TraceModuleOp(Operation):
    """Container for a simulation trace."""
    op_name: str = "trace.module"
    trace_name: str = ""

    def __str__(self) -> str:
        return f"trace.module @{self.trace_name}"


@dataclass
class TraceClockOp(Operation):
    """Defines the clock for the trace."""
    op_name: str = "trace.clock"
    clock_name: str = ""
    period: Optional[str] = None      # e.g., "10ns"
    edge: str = "posedge"             # posedge, negedge

    def __str__(self) -> str:
        period_str = f" period={self.period}" if self.period else ""
        return f"trace.clock @{self.clock_name} edge={self.edge}{period_str}"


@dataclass
class TraceSignalOp(Operation):
    """Declares a signal (RTL wire/reg) in the trace."""
    op_name: str = "trace.signal"
    signal_name: str = ""
    width: int = 1
    is_signed: bool = False

    def __str__(self) -> str:
        signed_str = " signed" if self.is_signed else ""
        return f"trace.signal @{self.signal_name} <{self.width}>{signed_str}"


@dataclass
class TraceCycleOp(Operation):
    """A time step (typically one clock cycle)."""
    op_name: str = "trace.cycle"
    cycle_number: int = 0

    def __str__(self) -> str:
        return f"trace.cycle {self.cycle_number}"


@dataclass
class TraceValueOp(Operation):
    """Value of a signal in a specific cycle."""
    op_name: str = "trace.value"
    signal_name: str = ""
    value: Any = None                 # int, bool, string for bit vectors

    def __str__(self) -> str:
        return f"trace.value @{self.signal_name} = {self.value}"


@dataclass
class TraceAnnotationOp(Operation):
    """Mapping from an RTL signal to a SpecIR element (for lifting)."""
    op_name: str = "trace.annotation"
    signal_name: str = ""
    specir_ref: str = ""              # e.g., "module.state[name=head]"
    kind: str = "register"            # register, memory, rule_condition, etc.

    def __str__(self) -> str:
        return f"trace.annotation @{self.signal_name} -> {self.specir_ref} ({self.kind})"


@dataclass
class TraceCycleData:
    """Internal data for one cycle: signal name -> value."""
    cycle: int
    values: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TraceModule:
    """Container for a simulation trace."""
    module_op: TraceModuleOp
    clock: Optional[TraceClockOp] = None
    signals: List[TraceSignalOp] = field(default_factory=list)
    annotations: List[TraceAnnotationOp] = field(default_factory=list)
    cycles: List[TraceCycleData] = field(default_factory=list)

    def add_cycle(self, cycle_num: int, values: Dict[str, Any]) -> None:
        """Add a cycle's worth of signal values."""
        self.cycles.append(TraceCycleData(cycle=cycle_num, values=values))

    def get_signal_value(self, signal_name: str, cycle: int) -> Optional[Any]:
        """Retrieve value of a signal at a given cycle."""
        for c in self.cycles:
            if c.cycle == cycle:
                return c.values.get(signal_name)
        return None

    def __str__(self) -> str:
        lines = [str(self.module_op), "{"]
        if self.clock:
            lines.append(f"  {self.clock}")
        for sig in self.signals:
            lines.append(f"  {sig}")
        for ann in self.annotations:
            lines.append(f"  {ann}")
        for cycle in self.cycles:
            lines.append(f"  trace.cycle {cycle.cycle}")
            for sig, val in cycle.values.items():
                lines.append(f"    trace.value @{sig} = {val}")
        lines.append("}")
        return "\n".join(lines)
