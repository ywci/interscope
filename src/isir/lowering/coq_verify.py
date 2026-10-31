# src/isir/lowering/coq_verify.py
#
# Coq verification gate: detect and eliminate `Admitted` in generated proofs.
#
# `Admitted` (unlike `Axiom`) declares `Theorem X : P` but leaves it unproved,
# which is both unsound and misleading (it *looks* proved).  The LLM prover
# replaces each `Admitted` with a real `Proof. ... Qed.`; the verification is
# "complete" only when no `Admitted` remains.  Properties that are genuinely out
# of scope (e.g. unbounded liveness) are downgraded to an explicit `Axiom`.

from __future__ import annotations

import re
from typing import Iterable, List


def find_admitted(coq_text: str) -> List[str]:
    """Return the names of theorems that are still `Admitted` (no `Qed.`).

    Tracks the most recent `Theorem NAME :` and reports it if it is followed by
    an `Admitted.` without an intervening `Qed.` (or a new theorem/axiom).
    """
    admitted: List[str] = []
    current: str | None = None
    seen_admitted = False
    seen_qed = False

    for line in coq_text.splitlines():
        thm = re.match(r"\s*Theorem\s+([A-Za-z0-9_']+)\s*:", line)
        ax = re.match(r"\s*(?:Axiom|Parameter|Definition|Lemma|Fixpoint)\s+([A-Za-z0-9_']+)", line)
        if thm or ax:
            if current is not None and seen_admitted and not seen_qed:
                admitted.append(current)
            current = thm.group(1) if thm else None
            seen_admitted = False
            seen_qed = False
            continue
        if re.search(r"\bAdmitted\.", line):
            seen_admitted = True
        if re.search(r"\bQed\.", line):
            seen_qed = True

    if current is not None and seen_admitted and not seen_qed:
        admitted.append(current)
    return admitted


def verify_no_admitted(coq_text: str) -> List[str]:
    """The gate: return the Admitted theorem names (empty means fully proved)."""
    return find_admitted(coq_text)


def downgrade_to_axiom(coq_text: str, names: Iterable[str]) -> str:
    """Rewrite `Theorem NAME : P. Admitted.` to `Axiom NAME : P.` for `names`.

    The trailing `Admitted.` line is dropped, so the result carries no proof
    placeholder — only an explicit assumption.
    """
    names = set(names)
    out: List[str] = []
    downgrading = False
    for line in coq_text.splitlines():
        m = re.match(r"\s*Theorem\s+([A-Za-z0-9_']+)\s*:", line)
        if m and m.group(1) in names:
            out.append(line.replace("Theorem", "Axiom", 1))
            downgrading = True
            continue
        if downgrading and re.search(r"\bAdmitted\.", line):
            downgrading = False
            continue  # drop the placeholder
        out.append(line)
    return "\n".join(out) + "\n"
