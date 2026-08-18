# src/specir/dialects/spec_ir.py
#
# Spec IR dialect – defines base classes and spec-level operations
# (spec.state, spec.rule, spec.property, spec.directive).
# This is the highest-level dialect in the SpecIR lowering pipeline.

from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field


class Dialect:
    """Base class for a dialect."""
    name: str


class Type:
    """Base class for types in the IR."""
    pass


@dataclass
class Operation:
    """
    Base class for all operations in the IR.

    Subclasses **must** define a class attribute `op_name` that identifies
    the dialect operation (e.g. ``op_name = "spec.state"``).
    """
    operands: List[Any] = field(default_factory=list)
    attributes: Dict[str, Any] = field(default_factory=dict)
    result_types: List[Type] = field(default_factory=list)

    @property
    def name(self) -> str:
        """Canonical operation name (delegates to the subclass `op_name`)."""
        return self.op_name

    def __str__(self) -> str:
        return f"{self.name}({', '.join(str(o) for o in self.operands)})"


class SpecDialect(Dialect):
    name = "spec"


class StateType(Type):
    pass


class RuleType(Type):
    pass


class PropertyType(Type):
    pass


class DirectiveType(Type):
    pass


@dataclass
class SpecStateOp(Operation):
    """Declares a state element (register, memory, wire)."""
    op_name: str = "spec.state"

    state_name: str = ""
    kind: str = ""  # register, memory, wire
    data_type: str = ""  # "bits<8>", "int", "bool", etc.
    initial: Optional[Any] = None
    attributes: List[str] = field(default_factory=list)


@dataclass
class SpecRuleOp(Operation):
    """Defines a rule with condition and actions."""
    op_name: str = "spec.rule"

    rule_name: str = ""
    condition: Optional[str] = None  # S‑expression string
    actions: List[str] = field(default_factory=list)  # list of S‑expression strings
    priority: Optional[int] = None
    rule_attributes: List[str] = field(default_factory=list)  # atomic, speculative, commutative


@dataclass
class SpecPropertyOp(Operation):
    """Defines a temporal property."""
    op_name: str = "spec.property"

    prop_name: str = ""
    kind: str = "safety"  # safety, liveness, invariant
    expression: Dict[str, Any] = field(default_factory=dict)  # TemporalExpr as dict
    assumes: List[str] = field(default_factory=list)
    guarantees: List[str] = field(default_factory=list)


@dataclass
class SpecDirectiveOp(Operation):
    """Verification directive (assume, assert, cover)."""
    op_name: str = "spec.directive"

    directive_name: str = ""
    kind: str = ""  # assume, assert, cover
    expression: str = ""
    clock: Optional[str] = None
    severity: str = "error"  # for assert directives


@dataclass
class SpecScheduleOp(Operation):
    """Defines concurrency schedule."""
    op_name: str = "spec.schedule"

    kind: str = "parallel"  # parallel, sequential, conflict_free
    rule_order: List[str] = field(default_factory=list)
    conflict_sets: List[List[str]] = field(default_factory=list)


@dataclass
class Interface:
    """Interface signal (input/output/inout).

    The field ``data_type`` holds the canonical type string (e.g. ``"bits<8>"``).
    It is populated from the YAML key ``type`` by the AST‑to‑Spec converter.
    """
    name: str
    direction: str                       # input, output, inout
    data_type: str                       # "bits<8>", "bool", etc.
    protocol: Optional[str] = None       # ready_valid, handshake, fixed_cycle, none


@dataclass
class SpecModule:
    """Container for a complete design in the spec dialect."""
    name: str
    version: str = "0.1"
    parameters: Dict[str, Any] = field(default_factory=dict)
    clocks: List[Dict[str, Any]] = field(default_factory=list)
    resets: List[Dict[str, Any]] = field(default_factory=list)
    inputs: List[Interface] = field(default_factory=list)
    outputs: List[Interface] = field(default_factory=list)
    types: List[Dict[str, Any]] = field(default_factory=list)          # user-defined types
    components: List[Dict[str, Any]] = field(default_factory=list)     # hierarchical instances
    fairness: List[Dict[str, Any]] = field(default_factory=list)       # fairness constraints
    state_ops: List[SpecStateOp] = field(default_factory=list)
    rule_ops: List[SpecRuleOp] = field(default_factory=list)
    property_ops: List[SpecPropertyOp] = field(default_factory=list)
    directive_ops: List[SpecDirectiveOp] = field(default_factory=list)
    schedule_op: Optional[SpecScheduleOp] = None
    proof_obligations: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        lines = [f"spec.module @{self.name} {{"]
        for state in self.state_ops:
            lines.append(f"  {state}")
        for rule in self.rule_ops:
            lines.append(f"  {rule}")
        for prop in self.property_ops:
            lines.append(f"  {prop}")
        for directive in self.directive_ops:
            lines.append(f"  {directive}")
        if self.schedule_op:
            lines.append(f"  {self.schedule_op}")
        lines.append("}")
        return "\n".join(lines)
