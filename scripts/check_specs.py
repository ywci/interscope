#!/usr/bin/env python3
# scripts/check_specs.py
#
# Check that every examples/*/*.isir has a verified natural-language
# specification (a sibling `<name>.md`).  Run this when adding a new example or
# a new natural-language spec:
#
#   python scripts/check_specs.py             # completeness check
#   python scripts/check_specs.py --verify    # + lossless round-trip check
#
# Exits non-zero if any example is missing its spec or fails verification, so it
# can gate CI / the release of a new spec.

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from isir.lowering.ast_to_isir import convert_ast_to_isir_module  # noqa: E402
from isir.parser.parser import parse_isir  # noqa: E402


def _all_examples(root: Path):
    return sorted((root / "examples").glob("*/*.isir"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--verify", action="store_true",
        help="also run the lossless round-trip check for every example",
    )
    ap.add_argument("--cycles", type=int, default=20)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[1]
    examples = _all_examples(root)

    missing: list = []
    failed_verify: list = []
    for isir in examples:
        md = isir.with_suffix(".md")
        if not md.exists():
            missing.append(isir)
            continue
        if args.verify:
            from gen_spec import verify_roundtrip  # noqa: E402  (scripts/ on sys.path)
            spec = convert_ast_to_isir_module(parse_isir(isir).module)
            if not verify_roundtrip(spec, args.cycles, args.seed):
                failed_verify.append(isir)

    if missing:
        print(f"ERROR: {len(missing)} example(s) missing a natural-language spec (.md):")
        for p in missing:
            print(f"  - {p}")
    if failed_verify:
        print(f"ERROR: {len(failed_verify)} example(s) failed the round-trip check:")
        for p in failed_verify:
            print(f"  - {p}")

    if missing or failed_verify:
        return 1

    suffix = " (round-trip verified)" if args.verify else ""
    print(f"OK: all {len(examples)} examples have a natural-language spec{suffix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
