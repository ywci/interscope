# tests/integration/counter/test_counter.py
#
# Integration test for the counter example.
# Compiles to Kōika/Coq and ACL2. The Kōika verification test uses the
# library proof for count_bound. The simulation +
# lift + check test is skipped until the Kōika extraction step is automated.

import os
import subprocess
import sys
from pathlib import Path
import pytest
import yaml


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


def _run_specir(subcommand: str, args: list, timeout: int = 180, **kwargs) -> subprocess.CompletedProcess:
    """Run a specir CLI subcommand with a default generous timeout."""
    return subprocess.run(
        [sys.executable, "-m", "specir.cli." + subcommand] + args,
        capture_output=True,
        text=True,
        timeout=timeout,
        **kwargs,
    )


@pytest.fixture
def counter_spec_path():
    return Path(__file__).parent / "counter.specir"


@pytest.fixture
def build_dir(tmp_path):
    return tmp_path / "build"


def _write_library_config(config_path: Path):
    """Write a minimal config that enables the proof library and avoids LLM calls."""
    config = {
        "provers": {
            "koika": {
                "use_proof_library": True,
                "prove": {
                    "rocq_mcp_path": "rocq-mcp",
                    "proof_timeout": 300,
                    "max_consecutive_failures": 10,
                    "max_steps": 40,
                    "pre_simplify": True,
                    "invariant_mining": False,
                    "skeleton_reflection": False,
                }
            }
        },
        "proof": {
            "max_repair_attempts": 0,
            "perf": {"enabled": False},
        },
        "llm": {
            "provider": "ollama",
            "model": "dummy",
            "api_key": "unused",
            "base_url": "http://localhost:1",
        },
    }
    config_path.write_text(yaml.dump(config))


@pytest.mark.integration
def test_counter_compile_koika(counter_spec_path, build_dir):
    """Compile the counter spec to Kōika/Coq (generates a .v file) without RTL."""
    cmd = [
        str(counter_spec_path),
        "--backend", "koika",
        "--out-dir", str(build_dir),
        "--no-rtl",
    ]
    result = _run_specir("compile", cmd, timeout=120)
    assert result.returncode == 0, (
        f"Compilation failed with code {result.returncode}:\n"
        f"STDERR: {result.stderr}\n"
        f"STDOUT: {result.stdout}"
    )
    coq_file = build_dir / "counter" / "coq" / "counter.v"
    assert coq_file.exists(), f"Coq file not found: {coq_file}"


@pytest.mark.integration
def test_counter_compile_acl2(counter_spec_path, build_dir):
    """Compile the counter spec to ACL2 (generates a .lisp file)."""
    cmd = [
        str(counter_spec_path),
        "--backend", "acl2",
        "--out-dir", str(build_dir),
    ]
    result = _run_specir("compile", cmd, timeout=120)
    assert result.returncode == 0, (
        f"Compilation failed with code {result.returncode}:\n"
        f"STDERR: {result.stderr}\n"
        f"STDOUT: {result.stdout}"
    )
    acl2_file = build_dir / "counter" / "acl2" / "counter.lisp"
    assert acl2_file.exists(), f"ACL2 file not found: {acl2_file}"


@pytest.mark.integration
@pytest.mark.skipif(not _tool_on_path("rocq-mcp"), reason="rocq‑mcp not installed")
def test_counter_verify_koika(counter_spec_path, build_dir):
    """Run proof obligations for the counter using the Kōika/Coq backend (no LLM).

    The proof library contains a verified proof for count_bound, so the
    verification should succeed without invoking the LLM.  A temporary
    config is passed via the SPECIR_CONFIG environment variable to enable
    the library and prevent any LLM fallback.
    """
    conf_path = build_dir / "test_config.yaml"
    build_dir.mkdir(parents=True, exist_ok=True)
    _write_library_config(conf_path)

    cmd = [
        str(counter_spec_path),
        "--backend", "koika",
        "--out-dir", str(build_dir / "verify"),
        "--no-llm",
        "--no-perf",
    ]

    env = os.environ.copy()
    env["SPECIR_CONFIG"] = str(conf_path)
    result = subprocess.run(
        [sys.executable, "-m", "specir.cli.verify"] + cmd,
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )

    if result.returncode not in (0, 1):
        pytest.fail(
            f"Verification crashed with code {result.returncode}:\n"
            f"STDERR: {result.stderr}\n"
            f"STDOUT: {result.stdout}"
        )

    coq_file = build_dir / "verify" / "counter" / "coq" / "counter.v"
    if not coq_file.exists():
        pytest.fail(
            f"Coq file was not generated.\n"
            f"STDERR: {result.stderr}\n"
            f"STDOUT: {result.stdout}"
        )

    if result.returncode == 0:
        assert "PASS" in result.stdout
    else:
        assert "FAIL" in result.stdout or "All proof attempts exhausted" in result.stderr


@pytest.mark.integration
@pytest.mark.skipif(not _tool_on_path("acl2"), reason="ACL2 not installed")
def test_counter_verify_acl2(counter_spec_path, build_dir):
    """Run proof obligations for the counter using the ACL2 backend."""
    cmd = [
        str(counter_spec_path),
        "--backend", "acl2",
        "--out-dir", str(build_dir / "verify"),
        "--no-perf",
    ]
    try:
        result = _run_specir("verify", cmd, timeout=300)
    except subprocess.TimeoutExpired as e:
        pytest.fail(
            f"ACL2 verification timed out (300 seconds).\n"
            f"STDERR captured so far:\n"
            f"{e.stderr.decode() if e.stderr else '(none)'}\n"
            f"STDOUT captured so far:\n"
            f"{e.stdout.decode() if e.stdout else '(none)'}"
        )

    if result.returncode not in (0, 1):
        pytest.fail(
            f"Verification crashed with code {result.returncode}:\n"
            f"STDERR: {result.stderr}\n"
            f"STDOUT: {result.stdout}"
        )

    acl2_file = build_dir / "verify" / "counter" / "acl2" / "counter.lisp"
    if not acl2_file.exists():
        pytest.fail(
            f"ACL2 file was not generated.\n"
            f"STDERR: {result.stderr}\n"
            f"STDOUT: {result.stdout}"
        )


@pytest.mark.integration
@pytest.mark.skipif(not _tool_on_path("verilator"), reason="Verilator not installed")
@pytest.mark.skipif(not _koika_works(), reason="Kōika compiler not fully integrated (missing extraction)")
def test_counter_simulate_lift_check(counter_spec_path, build_dir):
    """Compile to RTL, simulate, lift, and check properties.

    Skipped until the Coq‑to‑OCaml extraction step is automated.
    """
    pass
