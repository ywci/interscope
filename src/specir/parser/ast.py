# src/specir/parser/ast.py
#
# Abstract Syntax Tree (AST) dataclasses for SpecIR.
# These classes represent the parsed structure of a .specir file.

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Union


@dataclass
class EvidenceRef:
    """Reference to an evidence artifact."""
    type: str  # "uri" or "local_id"
    value: str


@dataclass
class Evidence:
    """Evidence attached to a SpecIR element (full object with engine, status)."""
    type: str  # counterexample_trace, inductive_invariant, coq_theorem, etc.
    ref: EvidenceRef
    engine: str
    status: Optional[str] = None


@dataclass
class Candidate:
    """LLM-generated candidate with confidence score (wraps any value)."""
    value: Any
    confidence: float
    source: Optional[str] = None
    alternatives: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class OneOf:
    """Ambiguity placeholder – LLM must resolve which alternative is correct."""
    alternatives: List[Any] = field(default_factory=list)
    resolution: Optional[str] = None  # "user" or "verification"


@dataclass
class Parameter:
    """Module parameter."""
    name: str
    type: str  # int, bit, string
    default: Optional[Union[str, int, bool]] = None


@dataclass
class Clock:
    """Clock definition."""
    name: str
    edge: str  # "posedge" or "negedge"
    period: Optional[str] = None  # e.g., "10ns"


@dataclass
class Reset:
    """Reset definition."""
    name: str
    polarity: str  # "active_high" or "active_low"
    async_reset: bool  # asynchronous reset (Python keyword 'async' avoided)
    affects: Union[str, List[str]]  # "all" or list of state names


@dataclass
class Interface:
    """Input/output interface."""
    name: str
    direction: str  # "input", "output", "inout"
    type: Union[str, Dict]  # type spec (e.g., "bits<32>" or complex)
    protocol: Optional[str] = None  # "ready_valid", "handshake", "fixed_cycle", "none"


@dataclass
class UserType:
    """User-defined type (enum or struct)."""
    name: str
    kind: str  # "enum" or "struct"
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
    evidence: Optional[EvidenceRef] = None  # single evidence reference


@dataclass
class State:
    """State declaration (register, memory, wire)."""
    name: str
    kind: str  # "register", "memory", "wire"
    type: Union[str, Dict]  # type specification
    initial: Optional[Any] = None
    attributes: List[str] = field(default_factory=list)  # stable, volatile, shadow
    evidence: Optional[EvidenceRef] = None  # single evidence reference


@dataclass
class Rule:
    """Rule definition."""
    name: str
    condition: Optional[Union[str, List]] = None  # S-expression
    action: List[Union[str, List]] = field(default_factory=list)  # list of write actions
    priority: Optional[int] = None
    attributes: List[str] = field(default_factory=list)  # atomic, speculative, commutative
    evidence: Optional[EvidenceRef] = None  # single evidence reference


@dataclass
class Directive:
    """Verification directive (assume, assert, cover)."""
    type: str  # "assume", "assert", "cover"
    name: str
    expression: Union[str, List]
    clock: Optional[str] = None
    severity: Optional[str] = None  # "error", "warning" (for assert)


@dataclass
class TemporalExpr:
    """Temporal property expression."""
    kind: str  # "always", "eventually", "until"
    operand: Optional[Union[str, List]] = None  # for always/eventually
    left: Optional[Union[str, List]] = None  # for until
    right: Optional[Union[str, List]] = None  # for until
    bound: Optional[int] = None


@dataclass
class Property:
    """Temporal property."""
    name: str
    kind: str  # "safety", "liveness", "invariant"
    expression: TemporalExpr
    assumes: List[Union[str, List]] = field(default_factory=list)
    guarantees: List[Union[str, List]] = field(default_factory=list)
    proof_status: str = "unproved"
    evidence: List[EvidenceRef] = field(default_factory=list)


@dataclass
class Schedule:
    """Concurrency control schedule."""
    kind: str  # "parallel", "sequential", "conflict_free"
    rule_order: List[str] = field(default_factory=list)
    conflict_sets: List[List[str]] = field(default_factory=list)


@dataclass
class Fairness:
    """Fairness constraint."""
    name: str
    type: str  # "weak" or "strong"
    condition: Union[str, List]


@dataclass
class ProofObligationFeedback:
    """Iterative repair feedback entry."""
    iteration: int
    error: str
    resolution: str


@dataclass
class ProofObligation:
    """
    Link between a property and verification artifacts.

    PERF (Proof tree Exploration with Reflective Feedback) support:
    The PERF-specific fields allow per-obligation overrides of the global
    PERF configuration. If a field is None, the global PERF config value
    is used instead.

    Fields:
        property: Name of the property to prove.
        status: unproved, proved, disproved, inconclusive.
        engine: theorem_proving, model_checking, simulation, or perf.
        backend: koika, acl2 (required for theorem_proving/perf).
        artifact: Optional {type, ref} pointing to proof artifact.
        assumes: Additional assumptions for this proof.
        guarantees: Additional guarantees for this proof.
        metadata: Freeform metadata (includes PERF overrides).
        confidence: LLM confidence score (0.0-1.0).
        feedback: Iterative repair history.

        PERF-specific overrides (all optional):
        perf_beam_size: Number of proof strategies to keep per depth.
        perf_branches: Number of divergent repair attempts per failed proof.
        perf_depth_limit: Maximum refinement iterations.
        perf_primary_dimension: Which Pareto dimension drives beam selection.
        perf_dimensions: List of Pareto dimensions for scoring.
        perf_generation_temperature: LLM temperature for generating children.
        perf_trace_alignment_weight: Weight for trace_alignment dimension (0.0-1.0).
    """
    property: str
    status: str                    # unproved, proved, disproved, inconclusive
    engine: str                    # theorem_proving, model_checking, simulation, perf
    backend: Optional[str] = None  # koika, acl2
    artifact: Optional[Dict[str, str]] = None  # {type, ref}
    assumes: List[Union[str, List]] = field(default_factory=list)
    guarantees: List[Union[str, List]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    confidence: Optional[float] = None
    feedback: List[ProofObligationFeedback] = field(default_factory=list)

    # PERF-specific per-obligation overrides (all optional)
    perf_beam_size: Optional[int] = None
    perf_branches: Optional[int] = None
    perf_depth_limit: Optional[int] = None
    perf_primary_dimension: Optional[str] = None
    perf_dimensions: Optional[List[str]] = None
    perf_generation_temperature: Optional[float] = None
    perf_trace_alignment_weight: Optional[float] = None

    def __post_init__(self) -> None:
        """Validate PERF fields if they are set."""
        # Validate beam_size
        if self.perf_beam_size is not None and self.perf_beam_size < 1:
            raise ValueError(f"perf_beam_size must be >= 1, got {self.perf_beam_size}")

        # Validate branches
        if self.perf_branches is not None and self.perf_branches < 1:
            raise ValueError(f"perf_branches must be >= 1, got {self.perf_branches}")

        # Validate depth_limit
        if self.perf_depth_limit is not None and self.perf_depth_limit < 1:
            raise ValueError(f"perf_depth_limit must be >= 1, got {self.perf_depth_limit}")

        # Validate temperature
        if self.perf_generation_temperature is not None:
            if not 0.0 <= self.perf_generation_temperature <= 1.0:
                raise ValueError(
                    f"perf_generation_temperature must be between 0.0 and 1.0, "
                    f"got {self.perf_generation_temperature}"
                )

        # Validate weight
        if self.perf_trace_alignment_weight is not None:
            if not 0.0 <= self.perf_trace_alignment_weight <= 1.0:
                raise ValueError(
                    f"perf_trace_alignment_weight must be between 0.0 and 1.0, "
                    f"got {self.perf_trace_alignment_weight}"
                )

        # Validate dimensions (if provided, check they are non-empty)
        if self.perf_dimensions is not None:
            if not self.perf_dimensions:
                raise ValueError("perf_dimensions list cannot be empty")
            # Check that all dimensions are strings
            for dim in self.perf_dimensions:
                if not isinstance(dim, str):
                    raise ValueError(
                        f"perf_dimensions must contain strings, got {type(dim)}"
                    )

        # Validate primary dimension is in dimensions (if both set)
        if (self.perf_primary_dimension is not None and
            self.perf_dimensions is not None and
            self.perf_primary_dimension not in self.perf_dimensions):
            raise ValueError(
                f"perf_primary_dimension '{self.perf_primary_dimension}' must be "
                f"one of perf_dimensions: {self.perf_dimensions}"
            )

    def to_perf_overrides(self) -> Dict[str, Any]:
        """
        Extract PERF overrides as a dictionary for merging with global config.

        Returns:
            Dictionary with PERF override keys, excluding None values.
        """
        result = {}
        if self.perf_beam_size is not None:
            result["beam_size"] = self.perf_beam_size
        if self.perf_branches is not None:
            result["branches_per_node"] = self.perf_branches
        if self.perf_depth_limit is not None:
            result["depth_limit"] = self.perf_depth_limit
        if self.perf_primary_dimension is not None:
            result["primary_dimension"] = self.perf_primary_dimension
        if self.perf_dimensions is not None:
            result["dimensions"] = self.perf_dimensions
        if self.perf_generation_temperature is not None:
            result["generation_temperature"] = self.perf_generation_temperature
        if self.perf_trace_alignment_weight is not None:
            result["trace_alignment_weight"] = self.perf_trace_alignment_weight
        return result


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
    evidence: List[Evidence] = field(default_factory=list)


@dataclass
class SpecIR:
    """Root of the SpecIR AST."""
    specir_version: str
    module: Module
    metadata: Optional[Metadata] = None
    evidence: List[Evidence] = field(default_factory=list)
