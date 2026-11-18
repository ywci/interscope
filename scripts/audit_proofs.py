#!/usr/bin/env python3
# scripts/audit_proofs.py
#
# Audit proof completeness across every example × backend.  A proof is
# "complete" when the verify run returns success (the Coq theorem is Qed., not
# Admitted., and the ACL2 defthm is proved, not skip-proofs).
#
# Usage:
#   python scripts/audit_proofs.py [--backends koika,acl2,koika_acl2] [--timeout 120]

import argparse
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
EXAMPLES = sorted((REPO / "examples").glob("*/*.isir"))


def run_verify(isir: str, backend: str, timeout: int):
    cmd = [sys.executable, "-m", "isir.cli.verify", isir, "--backend", backend]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        ok = r.returncode == 0 and "0 failed" in (r.stdout + r.stderr)
        out = r.stdout + r.stderr
        n_pass = out.count("  PASS:") + out.count("PASS:")
        summary = ""
        for line in out.splitlines():
            if "Verification Summary" in line:
                summary = line.strip()
                break
        return ok, summary
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--backends", default="koika,acl2,koika_acl2")
    ap.add_argument("--timeout", type=int, default=120)
    args = ap.parse_args()
    backends = [b.strip() for b in args.backends.split(",") if b.strip()]

    print(f"example | " + " | ".join(backends), flush=True)
    print("-" * 60)
    incomplete = []
    for isir in EXAMPLES:
        name = isir.stem
        row = []
        for backend in backends:
            ok, summary = run_verify(str(isir), backend, args.timeout)
            row.append("PASS" if ok else ("FAIL" if summary != "TIMEOUT" else "TIMEOUT"))
            if not ok:
                incomplete.append((name, backend, summary or "FAIL"))
        print(f"{name:20s} | " + " | ".join(row), flush=True)

    print("\n===== Incomplete proofs =====")
    if not incomplete:
        print("none")
    for name, backend, summary in incomplete:
        print(f"{name:20s} {backend:14s} {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
