#!/usr/bin/env python3
# scripts/verify_proofs.py
#
# Verify that the dumped proof code of every example × backend is COMPLETE (no
# `Admitted.`/`skip-proofs` placeholder) and CORRECT (the generated file
# actually re-compiles).
#
#   complete : the Coq theorem is `Qed.` (not `Admitted.`), the ACL2 defthm is
#              proved (not skip-proofs)
#   correct  : re-running coqc (Koika) / ACL2 `ld` (ACL2) on the file succeeds
#
# Usage:
#   python scripts/verify_proofs.py [--backends koika,acl2]

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
EXAMPLES = sorted((REPO / "examples").glob("*/*.isir"))
COQC = shutil.which("coqc")
ACL2 = shutil.which("acl2")


def check_koika(ex_dir: Path):
    v = ex_dir / "coq" / f"{ex_dir.name}.v"
    if not v.exists():
        return "no-file", "no-file"
    text = v.read_text()
    complete = "Admitted." not in text and "Qed." in text
    # correctness: re-compile with coqc
    if COQC:
        r = subprocess.run([COQC, "-Q", str(v.parent), "Test", str(v)],
                           capture_output=True, text=True, timeout=120, cwd=str(v.parent))
        correct = r.returncode == 0
    else:
        correct = None
    return ("complete" if complete else "INCOMPLETE",
            ("correct" if correct else "INCORRECT") if correct is not None else "n/a")


def check_acl2(ex_dir: Path):
    l = ex_dir / "acl2" / f"{ex_dir.name}.lisp"
    if not l.exists():
        return "no-file", "no-file"
    text = l.read_text()
    complete = "skip-proofs" not in text.lower() and "defthm" in text.lower()
    if ACL2:
        r = subprocess.run([ACL2], input=f'(in-package "ACL2")\n(ld "{l}")\n',
                           capture_output=True, text=True, timeout=120)
        correct = r.returncode == 0 and "ACL2 Error" not in (r.stdout + r.stderr)
    else:
        correct = None
    return ("complete" if complete else "INCOMPLETE",
            ("correct" if correct else "INCORRECT") if correct is not None else "n/a")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--backends", default="koika,acl2")
    args = ap.parse_args()
    backends = [b.strip() for b in args.backends.split(",") if b.strip()]

    print(f"example | " + " | ".join(f"{b} (complete/correct)" for b in backends))
    print("-" * 80)
    bad = []
    for isir in EXAMPLES:
        name = isir.stem
        ex_dir = REPO / "build" / "verify" / name
        cells = []
        for backend in backends:
            if backend == "koika":
                c, r = check_koika(ex_dir)
            elif backend == "acl2":
                c, r = check_acl2(ex_dir)
            else:
                continue
            cells.append(f"{c}/{r}")
            if c != "complete" or r not in ("correct", "n/a"):
                bad.append((name, backend, c, r))
        print(f"{name:20s} | " + " | ".join(cells))

    print("\n===== Incomplete / incorrect =====")
    if not bad:
        print("none")
    for name, backend, c, r in bad:
        print(f"{name:20s} {backend:8s} {c} / {r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
