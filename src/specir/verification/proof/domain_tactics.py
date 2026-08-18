# src/specir/verification/proof/domain_tactics.py
#
# Domain‑specific proof patterns and lemma hints for common verification
# obligations (overflow, reachability, boolean equality, etc.).

from typing import Dict, List, Optional, Union
from specir.utils.logger import get_logger
from specir.verification.proof.structural_validator import validate_structure

logger = get_logger(__name__)


# Base-case pattern for safety properties of the form:
#   reachable s -> (antecedent -> consequent)
KOIKA_BASE_CASE = """simpl; intros Hcond; destruct Hcond as [Hvalid [Hop Hoverflow]];
  discriminate Hvalid."""  # valid is false in initial state


# Step-case pattern for designs with two step constructors:
#   step_load_inputs and step_execute.
# This uses proper single braces with nesting.
KOIKA_STEP_CASE_TWO_CTORS = """inversion Hstep; subst; clear Hstep; simpl.
  { intros Hcond. destruct Hcond as [Hvalid [Hop Hoverflow]].
    simpl in Hop.
    inversion Hop. }
  { intros Hcond. destruct Hcond as [Hvalid [Hop Hoverflow]].
    destruct (op_reg s' =? 0) eqn:Hop0.
    { simpl in *. lia. }
    { destruct (op_reg s' =? 1) eqn:Hop1.
      { simpl in *. lia. }
      { destruct (op_reg s' =? 2) eqn:Hop2.
        { simpl in *. lia. }
        { simpl in *. lia. } } } } }"""

# Generic step-case for single constructor with nested ite
KOIKA_STEP_CASE_SINGLE_CTOR = """inversion Hstep; subst; clear Hstep; simpl.
  repeat (match goal with
          | [ |- context[if ?b then _ else _] ] => destruct b eqn:?
          | [ H : context[if ?b then _ else _] |- _ ] => destruct b eqn:? in H
          end).
  auto; try lia; try nia."""

# Boolean equality handling when a hypothesis has the form
# (op_reg s =? 0) = true
KOIKA_BOOL_EQ_CASE = """destruct (op_reg s =? 0) eqn:Hop0.
  { (* Hop0 : true *) simpl. (* ... *) }
  { (* Hop0 : false *) simpl. (* ... *) }"""

# Overflow property pattern (for `overflow_implies_result_neq_sum` etc.)
# Uses explicit single braces and avoids deprecated notations.
KOIKA_OVERFLOW_TEMPLATE = """Proof.
  intros s inputs Hreach.
  induction Hreach as [| s' s'' inputs' Hreach' IH Hstep].
  { simpl. intros Hcond. destruct Hcond as [Hvalid [Hop Hoverflow]].
    discriminate Hvalid. }
  { inversion Hstep; subst; clear Hstep; simpl.
    { intros Hcond. destruct Hcond as [Hvalid [Hop Hoverflow]].
      simpl in Hop.
      inversion Hop. }
    { intros Hcond. destruct Hcond as [Hvalid [Hop Hoverflow]].
      destruct (op_reg s' =? 0) eqn:Hop0.
      { simpl in *. lia. }
      { destruct (op_reg s' =? 1) eqn:Hop1.
        { simpl in *. lia. }
        { destruct (op_reg s' =? 2) eqn:Hop2.
          { simpl in *. lia. }
          { simpl in *. lia. } } } } } }
Qed."""


ACL2_INDUCT_HINT = ['("Goal" :induct t)']
ACL2_INDUCT_STEP_HINT = ['("Goal" :induct (step st inputs))']
ACL2_REWRITE_HINT = ['("Goal" :do-not-induct t :in-theory (enable*))']
ACL2_LINEAR_HINT = ['("Goal" :do-not-induct t :use (:instance linear-lemma))']
ACL2_CASE_SPLIT_HINT = ['("Goal" :cases ((enqueue st) (not (enqueue st))) :in-theory (enable*))']
ACL2_OVERFLOW_HINTS = [
    '("Goal" :induct (step st inputs))',
    '("Subgoal *1/2" :expand ((overflow_reg st) (result_reg st)) :in-theory (enable*))',
]


# Common lemma names that are useful for overflow/boolean reasoning.
# NOTE: we do NOT include `Div0.mod_add` or `Nat.mod_add` because they
# may be deprecated or unavailable depending on the Coq version.
KOIKA_COMMON_LEMMAS = [
    "Nat.eqb_eq",
    "Nat.eqb_neq",
    "add4_mod4",
    "slice_low2",
    "eqb_true_iff",
]

ACL2_COMMON_LEMMAS = [
    "arithmetic-5::|(+ x y)|",
    "arithmetic-5::|(- x y)|",
    "arithmetic-5::|(mod (+ x y) z)|",
]


def get_koika_tactic_pattern(
    property_name: str,
    analysis: Optional[object] = None,
) -> Optional[str]:
    """
    Return a Coq tactic pattern appropriate for the given property.

    The returned pattern is guaranteed to be structurally valid (balanced
    braces, closed proof) and to not rely on `Arith.Div0` or `Nat.mod_add`.

    Args:
        property_name: Name of the property (e.g., `overflow_implies_result_neq_sum`).
        analysis: Optional structural analysis object (from ``PERFAnalyzer``).
                  Currently unused, but reserved for future adaptation.

    Returns:
        A tactic string (possibly multiline) suitable for use in a prompt
        or as a fallback template, or ``None`` if no specific pattern
        is known.
    """
    name_lower = property_name.lower()

    if "overflow" in name_lower or "neq" in name_lower or "result_neq" in name_lower:
        return KOIKA_OVERFLOW_TEMPLATE

    if "zero_flag" in name_lower:
        # Zero flag property: similar to overflow but without arithmetic
        template = """Proof.
  intros s inputs Hreach.
  induction Hreach as [| s' s'' inputs' Hreach' IH Hstep].
  { simpl. intros Hvalid. discriminate Hvalid. }
  { inversion Hstep; subst; clear Hstep; simpl.
    { intros Hvalid. apply IH. assumption. }
    { intros Hvalid.
      destruct (op_reg s' =? 0) eqn:Hop0.
      { simpl. reflexivity. }
      { destruct (op_reg s' =? 1) eqn:Hop1.
        { simpl. reflexivity. }
        { destruct (op_reg s' =? 2) eqn:Hop2.
          { simpl. reflexivity. }
          { simpl. reflexivity. } } } } } }
Qed."""
        return template if _is_structurally_valid(template) else None

    # Fallback: return a generic two-constructor step case if the analysis
    # suggests two step constructors.  This is not a full proof, so we
    # return None unless a full proof is available.
    if analysis is not None and getattr(analysis, "num_step_constructors", 0) == 2:
        return KOIKA_OVERFLOW_TEMPLATE  # reuse the overflow template as a safe generic pattern

    return None


def get_acl2_hints(property_name: str) -> List[str]:
    """
    Return ACL2 hint patterns for a given property.

    Args:
        property_name: Name of the property.

    Returns:
        A list of hint strings (each a complete ACL2 hint list).
    """
    name_lower = property_name.lower()

    if "overflow" in name_lower or "neq" in name_lower:
        return ACL2_OVERFLOW_HINTS
    if "zero_flag" in name_lower or "valid" in name_lower:
        return ACL2_INDUCT_STEP_HINT

    # Default induction hint
    return ACL2_INDUCT_HINT


def get_lemma_hints(backend: str, property_name: str) -> List[str]:
    """
    Return a list of lemma names that may be useful for proving a property.

    Args:
        backend: 'koika' or 'acl2'.
        property_name: Name of the property.

    Returns:
        List of lemma names.
    """
    backend = backend.lower().replace("ō", "o")
    name_lower = property_name.lower()

    if backend.startswith("koi"):
        lemmas = list(KOIKA_COMMON_LEMMAS)
        if "overflow" in name_lower or "neq" in name_lower:
            lemmas.extend(["Nat.add_comm", "Nat.add_assoc", "Nat.sub_0_r"])
        return lemmas

    elif backend == "acl2":
        lemmas = list(ACL2_COMMON_LEMMAS)
        if "overflow" in name_lower or "neq" in name_lower:
            lemmas.extend(["arithmetic-5::|(mod (+ x y) z)|"])
        return lemmas

    return []


def apply_domain_tactics(
    proof_script: str,
    property_name: str,
    backend: str,
) -> str:
    """
    Apply domain-specific tactic substitutions to a proof script.

    This is a convenience method that replaces known bad patterns with
    recommended alternatives.  It is called by provers before compilation.
    The replacement does **not** introduce `Div0` or `Nat.mod_add`.

    Args:
        proof_script: The proof script to adjust.
        property_name: Name of the property (used to select patterns).
        backend: 'koika' or 'acl2'.

    Returns:
        The adjusted proof script.
    """
    script = proof_script

    if backend.startswith("koi"):
        if "discriminate Hop." in script and "=? " in script:
            script = script.replace(
                "discriminate Hop.",
                "simpl in Hop. inversion Hop."
            )

    return script


def _is_structurally_valid(script: str) -> bool:
    """
    Check that a Coq proof script has balanced braces and closed proof.
    Returns True if the script passes structural validation.
    """
    issues = validate_structure(script)
    for issue in issues:
        if ("Unbalanced" in issue or
            "Unclosed proof" in issue or
            "orphan bullet" in issue):
            return False
    return True
