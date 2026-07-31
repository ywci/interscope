# src/specir/dialects/trace_ir.py
#
# Trace dialect – captures cycle-by-cycle simulation data (VCD, etc.)
# and supports lifting back to abstract SpecIR events.
# Provides operations: trace.module, trace.clock, trace.signal, trace.cycle,
# trace.value, trace.annotation.

from typing import List, Dict, Any, Optional, Set, Tuple
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
    """
    Mapping from an RTL signal to a SpecIR element (for lifting).

    PERF-specific fields:
      - property_name: Name of the property this annotation relates to.
      - property_holds: Whether the property holds at this signal/cycle.
      - failing_cycle: The cycle where the property failed (if applicable).
      - details: Additional details about the property evaluation.
      - signal_group: The group this signal belongs to (control, data, state, etc.).
    """
    op_name: str = "trace.annotation"
    signal_name: str = ""
    specir_ref: str = ""              # e.g., "module.state[name=head]"
    kind: str = "register"            # register, memory, rule_condition, etc.

    # PERF-specific fields
    property_name: Optional[str] = None
    property_holds: Optional[bool] = None
    failing_cycle: Optional[int] = None
    details: Optional[str] = None
    signal_group: str = "state"       # "control", "data", "state", "input", "output"

    def __str__(self) -> str:
        base = f"trace.annotation @{self.signal_name} -> {self.specir_ref} ({self.kind})"
        if self.property_name:
            base += f" [prop={self.property_name}"
            if self.property_holds is not None:
                base += f", holds={self.property_holds}"
            if self.failing_cycle is not None:
                base += f", fail_cycle={self.failing_cycle}"
            base += "]"
        return base

    def to_json(self) -> Dict[str, Any]:
        """Export to JSON-serializable dict."""
        result = {
            "signal_name": self.signal_name,
            "specir_ref": self.specir_ref,
            "kind": self.kind,
            "signal_group": self.signal_group,
        }
        if self.property_name:
            result["property_name"] = self.property_name
        if self.property_holds is not None:
            result["property_holds"] = self.property_holds
        if self.failing_cycle is not None:
            result["failing_cycle"] = self.failing_cycle
        if self.details:
            result["details"] = self.details
        return result


@dataclass
class TraceCycleData:
    """Internal data for one cycle: signal name -> value."""
    cycle: int
    values: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TracePropertyEvaluation:
    """
    PERF-specific: Result of evaluating a property against a trace.

    Attributes:
        property_name: Name of the evaluated property.
        holds: Whether the property holds over the entire trace.
        failing_cycle: The first cycle where the property fails (if any).
        vacuous: Whether the property is vacuously true (assumption violation).
        details: Additional details about the evaluation.
    """
    property_name: str
    holds: bool
    failing_cycle: Optional[int] = None
    vacuous: bool = False
    details: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "property_name": self.property_name,
            "holds": self.holds,
            "failing_cycle": self.failing_cycle,
            "vacuous": self.vacuous,
            "details": self.details,
        }


@dataclass
class TraceModule:
    """
    Container for a simulation trace.

    PERF-specific fields:
      - property_evaluations: Results of property evaluations on this trace.
      - signal_groups: Mapping from group name to list of signal names.
    """
    module_op: TraceModuleOp
    clock: Optional[TraceClockOp] = None
    signals: List[TraceSignalOp] = field(default_factory=list)
    annotations: List[TraceAnnotationOp] = field(default_factory=list)
    cycles: List[TraceCycleData] = field(default_factory=list)

    # PERF-specific fields
    property_evaluations: List[TracePropertyEvaluation] = field(default_factory=list)
    signal_groups: Dict[str, List[str]] = field(default_factory=dict)

    def add_cycle(self, cycle_num: int, values: Dict[str, Any]) -> None:
        """Add a cycle's worth of signal values."""
        self.cycles.append(TraceCycleData(cycle=cycle_num, values=values))

    def get_signal_value(self, signal_name: str, cycle: int) -> Optional[Any]:
        """Retrieve value of a signal at a given cycle."""
        for c in self.cycles:
            if c.cycle == cycle:
                return c.values.get(signal_name)
        return None

    def get_all_values_at_cycle(self, cycle: int) -> Optional[Dict[str, Any]]:
        """Retrieve all signal values at a given cycle."""
        for c in self.cycles:
            if c.cycle == cycle:
                return c.values
        return None

    def add_property_evaluation(self, evaluation: TracePropertyEvaluation) -> None:
        """Add a property evaluation result to the trace."""
        self.property_evaluations.append(evaluation)

    def get_property_evaluation(self, property_name: str) -> Optional[TracePropertyEvaluation]:
        """Get the evaluation result for a specific property."""
        for eval_ in self.property_evaluations:
            if eval_.property_name == property_name:
                return eval_
        return None

    def get_failing_properties(self) -> List[TracePropertyEvaluation]:
        """Get all property evaluations that failed."""
        return [e for e in self.property_evaluations if not e.holds]

    def extract_failing_trace(
        self,
        property_name: str,
        window: int = 5,
    ) -> Dict[str, Any]:
        """
        Extract a window of cycles around a failure for PERF reflection.

        Args:
            property_name: Name of the failed property.
            window: Number of cycles before and after the failing cycle to include.

        Returns:
            A dictionary with:
              - property_name: The property name.
              - failing_cycle: The cycle where the failure occurred.
              - window_start: The first cycle in the window.
              - window_end: The last cycle in the window.
              - window: List of cycle data (cycle number and signal values).
              - signals_available: List of signal names available in the window.
              - property_details: Additional details about the failure.
        """
        eval_result = self.get_property_evaluation(property_name)
        if eval_result is None:
            return {
                "property_name": property_name,
                "error": f"Property '{property_name}' not evaluated on this trace",
                "window": [],
            }

        if eval_result.holds:
            return {
                "property_name": property_name,
                "error": f"Property '{property_name}' holds (no failure to extract)",
                "window": [],
            }

        failing_cycle = eval_result.failing_cycle
        if failing_cycle is None:
            # No specific cycle recorded; use the last cycle
            failing_cycle = len(self.cycles) - 1 if self.cycles else 0

        start = max(0, failing_cycle - window)
        end = min(len(self.cycles), failing_cycle + window + 1)

        window_data = []
        for i in range(start, end):
            cycle_data = self.get_all_values_at_cycle(i)
            if cycle_data is None:
                cycle_data = {}
            window_data.append({
                "cycle": i,
                "values": cycle_data,
            })

        # Get all signal names available in this window
        signals_available = set()
        for wd in window_data:
            signals_available.update(wd["values"].keys())

        return {
            "property_name": property_name,
            "failing_cycle": failing_cycle,
            "window_start": start,
            "window_end": end - 1,
            "window": window_data,
            "signals_available": sorted(signals_available),
            "property_details": eval_result.details,
            "vacuous": eval_result.vacuous,
        }

    def get_signals_by_group(self, group: str) -> List[str]:
        """
        Get signal names belonging to a specific group.

        Args:
            group: Group name ("control", "data", "state", "input", "output").

        Returns:
            List of signal names in that group.
        """
        if group in self.signal_groups:
            return self.signal_groups[group]

        # Build from annotations
        group_signals = [
            ann.signal_name for ann in self.annotations
            if ann.signal_group == group
        ]
        self.signal_groups[group] = group_signals
        return group_signals

    def get_all_signal_groups(self) -> Dict[str, List[str]]:
        """
        Get all signal groups with their signal names.

        Returns:
            Dictionary mapping group name to list of signal names.
        """
        if not self.signal_groups:
            # Build from annotations
            groups: Dict[str, List[str]] = {}
            for ann in self.annotations:
                group = ann.signal_group
                if group not in groups:
                    groups[group] = []
                groups[group].append(ann.signal_name)
            self.signal_groups = groups
        return self.signal_groups

    def filter_relevant_signals(self, relevant_signals: List[str]) -> "TraceModule":
        """
        Filter the trace to only include relevant signals.

        This is used by PERF to reduce the trace size for reflection.

        Args:
            relevant_signals: List of signal names to keep.

        Returns:
            A new TraceModule containing only the relevant signals.
        """
        import copy
        filtered = copy.deepcopy(self)

        # Convert to set for fast lookup
        keep_set = set(relevant_signals)

        # Filter signals
        filtered.signals = [
            s for s in self.signals
            if s.signal_name in keep_set
        ]

        # Filter annotations
        filtered.annotations = [
            a for a in self.annotations
            if a.signal_name in keep_set
        ]

        # Filter cycle values
        for cycle in filtered.cycles:
            cycle.values = {
                k: v for k, v in cycle.values.items()
                if k in keep_set
            }

        # Rebuild signal groups
        filtered.signal_groups = {}
        for ann in filtered.annotations:
            group = ann.signal_group
            if group not in filtered.signal_groups:
                filtered.signal_groups[group] = []
            filtered.signal_groups[group].append(ann.signal_name)

        return filtered

    def filter_by_group(self, group: str) -> "TraceModule":
        """
        Filter the trace to only include signals from a specific group.

        This is used by PERF to focus on control signals, data signals, etc.

        Args:
            group: Group name ("control", "data", "state", "input", "output").

        Returns:
            A new TraceModule containing only signals from the specified group.
        """
        relevant_signals = self.get_signals_by_group(group)
        return self.filter_relevant_signals(relevant_signals)

    def get_failing_window(
        self,
        property_name: str,
        window_size: int = 5,
        relevant_signals: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Convenience method: extract a failing window and optionally filter signals.

        Args:
            property_name: Name of the failed property.
            window_size: Number of cycles before/after the failure.
            relevant_signals: Optional list of signals to include.

        Returns:
            Dictionary with property evaluation data and filtered window.
        """
        result = self.extract_failing_trace(property_name, window=window_size)

        if relevant_signals:
            # Filter the window values to only include relevant signals
            keep_set = set(relevant_signals)
            filtered_window = []
            for wd in result.get("window", []):
                filtered_window.append({
                    "cycle": wd["cycle"],
                    "values": {k: v for k, v in wd["values"].items() if k in keep_set},
                })
            result["window"] = filtered_window
            result["signals_available"] = [s for s in result.get("signals_available", []) if s in keep_set]

        return result

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
            for sig, val in list(cycle.values.items())[:10]:  # show first 10
                lines.append(f"    trace.value @{sig} = {val}")
            if len(cycle.values) > 10:
                lines.append(f"    ... and {len(cycle.values) - 10} more signals")
        if self.property_evaluations:
            lines.append("")
            lines.append("  PERF property evaluations:")
            for eval_ in self.property_evaluations:
                status = "PASS" if eval_.holds else "FAIL"
                if eval_.vacuous:
                    status += " (vacuous)"
                lines.append(f"    {status}: {eval_.property_name}")
                if eval_.failing_cycle is not None:
                    lines.append(f"      fail_cycle={eval_.failing_cycle}")
        lines.append("}")
        return "\n".join(lines)
