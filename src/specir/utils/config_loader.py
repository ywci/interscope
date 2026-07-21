# src/specir/utils/config_loader.py
#
# Loads configuration from conf/config.yaml, supports environment variable substitution,
# and provides singleton access to configuration for the InterScope project.

import os
import re
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


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


def load_config(config_path: Optional[Path] = None, force_reload: bool = False) -> Dict[str, Any]:
    """
    Load the InterScope configuration file.

    Args:
        config_path: Path to config.yaml. If None, uses <project_root>/conf/config.yaml.
        force_reload: If True, reload the configuration even if already loaded.

    Returns:
        Dictionary containing the configuration.

    Raises:
        FileNotFoundError: If the configuration file does not exist.
        yaml.YAMLError: If the YAML file is malformed.
    """
    global _CONFIG, _PROJECT_ROOT

    if _CONFIG is not None and not force_reload:
        return _CONFIG

    if config_path is None:
        if _PROJECT_ROOT is None:
            _PROJECT_ROOT = _find_project_root()
        config_path = _PROJECT_ROOT / "conf" / "config.yaml"

    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        raw_config = yaml.safe_load(f)

    config = _substitute_env_vars(raw_config)

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
        "verify": "build/verify"
    }
    for key, default in dir_defaults.items():
        config["directories"].setdefault(key, default)

    _CONFIG = config
    return config


def get_config(key: Optional[str] = None, default: Any = None) -> Any:
    """
    Get a configuration value by dot‑separated key (e.g., "llm.provider").

    Args:
        key: Dot‑separated path to the configuration value. If None, returns the whole config.
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
