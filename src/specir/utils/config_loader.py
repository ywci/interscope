# src/specir/utils/config_loader.py
#
# Loads configuration from conf/config.yaml, supports environment variable
# substitution, and provides singleton access to configuration for the
# InterScope project.

import os
import re
import yaml
from pathlib import Path
from typing import Any, Dict, Optional

_CONFIG: Optional[Dict[str, Any]] = None
_PROJECT_ROOT: Optional[Path] = None


def _find_project_root() -> Path:
    """
    Find the project root directory by looking for 'conf/config.yaml'
    or a marker file (e.g., 'run.sh', 'LICENSE').
    Starts from the current working directory and walks upwards.
    """
    current = Path.cwd()
    for parent in [current] + list(current.parents):
        if (parent / "conf" / "config.yaml").exists():
            return parent

    return current


def _substitute_env_vars(value: Any) -> Any:
    """
    Recursively substitute environment variables in strings of the form ${VAR_NAME}.
    """
    if isinstance(value, str):
        pattern = r'\${([^}]+)}'
        def replacer(match):
            var_name = match.group(1)
            return os.environ.get(var_name, match.group(0))
        return re.sub(pattern, replacer, value)
    elif isinstance(value, dict):
        return {k: _substitute_env_vars(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_substitute_env_vars(item) for item in value]
    else:
        return value


def _validate_config(config: Dict[str, Any]) -> None:
    """
    Validate the configuration for PERF compatibility.

    Checks the critical conflict: PERF enabled with use_proof_library.

    Args:
        config: The loaded configuration dictionary.

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
            "  - Set 'provers.koika.use_proof_library: false' to enable PERF."
        )


def _apply_perf_env_overrides(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply PERF environment variable overrides to the configuration.

    Supported environment variables:
      PERF_ENABLED           (true/false)
      PERF_BEAM_SIZE         (int)
      PERF_BRANCHES          (int, branches_per_node)
      PERF_DEPTH             (int, depth_limit)
      PERF_DIMENSIONS        (comma-separated list)
      PERF_PRIMARY_DIMENSION (str)
      PERF_TEMPERATURE       (float, generation_temperature)
      PERF_MAX_WORKERS       (int)
      PERF_TIMEOUT_NODE      (int, timeout_per_node)
      PERF_TOURNAMENT_SIZE   (int, scoring_tournament_size)
      PERF_ALWAYS_VERIFY     (true/false, always_verify_children)
    """
    perf_cfg = config.setdefault("proof", {}).setdefault("perf", {})

    # Core settings
    if "PERF_ENABLED" in os.environ:
        val = os.environ["PERF_ENABLED"].lower()
        perf_cfg["enabled"] = val in ("true", "1", "yes")

    if "PERF_BEAM_SIZE" in os.environ:
        try:
            perf_cfg["beam_size"] = int(os.environ["PERF_BEAM_SIZE"])
        except ValueError:
            pass

    if "PERF_BRANCHES" in os.environ:
        try:
            perf_cfg["branches_per_node"] = int(os.environ["PERF_BRANCHES"])
        except ValueError:
            pass

    if "PERF_DEPTH" in os.environ:
        try:
            perf_cfg["depth_limit"] = int(os.environ["PERF_DEPTH"])
        except ValueError:
            pass

    if "PERF_DIMENSIONS" in os.environ:
        dims = [d.strip() for d in os.environ["PERF_DIMENSIONS"].split(",") if d.strip()]
        if dims:
            perf_cfg["dimensions"] = dims

    if "PERF_PRIMARY_DIMENSION" in os.environ:
        perf_cfg["primary_dimension"] = os.environ["PERF_PRIMARY_DIMENSION"].strip()

    if "PERF_TEMPERATURE" in os.environ:
        try:
            perf_cfg["generation_temperature"] = float(os.environ["PERF_TEMPERATURE"])
        except ValueError:
            pass

    if "PERF_MAX_WORKERS" in os.environ:
        try:
            perf_cfg["max_workers"] = int(os.environ["PERF_MAX_WORKERS"])
        except ValueError:
            pass

    if "PERF_TIMEOUT_NODE" in os.environ:
        try:
            perf_cfg["timeout_per_node"] = int(os.environ["PERF_TIMEOUT_NODE"])
        except ValueError:
            pass

    if "PERF_TOURNAMENT_SIZE" in os.environ:
        try:
            perf_cfg["scoring_tournament_size"] = int(os.environ["PERF_TOURNAMENT_SIZE"])
        except ValueError:
            pass

    if "PERF_ALWAYS_VERIFY" in os.environ:
        val = os.environ["PERF_ALWAYS_VERIFY"].lower()
        perf_cfg["always_verify_children"] = val in ("true", "1", "yes")

    return config


def deep_merge_configs(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recursively merge *override* into *base*.

    - For keys that are dictionaries in both, merge recursively.
    - For keys that are lists in both, replace the list (override wins).
    - For all other cases, the override value replaces the base value.

    Args:
        base: The base configuration dictionary.
        override: The dictionary containing overrides.

    Returns:
        A new merged dictionary (the original ``base`` is not modified).
    """
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge_configs(result[key], value)
        else:
            result[key] = value
    return result


def load_external_config(filepath: Path) -> Dict[str, Any]:
    """
    Load a YAML configuration file from *filepath* and return it as a dictionary.

    Args:
        filepath: Path to the YAML file.

    Returns:
        The parsed dictionary.

    Raises:
        FileNotFoundError: If the file does not exist.
        yaml.YAMLError: If the YAML is malformed.
    """
    if not filepath.exists():
        raise FileNotFoundError(f"External configuration file not found: {filepath}")
    with open(filepath, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, dict):
        raise ValueError(f"External configuration file must be a dictionary: {filepath}")
    return _substitute_env_vars(raw)


def load_config(
    config_path: Optional[Path] = None,
    force_reload: bool = False,
    external_config_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Load the InterScope configuration file, optionally merging an external config.

    Args:
        config_path: Path to config.yaml. If None, uses <project_root>/conf/config.yaml,
                     unless the environment variable SPECIR_CONFIG is set.
        force_reload: If True, reload the configuration even if already loaded.
        external_config_path: Optional path to an additional YAML file whose
                              contents will be deep‑merged into the main config.

    Returns:
        Dictionary containing the configuration.

    Raises:
        FileNotFoundError: If the configuration file does not exist.
        yaml.YAMLError: If the YAML file is malformed.
        ValueError: If configuration validation fails.
    """
    global _CONFIG, _PROJECT_ROOT

    if _CONFIG is not None and not force_reload and external_config_path is None:
        return _CONFIG

    if config_path is None:
        # Check environment variable
        env_path = os.environ.get("SPECIR_CONFIG")
        if env_path:
            config_path = Path(env_path)
        else:
            if _PROJECT_ROOT is None:
                _PROJECT_ROOT = _find_project_root()
            config_path = _PROJECT_ROOT / "conf" / "config.yaml"

    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        raw_config = yaml.safe_load(f)

    config = _substitute_env_vars(raw_config)

    # Apply defaults
    config.setdefault("llm", {})
    config["llm"].setdefault("temperature", 0.2)
    config["llm"].setdefault("max_tokens", 2048)
    config["llm"].setdefault("timeout", 120)
    config["llm"].setdefault("retries", 3)

    config.setdefault("provers", {})
    for prover in ["koika", "acl2"]:
        config["provers"].setdefault(prover, {})
        config["provers"][prover].setdefault("enabled", True)
        config["provers"][prover].setdefault("lemma_mining", True)
        config["provers"][prover].setdefault("prove", {})

        if prover == "koika":
            config["provers"]["koika"].setdefault("use_proof_library", True)
            prove_cfg = config["provers"]["koika"]["prove"]
            prove_cfg.setdefault("skill", "rocq-mcp")
            prove_cfg.setdefault("coq_tactic_hints", [
                "induction", "simpl", "auto", "eauto",
                "rewrite", "inversion", "subst",
                "destruct", "split", "lia", "nia"
            ])
            prove_cfg.setdefault("proof_timeout", 600)
            prove_cfg.setdefault("max_consecutive_failures", 10)
            prove_cfg.setdefault("max_steps", 80)
            prove_cfg.setdefault("pre_simplify", True)
            prove_cfg.setdefault("invariant_mining", True)
            prove_cfg.setdefault("skeleton_reflection", True)
            prove_cfg.setdefault("skeleton_step_tactics", [])

        elif prover == "acl2":
            prove_cfg = config["provers"]["acl2"]["prove"]
            prove_cfg.setdefault("skill", "acl2_builtin")
            prove_cfg.setdefault("hint_classes", ["rewrite", "linear", "induct"])
            prove_cfg.setdefault("skolem_depth", 2)
            prove_cfg.setdefault("defun_sk_enabled", True)

    config.setdefault("verification", {})
    verification_defaults = {
        "default_backend": "koika",
        "bmc_max_depth": 100,
        "ic3_max_steps": 1000,
        "simulation_cycles": 1000,
        "formal_timeout": 300,
        "split_monolithic_rules": False,
        "rule_split_attribute": "split"
    }
    for key, default in verification_defaults.items():
        config["verification"].setdefault(key, default)

    config.setdefault("proof", {})
    config["proof"].setdefault("max_repair_attempts", 5)

    perf_defaults = {
        "enabled": False,
        "beam_size": 3,
        "branches_per_node": 4,
        "depth_limit": 3,
        "dimensions": ["subgoal_reduction", "trace_alignment", "syntactic_purity"],
        "primary_dimension": "subgoal_reduction",
        "scoring_tournament_size": 2,
        "generation_temperature": 0.4,
        "always_verify_children": True,
        "max_workers": 4,
        "timeout_per_node": 300,
        "trace_alignment_weight": 0.6,
    }
    config["proof"].setdefault("perf", {})
    for key, default in perf_defaults.items():
        config["proof"]["perf"].setdefault(key, default)

    config.setdefault("lifting", {})
    lifting_defaults = {
        "vcd_parser": "builtin",
        "default_mapping_file": "build/rtl/mapping.json",
        "llm_lifter_enabled": True,
        "llm_lifter_confidence_threshold": 0.7
    }
    for key, default in lifting_defaults.items():
        config["lifting"].setdefault(key, default)

    config.setdefault("evidence", {})
    config["evidence"].setdefault("db_path", "build/evidence.db")
    config["evidence"].setdefault("auto_commit", True)

    config.setdefault("logging", {})
    config["logging"].setdefault("level", "INFO")

    config.setdefault("directories", {})
    dir_defaults = {
        "build": "build",
        "rtl": "build/rtl",
        "traces": "build/traces",
        "logs": "build/logs",
        "temp": "build/temp",
        "verify": "build/verify",
        "tools": "tools"
    }
    for key, default in dir_defaults.items():
        config["directories"].setdefault(key, default)

    config = _apply_perf_env_overrides(config)

    # Merge external config if provided
    if external_config_path is not None:
        external = load_external_config(external_config_path)
        config = deep_merge_configs(config, external)

    _validate_config(config)

    _CONFIG = config
    return config


def get_config(key: Optional[str] = None, default: Any = None) -> Any:
    """
    Get a configuration value by dot-separated key (e.g., "llm.provider").

    Args:
        key: Dot-separated path to the configuration value. If None, returns the whole config.
        default: Value to return if the key is not found.

    Returns:
        Configuration value or the full config dict if key is None.
    """
    config = load_config()
    if key is None:
        return config

    parts = key.split(".")
    current = config
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return default
    return current


def get_project_root() -> Path:
    """
    Return the absolute path to the project root (where conf/ and src/ live).
    """
    global _PROJECT_ROOT
    if _PROJECT_ROOT is None:
        _PROJECT_ROOT = _find_project_root()
    return _PROJECT_ROOT


def reload_config() -> Dict[str, Any]:
    """
    Force a reload of the configuration.

    Returns:
        The newly loaded configuration dictionary.
    """
    return load_config(force_reload=True)
