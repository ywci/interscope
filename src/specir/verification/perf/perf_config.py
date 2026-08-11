# src/specir/verification/perf/perf_config.py
#
# PERF (Proof tree Exploration with Reflective Feedback) configuration.
# Defines the configuration dataclass, validation logic, and loading from
# the global config.yaml or per‑obligation metadata.

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Set
from pathlib import Path
from specir.utils.logger import get_logger

logger = get_logger(__name__)

# Valid Pareto dimensions recognized by PERF
VALID_DIMENSIONS: Set[str] = {
    "subgoal_reduction",    # Number of Coq subgoals closed relative to parent
    "trace_alignment",      # How well the proof handles the MC counterexample trace
    "syntactic_purity",     # Tie‑breaker: prefers simpler, non‑invasive repairs
    "correctness",          # General correctness (fallback)
    "completeness",         # Completeness of the proof (fallback)
    "progress",             # Whether the proof moves toward the goal (fallback)
}

DEFAULT_DIMENSIONS: List[str] = [
    "subgoal_reduction",
    "trace_alignment",
    "syntactic_purity",
]

# Sensible default diversity strategies – each is a short description that
# the LLM can use to differentiate proof attempts.
DEFAULT_DIVERSITY_STRATEGIES: List[str] = [
    "induction on reachable + auto/lia",
    "induction on reachable + destruct on step cases",
    "case analysis on conditions (remember/destruct)",
    "use available lemmas with rewrite and auto",
    "apply inversion and substitution, then lia/nia",
    "use functional induction instead of structural induction",
    "forward reasoning: assert a helper lemma first",
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
        primary_dimension: Which dimension is used for tie‑breaking when selecting the beam.
        trace_alignment_weight: Weight for trace_alignment dimension (0.0‑1.0).
        use_proof_library: Whether to allow PROOF_LIBRARY cache (PERF disables it).
        try_skeleton_first: Whether to attempt a fast skeleton proof before PERF.
        temperature_decay: If > 0, factor by which generation_temperature is
            multiplied after each depth (0.0 = no decay, 1.0 = constant).
        temperature_min: Minimum allowable generation temperature during decay.
        early_stop_patience: Number of consecutive depths with no Pareto
            improvement before halting the search early (0 = disabled).
        early_stop_min_improvement: Minimum relative improvement in the primary
            dimension score required to reset patience.
        use_template_generator: If True, include template‑based variants
            alongside LLM‑generated ones (or as a fallback when no LLM is available).
        max_tool_failures_before_fallback: Consecutive tool errors (e.g. “Unknown error”
            from rocq‑mcp) before PERF switches to the direct coqc verifier.
            0 = never fall back.
        enable_fast_failure_diagnostics: If True, after depth 2 with no observable
            progress PERF runs a diagnostic pass that may abort the search early
            with a human‑readable recommendation.
        coqc_timeout: Timeout (seconds) for the coqc fallback verifier.
        diversity_strategies: List of strategy descriptions used as diversity tags
            when generating proof variants.  The i‑th variant receives the i‑th tag
            (cycling if more variants than tags).  An empty list disables explicit
            strategy hints.
        unify_repair_and_generation: If True, when a parent has a known error,
            the LLM is asked in a single call to produce both a repair of the
            failed attempt and the requested number of divergent variants.
        parallel_variant_generation: If True, all LLM prompts for a generation
            step are submitted simultaneously via `generate_batch()` instead of
            sequentially.
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

    # Tie‑breaking and weighting
    primary_dimension: str = "subgoal_reduction"
    trace_alignment_weight: float = 0.6

    # Library conflict
    use_proof_library: bool = False

    # Fast‑path: try a skeleton proof before launching PERF
    try_skeleton_first: bool = False

    # Temperature scheduling
    temperature_decay: float = 0.0      # e.g., 0.9 → reduce to 90% each depth
    temperature_min: float = 0.1

    # Early stopping
    early_stop_patience: int = 0         # depths with no Pareto improvement before quitting
    early_stop_min_improvement: float = 0.01  # relative improvement threshold

    # Template generator
    use_template_generator: bool = False

    # Tool health / fast‑failure diagnostics
    max_tool_failures_before_fallback: int = 3
    enable_fast_failure_diagnostics: bool = True
    coqc_timeout: int = 300

    diversity_strategies: List[str] = field(default_factory=lambda: DEFAULT_DIVERSITY_STRATEGIES.copy())

    unify_repair_and_generation: bool = False
    parallel_variant_generation: bool = False

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

        # Temperature scheduling
        if not 0.0 <= self.temperature_decay <= 1.0:
            raise ValueError(
                f"temperature_decay must be between 0.0 and 1.0, "
                f"got {self.temperature_decay}"
            )
        if not 0.0 <= self.temperature_min <= 1.0:
            raise ValueError(
                f"temperature_min must be between 0.0 and 1.0, "
                f"got {self.temperature_min}"
            )
        if self.temperature_decay > 0 and self.temperature_min >= self.generation_temperature:
            raise ValueError(
                "temperature_min must be less than generation_temperature "
                "when decay is active"
            )

        # Early stopping
        if self.early_stop_patience < 0:
            raise ValueError(
                f"early_stop_patience must be >= 0, got {self.early_stop_patience}"
            )
        if self.early_stop_min_improvement < 0.0:
            raise ValueError(
                f"early_stop_min_improvement must be >= 0.0, "
                f"got {self.early_stop_min_improvement}"
            )

        # Tool health / fast‑failure
        if self.max_tool_failures_before_fallback < 0:
            raise ValueError(
                f"max_tool_failures_before_fallback must be >= 0, "
                f"got {self.max_tool_failures_before_fallback}"
            )
        if self.coqc_timeout < 1:
            raise ValueError(
                f"coqc_timeout must be >= 1, got {self.coqc_timeout}"
            )

        # Diversity strategies – optional but must be a list of strings
        if not isinstance(self.diversity_strategies, list):
            raise ValueError(
                f"diversity_strategies must be a list, got {type(self.diversity_strategies)}"
            )
        for idx, tag in enumerate(self.diversity_strategies):
            if not isinstance(tag, str):
                raise ValueError(
                    f"diversity_strategies[{idx}] must be a string, got {type(tag)}"
                )

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
            "temperature_decay": self.temperature_decay,
            "temperature_min": self.temperature_min,
            "early_stop_patience": self.early_stop_patience,
            "early_stop_min_improvement": self.early_stop_min_improvement,
            "use_template_generator": self.use_template_generator,
            "max_tool_failures_before_fallback": self.max_tool_failures_before_fallback,
            "enable_fast_failure_diagnostics": self.enable_fast_failure_diagnostics,
            "coqc_timeout": self.coqc_timeout,
            "diversity_strategies": self.diversity_strategies.copy(),
            "unify_repair_and_generation": self.unify_repair_and_generation,
            "parallel_variant_generation": self.parallel_variant_generation,
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

        diversity = perf_cfg.get("diversity_strategies", None)
        if diversity is None:
            diversity = DEFAULT_DIVERSITY_STRATEGIES.copy()
        else:
            diversity = list(diversity)

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
            temperature_decay=perf_cfg.get("temperature_decay", 0.0),
            temperature_min=perf_cfg.get("temperature_min", 0.1),
            early_stop_patience=perf_cfg.get("early_stop_patience", 0),
            early_stop_min_improvement=perf_cfg.get("early_stop_min_improvement", 0.01),
            use_template_generator=perf_cfg.get("use_template_generator", False),
            max_tool_failures_before_fallback=perf_cfg.get("max_tool_failures_before_fallback", 3),
            enable_fast_failure_diagnostics=perf_cfg.get("enable_fast_failure_diagnostics", True),
            coqc_timeout=perf_cfg.get("coqc_timeout", 300),
            diversity_strategies=diversity,
            unify_repair_and_generation=perf_cfg.get("unify_repair_and_generation", False),
            parallel_variant_generation=perf_cfg.get("parallel_variant_generation", False)
        )

    @classmethod
    def from_obligation_metadata(
        cls,
        global_config: "PERFConfig",
        obligation_metadata: Dict[str, Any]
    ) -> "PERFConfig":
        """
        Merge obligation‑level metadata overrides into the global PERF config.

        Args:
            global_config: The base PERF configuration.
            obligation_metadata: The metadata.perf dict from a proof obligation.

        Returns:
            A new PERFConfig instance with obligation‑level overrides applied.
        """
        perf_override = obligation_metadata.get("perf", {})

        kwargs = global_config.to_dict()

        for key in (
            "enabled", "beam_size", "branches_per_node", "depth_limit",
            "dimensions", "scoring_tournament_size", "generation_temperature",
            "always_verify_children", "max_workers", "timeout_per_node",
            "primary_dimension", "trace_alignment_weight", "try_skeleton_first",
            "temperature_decay", "temperature_min", "early_stop_patience",
            "early_stop_min_improvement", "use_template_generator",
            "max_tool_failures_before_fallback", "enable_fast_failure_diagnostics",
            "coqc_timeout", "diversity_strategies",
            "unify_repair_and_generation", "parallel_variant_generation"
        ):
            if key in perf_override:
                kwargs[key] = perf_override[key]

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
        metadata = obligation.get("metadata", {})
        perf_override = metadata.get("perf", {})
        if "enabled" in perf_override:
            return bool(perf_override["enabled"])

        return self.enabled

    def __repr__(self) -> str:
        """Human‑readable representation of the configuration."""
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
            f"  temperature_decay={self.temperature_decay},\n"
            f"  temperature_min={self.temperature_min},\n"
            f"  early_stop_patience={self.early_stop_patience},\n"
            f"  early_stop_min_improvement={self.early_stop_min_improvement},\n"
            f"  use_template_generator={self.use_template_generator},\n"
            f"  max_tool_failures_before_fallback={self.max_tool_failures_before_fallback},\n"
            f"  enable_fast_failure_diagnostics={self.enable_fast_failure_diagnostics},\n"
            f"  coqc_timeout={self.coqc_timeout},\n"
            f"  diversity_strategies={self.diversity_strategies},\n"
            f"  unify_repair_and_generation={self.unify_repair_and_generation},\n"
            f"  parallel_variant_generation={self.parallel_variant_generation},\n"
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

    validate_perf_against_config(config)

    return PERFConfig.from_global_config(config)
