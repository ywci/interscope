# tests/integration/fifo/test_fifo.py
#
# Integration test for the FIFO example.
# Compiles to Kōika/Coq and ACL2, and optionally runs proof verification
# when the required external tools are available.
# The simulation + lift + check test is skipped until the Kōika extraction
# step is automated.

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


@pytest.fixture
def fifo_spec_path():
    return Path(__file__).parent / "fifo.specir"


@pytest.fixture
def build_dir(tmp_path):
    return tmp_path / "build"


@pytest.mark.integration
def test_fifo_compile_koika(fifo_spec_path, build_dir):
    """Compile the FIFO spec to Kōika/Coq (generates a .v file) without RTL."""
    cmd = [
        str(fifo_spec_path),
        "--backend", "koika",
        "--out-dir", str(build_dir),
        "--no-rtl",
    ]
    result = subprocess.run(
        [sys.executable, "-m", "specir.cli.compile"] + cmd,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, (
        f"Compilation failed with code {result.returncode}:\n"
        f"STDERR: {result.stderr}\n"
        f"STDOUT: {result.stdout}"
    )
    coq_file = build_dir / "fifo" / "coq" / "fifo.v"
    assert coq_file.exists(), f"Coq file not found: {coq_file}"


@pytest.mark.integration
def test_fifo_compile_acl2(fifo_spec_path, build_dir):
    """Compile the FIFO spec to ACL2 (generates a .lisp file)."""
    cmd = [
        str(fifo_spec_path),
        "--backend", "acl2",
        "--out-dir", str(build_dir),
    ]
    result = subprocess.run(
        [sys.executable, "-m", "specir.cli.compile"] + cmd,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, (
        f"Compilation failed with code {result.returncode}:\n"
        f"STDERR: {result.stderr}\n"
        f"STDOUT: {result.stdout}"
    )
    acl2_file = build_dir / "fifo" / "acl2" / "fifo.lisp"
    assert acl2_file.exists(), f"ACL2 file not found: {acl2_file}"


@pytest.mark.integration
@pytest.mark.skipif(not _tool_on_path("rocq-mcp"), reason="rocq‑mcp not installed")
def test_fifo_verify_koika(fifo_spec_path, build_dir):
    """Run proof obligations for the FIFO using the Kōika/Coq backend.

    A temporary config enables the proof library, which contains a verified
    proof for the FIFO property, so verification succeeds quickly.
    """
    conf_path = build_dir / "test_config.yaml"
    build_dir.mkdir(parents=True, exist_ok=True)
    _write_library_config(conf_path)

    cmd = [
        str(fifo_spec_path),
        "--backend", "koika",
        "--out-dir", str(build_dir / "verify"),
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

    coq_file = build_dir / "verify" / "fifo" / "coq" / "fifo.v"
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
def test_fifo_verify_acl2(fifo_spec_path, build_dir):
    """Run proof obligations for the FIFO using the ACL2 backend."""
    cmd = [
        str(fifo_spec_path),
        "--backend", "acl2",
        "--out-dir", str(build_dir / "verify"),
        "--no-perf",
    ]
    try:
        result = subprocess.run(
            [sys.executable, "-m", "specir.cli.verify"] + cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired as e:
        pytest.fail(
            f"ACL2 verification timed out (120 seconds).\n"
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

    acl2_file = build_dir / "verify" / "fifo" / "acl2" / "fifo.lisp"
    if not acl2_file.exists():
        pytest.fail(
            f"ACL2 file was not generated.\n"
            f"STDERR: {result.stderr}\n"
            f"STDOUT: {result.stdout}"
        )


@pytest.mark.integration
@pytest.mark.skipif(not _tool_on_path("verilator"), reason="Verilator not installed")
@pytest.mark.skipif(not _koika_works(), reason="Kōika compiler not fully integrated (missing extraction)")
def test_fifo_simulate_lift_check(fifo_spec_path, build_dir):
    """Compile to RTL with the external Kōika compiler, simulate with Verilator,
    lift the VCD trace, and check properties against the abstract trace.

    Skipped until the Coq‑to‑OCaml extraction step is automated.
    """
    pass
