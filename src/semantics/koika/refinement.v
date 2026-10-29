(* ISIR.koika.refinement
 *
 * The refinement relation between the ISIR source semantics (ISIR.isir)
 * and a Kōika `bits_t N` design, stated in three dimensions and composed into
 * a single `refines` predicate.
 *
 * Dimensions (per the revised plan):
 *   1. definedness_preservation — an ISIR-defined step implies a defined
 *      Kōika step (no new undefined behavior: uninitialized registers, width
 *      truncation, rule ordering that leaves a state element undriven).
 *   2. value_refinement — every observable result the Kōika produces is a
 *      result the ISIR source may produce.  "Poison cleanliness" (no silent
 *      truncation / signedness mismatch / uninitialized read) is folded into
 *      this dimension: the Kōika next state must correspond to the ISIR next
 *      state via R_state, so it cannot fall outside the ISIR-defined set.
 *   3. refines — the conjunction of the two.
 *)

Require Import ISIR.isir.
Require Import ISIR.koika.koika_correspondence.

Section Refinement.
  Context (reg_t : Type).
  Context (rw : nat -> nat) (reg_id : reg_t -> nat).

  (** The Kōika state: a bit-vector register store (regular registers; memory
      writes are unsupported, so memories are outside this correspondence). *)
  Definition koika_state := koika_store reg_t rw reg_id.

  (** The abstract Kōika single-cycle step. *)
  Context (step_koika : koika_state -> option koika_state).

  Context (sched : schedule) (rules : list rule) (mem_w : widths).

  (* ---------------------------------------------------------------- *)
  (* 1. Definedness preservation                                       *)
  (* ---------------------------------------------------------------- *)

  (** If the ISIR step is defined at a corresponding state, the Kōika step is
      also defined (the lowering introduces no new undefined behavior). *)
  Definition definedness_preservation : Prop :=
    forall (s : state) (i : inputs) (mem : memories) (ks : koika_state),
      R_state reg_t rw reg_id s ks ->
      step sched rules rw mem_w s i mem <> None ->
      step_koika ks <> None.

  (* ---------------------------------------------------------------- *)
  (* 2. Value refinement (poison cleanliness folded in)                *)
  (* ---------------------------------------------------------------- *)

  (** Every Kōika next state corresponds to the ISIR next state via [R_state].
      Since [R_state] pins the Kōika value to the ISIR value wrapped to the
      register width, the Kōika cannot silently truncate, sign-extend, or read
      an uninitialized register outside the ISIR-defined set. *)
  Definition value_refinement : Prop :=
    forall (s s' : state) (i : inputs) (mem mem' : memories) (ks ks' : koika_state),
      R_state reg_t rw reg_id s ks ->
      step sched rules rw mem_w s i mem = Some (s', mem') ->
      step_koika ks = Some ks' ->
      R_state reg_t rw reg_id s' ks'.

  (* ---------------------------------------------------------------- *)
  (* 3. Composition                                                    *)
  (* ---------------------------------------------------------------- *)

  Definition refines : Prop :=
    definedness_preservation /\ value_refinement.

  (* `refines` projects to each dimension. *)
  Lemma refines_definedness : refines -> definedness_preservation.
  Proof. unfold refines. tauto. Qed.

  Lemma refines_value : refines -> value_refinement.
  Proof. unfold refines. tauto. Qed.
End Refinement.

(* ------------------------------------------------------------------ *)
(* A worked example: an identity Kōika step satisfies value refinement *)
(* when the ISIR step also returns the same store (up to R_state).     *)
(* ------------------------------------------------------------------ *)

Section IdentityExample.
  Context (reg_t : Type).
  Context (rw : nat -> nat) (reg_id : reg_t -> nat).
  Context (sched : schedule) (rules : list rule) (mem_w : widths).

  (** The Kōika step is the identity on the register store. *)
  Definition identity_step (ks : koika_store reg_t rw reg_id)
    : option (koika_store reg_t rw reg_id) := Some ks.

  (** An ISIR step that leaves the store unchanged (a rule that does nothing)
      refines the identity Kōika step, since R_state is reflexive on equal
      stores.  This is the degenerate "no-op" case, stated to pin the shape of
      [refines]. *)
  Lemma identity_value_refinement :
    (forall s i mem, step sched rules rw mem_w s i mem = Some (s, mem)) ->
    value_refinement reg_t rw reg_id identity_step sched rules mem_w.
  Proof.
    intros Hstep s s' i mem mem' ks ks' HR H1 H2.
    unfold identity_step in H2. injection H2 as ->.
    rewrite Hstep in H1. injection H1 as -> ->.
    exact HR.
  Qed.
End IdentityExample.
