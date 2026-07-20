# src/specir/dialects/assert_ir.py
#
# Unified assert dialect – language-agnostic assertions for SVA, VHDL PSL, and Verilog OVL.
# Provides operations: assert.always, assert.sequence, assert.property, assert.assume,
# assert.cover, assert.clock, assert.reset.

from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from specir.dialects.spec_ir import Dialect, Operation, Type


class AssertDialect(Dialect):
    name = "assert"


class AssertPropertyType(Type):
    pass


class AssertSequenceType(Type):
    pass


@dataclass
class AssertAlwaysOp(Operation):
    """Boolean invariant checked every cycle."""
    name: str = "assert.always"
    condition: str = ""                # S‑expression string
    clock: Optional[str] = None
    reset: Optional[str] = None
    label: Optional[str] = None        # original property/directive name


@dataclass
class AssertSequenceOp(Operation):
    """Temporal sequence of events."""
    name: str = "assert.sequence"
    sequence: List[str] = field(default_factory=list)  # list of S‑expressions or events
    clock: Optional[str] = None
    reset: Optional[str] = None
    label: Optional[str] = None


@dataclass
class AssertPropertyOp(Operation):
    """Temporal property (always, eventually, until) with optional bound."""
    name: str = "assert.property"
    kind: str = "always"              # always, eventually, until
    operand: Optional[str] = None     # for always/eventually
    left: Optional[str] = None        # for until
    right: Optional[str] = None       # for until
    bound: Optional[int] = None
    clock: Optional[str] = None
    reset: Optional[str] = None
    label: Optional[str] = None


@dataclass
class AssertAssumeOp(Operation):
    """Environment constraint (assumption)."""
    name: str = "assert.assume"
    condition: str = ""
    clock: Optional[str] = None
    reset: Optional[str] = None
    label: Optional[str] = None


@dataclass
class AssertCoverOp(Operation):
    """Reachability target."""
    name: str = "assert.cover"
    condition: str = ""               # boolean or temporal expression
    clock: Optional[str] = None
    reset: Optional[str] = None
    label: Optional[str] = None


@dataclass
class AssertClockOp(Operation):
    """Declare default clock for subsequent assertions."""
    name: str = "assert.clock"
    clock_name: str = ""
    edge: str = "posedge"             # posedge or negedge
    label: Optional[str] = None


@dataclass
class AssertResetOp(Operation):
    """Declare reset condition for subsequent assertions."""
    name: str = "assert.reset"
    reset_condition: str = ""         # S‑expression (e.g., "(!rst_n)")
    label: Optional[str] = None


@dataclass
class AssertModule:
    """Container for a set of assertions."""
    name: str
    clock: Optional[AssertClockOp] = None
    reset: Optional[AssertResetOp] = None
    assumptions: List[AssertAssumeOp] = field(default_factory=list)
    always_checks: List[AssertAlwaysOp] = field(default_factory=list)
    sequences: List[AssertSequenceOp] = field(default_factory=list)
    properties: List[AssertPropertyOp] = field(default_factory=list)
    covers: List[AssertCoverOp] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        lines = [f"assert.module @{self.name} {{"]
        if self.clock:
            lines.append(f"  {self.clock}")
        if self.reset:
            lines.append(f"  {self.reset}")
        for a in self.assumptions:
            lines.append(f"  {a}")
        for c in self.always_checks:
            lines.append(f"  {c}")
        for s in self.sequences:
            lines.append(f"  {s}")
        for p in self.properties:
            lines.append(f"  {p}")
        for cv in self.covers:
            lines.append(f"  {cv}")
        lines.append("}")
        return "\n".join(lines)


def from_spec_module(spec_module) -> AssertModule:
    """
    Convert a SpecModule (from spec dialect) into an AssertModule.
    This is a placeholder; actual implementation will map spec.state, spec.rule,
    spec.property to assert operations.
    """
    raise NotImplementedError("Conversion from SpecModule to AssertModule not yet implemented")
