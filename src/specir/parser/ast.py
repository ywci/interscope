# src/specir/parser/ast.py
#
# Abstract Syntax Tree (AST) dataclasses for SpecIR.
# These classes represent the parsed structure of a .specir file.
# Revised: fixed evidence types to match JSON Schema and annotator usage.
# State.evidence and Rule.evidence are now single EvidenceRef (not lists).
# Property.evidence is List[EvidenceRef]. Module.evidence is List[Evidence].

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Union

@dataclass
class EvidenceRef:
    """Reference to an evidence artifact."""
    type: str                     # "uri" or "local_id"
    value: str


@dataclass
class Evidence:
    """Evidence attached to a SpecIR element (full object with engine, status)."""
    type: str                     # counterexample_trace, inductive_invariant, coq_theorem, etc.
    ref: EvidenceRef
    engine: str
    status: Optional[str] = None


@dataclass
class Candidate:
    """LLM‑generated candidate with confidence score (wraps any value)."""
    value: Any
    confidence: float
    source: Optional[str] = None
    alternatives: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class OneOf:
    """Ambiguity placeholder – LLM must resolve which alternative is correct."""
    alternatives: List[Any] = field(default_factory=list)
    resolution: Optional[str] = None   # "user" or "verification"


@dataclass
class Parameter:
    """Module parameter."""
    name: str
    type: str                     # int, bit, string
    default: Optional[Union[str, int, bool]] = None


@dataclass
class Clock:
    """Clock definition."""
    name: str
    edge: str                     # "posedge" or "negedge"
    period: Optional[str] = None   # e.g., "10ns"


@dataclass
class Reset:
    """Reset definition."""
    name: str
    polarity: str                 # "active_high" or "active_low"
    async_reset: bool             # asynchronous reset (Python keyword 'async' avoided)
    affects: Union[str, List[str]]   # "all" or list of state names


@dataclass
class Interface:
    """Input/output interface."""
    name: str
    direction: str                # "input", "output", "inout"
    type: Union[str, Dict]        # type spec (e.g., "bits<32>" or complex)
    protocol: Optional[str] = None  # "ready_valid", "handshake", "fixed_cycle", "none"


@dataclass
class UserType:
    """User-defined type (enum or struct)."""
    name: str
    kind: str                     # "enum" or "struct"
    values: Optional[List[str]] = None   # for enum
    fields: Optional[Dict[str, str]] = None  # for struct (name -> type)
    encoding: Optional[str] = None


@dataclass
class ComponentInstance:
    """Hierarchical component instantiation."""
    name: str
    module: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    port_map: Dict[str, str] = field(default_factory=dict)
    evidence: Optional[EvidenceRef] = None   # single evidence reference


@dataclass
class State:
    """State declaration (register, memory, wire)."""
    name: str
    kind: str                     # "register", "memory", "wire"
    type: Union[str, Dict]        # type specification
    initial: Optional[Any] = None
    attributes: List[str] = field(default_factory=list)  # stable, volatile, shadow
    evidence: Optional[EvidenceRef] = None   # single evidence reference


@dataclass
class Rule:
    """Rule definition."""
    name: str
    condition: Optional[Union[str, List]] = None   # S-expression
    action: List[Union[str, List]] = field(default_factory=list)  # list of write actions
    priority: Optional[int] = None
    attributes: List[str] = field(default_factory=list)   # atomic, speculative, commutative
    evidence: Optional[EvidenceRef] = None   # single evidence reference


@dataclass
class Directive:
    """Verification directive (assume, assert, cover)."""
    type: str                     # "assume", "assert", "cover"
    name: str
    expression: Union[str, List]
    clock: Optional[str] = None
    severity: Optional[str] = None   # "error", "warning" (for assert)


@dataclass
class TemporalExpr:
    """Temporal property expression."""
    kind: str                     # "always", "eventually", "until"
    operand: Optional[Union[str, List]] = None   # for always/eventually
    left: Optional[Union[str, List]] = None      # for until
    right: Optional[Union[str, List]] = None     # for until
    bound: Optional[int] = None


@dataclass
class Property:
    """Temporal property."""
    name: str
    kind: str                     # "safety", "liveness", "invariant"
    expression: TemporalExpr
    assumes: List[Union[str, List]] = field(default_factory=list)
    guarantees: List[Union[str, List]] = field(default_factory=list)
    proof_status: str = "unproved"
    evidence: List[EvidenceRef] = field(default_factory=list)   # list of evidence references


@dataclass
class Schedule:
    """Concurrency control schedule."""
    kind: str                     # "parallel", "sequential", "conflict_free"
    rule_order: List[str] = field(default_factory=list)
    conflict_sets: List[List[str]] = field(default_factory=list)


@dataclass
class Fairness:
    """Fairness constraint."""
    name: str
    type: str                     # "weak" or "strong"
    condition: Union[str, List]


@dataclass
class ProofObligationFeedback:
    """Iterative repair feedback entry."""
    iteration: int
    error: str
    resolution: str


@dataclass
class ProofObligation:
    """Link between a property and verification artifacts."""
    property: str
    status: str                   # unproved, proved, disproved, inconclusive
    engine: str                   # theorem_proving, model_checking, simulation
    backend: Optional[str] = None  # koika, acl2
    artifact: Optional[Dict[str, str]] = None   # {type, ref}
    assumes: List[Union[str, List]] = field(default_factory=list)
    guarantees: List[Union[str, List]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    confidence: Optional[float] = None
    feedback: List[ProofObligationFeedback] = field(default_factory=list)


@dataclass
class Metadata:
    """Engine-specific hints."""
    engine: Optional[str] = None
    options: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Module:
    """Top-level SpecIR module."""
    name: str
    version: Optional[str] = None
    parameters: List[Parameter] = field(default_factory=list)
    clocks: List[Clock] = field(default_factory=list)
    resets: List[Reset] = field(default_factory=list)
    inputs: List[Interface] = field(default_factory=list)
    outputs: List[Interface] = field(default_factory=list)
    types: List[UserType] = field(default_factory=list)
    components: List[ComponentInstance] = field(default_factory=list)
    state: List[State] = field(default_factory=list)
    rules: List[Rule] = field(default_factory=list)
    directives: List[Directive] = field(default_factory=list)
    properties: List[Property] = field(default_factory=list)
    schedule: Optional[Schedule] = None
    fairness: List[Fairness] = field(default_factory=list)
    proof_obligations: List[ProofObligation] = field(default_factory=list)
    metadata: Optional[Metadata] = None
    evidence: List[Evidence] = field(default_factory=list)   # list of full Evidence objects


@dataclass
class SpecIR:
    """Root of the SpecIR AST."""
    specir_version: str
    module: Module
    metadata: Optional[Metadata] = None
    evidence: List[Evidence] = field(default_factory=list)   # top-level evidence
