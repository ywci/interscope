# src/specir/cli/validate_config.py
#
# CLI subcommand `validate-config` – validates the InterScope configuration
# file (conf/config.yaml) and checks for common conflicts, especially
# the PERF vs. use_proof_library conflict.
#
# Usage:
#   python -m specir.cli.validate_config
#   python -m specir.cli.validate_config --config /path/to/config.yaml

import yaml
import argparse
import sys
from pathlib import Path
from specir.utils.logger import setup_logging, get_logger
from specir.utils.config_loader import get_project_root, load_config

logger = get_logger(__name__)


def _setup_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="specir validate-config",
        description="Validate the InterScope configuration file (conf/config.yaml)."
    )
    parser.add_argument(
        "--config", "-c", type=str, default=None,
        help="Path to config.yaml (default: <project_root>/conf/config.yaml)"
    )
    parser.add_argument(
        "--debug", action="store_true",
        help="Enable debug logging"
    )
    return parser


def validate_config(config_path: Path, verbose: bool = True) -> bool:
    """
    Validate the configuration file for conflicts and correctness.

    Args:
        config_path: Path to the configuration file.
        verbose: If True, print validation results to stdout.

    Returns:
        True if the configuration is valid, False otherwise.
    """
    errors = []
    warnings = []

    # 1. Check file existence
    if not config_path.exists():
        errors.append(f"Configuration file not found: {config_path}")
        return False

    # 2. Load YAML
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        errors.append(f"YAML parsing error: {e}")
        return False
    except Exception as e:
        errors.append(f"Failed to read configuration: {e}")
        return False

    if not isinstance(config, dict):
        errors.append("Configuration root must be a dictionary")
        return False

    # 3. Check PERF vs. use_proof_library conflict
    perf_enabled = config.get("proof", {}).get("perf", {}).get("enabled", False)
    use_library = config.get("provers", {}).get("koika", {}).get("use_proof_library", True)

    if perf_enabled and use_library:
        errors.append(
            "Configuration conflict detected:\n"
            "  - proof.perf.enabled = true\n"
            "  - provers.koika.use_proof_library = true\n\n"
            "These settings are mutually exclusive.\n"
            "The cached PROOF_LIBRARY bypasses the PERF traversal entirely, "
            "preventing reflective exploration.\n\n"
            "To fix, choose one of the following:\n"
            "  1. Run PERF: Set 'use_proof_library: false' in the koika prover config.\n"
            "  2. Use cached proofs: Set 'perf.enabled: false' in the proof config."
        )

    # 4. Check LLM configuration if PERF is enabled
    if perf_enabled:
        llm_cfg = config.get("llm", {})
        provider = llm_cfg.get("provider", "").lower()
        model = llm_cfg.get("model", "")

        if not provider:
            warnings.append(
                "PERF is enabled but 'llm.provider' is not set.\n"
                "PERF requires an LLM for generation and reflection.\n"
                "Please set 'llm.provider' (e.g., 'ollama', 'openai', 'anthropic')."
            )

        if not model:
            warnings.append(
                "PERF is enabled but 'llm.model' is not set.\n"
                "Please set 'llm.model' (e.g., 'qwen3.5:27b', 'gpt-4')."
            )

        # Check if provider is supported
        supported = {"ollama", "openai", "anthropic", "deepseek"}
        if provider and provider not in supported:
            warnings.append(
                f"Unsupported LLM provider '{provider}'. "
                f"Supported providers: {', '.join(sorted(supported))}"
            )

    # 5. Check PERF parameter validity (if enabled)
    if perf_enabled:
        perf_cfg = config.get("proof", {}).get("perf", {})
        beam = perf_cfg.get("beam_size", 3)
        branches = perf_cfg.get("branches_per_node", 4)
        depth = perf_cfg.get("depth_limit", 3)
        dims = perf_cfg.get("dimensions", [])

        if not isinstance(beam, int) or beam < 1:
            errors.append(f"'beam_size' must be a positive integer, got {beam}")
        if not isinstance(branches, int) or branches < 1:
            errors.append(f"'branches_per_node' must be a positive integer, got {branches}")
        if not isinstance(depth, int) or depth < 1:
            errors.append(f"'depth_limit' must be a positive integer, got {depth}")
        if not dims:
            warnings.append("'dimensions' list is empty. Using defaults: subgoal_reduction, trace_alignment, syntactic_purity")
        if not isinstance(dims, list):
            errors.append("'dimensions' must be a list of strings")

    # 6. Print results
    if verbose:
        print()
        print("=" * 60)
        print("  InterScope Configuration Validation")
        print("=" * 60)
        print(f"  Config file: {config_path}")
        print(f"  PERF enabled: {perf_enabled}")
        print(f"  Proof library: {'enabled' if use_library else 'disabled'}")
        print()

        if errors:
            print(f"  {RED if sys.stdout.isatty() else ''}[ERROR]{RESET if sys.stdout.isatty() else ''} {len(errors)} configuration error(s) found:")
            for error in errors:
                print(f"    - {error}")
            print()

        if warnings:
            print(f"  {YELLOW if sys.stdout.isatty() else ''}[WARNING]{RESET if sys.stdout.isatty() else ''} {len(warnings)} configuration warning(s):")
            for warning in warnings:
                print(f"    - {warning}")
            print()

        if not errors and not warnings:
            print("  [SUCCESS] Configuration is valid.")
        elif not errors:
            print("  [SUCCESS] No errors found (warnings are informational).")
        else:
            print("  [FAILED] Configuration has errors. Please fix them and try again.")

        print("=" * 60)
        print()

    return len(errors) == 0


def main() -> int:
    """Execute the validate-config command."""
    parser = _setup_arg_parser()
    args = parser.parse_args()

    log_level = "DEBUG" if args.debug else "INFO"
    setup_logging(level=log_level)

    if args.config:
        config_path = Path(args.config).resolve()
    else:
        config_path = get_project_root() / "conf" / "config.yaml"

    valid = validate_config(config_path, verbose=True)
    return 0 if valid else 1


if __name__ == "__main__":
    sys.exit(main())