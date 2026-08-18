# src/specir/verification/proof/structural_validator.py
#
# Structural validation of Coq proof scripts.
#
# This module provides lightweight, deterministic checks for common
# structural issues that cause compilation errors or make proofs harder
# for LLM repair.  It is used by the PERF traversal, the linear prover,
# and the repair loop to reject or penalise problematic scripts before
# they are sent to the tool.
#
# The validator currently checks:
#   - Balanced braces `{` / `}` and parentheses `(` / `)`.
#   - Unclosed `Proof.` blocks (no matching `Qed.`/`Admitted.`).
#   - Presence of deprecated notations (e.g., `Nat.mod_add`,
#     `Nat.add_mod`, `Nat.mod_same`, etc.) that produce warnings and may be
#     rejected by modern Coq.  These are reported as HARD ERROR entries so
#     that PERF can immediately filter out scripts containing them.
#   - Presence of `discriminate` on hypotheses that appear to be
#     boolean equalities (e.g., `(op_reg s =? 0) = true`).
#   - Orphan bullet lines (a line consisting solely of `-`, `+`, `*`).
#     These often cause focus errors.
#   - Mixed bullet and brace usage – using both `-/+/*` and
#     `{ ... }` subgoal separation in the same proof often leads to
#     `[Focus] Wrong bullet` or “This proof is focused, but cannot be
#     unfocused this way”.
#   - Focus‑error patterns – lines containing subgoal bullets that are
#     likely to cause focus issues when combined with explicit braces.
#   - Missing standard imports: checks for the presence of common
#     `Require Import` lines if the script uses tactics or lemmas
#     that depend on them (e.g., `lia`, `nia`, `Nat.eqb_eq`).
#
# The checks are intentionally conservative; a script that passes is
# not guaranteed to compile, but one that fails should be treated with
# suspicion.

import re
from typing import List, Dict
from specir.utils.logger import get_logger

logger = get_logger(__name__)

DEPRECATED_NOTATIONS: Dict[str, str] = {
    "Nat.mod_add": "Div0.mod_add",
    "Nat.mod_mul": "Div0.mod_mul",
    "Nat.mod_mod": "Div0.mod_mod",
    "Nat.mod_same": "Div0.mod_same",
    "Nat.mod_1_l": "Div0.mod_1_l",
    "Nat.mod_1_r": "Div0.mod_1_r",
    "Nat.mod_0_l": "Div0.mod_0_l",
    "Nat.mod_0_r": "Div0.mod_0_r",
    "Nat.add_mod": "Div0.add_mod",
    "Nat.mul_mod": "Div0.mul_mod",
    "Nat.sub_mod": "Div0.sub_mod",
    "Nat.div_add": "Div0.div_add",
    "Nat.div_mul": "Div0.div_mul",
    "Nat.div_div": "Div0.div_div",
    "Nat.div_same": "Div0.div_same",
    "Nat.div_1_r": "Div0.div_1_r",
    "Nat.div_1_l": "Div0.div_1_l",
}

# Common tactic/lemma dependencies and their required imports.
COMMON_DEPENDENCIES = {
    "lia": ["Require Import Lia."],
    "nia": ["Require Import Lia."],
    "Nat.eqb_eq": ["Require Import Arith.PeanoNat."],
    "Nat.eqb_neq": ["Require Import Arith.PeanoNat."],
    "Div0.add_mod": ["Require Import Arith.Div0."],
    "Div0.mod_add": ["Require Import Arith.Div0."],
    "Div0.mod_same": ["Require Import Arith.Div0."],
    "Div0.mod_mod": ["Require Import Arith.Div0."],
    "list_update": ["Require Import Lists.List."],
    "nth_default": ["Require Import Lists.List."],
    "ListNotations": ["Require Import Lists.List."],
}


def validate_structure(script: str, context: str = "") -> List[str]:
    """
    Validate a Coq proof script for common structural issues.

    Args:
        script: The proof script as a string (typically includes
                `Proof.` … `Qed.` or `Admitted.`).
        context: Optional surrounding Coq environment (definitions and
                 imports) to check for missing dependencies. If empty,
                 missing-import checks are skipped.

    Returns:
        A list of issue strings describing problems found. An empty
        list means no obvious structural issues were detected.
    """
    if not script:
        return ["Empty proof script"]

    issues: List[str] = []

    # 1. Balanced braces and parentheses.
    issues.extend(_check_balanced_delimiters(script))

    # 2. Unclosed Proof blocks.
    issues.extend(_check_unclosed_proofs(script))

    # 3. Deprecated notations – now reported as HARD ERROR.
    issues.extend(_check_deprecated_notations(script))

    # 4. Suspicious `discriminate` on boolean equalities.
    issues.extend(_check_boolean_discriminate(script))

    # 5. Orphan bullet lines (focus errors).
    issues.extend(_check_orphan_bullets(script))

    # 6. Mixed bullet and brace usage (focus error contributor).
    issues.extend(_check_mixed_bullets_braces(script))

    # 7. Additional focus‑error patterns.
    issues.extend(_check_focus_patterns(script))

    # 8. Missing standard imports (if context provided).
    if context:
        issues.extend(_check_missing_imports(script, context))

    return issues


def _check_balanced_delimiters(script: str) -> List[str]:
    """
    Check that parentheses and curly braces are balanced.
    """
    issues = []

    # Remove comments and strings to avoid false positives.
    clean = _remove_comments(script)
    clean = _remove_strings(clean)

    for open_delim, close_delim, name in [
        ("{", "}", "braces"),
        ("(", ")", "parentheses"),
        ("[", "]", "square brackets"),
    ]:
        balance = 0
        for ch in clean:
            if ch == open_delim:
                balance += 1
            elif ch == close_delim:
                balance -= 1
                if balance < 0:
                    issues.append(f"Unbalanced {name}: unexpected '{close_delim}'")
                    break
        if balance > 0:
            issues.append(f"Unbalanced {name}: missing {balance} closing '{close_delim}'")

    return issues


def _check_unclosed_proofs(script: str) -> List[str]:
    """
    Detect `Proof.` blocks that are not closed by `Qed.` or `Admitted.`.

    This is important because an open proof before a theorem causes the
    Coq error "Nested proofs are discouraged and not allowed by default."
    """
    # Strip comments and strings to avoid counting inside them.
    clean = _remove_comments(script)
    clean = _remove_strings(clean)

    proof_depth = 0
    issues = []

    for line_no, line in enumerate(clean.splitlines(), start=1):
        # Count proof starts and ends in the line.
        starts = len(re.findall(r"\bProof\.", line))
        ends_qed = len(re.findall(r"\bQed\.", line))
        ends_admitted = len(re.findall(r"\bAdmitted\.", line))

        proof_depth += starts
        proof_depth -= (ends_qed + ends_admitted)

        if proof_depth < 0:
            issues.append(f"Line {line_no}: unexpected 'Qed.'/'Admitted.' without open 'Proof.'")
            proof_depth = 0

    if proof_depth > 0:
        issues.append(
            f"Unclosed proof block(s): {proof_depth} 'Proof.' without matching "
            "'Qed.'/'Admitted.'"
        )
    return issues


def _check_deprecated_notations(script: str) -> List[str]:
    """
    Detect use of deprecated notations (e.g., ``Nat.mod_add``,
    ``Nat.add_mod``, ``Nat.mod_same``).

    These are now reported as HARD ERROR so that PERF can treat them
    as immediate rejection criteria.
    """
    issues = []
    for old, new in DEPRECATED_NOTATIONS.items():
        if re.search(rf"\b{re.escape(old)}\b", script):
            issues.append(
                f"[HARD ERROR] Deprecated notation '{old}' found; use '{new}' instead."
            )
    return issues


def _check_boolean_discriminate(script: str) -> List[str]:
    """
    Detect `discriminate` on hypotheses that likely are boolean equalities.

    This is a heuristic based on the common pattern:
        Hop : (op_reg s =? 0) = true
        discriminate Hop.

    We flag any `discriminate <name>.` where the same proof contains a
    hypothesis of the form `(<expr> =? <expr>) = true` and the name is
    used in that hypothesis.
    """
    issues = []

    discr_pattern = re.compile(r"discriminate\s+(\w+)\.")
    for m in discr_pattern.finditer(script):
        hyp_name = m.group(1)

        boolean_hyp_pattern = re.compile(
            rf"{re.escape(hyp_name)}\s*:\s*\(?[^\)]*(?:=\?|Nat\.eqb)[^\)]*\)?\s*=\s*true"
        )
        if boolean_hyp_pattern.search(script):
            issues.append(
                f"`discriminate {hyp_name}` used on a boolean equality; "
                "use `inversion` or `rewrite Nat.eqb_eq` instead."
            )
            break

    return issues


def _check_orphan_bullets(script: str) -> List[str]:
    """
    Detect lines that consist solely of a bullet character (`-`, `+`, `*`)
    and nothing else (except possibly whitespace).  Such lines often
    indicate misuse of bullets and can lead to `Wrong bullet` errors.
    """
    issues = []
    orphan_pattern = re.compile(r"^\s*([-+*])\s*$")
    for i, line in enumerate(script.splitlines(), start=1):
        if orphan_pattern.match(line):
            issues.append(
                f"Line {i}: orphan bullet '{line.strip()}' without a following tactic or comment."
            )
    return issues


def _check_mixed_bullets_braces(script: str) -> List[str]:
    """
    Detect scripts that mix bullet‑based subgoal separation (`-`, `+`, `*`)
    with explicit brace blocks (`{ ... }`).

    Mixing the two often leads to focus errors because Coq treats bullets
    as a lightweight focus mechanism that cannot be safely combined with
    explicit braces in all contexts.
    """
    issues = []

    # Check if the script contains any bullet line (a line starting with
    # -/+/* followed by whitespace or end-of-line).
    bullet_pattern = re.compile(r"^\s*[-+*]\s", re.MULTILINE)
    has_bullets = bool(bullet_pattern.search(script))

    # Check if the script contains any brace line (a line starting with `{`
    # or ending with `}`).
    brace_pattern = re.compile(r"^\s*\{|\}\s*$", re.MULTILINE)
    has_braces = bool(brace_pattern.search(script))

    if has_bullets and has_braces:
        issues.append(
            "[HARD ERROR] Mixed bullet and brace usage detected; "
            "use only `{ ... }` blocks for subgoal separation to avoid focus errors."
        )

    return issues


def _check_focus_patterns(script: str) -> List[str]:
    """
    Detect patterns that commonly cause focus errors:
      - A line that starts with a bullet and is followed by a closing brace
        (e.g., `- }` or `+ }`), which indicates an attempt to close a brace
        while still inside a bullet focus.
      - Multiple bullets of the same type at the same indentation level
        without proper closure.
      - Lines that contain only `{` or `}` but no tactic.

    These are heuristic checks; they are not intended to be exhaustive.
    """
    issues = []

    # Check for bullet followed by closing brace on same line.
    bullet_brace_pattern = re.compile(r"^\s*[-+*]\s*\}", re.MULTILINE)
    if bullet_brace_pattern.search(script):
        issues.append(
            "[HARD ERROR] Bullet followed by closing brace detected; "
            "this is a common cause of focus errors. Use explicit braces."
        )

    # Check for consecutive bullet lines of the same type that are not
    # separated by a closing brace (probably an unclosed subgoal).
    lines = script.splitlines()
    last_bullet = None
    last_indent = -1
    for i, line in enumerate(lines, start=1):
        stripped = line.strip()
        bullet_match = re.match(r"^([-+*])\s", stripped)
        if bullet_match:
            bullet_char = bullet_match.group(1)
            indent = len(line) - len(line.lstrip())
            if last_bullet is not None and bullet_char == last_bullet and indent == last_indent:
                issues.append(
                    f"Line {i}: consecutive bullets of same type and indentation "
                    "without proper closure; this often causes `Wrong bullet`."
                )
            last_bullet = bullet_char
            last_indent = indent
        elif stripped and not stripped.startswith('(*'):
            # Any non‑bullet, non‑comment line resets the tracking.
            last_bullet = None
            last_indent = -1

    return issues


def _check_missing_imports(script: str, context: str) -> List[str]:
    """
    Detect missing standard imports based on the tactics/lemmas used in
    the script and the provided context.  If a required import is not
    present in the context, flag it.
    """
    issues = []
    for pattern, required_imports in COMMON_DEPENDENCIES.items():
        if re.search(rf"\b{re.escape(pattern)}\b", script):
            for imp in required_imports:
                if imp not in context:
                    issues.append(
                        f"Missing import '{imp}' (required by '{pattern}')"
                    )
    return issues


def _remove_comments(script: str) -> str:
    """
    Remove Coq comments (``(* ... *)``) from a script.
    This is intentionally simple; nested comments are not handled.
    """
    return re.sub(r"\(\*.*?\*\)", "", script, flags=re.DOTALL)


def _remove_strings(script: str) -> str:
    """
    Remove string literals (``"..."``) from a script.
    """
    return re.sub(r'"(?:[^"\\]|\\.)*"', '""', script)
