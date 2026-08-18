# src/specir/verification/proof/koika/auto_patcher.py
#
# Deterministic patching of common Coq proof errors.
#
# This module provides a set of functions that attempt to repair
# the most frequent mechanical mistakes found in LLM‑generated Coq
# proofs for Kōika designs.  The patches are designed to be safe
# and idempotent; they do not require an LLM and can be applied
# before compilation or before passing a script to the repair loop.
#
# Supported patches:
#   1. Replacement of deprecated notations (e.g., Nat.mod_add → Div0.mod_add).
#   2. Correction of `discriminate` on boolean equalities, which often
#      appear as hypotheses like `(op_reg s =? 0) = true`.
#   3. Removal of orphan bullet lines (lines that consist solely of a bullet
#      character).  This patch is applied **only** when the error message
#      indicates a focus/bullet problem or when such orphan lines are
#      detected.

import re
from typing import Dict, List, Optional
from specir.utils.logger import get_logger
from specir.verification.proof.structural_validator import validate_structure

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


def patch_deprecated_notations(script: str) -> str:
    """
    Replace deprecated lemma names with their modern equivalents.

    Args:
        script: Coq proof script.

    Returns:
        Script with deprecated notations replaced.
    """
    if not script:
        return script

    patched = script
    for old, new in DEPRECATED_NOTATIONS.items():
        # Use word boundaries to avoid partial replacements.
        patched = re.sub(rf"\b{re.escape(old)}\b", new, patched)

    if patched != script:
        logger.debug("Patched deprecated notations in script.")
    return patched


def patch_discriminate_on_bool(script: str, error_msg: str = "") -> str:
    """
    Replace `discriminate` on hypotheses that are boolean equalities
    (e.g., `Hop : (op_reg s =? 0) = true`) with `inversion`.

    This patch is triggered when:
      - The provided ``error_msg`` contains ``"Not a discriminable equality"``, or
      - The script itself contains a hypothesis of the form
        ``<name> : ( ... =? ... ) = true`` and a corresponding
        ``discriminate <name>.`` command.

    Args:
        script: Coq proof script.
        error_msg: Optional error message from Coq (used to select patches).

    Returns:
        Script with offending `discriminate` commands replaced by `inversion`.
    """
    if not script:
        return script

    patched = script
    error_lower = error_msg.lower()

    # Determine if we should apply the patch globally based on the error.
    apply_global = "not a discriminable equality" in error_lower

    # Find all `discriminate <name>.` commands.
    discr_pattern = re.compile(r"discriminate\s+(\w+)\.")
    matches = list(discr_pattern.finditer(patched))

    for m in matches:
        hyp_name = m.group(1)

        # Check whether this hypothesis is a boolean equality.
        boolean_hyp_pattern = re.compile(
            rf"{re.escape(hyp_name)}\s*:\s*\(?[^\)]*(?:=\?|Nat\.eqb)[^\)]*\)?\s*=\s*true"
        )
        is_bool_hyp = bool(boolean_hyp_pattern.search(patched))

        if is_bool_hyp or (apply_global and not is_bool_hyp):
            new_cmd = f"inversion {hyp_name}."
            start, end = m.span()
            patched = patched[:start] + new_cmd + patched[end:]
            logger.debug(
                "Patched `discriminate %s` to `inversion %s`.",
                hyp_name, hyp_name
            )

    return patched


def patch_orphan_bullets(script: str) -> str:
    """
    Remove orphan bullet lines.

    An orphan bullet line is a line that consists **solely** of a bullet
    character (`-`, `+`, `*`) and no other content.  Such lines commonly
    cause `[Focus] Wrong bullet` errors and do not contribute to the proof.
    This function replaces them with a harmless comment.

    Well‑formed bullets that are followed by tactics or comments are left
    untouched, so no unbalanced braces are introduced.

    Args:
        script: Coq proof script.

    Returns:
        Script with orphan bullet lines removed.
    """
    if not script:
        return script

    lines = script.splitlines()
    out_lines: List[str] = []
    changed = False

    for line in lines:
        stripped = line.strip()
        if stripped in ("-", "+", "*"):
            # Replace the orphan bullet with a harmless comment.
            out_lines.append("  (* orphan bullet removed by auto‑patcher *)")
            changed = True
        else:
            out_lines.append(line)

    if changed:
        logger.debug("Removed orphan bullet lines from script.")
    return "\n".join(out_lines)


# Alias for backward compatibility with older test expectations.
# The name `patch_bullets_to_braces` historically referred to removing
# orphan bullets only (not a full conversion), so we provide the same
# behaviour as `patch_orphan_bullets`.
patch_bullets_to_braces = patch_orphan_bullets


def _has_orphan_bullets(script: str) -> bool:
    """Return True if the script contains any line that is only a bullet."""
    for line in script.splitlines():
        if line.strip() in ("-", "+", "*"):
            return True
    return False


def _is_focus_error(error_msg: str) -> bool:
    """Return True if the error message indicates a focus or bullet problem."""
    if not error_msg:
        return False
    lower = error_msg.lower()
    return (
        "focused, but cannot be unfocused" in lower
        or "wrong bullet" in lower
        or "focus" in lower
    )


def _has_bullets(script: str) -> bool:
    """Return True if the script contains at least one bullet line."""
    bullet_pattern = re.compile(r"^\s*[-+*]\s", re.MULTILINE)
    return bool(bullet_pattern.search(script))


def _convert_bullets_to_braces_safe(script: str) -> str:
    """
    Attempt to convert bullet‑based subgoal separation to explicit braces.

    The conversion is conservative:
      - It only processes lines that start with a bullet (`-`, `+`, `*`)
        followed by whitespace or end‑of‑line.
      - For a bullet line that contains tactics after the bullet
        (e.g., ``+ simpl.``), it becomes ``{ simpl. }``.
      - For a standalone bullet line, it becomes ``{`` and a matching ``}``
        is inserted before the next bullet at the same or lower indentation,
        or before ``Qed.``/``Admitted.`` if it terminates the subgoal.

    The function is guaranteed not to introduce unbalanced braces because
    any conversion that would cause an imbalance is discarded by the caller
    (see `patch_focus_errors`).

    Args:
        script: Coq proof script.

    Returns:
        Script with bullets converted to braces, or the original script
        if the conversion cannot be performed safely.
    """
    if not script:
        return script

    lines = script.splitlines()
    output: List[str] = []
    stack: List[tuple] = []

    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        stripped = line.lstrip()
        indent = len(line) - len(stripped)

        bullet_match = re.match(r"^([-+*])(?:\s+(.*))?$", stripped)
        if bullet_match:
            bullet_char = bullet_match.group(1)
            content = bullet_match.group(2)

            # Close any open blocks whose indent is >= current indent.
            while stack and stack[-1][0] >= indent:
                out_indent = stack[-1][0]
                output.append(" " * out_indent + "}")
                stack.pop()

            if content:
                content = content.strip()
                if content.endswith("}"):
                    new_line = " " * indent + "{ " + content.rstrip("}").rstrip() + " }"
                else:
                    new_line = " " * indent + "{ " + content + " }"
                output.append(new_line)
            else:
                output.append(" " * indent + "{")
                stack.append((indent, bullet_char))
            i += 1
            continue

        if stripped in ("Qed.", "Admitted.", "Defined.", "Abort."):
            while stack:
                out_indent = stack[-1][0]
                output.append(" " * out_indent + "}")
                stack.pop()

        output.append(line)
        i += 1

    while stack:
        out_indent = stack[-1][0]
        output.append(" " * out_indent + "}")
        stack.pop()

    return "\n".join(output)


def patch_focus_errors(script: str, error_msg: str = "") -> str:
    """
    Attempt to repair focus/bullet errors by converting bullet‑based
    subgoal separation to explicit braces.

    This patch is triggered only when `error_msg` indicates a focus error
    or `[Focus] Wrong bullet`.  After conversion, the result is validated;
    if structural issues are introduced, the original script is returned.

    **Note:** This function is **not called automatically** in `auto_patch`
    because the conversion can be unsafe and cause unbalanced braces.
    It is kept for optional manual use or future improvements.

    Args:
        script: Coq proof script.
        error_msg: Error message from Coq (optional).

    Returns:
        Script with bullets converted to braces, or original if unsafe.
    """
    if not script or not _is_focus_error(error_msg):
        return script

    if not _has_bullets(script):
        return script

    converted = _convert_bullets_to_braces_safe(script)

    issues = validate_structure(converted)
    critical_issues = [
        issue for issue in issues
        if ("Unbalanced" in issue or
            "Unclosed proof" in issue or
            "orphan bullet" in issue)
    ]
    if critical_issues:
        logger.warning(
            "Bullet-to-brace conversion introduced structural issues (%s). Reverting.",
            "; ".join(critical_issues[:3])
        )
        return script

    logger.debug("Bullet-to-brace conversion applied successfully.")
    return converted


def auto_patch(script: str, error_msg: str = "") -> str:
    """
    Apply all safe, deterministic patches to a Coq proof script.

    This version **does not** apply the bullet‑to‑brace conversion
    (`patch_focus_errors`) because it can introduce unbalanced braces.
    Only the following patches are applied:

      1. Replace deprecated notations.
      2. Patch `discriminate` on boolean equalities.
      3. Remove orphan bullet lines (only when a focus error is detected
         or orphan bullets exist).

    Args:
        script: The failing proof script (should include ``Proof.`` … ``Qed.``).
        error_msg: Optional error message from Coq, used to select patches.

    Returns:
        A patched script.
    """
    if not script:
        return script

    patched = script

    # 1. Always replace deprecated notations.
    patched = patch_deprecated_notations(patched)

    # 2. Patch `discriminate` on boolean equalities.
    patched = patch_discriminate_on_bool(patched, error_msg)

    # 3. Remove orphan bullet lines when:
    #    - the error message indicates a focus/bullet problem, or
    #    - orphan bullets are present in the script.
    error_lower = error_msg.lower()
    focus_error = _is_focus_error(error_msg) or "wrong bullet" in error_lower
    if focus_error or _has_orphan_bullets(patched):
        patched = patch_orphan_bullets(patched)

    issues = validate_structure(patched)
    critical_issues = [
        issue for issue in issues
        if ("Unbalanced" in issue or
            "Unclosed proof" in issue or
            "orphan bullet" in issue)
    ]
    if critical_issues:
        logger.warning(
            "Auto‑patcher produced a script with structural issues: %s",
            "; ".join(critical_issues),
        )
    else:
        logger.debug("Auto‑patcher output passed structural validation.")

    if patched != script:
        logger.info("Auto‑patcher modified the proof script.")
    return patched
