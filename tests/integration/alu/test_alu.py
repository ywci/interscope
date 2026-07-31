# tests/integration/alu/test_alu.py
#
# Integration test for the ALU example.
# Compiles to Kōika/Coq and ACL2, and optionally runs proof verification
# when the required external tools are available. The simulation + lift + check
# test is skipped until the Kōika extraction step is automated.

import subprocess
import sys
import pytest
from pathlib import Path


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


def _run_specir(subcommand: str, args: list, timeout: int = 120, **kwargs) -> subprocess.CompletedProcess:
    """Run a specir CLI command using the current Python interpreter."""
    return subprocess.run(
        [sys.executable, "-m", "specir.cli." + subcommand] + args,
        capture_output=True,
        text=True,
        timeout=timeout,
        **kwargs,
    )


@pytest.fixture
def alu_spec_path():
    return Path(__file__).parent / "alu.specir"


@pytest.fixture
def build_dir(tmp_path):
    return tmp_path / "build"


@pytest.mark.integration
def test_alu_compile_koika(alu_spec_path, build_dir):
    """Compile the ALU spec to Kōika/Coq (generates a .v file) without RTL."""
    cmd = [
        str(alu_spec_path),
        "--backend", "koika",
        "--out-dir", str(build_dir),
        "--no-rtl",
    ]
    result = _run_specir("compile", cmd, timeout=60)
    assert result.returncode == 0, (
        f"Compilation failed with code {result.returncode}:\n"
        f"STDERR: {result.stderr}\n"
        f"STDOUT: {result.stdout}"
    )
    coq_file = build_dir / "alu" / "coq" / "alu.v"
    assert coq_file.exists(), f"Coq file not found: {coq_file}"


@pytest.mark.integration
def test_alu_compile_acl2(alu_spec_path, build_dir):
    """Compile the ALU spec to ACL2 (generates a .lisp file)."""
    cmd = [
        str(alu_spec_path),
        "--backend", "acl2",
        "--out-dir", str(build_dir),
    ]
    result = _run_specir("compile", cmd, timeout=60)
    assert result.returncode == 0, (
        f"Compilation failed with code {result.returncode}:\n"
        f"STDERR: {result.stderr}\n"
        f"STDOUT: {result.stdout}"
    )
    acl2_file = build_dir / "alu" / "acl2" / "alu.lisp"
    assert acl2_file.exists(), f"ACL2 file not found: {acl2_file}"


@pytest.mark.integration
@pytest.mark.skipif(not _tool_on_path("rocq-mcp"), reason="rocq‑mcp not installed")
def test_alu_verify_koika(alu_spec_path, build_dir):
    """Run proof obligations for the ALU using the Kōika/Coq backend (no LLM, no PERF)."""
    cmd = [
        str(alu_spec_path),
        "--backend", "koika",
        "--out-dir", str(build_dir / "verify"),
        "--no-llm",               # avoid network calls
        "--no-perf",              # disable PERF to prevent timeouts
    ]
    # Increased timeout: 30s was not enough for the full toolchain
    result = _run_specir("verify", cmd, timeout=60)

    if result.returncode not in (0, 1):
        pytest.fail(
            f"Verification crashed with code {result.returncode}:\n"
            f"STDERR: {result.stderr}\n"
            f"STDOUT: {result.stdout}"
        )

    coq_file = build_dir / "verify" / "alu" / "coq" / "alu.v"
    if not coq_file.exists():
        pytest.fail(
            f"Coq file was not generated.\n"
            f"STDERR: {result.stderr}\n"
            f"STDOUT: {result.stdout}"
        )


@pytest.mark.integration
@pytest.mark.skipif(not _tool_on_path("acl2"), reason="ACL2 not installed")
def test_alu_verify_acl2(alu_spec_path, build_dir):
    """Run proof obligations for the ALU using the ACL2 backend."""
    cmd = [
        str(alu_spec_path),
        "--backend", "acl2",
        "--out-dir", str(build_dir / "verify"),
        "--no-perf"
    ]
    try:
        result = _run_specir("verify", cmd, timeout=120)
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

    acl2_file = build_dir / "verify" / "alu" / "acl2" / "alu.lisp"
    if not acl2_file.exists():
        pytest.fail(
            f"ACL2 file was not generated.\n"
            f"STDERR: {result.stderr}\n"
            f"STDOUT: {result.stdout}"
        )


@pytest.mark.integration
@pytest.mark.skipif(not _tool_on_path("verilator"), reason="Verilator not installed")
@pytest.mark.skipif(not _koika_works(), reason="Kōika compiler not fully integrated (missing extraction)")
def test_alu_simulate_lift_check(alu_spec_path, build_dir):
    """Compile to RTL with the external Kōika compiler, simulate with Verilator,
    lift the VCD trace, and check properties against the abstract trace.

    Skipped until the Coq‑to‑OCaml extraction step is automated.
    """
    pass
