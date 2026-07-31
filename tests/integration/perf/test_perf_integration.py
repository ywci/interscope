# tests/integration/perf/test_perf_integration.py
#
# Integration tests for PERF (Proof tree Exploration with Reflective Feedback).
# These tests run the full `specir verify` command with PERF enabled and check
# that the traversal executes, respects configuration flags, and produces
# expected outcomes (success or graceful failure).
#
# Since PERF requires LLM calls and may be slow, these tests are marked as
# integration and may be skipped if required tools (rocq-mcp, acl2, sby) are
# not installed or if the LLM is not configured.

import subprocess
import sys
import os
import pytest
import yaml
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent


def _tool_on_path(name: str) -> bool:
    import shutil
    return shutil.which(name) is not None


def _koika_works() -> bool:
    """Return True if the Kōika compiler is installed and responds to --help."""
    if not _tool_on_path("koika"):
        return False
    try:
        subprocess.run(["koika", "--help"], capture_output=True, timeout=5, check=True)
        return True
    except Exception:
        return False


def _rocq_works() -> bool:
    """Return True if rocq-mcp is on the path."""
    return _tool_on_path("rocq-mcp")


def _acl2_works() -> bool:
    """Return True if ACL2 is installed (checked via acl2-mcp)."""
    return _tool_on_path("acl2-mcp") or _tool_on_path("acl2")


def _sby_works() -> bool:
    """Return True if SymbiYosys (sby) is on the path."""
    return _tool_on_path("sby")


def _llm_available(config_path: Path) -> bool:
    """Check if the LLM configuration is usable (e.g., Ollama is running)."""
    try:
        with open(config_path) as f:
            cfg = yaml.safe_load(f)
        provider = cfg.get("llm", {}).get("provider", "").lower()
        model = cfg.get("llm", {}).get("model", "")
        if provider and model:
            return True
    except Exception:
        pass
    return False


def _run_specir(subcommand: str, args: list, timeout: int = 120, **kwargs) -> subprocess.CompletedProcess:
    """
    Run a specir CLI command with the given subcommand and arguments.
    Ensures PYTHONPATH includes the project's src/ directory so that the
    specir module is found.
    """
    env = kwargs.pop("env", os.environ.copy())
    # Set PYTHONPATH so that the src/ directory is on the path
    src_path = str(PROJECT_ROOT / "src")
    if "PYTHONPATH" in env:
        env["PYTHONPATH"] = src_path + os.pathsep + env["PYTHONPATH"]
    else:
        env["PYTHONPATH"] = src_path

    return subprocess.run(
        [sys.executable, "-m", "specir.cli." + subcommand] + args,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
        cwd=str(PROJECT_ROOT),
        **kwargs,
    )


@pytest.fixture
def alu_spec_path():
    """Path to the ALU spec in the same directory."""
    return Path(__file__).parent / "alu.specir"


@pytest.fixture
def build_dir(tmp_path):
    """Temporary build directory for each test."""
    return tmp_path / "build"


@pytest.fixture
def perf_config_path(tmp_path):
    """Create a PERF-specific configuration with small beam/depth."""
    config_data = {
        "llm": {
            "provider": "ollama",
            "model": "qwen3.5:27b",
            "base_url": "http://localhost:11434/v1",
            "temperature": 0.2,
            "max_tokens": 131072,
            "timeout": 120,
            "retries": 3,
        },
        "provers": {
            "koika": {
                "enabled": True,
                "lemma_mining": True,
                "use_proof_library": False,
                "prove": {
                    "skill": "rocq-mcp",
                    "rocq_mcp_path": "rocq-mcp",
                    "coq_tactic_hints": ["induction", "simpl", "auto", "eauto"],
                    "proof_timeout": 600,
                    "max_consecutive_failures": 10,
                    "max_steps": 80,
                    "pre_simplify": True,
                    "invariant_mining": True,
                }
            },
            "acl2": {
                "enabled": True,
                "lemma_mining": True,
                "mcp_path": "acl2-mcp",
                "mcp_timeout": 30,
                "init_commands": [],
                "prove": {
                    "skill": "acl2_builtin",
                    "hint_classes": ["rewrite", "linear", "induct"],
                    "skolem_depth": 2,
                    "defun_sk_enabled": True,
                }
            }
        },
        "verification": {
            "default_backend": "koika",
            "bmc_max_depth": 100,
            "ic3_max_steps": 1000,
            "formal_timeout": 300,
        },
        "proof": {
            "max_repair_attempts": 3,
            "perf": {
                "enabled": True,
                "beam_size": 2,
                "branches_per_node": 2,
                "depth_limit": 2,
                "dimensions": ["subgoal_reduction", "trace_alignment"],
                "scoring_tournament_size": 2,
                "generation_temperature": 0.4,
                "always_verify_children": True,
                "max_workers": 2,
                "timeout_per_node": 60,
            }
        },
        "logging": {"level": "INFO"},
        "directories": {"build": "build"},
    }
    config_path = tmp_path / "config_perf.yaml"
    with open(config_path, "w") as f:
        yaml.dump(config_data, f, default_flow_style=False)
    return config_path


@pytest.fixture
def conflict_config_path(tmp_path):
    """Config with use_proof_library true and PERF enabled – should cause error."""
    config_data = {
        "llm": {"provider": "ollama", "model": "qwen3.5:27b"},
        "provers": {"koika": {"use_proof_library": True, "prove": {}}},
        "proof": {"perf": {"enabled": True}},
        "directories": {"build": "build"},
    }
    config_path = tmp_path / "config_conflict.yaml"
    with open(config_path, "w") as f:
        yaml.dump(config_data, f, default_flow_style=False)
    return config_path


@pytest.mark.integration
@pytest.mark.perf
@pytest.mark.skipif(not _rocq_works(), reason="rocq-mcp not installed")
@pytest.mark.skipif(not _koika_works(), reason="Kōika compiler not installed")
def test_perf_koika_alu(alu_spec_path, build_dir, perf_config_path):
    """
    Run PERF on the ALU spec with Koika backend.
    Tests the zero_flag_correct theorem proving obligation.
    """
    if not _llm_available(perf_config_path):
        pytest.skip("LLM not available (Ollama/OpenAI)")

    cmd = [
        str(alu_spec_path),
        "--backend", "koika",
        "--out-dir", str(build_dir / "verify"),
        "--perf",
    ]
    env = {"SPECIR_CONFIG": str(perf_config_path)}
    result = _run_specir("verify", cmd, timeout=180, env=env)

    assert result.returncode in (0, 1), (
        f"PERF verification crashed with code {result.returncode}:\n"
        f"STDERR: {result.stderr}\n"
        f"STDOUT: {result.stdout}"
    )


@pytest.mark.integration
@pytest.mark.perf
@pytest.mark.skipif(not _acl2_works(), reason="ACL2 not installed")
def test_perf_acl2_alu(alu_spec_path, build_dir, perf_config_path):
    """
    Run PERF on the ALU spec with ACL2 backend.
    Tests simple ACL2 obligations (zero_reg_is_bool, valid_is_bool, etc.).
    """
    if not _llm_available(perf_config_path):
        pytest.skip("LLM not available (Ollama/OpenAI)")

    cmd = [
        str(alu_spec_path),
        "--backend", "acl2",
        "--out-dir", str(build_dir / "verify"),
        "--perf",
    ]
    env = {"SPECIR_CONFIG": str(perf_config_path)}
    result = _run_specir("verify", cmd, timeout=180, env=env)

    assert result.returncode in (0, 1), (
        f"PERF ACL2 verification crashed with code {result.returncode}:\n"
        f"STDERR: {result.stderr}\n"
        f"STDOUT: {result.stdout}"
    )


@pytest.mark.integration
@pytest.mark.perf
@pytest.mark.skipif(not _rocq_works(), reason="rocq-mcp not installed")
@pytest.mark.skipif(not _koika_works(), reason="Kōika compiler not installed")
@pytest.mark.skipif(not _sby_works(), reason="SymbiYosys (sby) not installed")
def test_perf_with_model_checking_alu(alu_spec_path, build_dir, perf_config_path):
    """
    Run PERF on the ALU spec with model checking obligations.
    This tests the trace_alignment dimension (PERF uses MC counterexample traces).
    """
    if not _llm_available(perf_config_path):
        pytest.skip("LLM not available (Ollama/OpenAI)")

    cmd = [
        str(alu_spec_path),
        "--out-dir", str(build_dir / "verify"),
        "--perf",
    ]
    env = {"SPECIR_CONFIG": str(perf_config_path)}
    result = _run_specir("verify", cmd, timeout=300, env=env)

    assert result.returncode in (0, 1), (
        f"PERF with MC verification crashed with code {result.returncode}:\n"
        f"STDERR: {result.stderr}\n"
        f"STDOUT: {result.stdout}"
    )


@pytest.mark.integration
@pytest.mark.perf
def test_perf_conflict_detection(alu_spec_path, build_dir, conflict_config_path):
    """
    When PERF is enabled and use_proof_library is true, the system should
    raise a ConfigurationError, causing the verify command to exit with a non-zero code.
    """
    cmd = [
        str(alu_spec_path),
        "--backend", "koika",
        "--out-dir", str(build_dir / "verify"),
    ]
    env = {"SPECIR_CONFIG": str(conflict_config_path)}
    result = _run_specir("verify", cmd, timeout=10, env=env)

    assert result.returncode != 0, "Expected conflict error but verification succeeded"
    assert "Configuration conflict" in result.stderr or "use_proof_library" in result.stderr, (
        f"Expected conflict error message not found.\nSTDERR: {result.stderr}"
    )


@pytest.mark.integration
@pytest.mark.perf
@pytest.mark.skipif(not _rocq_works(), reason="rocq-mcp not installed")
@pytest.mark.skipif(not _koika_works(), reason="Kōika compiler not installed")
def test_perf_stats_flag_alu(alu_spec_path, build_dir, perf_config_path):
    """
    Use --perf-stats flag and verify statistics are printed.
    """
    if not _llm_available(perf_config_path):
        pytest.skip("LLM not available (Ollama/OpenAI)")

    cmd = [
        str(alu_spec_path),
        "--backend", "koika",
        "--out-dir", str(build_dir / "verify"),
        "--perf",
        "--perf-stats",
    ]
    env = {"SPECIR_CONFIG": str(perf_config_path)}
    result = _run_specir("verify", cmd, timeout=180, env=env)

    output = result.stdout + result.stderr
    assert "PERF Traversal Statistics" in output or "Total nodes generated" in output, (
        f"PERF statistics not printed.\nOutput: {output}"
    )
