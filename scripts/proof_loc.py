#!/usr/bin/env python3
# scripts/proof_loc.py
#
# Dump the generated proof code for each PASSED obligation and report its size
# in lines of code (LoC).  The proof code is the same script `--show-proof`
# prints: the Coq `Proof. ... Qed.` body for Koika, the `(defthm ... :hints ...)`
# form for ACL2.
#
# `--self-contained DIR` additionally emits a *re-compilable* proof artifact for
# each passed proof (context + theorem statement + proof body) and verifies it by
# re-running coqc (Koika) / ACL2 `ld` (ACL2).
#
# Usage:
#   python scripts/proof_loc.py <file.isir> --backend <koika|acl2|koika_acl2> [--search <s>]
#   python scripts/proof_loc.py <file.isir> --backend koika --dump DIR
#   python scripts/proof_loc.py <file.isir> --backend koika_acl2 --self-contained DIR

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
COQC = shutil.which("coqc")
ACL2 = shutil.which("acl2")


def run_verify(isir: str, backend: str, search: str) -> str:
    cmd = [
        sys.executable, "-m", "isir.cli.verify", isir,
        "--backend", backend, "--search", search, "--show-proof",
    ]
    env = dict(__import__("os").environ)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600, env=env)
    return r.stdout + r.stderr


def extract_proofs(out: str):
    """Yield (property, backend, proof_script) from `--show-proof` output."""
    lines = out.splitlines()
    i = 0
    while i < len(lines):
        m = re.match(r"PASS: (\S+) \((\w+)\)", lines[i])
        if m and i + 1 < len(lines) and lines[i + 1].strip() == "Proof:":
            prop, backend = m.group(1), m.group(2)
            j = i + 2
            body = []
            while j < len(lines):
                ln = lines[j]
                if re.match(r"(PASS|FAIL): ", ln):
                    break
                if ln.startswith("=====") or ln.startswith("Verification Summary") \
                        or re.match(r"\d{4}-\d{2}-\d{2}", ln):
                    break
                body.append(ln)
                j += 1
            yield prop, backend, "\n".join(body).rstrip()
            i = j
        else:
            i += 1


def _which_backend(script: str) -> str:
    return "acl2" if script.lstrip().startswith("(defthm") else "koika"


def _koika_self_contained(ex_name: str, prop: str, script: str, out_dir: Path):
    """Emit + verify a self-contained Coq file for one Koika proof."""
    v = REPO / "build" / "verify" / ex_name / "coq" / f"{ex_name}.v"
    if not v.exists():
        return "no-context", None, f"generated {v} missing"
    text = v.read_text()
    idx = text.find(f"(* PERF_Obligation: {prop} *)")
    if idx < 0:
        return "no-context", None, f"marker for '{prop}' not found in {v.name}"
    context = text[:idx].rstrip()
    m = re.search(rf"Theorem {re.escape(prop)}_proved\s*:\s*([^.]*\.)", text[idx:])
    if not m:
        return "no-context", None, f"theorem statement for '{prop}' not found"
    statement = m.group(1).strip().rstrip(".")
    name = f"{prop}_proved"
    full = f"{context}\n\nTheorem {name} : {statement}.\n{script}\n"
    out = out_dir / f"{prop}_koika_self.v"
    out.write_text(full, encoding="utf-8")
    r = subprocess.run([COQC, str(out)], capture_output=True, text=True, timeout=300,
                       cwd=str(out_dir))
    ok = r.returncode == 0
    detail = "" if ok else (r.stderr or r.stdout)[-300:]
    return ("ok" if ok else "FAIL"), out.name, detail


def _acl2_self_contained(ex_name: str, prop: str, script: str, out_dir: Path):
    """Emit + verify a self-contained ACL2 file for one ACL2 proof."""
    l = REPO / "build" / "verify" / ex_name / "acl2" / f"{ex_name}.lisp"
    if not l.exists():
        return "no-context", None, f"generated {l} missing"
    text = l.read_text()
    idx = text.find("(skip-proofs")
    context = text[:idx].rstrip() if idx >= 0 else text.rstrip()
    full = f"{context}\n\n{script}\n"
    out = out_dir / f"{prop}_acl2_self.lisp"
    out.write_text(full, encoding="utf-8")
    r = subprocess.run([ACL2], input=f'(in-package "ACL2")\n(ld "{out}")\n',
                       capture_output=True, text=True, timeout=300, cwd=str(out_dir))
    ok = r.returncode == 0 and "ACL2 Error" not in (r.stdout + r.stderr)
    detail = "" if ok else (r.stderr or r.stdout)[-300:]
    return ("ok" if ok else "FAIL"), out.name, detail


def _self_contained(ex_name: str, prop: str, script: str, out_dir: Path):
    if _which_backend(script) == "acl2":
        return _acl2_self_contained(ex_name, prop, script, out_dir)
    return _koika_self_contained(ex_name, prop, script, out_dir)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("isir", help=".isir file")
    ap.add_argument("--backend", default="koika")
    ap.add_argument("--search", default="perf")
    ap.add_argument("--dump", help="directory to write <prop>.<backend>.proof files")
    ap.add_argument("--self-contained", metavar="DIR",
                    help="emit + re-compile a self-contained proof per passed obligation")
    args = ap.parse_args()

    out = run_verify(args.isir, args.backend, args.search)
    proofs = list(extract_proofs(out))
    if not proofs:
        print("no passed proofs found (check backend/obligation tags)")
        return 1

    total = 0
    print(f"{'property':30s} {'backend':12s} {'LoC':>5s}")
    print("-" * 50)
    for prop, backend, script in proofs:
        loc = len(script.splitlines())
        total += loc
        print(f"{prop:30s} {backend:12s} {loc:5d}")
        if args.dump:
            d = Path(args.dump)
            d.mkdir(parents=True, exist_ok=True)
            (d / f"{prop}.{backend}.proof").write_text(script, encoding="utf-8")
    print("-" * 50)
    print(f"{'total':30s} {'':12s} {total:5d}")
    if proofs:
        print(f"{'average':30s} {'':12s} {total / len(proofs):5.1f}")

    if args.self_contained:
        out_dir = Path(args.self_contained)
        out_dir.mkdir(parents=True, exist_ok=True)
        ex_name = Path(args.isir).stem
        print("\n===== Self-contained re-compilation =====")
        for prop, backend, script in proofs:
            status, fname, detail = _self_contained(ex_name, prop, script, out_dir)
            line = f"{prop:30s} {status}"
            if fname:
                line += f"  ({fname})"
            print(line)
            if detail:
                print(f"    {detail.strip()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
