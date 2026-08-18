# src/specir/verification/proof/tactic_modernizer.py
#
# Tactic modernisation for Coq proof scripts.
# Replaces deprecated tactics with their modern equivalents where
# such replacements do **not** introduce hard dependencies on optional
# modules (e.g., Arith.Div0).
#
# The module is used by the KoikaProver and other components to ensure
# that generated proofs are compatible with modern Coq (>= 8.17)
# without breaking on systems that lack certain logical paths.
#
# Main replacements:
#   - `omega` -> `lia`
#   - `romega` -> `lia`
#   - `Require Import Omega.` -> `Require Import Lia.`
#   - conservative correction of `discriminate` on boolean equalities
#
# Optional replacement (disabled by default):
#   - `Nat.mod_add` / `Nat.mod_mul` / `Nat.add_mod` / `Nat.mod_same` etc.
#     -> `Div0.mod_add` / `Div0.mod_mul` / `Div0.add_mod` / `Div0.mod_same`
#     This is **only** applied when `replace_nat_mod_add=True` is
#     passed to `modernize_tactics`.  By default it remains disabled to
#     avoid introducing a hard dependency on `Arith.Div0`, which is not
#     available on all Coq installations.

import re
from typing import Dict, List, Optional
from specir.utils.logger import get_logger

logger = get_logger(__name__)

_DEPRECATED_TACTICS: Dict[str, str] = {
    # `omega` is deprecated since 8.12, use `lia`
    "omega": "lia",
    # `romega` is deprecated, use `lia`
    "romega": "lia",
}

_EXTRA_REPLACEMENTS: Dict[str, str] = {
    "Require Import Omega.": "Require Import Lia.",
    "Require Export Omega.": "Require Export Lia.",
}

_NAT_MOD_REPLACEMENTS: Dict[str, str] = {
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


def modernize_tactics(
    script: str,
    context_hypotheses: Optional[List[str]] = None,
    replace_nat_mod_add: bool = False,
) -> str:
    """
    Apply safe tactic and notation modernisation to a Coq proof script.

    Args:
        script: The proof script (or any Coq text) as a string.
        context_hypotheses: Optional list of hypothesis names to help
                            disambiguate `discriminate` corrections.
        replace_nat_mod_add: If True, also replace deprecated `Nat.mod_*`
                             and `Nat.div_*` lemmas with their
                             `Div0.*` counterparts.  **Default is False**
                             because `Arith.Div0` may not be available on
                             all Coq installations.  Use this option only
                             when the environment includes the required
                             module.

    Returns:
        The script with deprecated tactics/imports replaced and
        boolean‑equality `discriminate` commands corrected.
    """
    if not script:
        return script

    modernized = script

    # 1. Replace deprecated tactics (omega -> lia, etc.)
    for old, new in _DEPRECATED_TACTICS.items():
        # Tactics appear as standalone commands; use negative lookbehind/lookahead
        # to ensure we don't replace part of a larger identifier.
        modernized = re.sub(
            rf"(?<![\w'])({re.escape(old)})(?![\w'])",
            new,
            modernized
        )

    # 2. Replace import lines
    for old, new in _EXTRA_REPLACEMENTS.items():
        modernized = modernized.replace(old, new)

    # 3. Optional: replace deprecated Nat.mod_* / Nat.div_* with Div0.*
    if replace_nat_mod_add:
        for old, new in _NAT_MOD_REPLACEMENTS.items():
            # Use word boundaries to avoid partial replacements.
            modernized = re.sub(
                rf"\b{re.escape(old)}\b",
                new,
                modernized
            )
        if any(old in script for old in _NAT_MOD_REPLACEMENTS):
            logger.debug(
                "Optional Nat.mod*/Nat.div* replacement applied "
                "(replace_nat_mod_add=True)."
            )

    # 4. Conservative correction of `discriminate` on boolean equalities.
    #    If the script contains a hypothesis of the form `name : (...) = true`
    #    and a command `discriminate name.`, change to `inversion name.`.
    #    This addresses the common "Not a discriminable equality" error.
    modernized = _modernize_boolean_discriminate(modernized)

    if modernized != script:
        logger.debug("Tactic modernisation applied to script.")

    return modernized


def _modernize_boolean_discriminate(script: str) -> str:
    """
    Detect and correct `discriminate` on boolean equalities.

    This is a heuristic: if the script contains a command
    `discriminate <name>.` and also contains a hypothesis line that
    looks like `<name> : ( ... =? ... ) = true` or
    `<name> : (Nat.eqb ... ...) = true`, then we replace that
    `discriminate` with `inversion`.  The patch is applied only to the
    specific occurrence, not globally.

    Args:
        script: Coq proof script.

    Returns:
        Script with offending `discriminate` commands replaced.
    """
    if not script:
        return script

    # Find all discriminate commands.
    discr_pattern = re.compile(r"discriminate\s+(\w+)\.")
    # We need to perform replacements, so iterate over matches in reverse
    # to avoid index shifts.
    matches = list(discr_pattern.finditer(script))
    for m in reversed(matches):
        hyp_name = m.group(1)

        # Check if this hypothesis is declared as a boolean equality.
        # Pattern: `hyp_name : ( ... =? ... ) = true` or
        #          `hyp_name : (Nat.eqb ... ...) = true`
        boolean_hyp_pattern = re.compile(
            rf"{re.escape(hyp_name)}\s*:\s*\(?[^\)]*(?:=\?|Nat\.eqb)[^\)]*\)?\s*=\s*true"
        )
        if boolean_hyp_pattern.search(script):
            start, end = m.span()
            script = script[:start] + f"inversion {hyp_name}." + script[end:]
            logger.debug(
                "Modernised `discriminate %s` to `inversion %s` (boolean equality).",
                hyp_name, hyp_name
            )

    return script
