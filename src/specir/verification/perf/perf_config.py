# src/specir/verification/perf/perf_config.py
#
# PERF (Proof tree Exploration with Reflective Feedback) configuration.
# Defines the configuration dataclass, validation logic, and loading from
# the global config.yaml or per‑obligation metadata.

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Set, Union
from specir.utils.logger import get_logger

logger = get_logger(__name__)

# Valid Pareto dimensions recognized by PERF
VALID_DIMENSIONS: Set[str] = {
    "subgoal_reduction",
    "trace_alignment",
    "syntactic_purity",
    "correctness",
    "completeness",
    "progress",
    "novelty",
    "structural_difference",
}

DEFAULT_DIMENSIONS: List[str] = [
    "subgoal_reduction",
    "trace_alignment",
    "syntactic_purity",
]

# Sensible default diversity strategies
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

    # Beam robustness and repair persistence
    min_beam_size: int = 2
    perf_light_repair_attempts: int = 2

    # Temperature scheduling
    temperature_decay: float = 0.0
    temperature_min: float = 0.1

    # Early stopping
    early_stop_patience: int = 0
    early_stop_min_improvement: float = 0.01

    # Template generator
    use_template_generator: bool = False

    # Tool health / fast‑failure diagnostics
    max_tool_failures_before_fallback: int = 3
    enable_fast_failure_diagnostics: bool = True
    coqc_timeout: int = 300

    diversity_strategies: List[str] = field(default_factory=lambda: DEFAULT_DIVERSITY_STRATEGIES.copy())

    unify_repair_and_generation: bool = False
    parallel_variant_generation: bool = False

    # NEW: Error history and adaptive branching
    error_history_enabled: bool = True
    error_history_max_entries: int = 200
    adaptive_branching_enabled: bool = True
    min_branches_for_hard_obligations: int = 6
    max_branches_for_hard_obligations: int = 12
    mc_guided_prompt_enabled: bool = False
    proof_pattern_cache_path: str = "build/perf_proof_patterns.json"

    # Backtracking (vertical reflection)
    backtracking_enabled: bool = False
    backtracking_stagnation_depth: int = 2
    backtracking_max_restarts: int = 3
    backtracking_max_backtrack_depth: int = 2
    backtracking_restore_beam_size: int = 3
    backtracking_avoid_repeated_branches: bool = True

    # Scoring enhancements for backtracking
    backtracking_store_all_scored_children: bool = True
    backtracking_diversity_dimensions: List[str] = field(default_factory=lambda: ["novelty", "structural_difference"])
    backtracking_diversity_weight: float = 0.3
    backtracking_alternate_primary_dimension: str = "syntactic_purity"
    backtracking_scoring_noise_std: float = 0.05
    backtracking_experience_penalty: bool = True

    # Forced regeneration after backtrack
    backtracking_force_regeneration: bool = True
    backtracking_regeneration_temperature_boost: float = 0.2
    backtracking_regeneration_strategy_hint: str = (
        "Previous proof attempts failed. Avoid the following common mistakes: "
        "1) Do not use reflexivity on hypotheses like 'false = true' – use discriminate instead. "
        "2) After inversion on the step hypothesis, destruct the nested conditionals (op_reg, etc.) "
        "   rather than applying the induction hypothesis directly. "
        "3) Use distinct case analysis for each branch of the operation."
    )

    # On‑demand backtracking triggers
    backtracking_on_demand_enabled: bool = False
    backtracking_on_demand_force_every: int = 0
    backtracking_on_demand_time_limit: float = 0.0
    backtracking_on_demand_max_same_error: int = 5
    backtracking_on_demand_skip_forced_regeneration: bool = True

    # Reflection quality assessment
    reflection_quality_window: int = 2
    min_reflection_quality: float = 0.2
    max_reflection_retries: int = 2
    reflection_quality_weights: Dict[str, float] = field(default_factory=lambda: {
        "primary_delta": 0.4,
        "error_shift": 0.2,
        "subgoal_reduction": 0.25,
        "diversity": 0.15,
    })

    # New backtracking enhancements
    backtrack_force_strategy_switch: bool = False
    backtrack_diversity_boost_after_stagnation: float = 0.2

    def __post_init__(self) -> None:
        """Validate the configuration after initialization."""
        self.validate()

    def validate(self) -> None:
        """Validate all configuration values."""
        # Core settings
        if self.beam_size < 1:
            raise ValueError(f"beam_size must be >= 1, got {self.beam_size}")
        if self.branches_per_node < 1:
            raise ValueError(f"branches_per_node must be >= 1, got {self.branches_per_node}")
        if self.depth_limit < 1:
            raise ValueError(f"depth_limit must be >= 1, got {self.depth_limit}")
        if not self.dimensions:
            raise ValueError("dimensions list cannot be empty")

        for dim in self.dimensions:
            if dim not in VALID_DIMENSIONS:
                raise ValueError(
                    f"Invalid dimension '{dim}'. Valid dimensions: {sorted(VALID_DIMENSIONS)}"
                )

        # Beam robustness and repair persistence
        if self.min_beam_size < 2:
            raise ValueError(f"min_beam_size must be at least 2, got {self.min_beam_size}")
        if self.perf_light_repair_attempts < 2:
            raise ValueError(
                f"perf_light_repair_attempts must be at least 2, got {self.perf_light_repair_attempts}"
            )

        # Scoring settings
        if self.scoring_tournament_size < 1:
            raise ValueError(f"scoring_tournament_size must be >= 1, got {self.scoring_tournament_size}")
        if not 0.0 <= self.generation_temperature <= 1.0:
            raise ValueError(
                f"generation_temperature must be between 0.0 and 1.0, got {self.generation_temperature}"
            )

        # Verification settings
        if self.max_workers < 1:
            raise ValueError(f"max_workers must be >= 1, got {self.max_workers}")
        if self.timeout_per_node < 1:
            raise ValueError(f"timeout_per_node must be >= 1, got {self.timeout_per_node}")

        # Weight settings
        if not 0.0 <= self.trace_alignment_weight <= 1.0:
            raise ValueError(
                f"trace_alignment_weight must be between 0.0 and 1.0, got {self.trace_alignment_weight}"
            )

        # Temperature scheduling
        if not 0.0 <= self.temperature_decay <= 1.0:
            raise ValueError(
                f"temperature_decay must be between 0.0 and 1.0, got {self.temperature_decay}"
            )
        if not 0.0 <= self.temperature_min <= 1.0:
            raise ValueError(
                f"temperature_min must be between 0.0 and 1.0, got {self.temperature_min}"
            )
        if self.temperature_decay > 0 and self.temperature_min >= self.generation_temperature:
            raise ValueError(
                "temperature_min must be less than generation_temperature when decay is active"
            )

        # Early stopping
        if self.early_stop_patience < 0:
            raise ValueError(f"early_stop_patience must be >= 0, got {self.early_stop_patience}")
        if self.early_stop_min_improvement < 0.0:
            raise ValueError(f"early_stop_min_improvement must be >= 0.0, got {self.early_stop_min_improvement}")

        # Tool health / fast‑failure
        if self.max_tool_failures_before_fallback < 0:
            raise ValueError(
                f"max_tool_failures_before_fallback must be >= 0, got {self.max_tool_failures_before_fallback}"
            )
        if self.coqc_timeout < 1:
            raise ValueError(f"coqc_timeout must be >= 1, got {self.coqc_timeout}")

        # Diversity strategies
        if not isinstance(self.diversity_strategies, list):
            raise ValueError(f"diversity_strategies must be a list, got {type(self.diversity_strategies)}")
        for idx, tag in enumerate(self.diversity_strategies):
            if not isinstance(tag, str):
                raise ValueError(f"diversity_strategies[{idx}] must be a string, got {type(tag)}")

        # NEW: Error history validation
        if not isinstance(self.error_history_enabled, bool):
            raise ValueError(f"error_history_enabled must be a bool, got {type(self.error_history_enabled)}")
        if self.error_history_max_entries < 1:
            raise ValueError(
                f"error_history_max_entries must be >= 1, got {self.error_history_max_entries}"
            )

        # NEW: Adaptive branching validation
        if not isinstance(self.adaptive_branching_enabled, bool):
            raise ValueError(f"adaptive_branching_enabled must be a bool, got {type(self.adaptive_branching_enabled)}")
        if self.min_branches_for_hard_obligations < 1:
            raise ValueError(
                f"min_branches_for_hard_obligations must be >= 1, got {self.min_branches_for_hard_obligations}"
            )
        if self.max_branches_for_hard_obligations < self.min_branches_for_hard_obligations:
            raise ValueError(
                f"max_branches_for_hard_obligations ({self.max_branches_for_hard_obligations}) must be >= "
                f"min_branches_for_hard_obligations ({self.min_branches_for_hard_obligations})"
            )

        # NEW: MC guided prompt validation
        if not isinstance(self.mc_guided_prompt_enabled, bool):
            raise ValueError(f"mc_guided_prompt_enabled must be a bool, got {type(self.mc_guided_prompt_enabled)}")

        # NEW: proof pattern cache path validation (basic string)
        if not isinstance(self.proof_pattern_cache_path, str):
            raise ValueError(
                f"proof_pattern_cache_path must be a string, got {type(self.proof_pattern_cache_path)}"
            )

        # Backtracking settings validation
        if self.backtracking_stagnation_depth < 1:
            raise ValueError(
                f"backtracking_stagnation_depth must be >= 1, got {self.backtracking_stagnation_depth}"
            )
        if self.backtracking_max_restarts < 0:
            raise ValueError(
                f"backtracking_max_restarts must be >= 0, got {self.backtracking_max_restarts}"
            )
        if self.backtracking_max_backtrack_depth < 0:
            raise ValueError(
                f"backtracking_max_backtrack_depth must be >= 0, got {self.backtracking_max_backtrack_depth}"
            )
        if self.backtracking_restore_beam_size < 1:
            raise ValueError(
                f"backtracking_restore_beam_size must be >= 1, got {self.backtracking_restore_beam_size}"
            )

        # Backtracking scoring enhancements validation
        if not 0.0 <= self.backtracking_diversity_weight <= 1.0:
            raise ValueError(
                f"backtracking_diversity_weight must be in [0.0, 1.0], got {self.backtracking_diversity_weight}"
            )
        if self.backtracking_scoring_noise_std < 0.0:
            raise ValueError(
                f"backtracking_scoring_noise_std must be >= 0.0, got {self.backtracking_scoring_noise_std}"
            )
        for dim in self.backtracking_diversity_dimensions:
            if dim not in VALID_DIMENSIONS:
                raise ValueError(
                    f"Invalid diversity dimension '{dim}'. Valid dimensions: {sorted(VALID_DIMENSIONS)}"
                )
        if self.backtracking_alternate_primary_dimension:
            if self.backtracking_alternate_primary_dimension not in VALID_DIMENSIONS:
                raise ValueError(
                    f"alternate_primary_dimension must be a valid dimension, "
                    f"got '{self.backtracking_alternate_primary_dimension}'"
                )

        # Forced regeneration validation
        if self.backtracking_regeneration_temperature_boost < 0.0:
            raise ValueError(
                f"backtracking_regeneration_temperature_boost must be >= 0.0, "
                f"got {self.backtracking_regeneration_temperature_boost}"
            )

        # On‑demand backtracking triggers validation
        if self.backtracking_on_demand_force_every < 0:
            raise ValueError(
                f"backtracking_on_demand_force_every must be >= 0, got {self.backtracking_on_demand_force_every}"
            )
        if self.backtracking_on_demand_time_limit < 0.0:
            raise ValueError(
                f"backtracking_on_demand_time_limit must be >= 0.0, got {self.backtracking_on_demand_time_limit}"
            )
        if self.backtracking_on_demand_max_same_error < 0:
            raise ValueError(
                f"backtracking_on_demand_max_same_error must be >= 0, got {self.backtracking_on_demand_max_same_error}"
            )

        # Reflection quality assessment validation
        if self.reflection_quality_window < 1:
            raise ValueError(
                f"reflection_quality_window must be >= 1, got {self.reflection_quality_window}"
            )
        if not 0.0 <= self.min_reflection_quality <= 1.0:
            raise ValueError(
                f"min_reflection_quality must be between 0.0 and 1.0, got {self.min_reflection_quality}"
            )
        if self.max_reflection_retries < 0:
            raise ValueError(
                f"max_reflection_retries must be >= 0, got {self.max_reflection_retries}"
            )

        # Reflection quality weights
        if not isinstance(self.reflection_quality_weights, dict):
            raise ValueError("reflection_quality_weights must be a dict")
        valid_keys = {"primary_delta", "error_shift", "subgoal_reduction", "diversity"}
        for key, val in self.reflection_quality_weights.items():
            if key not in valid_keys:
                raise ValueError(f"Invalid reflection weight key '{key}'")
            if not isinstance(val, (int, float)) or val < 0.0:
                raise ValueError(f"Reflection weight '{key}' must be a non‑negative number")

        # New backtracking enhancements validation
        if not 0.0 <= self.backtrack_diversity_boost_after_stagnation <= 1.0:
            raise ValueError(
                f"backtrack_diversity_boost_after_stagnation must be in [0.0, 1.0], "
                f"got {self.backtrack_diversity_boost_after_stagnation}"
            )

    def to_dict(self) -> Dict[str, Any]:
        """Convert the configuration to a flat dictionary for serialization."""
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
            "min_beam_size": self.min_beam_size,
            "perf_light_repair_attempts": self.perf_light_repair_attempts,
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
            # NEW
            "error_history_enabled": self.error_history_enabled,
            "error_history_max_entries": self.error_history_max_entries,
            "adaptive_branching_enabled": self.adaptive_branching_enabled,
            "min_branches_for_hard_obligations": self.min_branches_for_hard_obligations,
            "max_branches_for_hard_obligations": self.max_branches_for_hard_obligations,
            "mc_guided_prompt_enabled": self.mc_guided_prompt_enabled,
            "proof_pattern_cache_path": self.proof_pattern_cache_path,
            # Backtracking
            "backtracking_enabled": self.backtracking_enabled,
            "backtracking_stagnation_depth": self.backtracking_stagnation_depth,
            "backtracking_max_restarts": self.backtracking_max_restarts,
            "backtracking_max_backtrack_depth": self.backtracking_max_backtrack_depth,
            "backtracking_restore_beam_size": self.backtracking_restore_beam_size,
            "backtracking_avoid_repeated_branches": self.backtracking_avoid_repeated_branches,
            "backtracking_store_all_scored_children": self.backtracking_store_all_scored_children,
            "backtracking_diversity_dimensions": self.backtracking_diversity_dimensions.copy(),
            "backtracking_diversity_weight": self.backtracking_diversity_weight,
            "backtracking_alternate_primary_dimension": self.backtracking_alternate_primary_dimension,
            "backtracking_scoring_noise_std": self.backtracking_scoring_noise_std,
            "backtracking_experience_penalty": self.backtracking_experience_penalty,
            "backtracking_force_regeneration": self.backtracking_force_regeneration,
            "backtracking_regeneration_temperature_boost": self.backtracking_regeneration_temperature_boost,
            "backtracking_regeneration_strategy_hint": self.backtracking_regeneration_strategy_hint,
            # On‑demand backtracking
            "backtracking_on_demand_enabled": self.backtracking_on_demand_enabled,
            "backtracking_on_demand_force_every": self.backtracking_on_demand_force_every,
            "backtracking_on_demand_time_limit": self.backtracking_on_demand_time_limit,
            "backtracking_on_demand_max_same_error": self.backtracking_on_demand_max_same_error,
            "backtracking_on_demand_skip_forced_regeneration": self.backtracking_on_demand_skip_forced_regeneration,
            # Reflection quality assessment
            "reflection_quality_window": self.reflection_quality_window,
            "min_reflection_quality": self.min_reflection_quality,
            "max_reflection_retries": self.max_reflection_retries,
            "reflection_quality_weights": self.reflection_quality_weights.copy(),
            # New backtracking enhancements
            "backtrack_force_strategy_switch": self.backtrack_force_strategy_switch,
            "backtrack_diversity_boost_after_stagnation": self.backtrack_diversity_boost_after_stagnation,
        }

    @classmethod
    def from_global_config(cls, config: Dict[str, Any]) -> "PERFConfig":
        """
        Load PERF configuration from the global config.yaml.

        Supports both nested and flat keys for the new settings.
        """
        perf_cfg = config.get("proof", {}).get("perf", {})
        use_library = config.get("provers", {}).get("koika", {}).get("use_proof_library", True)
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

        error_history_cfg = perf_cfg.get("error_history", {})
        if isinstance(error_history_cfg, dict):
            error_history_enabled = error_history_cfg.get(
                "enabled", perf_cfg.get("error_history_enabled", True)
            )
            error_history_max_entries = error_history_cfg.get(
                "max_entries", perf_cfg.get("error_history_max_entries", 200)
            )
        else:
            error_history_enabled = perf_cfg.get("error_history_enabled", True)
            error_history_max_entries = perf_cfg.get("error_history_max_entries", 200)

        adaptive_cfg = perf_cfg.get("adaptive_branching", {})
        if isinstance(adaptive_cfg, dict):
            adaptive_enabled = adaptive_cfg.get(
                "enabled", perf_cfg.get("adaptive_branching_enabled", True)
            )
            min_branches_hard = adaptive_cfg.get(
                "min_branches_for_hard_obligations",
                perf_cfg.get("min_branches_for_hard_obligations", 6),
            )
            max_branches_hard = adaptive_cfg.get(
                "max_branches_for_hard_obligations",
                perf_cfg.get("max_branches_for_hard_obligations", 12),
            )
        else:
            adaptive_enabled = perf_cfg.get("adaptive_branching_enabled", True)
            min_branches_hard = perf_cfg.get("min_branches_for_hard_obligations", 6)
            max_branches_hard = perf_cfg.get("max_branches_for_hard_obligations", 12)

        mc_guided_prompt_enabled = perf_cfg.get("mc_guided_prompt_enabled", False)
        proof_pattern_cache_path = perf_cfg.get(
            "proof_pattern_cache_path", "build/perf_proof_patterns.json"
        )

        bt_cfg = perf_cfg.get("backtracking", {})
        on_demand_cfg = bt_cfg.get("on_demand", {})

        refl_weights = perf_cfg.get("reflection_quality_weights", None)
        if refl_weights is None:
            refl_weights = {
                "primary_delta": 0.4,
                "error_shift": 0.2,
                "subgoal_reduction": 0.25,
                "diversity": 0.15,
            }
        else:
            default_weights = {
                "primary_delta": 0.4,
                "error_shift": 0.2,
                "subgoal_reduction": 0.25,
                "diversity": 0.15,
            }
            default_weights.update(refl_weights)
            refl_weights = default_weights

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
            use_proof_library=False,
            try_skeleton_first=perf_cfg.get("try_skeleton_first", False),
            min_beam_size=perf_cfg.get("min_beam_size", 2),
            perf_light_repair_attempts=perf_cfg.get("perf_light_repair_attempts", 2),
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
            parallel_variant_generation=perf_cfg.get("parallel_variant_generation", False),
            error_history_enabled=error_history_enabled,
            error_history_max_entries=error_history_max_entries,
            adaptive_branching_enabled=adaptive_enabled,
            min_branches_for_hard_obligations=min_branches_hard,
            max_branches_for_hard_obligations=max_branches_hard,
            mc_guided_prompt_enabled=mc_guided_prompt_enabled,
            proof_pattern_cache_path=proof_pattern_cache_path,
            backtracking_enabled=bt_cfg.get("enabled", False),
            backtracking_stagnation_depth=bt_cfg.get("stagnation_depth", 2),
            backtracking_max_restarts=bt_cfg.get("max_restarts", 3),
            backtracking_max_backtrack_depth=bt_cfg.get("max_backtrack_depth", 2),
            backtracking_restore_beam_size=bt_cfg.get("restore_beam_size", 3),
            backtracking_avoid_repeated_branches=bt_cfg.get("avoid_repeated_branches", True),
            backtracking_store_all_scored_children=bt_cfg.get("store_all_scored_children", True),
            backtracking_diversity_dimensions=bt_cfg.get("diversity_dimensions", ["novelty", "structural_difference"]),
            backtracking_diversity_weight=bt_cfg.get("diversity_weight", 0.3),
            backtracking_alternate_primary_dimension=bt_cfg.get("alternate_primary_dimension", "syntactic_purity"),
            backtracking_scoring_noise_std=bt_cfg.get("scoring_noise_std", 0.05),
            backtracking_experience_penalty=bt_cfg.get("experience_penalty", True),
            backtracking_force_regeneration=bt_cfg.get("force_regeneration", True),
            backtracking_regeneration_temperature_boost=bt_cfg.get("regeneration_temperature_boost", 0.2),
            backtracking_regeneration_strategy_hint=bt_cfg.get(
                "regeneration_strategy_hint",
                (
                    "Previous proof attempts failed. Avoid the following common mistakes: "
                    "1) Do not use reflexivity on hypotheses like 'false = true' – use discriminate instead. "
                    "2) After inversion on the step hypothesis, destruct the nested conditionals (op_reg, etc.) "
                    "   rather than applying the induction hypothesis directly. "
                    "3) Use distinct case analysis for each branch of the operation."
                ),
            ),
            backtracking_on_demand_enabled=on_demand_cfg.get("enabled", False),
            backtracking_on_demand_force_every=on_demand_cfg.get("force_every", 0),
            backtracking_on_demand_time_limit=on_demand_cfg.get("time_limit", 0.0),
            backtracking_on_demand_max_same_error=on_demand_cfg.get("max_same_error", 5),
            backtracking_on_demand_skip_forced_regeneration=on_demand_cfg.get("skip_forced_regeneration", True),
            reflection_quality_window=perf_cfg.get("reflection_quality_window", 2),
            min_reflection_quality=perf_cfg.get("min_reflection_quality", 0.2),
            max_reflection_retries=perf_cfg.get("max_reflection_retries", 2),
            reflection_quality_weights=refl_weights,
            backtrack_force_strategy_switch=perf_cfg.get("backtrack_force_strategy_switch", False),
            backtrack_diversity_boost_after_stagnation=perf_cfg.get(
                "backtrack_diversity_boost_after_stagnation", 0.2
            ),
        )

    @classmethod
    def from_obligation_metadata(
        cls,
        global_config: "PERFConfig",
        obligation_metadata: Dict[str, Any]
    ) -> "PERFConfig":
        """Merge obligation‑level metadata overrides into the global PERF config."""
        perf_override = obligation_metadata.get("perf", {})
        kwargs = global_config.to_dict()

        allowed_keys = set(kwargs.keys())
        for key in list(kwargs.keys()):
            if key in perf_override:
                kwargs[key] = perf_override[key]

        kwargs["use_proof_library"] = False
        return cls(**kwargs)

    def get_effective_dimensions(self) -> List[str]:
        """Return the effective dimensions list for scoring."""
        dims = self.dimensions.copy()
        if self.primary_dimension not in dims:
            dims.insert(0, self.primary_dimension)
        return dims

    def is_enabled_for_obligation(self, obligation: Dict[str, Any]) -> bool:
        """Check if PERF is enabled for a specific proof obligation."""
        metadata = obligation.get("metadata", {})
        perf_override = metadata.get("perf", {})
        if "enabled" in perf_override:
            return bool(perf_override["enabled"])
        return self.enabled

    def __repr__(self) -> str:
        return f"PERFConfig(enabled={self.enabled}, beam_size={self.beam_size}, depth_limit={self.depth_limit})"


def validate_perf_against_config(config: Dict[str, Any]) -> None:
    """Validate the global configuration for PERF compatibility."""
    perf_enabled = config.get("proof", {}).get("perf", {}).get("enabled", False)
    use_library = config.get("provers", {}).get("koika", {}).get("use_proof_library", True)

    if perf_enabled and use_library:
        raise ValueError(
            "Configuration conflict: PERF enabled but use_proof_library is true.\n"
            "PERF requires 'provers.koika.use_proof_library: false' to prevent cache bypass.\n"
            "To fix:\n"
            "  - Set 'proof.perf.enabled: false' to disable PERF, OR\n"
            "  - Set 'provers.koika.use_proof_library: false' to enable PERF with library bypass."
        )


def get_perf_config(config: Optional[Dict[str, Any]] = None) -> PERFConfig:
    """Get the PERF configuration from the global config."""
    if config is None:
        from specir.utils.config_loader import get_config
        config = get_config()
    validate_perf_against_config(config)
    return PERFConfig.from_global_config(config)
