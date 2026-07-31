# src/specir/verification/perf/perf_config.py
#
# PERF (Proof tree Exploration with Reflective Feedback) configuration.
# Defines the configuration dataclass, validation logic, and loading from
# the global config.yaml or per-obligation metadata.

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Set
from pathlib import Path
from specir.utils.logger import get_logger

logger = get_logger(__name__)

# Valid Pareto dimensions recognized by PERF
VALID_DIMENSIONS: Set[str] = {
    "subgoal_reduction",    # Number of Coq subgoals closed relative to parent
    "trace_alignment",      # How well the proof handles the MC counterexample trace
    "syntactic_purity",     # Tie-breaker: prefers simpler, non-invasive repairs
    "correctness",          # General correctness (fallback)
    "completeness",         # Completeness of the proof (fallback)
    "progress",             # Whether the proof moves toward the goal (fallback)
}

DEFAULT_DIMENSIONS: List[str] = [
    "subgoal_reduction",
    "trace_alignment",
    "syntactic_purity",
]


@dataclass
class PERFConfig:
    """
    Configuration for PERF (Proof tree Exploration with Reflective Feedback).

    All fields have sensible defaults. Values can be overridden at the
    obligation level via metadata.perf in the .specir file.

    Attributes:
        enabled: Whether PERF is globally enabled.
        beam_size: Number of proof strategies to keep per depth (B).
        branches_per_node: Number of divergent repair attempts per failed proof (N).
        depth_limit: Maximum refinement iterations (L).
        dimensions: Pareto dimensions for scoring (D).
        scoring_tournament_size: Number of nodes each candidate is compared against.
        generation_temperature: LLM temperature for generating child proof scripts.
        always_verify_children: Whether to verify every generated child with the tool.
        max_workers: Maximum number of parallel workers for node evaluation.
        timeout_per_node: Timeout in seconds for a single node verification.
        primary_dimension: Which dimension is used for tie-breaking when selecting the beam.
        trace_alignment_weight: Weight for trace_alignment dimension (0.0-1.0).
        use_proof_library: Whether to allow PROOF_LIBRARY cache (PERF disables it).
        try_skeleton_first: Whether to attempt a fast skeleton proof before PERF.
    """

    # Core settings
    enabled: bool = False
    beam_size: int = 3
    branches_per_node: int = 4
    depth_limit: int = 3
    dimensions: List[str] = field(default_factory=lambda: DEFAULT_DIMENSIONS.copy())

    # Scoring settings
    scoring_tournament_size: int = 2
    generation_temperature: float = 0.4

    # Verification settings
    always_verify_children: bool = True
    max_workers: int = 4
    timeout_per_node: int = 300

    # Tie-breaking and weighting
    primary_dimension: str = "subgoal_reduction"
    trace_alignment_weight: float = 0.6

    # Library conflict
    use_proof_library: bool = False

    # Fast‑path: try a skeleton proof before launching PERF
    try_skeleton_first: bool = False

    def __post_init__(self) -> None:
        """Validate the configuration after initialization."""
        self.validate()

    def validate(self) -> None:
        """
        Validate all configuration values.

        Raises:
            ValueError: If any configuration value is invalid.
        """
        # Core settings
        if self.beam_size < 1:
            raise ValueError(f"beam_size must be >= 1, got {self.beam_size}")
        if self.branches_per_node < 1:
            raise ValueError(
                f"branches_per_node must be >= 1, got {self.branches_per_node}"
            )
        if self.depth_limit < 1:
            raise ValueError(f"depth_limit must be >= 1, got {self.depth_limit}")
        if not self.dimensions:
            raise ValueError("dimensions list cannot be empty")

        # Check all dimensions are valid
        for dim in self.dimensions:
            if dim not in VALID_DIMENSIONS:
                raise ValueError(
                    f"Invalid dimension '{dim}'. "
                    f"Valid dimensions: {sorted(VALID_DIMENSIONS)}"
                )

        # Primary dimension can be outside dimensions;
        # get_effective_dimensions will prepend it if needed.
        # No validation error required.

        # Scoring settings
        if self.scoring_tournament_size < 1:
            raise ValueError(
                f"scoring_tournament_size must be >= 1, got {self.scoring_tournament_size}"
            )
        if not 0.0 <= self.generation_temperature <= 1.0:
            raise ValueError(
                f"generation_temperature must be between 0.0 and 1.0, "
                f"got {self.generation_temperature}"
            )

        # Verification settings
        if self.max_workers < 1:
            raise ValueError(f"max_workers must be >= 1, got {self.max_workers}")
        if self.timeout_per_node < 1:
            raise ValueError(
                f"timeout_per_node must be >= 1, got {self.timeout_per_node}"
            )

        # Weight settings
        if not 0.0 <= self.trace_alignment_weight <= 1.0:
            raise ValueError(
                f"trace_alignment_weight must be between 0.0 and 1.0, "
                f"got {self.trace_alignment_weight}"
            )

        # try_skeleton_first is a bool, no further validation needed

    def to_dict(self) -> Dict[str, Any]:
        """Convert the configuration to a dictionary for serialization."""
        return {
            "enabled": self.enabled,
            "beam_size": self.beam_size,
            "branches_per_node": self.branches_per_node,
            "depth_limit": self.depth_limit,
            "dimensions": self.dimensions.copy(),
            "scoring_tournament_size": self.scoring_tournament_size,
            "generation_temperature": self.generation_temperature,
            "always_verify_children": self.always_verify_children,
            "max_workers": self.max_workers,
            "timeout_per_node": self.timeout_per_node,
            "primary_dimension": self.primary_dimension,
            "trace_alignment_weight": self.trace_alignment_weight,
            "use_proof_library": self.use_proof_library,
            "try_skeleton_first": self.try_skeleton_first,
        }

    @classmethod
    def from_global_config(cls, config: Dict[str, Any]) -> "PERFConfig":
        """
        Load PERF configuration from the global config.yaml.

        Args:
            config: The full configuration dictionary (from config_loader).

        Returns:
            A validated PERFConfig instance.
        """
        perf_cfg = config.get("proof", {}).get("perf", {})

        # Check for the use_proof_library conflict
        use_library = config.get("provers", {}).get("koika", {}).get(
            "use_proof_library", True
        )
        perf_enabled = perf_cfg.get("enabled", False)

        if perf_enabled and use_library:
            logger.warning(
                "PERF is enabled but use_proof_library is also true. "
                "PERF will disable the proof library to prevent cache bypass."
            )

        return cls(
            enabled=perf_enabled,
            beam_size=perf_cfg.get("beam_size", 3),
            branches_per_node=perf_cfg.get("branches_per_node", 4),
            depth_limit=perf_cfg.get("depth_limit", 3),
            dimensions=perf_cfg.get("dimensions", DEFAULT_DIMENSIONS.copy()),
            scoring_tournament_size=perf_cfg.get("scoring_tournament_size", 2),
            generation_temperature=perf_cfg.get("generation_temperature", 0.4),
            always_verify_children=perf_cfg.get("always_verify_children", True),
            max_workers=perf_cfg.get("max_workers", 4),
            timeout_per_node=perf_cfg.get("timeout_per_node", 300),
            primary_dimension=perf_cfg.get("primary_dimension", "subgoal_reduction"),
            trace_alignment_weight=perf_cfg.get("trace_alignment_weight", 0.6),
            use_proof_library=False,  # PERF always disables the library
            try_skeleton_first=perf_cfg.get("try_skeleton_first", False),
        )

    @classmethod
    def from_obligation_metadata(
        cls,
        global_config: "PERFConfig",
        obligation_metadata: Dict[str, Any],
    ) -> "PERFConfig":
        """
        Merge obligation-level metadata overrides into the global PERF config.

        Args:
            global_config: The base PERF configuration.
            obligation_metadata: The metadata.perf dict from a proof obligation.

        Returns:
            A new PERFConfig instance with obligation-level overrides applied.
        """
        perf_override = obligation_metadata.get("perf", {})

        # Start with a copy of the global config
        kwargs = global_config.to_dict()

        # Override with obligation-level settings
        if "enabled" in perf_override:
            kwargs["enabled"] = perf_override["enabled"]
        if "beam_size" in perf_override:
            kwargs["beam_size"] = perf_override["beam_size"]
        if "branches_per_node" in perf_override:
            kwargs["branches_per_node"] = perf_override["branches_per_node"]
        if "depth_limit" in perf_override:
            kwargs["depth_limit"] = perf_override["depth_limit"]
        if "dimensions" in perf_override:
            kwargs["dimensions"] = perf_override["dimensions"]
        if "scoring_tournament_size" in perf_override:
            kwargs["scoring_tournament_size"] = perf_override["scoring_tournament_size"]
        if "generation_temperature" in perf_override:
            kwargs["generation_temperature"] = perf_override["generation_temperature"]
        if "always_verify_children" in perf_override:
            kwargs["always_verify_children"] = perf_override["always_verify_children"]
        if "max_workers" in perf_override:
            kwargs["max_workers"] = perf_override["max_workers"]
        if "timeout_per_node" in perf_override:
            kwargs["timeout_per_node"] = perf_override["timeout_per_node"]
        if "primary_dimension" in perf_override:
            kwargs["primary_dimension"] = perf_override["primary_dimension"]
        if "trace_alignment_weight" in perf_override:
            kwargs["trace_alignment_weight"] = perf_override["trace_alignment_weight"]
        if "try_skeleton_first" in perf_override:
            kwargs["try_skeleton_first"] = perf_override["try_skeleton_first"]

        # PERF always disables the proof library at the engine level
        kwargs["use_proof_library"] = False

        return cls(**kwargs)

    def get_effective_dimensions(self) -> List[str]:
        """
        Return the effective dimensions list for scoring.
        This ensures the primary dimension is included.
        """
        dims = self.dimensions.copy()
        if self.primary_dimension not in dims:
            # Insert primary dimension at the front
            dims.insert(0, self.primary_dimension)
        return dims

    def is_enabled_for_obligation(self, obligation: Dict[str, Any]) -> bool:
        """
        Check if PERF is enabled for a specific proof obligation.

        An obligation can enable PERF in two ways:
        1. The global config has perf.enabled = True
        2. The obligation's metadata.perf.enabled = True

        Args:
            obligation: The proof obligation dictionary.

        Returns:
            True if PERF should be used for this obligation.
        """
        # First check obligation-level override
        metadata = obligation.get("metadata", {})
        perf_override = metadata.get("perf", {})
        if "enabled" in perf_override:
            return bool(perf_override["enabled"])

        # Fall back to global config
        return self.enabled

    def __repr__(self) -> str:
        """Human-readable representation of the configuration."""
        return (
            f"PERFConfig(\n"
            f"  enabled={self.enabled},\n"
            f"  beam_size={self.beam_size},\n"
            f"  branches_per_node={self.branches_per_node},\n"
            f"  depth_limit={self.depth_limit},\n"
            f"  dimensions={self.dimensions},\n"
            f"  primary_dimension={self.primary_dimension},\n"
            f"  scoring_tournament_size={self.scoring_tournament_size},\n"
            f"  generation_temperature={self.generation_temperature},\n"
            f"  always_verify_children={self.always_verify_children},\n"
            f"  max_workers={self.max_workers},\n"
            f"  timeout_per_node={self.timeout_per_node},\n"
            f"  try_skeleton_first={self.try_skeleton_first},\n"
            f")"
        )


def validate_perf_against_config(config: Dict[str, Any]) -> None:
    """
    Validate the global configuration for PERF compatibility.

    This checks the critical conflict: PERF enabled with use_proof_library.

    Args:
        config: The full configuration dictionary.

    Raises:
        ValueError: If PERF is enabled but use_proof_library is also true.
    """
    perf_enabled = config.get("proof", {}).get("perf", {}).get("enabled", False)
    use_library = config.get("provers", {}).get("koika", {}).get(
        "use_proof_library", True
    )

    if perf_enabled and use_library:
        raise ValueError(
            "Configuration conflict: PERF enabled but use_proof_library is true.\n"
            "PERF requires 'provers.koika.use_proof_library: false' to prevent cache bypass.\n"
            "To fix:\n"
            "  - Set 'proof.perf.enabled: false' to disable PERF, OR\n"
            "  - Set 'provers.koika.use_proof_library: false' to enable PERF with library bypass."
        )


# Convenience function for quick access
def get_perf_config(config: Optional[Dict[str, Any]] = None) -> PERFConfig:
    """
    Get the PERF configuration from the global config.

    Args:
        config: Optional configuration dictionary. If None, loads from config_loader.

    Returns:
        A validated PERFConfig instance.
    """
    if config is None:
        from specir.utils.config_loader import get_config
        config = get_config()

    # Validate the global config for PERF compatibility
    validate_perf_against_config(config)

    return PERFConfig.from_global_config(config)
