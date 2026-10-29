(* ISIR.koika.refinement_proofs
 *
 * Machine-checked refinement lemmas for the core fragment.
 *
 * The core fragment is the operator subset the Kōika RTL lowering supports:
 * single-clock, finite-width, no partial_spec, no memory ops, no slice/mul/
 * div/mod.  This module proves the *value correspondence* — the Kōika
 * `bits_t N` arithmetic equals the ISIR `nat` arithmetic wrapped to N bits —
 * for the core arithmetic operators, and composes it into a small end-to-end
 * theorem for a counter-like rule.
 *
 * The remaining operators (sub underflow, and/or/xor/eq/lt) are noted at the
 * bottom as the next increment; the out-of-fragment operators fall back to the
 * bounded SMT evidence.
 *)

Require Import ISIR.isir.
Require Import ISIR.koika.koika_correspondence.
Require Import Koika.Types.
Require Import Koika.Vect.
Require Import Coq.NArith.NArith.
Require Import Coq.Arith.PeanoNat.
Require Import Coq.micromega.Lia.

Open Scope nat_scope.

(* ------------------------------------------------------------------ *)
(* 1. The core fragment                                                *)
(* ------------------------------------------------------------------ *)

(** [core_fragment e] holds iff [e] uses only the operators the Kōika RTL
    lowering can emit: no partial_spec, no memory ops, no slice/mul/div/mod. *)
Fixpoint core_fragment (e : expr) : bool :=
  match e with
  | ELit _ | EVar _ | ERead _ => true
  | EPartial _ => false            (* partial_spec is outside the core fragment *)
  | EMemRead _ _ => false
  | EUnop _ x => core_fragment x
  | EBinop _ a b => core_fragment a && core_fragment b
  | EIte c t f => core_fragment c && core_fragment t && core_fragment f
  | ESlice _ _ _ => false          (* slice is outside the core fragment *)
  end.

(* ------------------------------------------------------------------ *)
(* 2. Value correspondence: bits_t N arithmetic == wrap N (nat)         *)
(* ------------------------------------------------------------------ *)

(** The Kōika `bits_t N` addition equals the ISIR `wrap N (x + y)`. *)
Lemma add_correspondence :
  forall sz x y,
    bits_to_nat (Bits.plus (nat_to_bits sz x) (nat_to_bits sz y)) = wrap sz (x + y).
Proof.
  intros sz x y.
  destruct sz as [|sz].
  - (* width 0: both sides are 0 *)
    unfold bits_to_nat, nat_to_bits, wrap, Bits.to_nat, Bits.of_nat, Bits.plus.
    reflexivity.
  - (* width S sz *)
    unfold bits_to_nat, nat_to_bits, wrap, Bits.to_nat, Bits.of_nat.
    rewrite Bits.to_N_plus.
    rewrite !Bits.to_N_of_N_mod.
    rewrite N2Nat.inj_mod.
    rewrite N2Nat.inj_add.
    rewrite !N2Nat.inj_mod.
    rewrite !Nat2N.id.
    rewrite N2Nat.inj_pow.
    rewrite Nat2N.id.
    change (N.to_nat 2) with 2.
    symmetry. apply Nat.Div0.add_mod.
Qed.

(** A bounded value is unchanged by wrapping (the idempotence of wrap). *)
Lemma wrap_bounded :
  forall w v, v < 2 ^ w -> wrap w v = v.
Proof.
  intros w v Hv. unfold wrap. destruct w.
  - cbn in *. lia.
  - apply Nat.mod_small. exact Hv.
Qed.

(** [nat_to_bits] / [bits_to_nat] round-trip a bounded value. *)
Lemma nat_bits_bounded :
  forall sz n, n < 2 ^ sz -> bits_to_nat (nat_to_bits sz n) = n.
Proof.
  intros sz n Hn.
  unfold bits_to_nat, nat_to_bits.
  rewrite <- pow2_correct in Hn.
  apply Bits.to_nat_of_nat. exact Hn.
Qed.

(** Two's-complement subtraction: the Kōika `Bits.minus` equals the ISIR
    `wrap sz (2^sz + x - y)` (for bounded operands). *)
Lemma sub_correspondence :
  forall sz x y,
    x < 2 ^ sz -> y < 2 ^ sz ->
    bits_to_nat (Bits.minus (nat_to_bits sz x) (nat_to_bits sz y)) = wrap sz (2 ^ sz + x - y).
Proof.
  intros sz x y Hx Hy.
  destruct sz as [|sz].
  - cbn. reflexivity.
  - unfold bits_to_nat, nat_to_bits, wrap, Bits.to_nat, Bits.of_nat.
    rewrite Bits.to_N_minus.
    rewrite !Bits.to_N_of_N_lt
      by (apply Bits.nat_lt_pow2_N; rewrite <- pow2_correct in *; assumption).
    rewrite N2Nat.inj_mod.
    rewrite N2Nat.inj_sub.
    rewrite N2Nat.inj_add.
    rewrite !Nat2N.id.
    rewrite N2Nat.inj_pow.
    rewrite Nat2N.id.
    change (N.to_nat 2) with 2.
    reflexivity.
Qed.

(** Value equality: `bits_to_nat` equal iff the wrapped values are equal. *)
Lemma eq_correspondence :
  forall sz x y,
    bits_to_nat (nat_to_bits sz x) = bits_to_nat (nat_to_bits sz y)
    <-> wrap sz x = wrap sz y.
Proof.
  intros sz x y.
  rewrite !nat_bits_roundtrip.
  unfold wrap. destruct sz.
  - split; auto.
  - reflexivity.
Qed.

(** Unsigned comparison: the Kōika `unsigned_lt` matches the wrapped nat `<`. *)
Lemma is_lt_compare_lt :
  forall (a b : N), Bits.is_lt (N.compare a b) = (a <? b)%N.
Proof.
  intros a b.
  unfold Bits.is_lt, Bits.comparison_beq.
  destruct (N.compare a b) eqn:E.
  - simpl. symmetry. rewrite N.ltb_ge. rewrite N.compare_eq_iff in E. subst. lia.
  - simpl. symmetry. rewrite N.ltb_lt. rewrite <- N.compare_lt_iff. exact E.
  - simpl. symmetry. rewrite N.ltb_ge. rewrite N.compare_gt_iff in E. lia.
Qed.

Lemma lt_correspondence :
  forall sz x y,
    Bits.unsigned_lt (nat_to_bits sz x) (nat_to_bits sz y) = (wrap sz x <? wrap sz y).
Proof.
  intros sz x y.
  unfold Bits.unsigned_lt, Bits.lift_comparison, nat_to_bits, Bits.of_nat.
  rewrite !Bits.to_N_of_N_mod.
  rewrite is_lt_compare_lt.
  destruct sz.
  - rewrite !N.mod_1_r. reflexivity.
  - unfold wrap.
    apply Bool.eq_iff_eq_true.
    rewrite N.ltb_lt, Nat.ltb_lt.
    change (2%N) with (N.of_nat 2).
    rewrite N_pow_Nat_pow.
    rewrite <- !Nat2N.inj_mod.
    unfold N.lt.
    rewrite <- !Nat2N.inj_compare.
    rewrite Nat.compare_lt_iff.
    reflexivity.
Qed.

(* ------------------------------------------------------------------ *)
(* Bitwise correspondence: and / or / xor                              *)
(* ------------------------------------------------------------------ *)

(** [N.div2] of a double-plus-low-bit recovers the high part. *)
Lemma N_div2_double_b2n : forall a (h : bool), N.div2 (N.b2n h + N.double a) = a.
Proof.
  intros a h. destruct h.
  - change (N.b2n true) with 1%N. rewrite N.add_comm. rewrite N.double_spec. rewrite <- N.succ_double_spec. apply N.div2_succ_double.
  - change (N.b2n false) with 0%N. rewrite N.add_0_l. apply N.div2_double.
Qed.

(** Bit 0 of a double-plus-low-bit is the low bit. *)
Lemma N_testbit_double_0 : forall a (h : bool), N.testbit (N.b2n h + N.double a) 0 = h.
Proof.
  intros a h. rewrite N.bit0_odd.
  destruct h.
  - change (N.b2n true) with 1%N. rewrite N.add_comm. rewrite N.double_spec. rewrite <- N.succ_double_spec. apply Ndouble_plus_one_bit0.
  - change (N.b2n false) with 0%N. rewrite N.add_0_l. apply Ndouble_bit0.
Qed.

(** Bit (S m) of a double-plus-low-bit is bit m of the high part. *)
Lemma N_testbit_double_S : forall a (h : bool) m,
    N.testbit (N.b2n h + N.double a) (N.succ m) = N.testbit a m.
Proof.
  intros a h m.
  rewrite <- N.add_1_r.
  rewrite <- N.shiftr_spec'.
  rewrite <- N.div2_spec.
  rewrite N_div2_double_b2n.
  reflexivity.
Qed.

Lemma N_land_b2n : forall h1 h2, N.land (N.b2n h1) (N.b2n h2) = N.b2n (andb h1 h2).
Proof. intros h1 h2; destruct h1, h2; cbn; reflexivity. Qed.
Lemma N_lor_b2n : forall h1 h2, N.lor (N.b2n h1) (N.b2n h2) = N.b2n (orb h1 h2).
Proof. intros h1 h2; destruct h1, h2; cbn; reflexivity. Qed.
Lemma N_lxor_b2n : forall h1 h2, N.lxor (N.b2n h1) (N.b2n h2) = N.b2n (xorb h1 h2).
Proof. intros h1 h2; destruct h1, h2; cbn; reflexivity. Qed.

(** The double decomposition of a bitwise operation. *)
Lemma N_land_double : forall a b h1 h2,
    N.land (N.b2n h1 + N.double a) (N.b2n h2 + N.double b) = (N.b2n (andb h1 h2) + N.double (N.land a b))%N.
Proof.
  intros a b h1 h2.
  apply N.bits_inj. intro n.
  rewrite N.land_spec.
  induction n using N.peano_ind.
  - rewrite !N_testbit_double_0. reflexivity.
  - rewrite !N_testbit_double_S. rewrite N.land_spec. reflexivity.
Qed.

Lemma N_lor_double : forall a b h1 h2,
    N.lor (N.b2n h1 + N.double a) (N.b2n h2 + N.double b) = (N.b2n (orb h1 h2) + N.double (N.lor a b))%N.
Proof.
  intros a b h1 h2.
  apply N.bits_inj. intro n.
  rewrite N.lor_spec.
  induction n using N.peano_ind.
  - rewrite !N_testbit_double_0. reflexivity.
  - rewrite !N_testbit_double_S. rewrite N.lor_spec. reflexivity.
Qed.

Lemma N_lxor_double : forall a b h1 h2,
    N.lxor (N.b2n h1 + N.double a) (N.b2n h2 + N.double b) = (N.b2n (xorb h1 h2) + N.double (N.lxor a b))%N.
Proof.
  intros a b h1 h2.
  apply N.bits_inj. intro n.
  rewrite N.lxor_spec.
  induction n using N.peano_ind.
  - rewrite !N_testbit_double_0. reflexivity.
  - rewrite !N_testbit_double_S. rewrite N.lxor_spec. reflexivity.
Qed.

(** The Kōika `bits_t N` bitwise ops equal `N.land`/`N.lor`/`N.lxor` on `to_N`. *)
Lemma to_N_and : forall sz (b1 b2 : Bits.bits sz),
    Bits.to_N (Bits.and b1 b2) = N.land (Bits.to_N b1) (Bits.to_N b2).
Proof.
  induction sz as [|sz IH]; intros b1 b2.
  - cbn. reflexivity.
  - destruct b1 as [h1 t1], b2 as [h2 t2].
    simpl.
    fold (Bits.and t1 t2).
    rewrite IH.
    change (if h1 then 1%N else 0%N) with (N.b2n h1).
    change (if h2 then 1%N else 0%N) with (N.b2n h2).
    change (if (h1 && h2)%bool then 1%N else 0%N) with (N.b2n (andb h1 h2)).
    fold (N.double (Bits.to_N t1)) (N.double (Bits.to_N t2)) (N.double (N.land (Bits.to_N t1) (Bits.to_N t2))).
    rewrite N_land_double. reflexivity.
Qed.

Lemma to_N_or : forall sz (b1 b2 : Bits.bits sz),
    Bits.to_N (Bits.or b1 b2) = N.lor (Bits.to_N b1) (Bits.to_N b2).
Proof.
  induction sz as [|sz IH]; intros b1 b2.
  - cbn. reflexivity.
  - destruct b1 as [h1 t1], b2 as [h2 t2].
    simpl.
    fold (Bits.or t1 t2).
    rewrite IH.
    change (if h1 then 1%N else 0%N) with (N.b2n h1).
    change (if h2 then 1%N else 0%N) with (N.b2n h2).
    change (if (h1 || h2)%bool then 1%N else 0%N) with (N.b2n (orb h1 h2)).
    fold (N.double (Bits.to_N t1)) (N.double (Bits.to_N t2)) (N.double (N.lor (Bits.to_N t1) (Bits.to_N t2))).
    rewrite N_lor_double. reflexivity.
Qed.

Lemma to_N_xor : forall sz (b1 b2 : Bits.bits sz),
    Bits.to_N (Bits.xor b1 b2) = N.lxor (Bits.to_N b1) (Bits.to_N b2).
Proof.
  induction sz as [|sz IH]; intros b1 b2.
  - cbn. reflexivity.
  - destruct b1 as [h1 t1], b2 as [h2 t2].
    simpl.
    fold (Bits.xor t1 t2).
    rewrite IH.
    change (if h1 then 1%N else 0%N) with (N.b2n h1).
    change (if h2 then 1%N else 0%N) with (N.b2n h2).
    change (if xorb h1 h2 then 1%N else 0%N) with (N.b2n (xorb h1 h2)).
    fold (N.double (Bits.to_N t1)) (N.double (Bits.to_N t2)) (N.double (N.lxor (Bits.to_N t1) (Bits.to_N t2))).
    rewrite N_lxor_double. reflexivity.
Qed.

(** The bitwise value correspondence for and/or/xor. *)
Lemma and_correspondence : forall sz x y,
    bits_to_nat (Bits.and (nat_to_bits sz x) (nat_to_bits sz y)) = nat_and (wrap sz x) (wrap sz y).
Proof.
  intros sz x y.
  unfold bits_to_nat, nat_to_bits, nat_and, Bits.to_nat, Bits.of_nat.
  rewrite to_N_and.
  destruct sz.
  - cbn. reflexivity.
  - unfold wrap.
    rewrite !Bits.to_N_of_N_mod.
    rewrite !Nat2N.inj_mod.
    rewrite <- !N_pow_Nat_pow.
    change (N.of_nat 2) with 2%N.
    reflexivity.
Qed.

Lemma or_correspondence : forall sz x y,
    bits_to_nat (Bits.or (nat_to_bits sz x) (nat_to_bits sz y)) = nat_or (wrap sz x) (wrap sz y).
Proof.
  intros sz x y.
  unfold bits_to_nat, nat_to_bits, nat_or, Bits.to_nat, Bits.of_nat.
  rewrite to_N_or.
  destruct sz.
  - cbn. reflexivity.
  - unfold wrap.
    rewrite !Bits.to_N_of_N_mod.
    rewrite !Nat2N.inj_mod.
    rewrite <- !N_pow_Nat_pow.
    change (N.of_nat 2) with 2%N.
    reflexivity.
Qed.

Lemma xor_correspondence : forall sz x y,
    bits_to_nat (Bits.xor (nat_to_bits sz x) (nat_to_bits sz y)) = nat_xor (wrap sz x) (wrap sz y).
Proof.
  intros sz x y.
  unfold bits_to_nat, nat_to_bits, nat_xor, Bits.to_nat, Bits.of_nat.
  rewrite to_N_xor.
  destruct sz.
  - cbn. reflexivity.
  - unfold wrap.
    rewrite !Bits.to_N_of_N_mod.
    rewrite !Nat2N.inj_mod.
    rewrite <- !N_pow_Nat_pow.
    change (N.of_nat 2) with 2%N.
    reflexivity.
Qed.

(* ------------------------------------------------------------------ *)
(* 3. A worked end-to-end theorem: a counter-like rule                  *)
(* ------------------------------------------------------------------ *)

(** Registers/inputs for the example: R = 0, I = 0. *)
Definition RP_R : nat := 0.
Definition RP_I : nat := 0.

(** The counter rule: R := (ite I (add (read R) 1) (read R)), width 4. *)
Definition counter_rule : rule :=
  mkRule (ELit 1)
    [ AWrite RP_R (EIte (EVar RP_I)
                        (EBinop BAdd (ERead RP_R) (ELit 1))
                        (ERead RP_R)) ].

Definition counter_widths : widths := fun _ => 4.

(** The reference next value of the counter rule, expressed as a nat function. *)
Definition counter_next (r : value) (i : value) : value :=
  if i =? 0 then r else wrap 4 (r + 1).

(** The Kōika version computes the same value in `bits_t 4` via [Bits.plus];
    [Bits.plus] matches [wrap 4 (r + 1)] by [add_correspondence]. *)
Lemma counter_value_correspondence :
  forall (r : value),
    bits_to_nat
      (Bits.plus (nat_to_bits 4 r) (nat_to_bits 4 1))
    = wrap 4 (r + 1).
Proof.
  intros. apply add_correspondence.
Qed.

(** The reference [eval] of the counter RHS is [counter_next].  This is the
    *state update* refinement lemma for the counter rule. *)
Lemma counter_eval_matches :
  forall st inp mem r i,
    st RP_R = Some r -> inp RP_I = Some i ->
    eval (EIte (EVar RP_I) (EBinop BAdd (ERead RP_R) (ELit 1)) (ERead RP_R))
         4 st inp mem = Some (counter_next r i).
Proof.
  intros st inp mem r i Hr Hi.
  unfold counter_next. cbn [eval].
  rewrite Hr, Hi.
  destruct i as [|i'].
  - reflexivity.
  - reflexivity.
Qed.

(** Every core-fragment expression is also in the supported subset (so
    [R_rule] holds for the counter rule). *)
Lemma counter_core_fragment :
  core_fragment (EIte (EVar RP_I) (EBinop BAdd (ERead RP_R) (ELit 1)) (ERead RP_R)) = true.
Proof. reflexivity. Qed.

(* ------------------------------------------------------------------ *)
(* 4. End-to-end refinement: a counter-like rule                       *)
(* ------------------------------------------------------------------ *)

Require Import ISIR.koika.refinement.

(** General value correspondence for [Bits.plus] on arbitrary bit-vectors. *)
Lemma add_bits_correspondence : forall sz (b1 b2 : Bits.bits sz),
    bits_to_nat (Bits.plus b1 b2) = wrap sz (bits_to_nat b1 + bits_to_nat b2).
Proof.
  intros sz b1 b2.
  unfold bits_to_nat, wrap, Bits.to_nat.
  rewrite Bits.to_N_plus.
  destruct sz.
  - cbn. reflexivity.
  - rewrite N2Nat.inj_mod.
    rewrite N2Nat.inj_add.
    rewrite N2Nat.inj_pow.
    rewrite Nat2N.id.
    change (N.to_nat 2) with 2.
    reflexivity.
Qed.

(** A concrete counter: register 0, width 4, rule `0 := add (read 0) 1`. *)
Definition counter_rw : nat -> nat := fun _ => 4.
Definition counter_reg_id : unit -> nat := fun _ => 0.
Definition counter_plus1_rule : rule :=
  mkRule (ELit 1) [ AWrite 0 (EBinop BAdd (ERead 0) (ELit 1)) ].

(** The Kōika single-cycle step: register 0 advances by `Bits.plus` with 1. *)
Definition counter_step_koika :
  koika_store unit counter_rw counter_reg_id
  -> option (koika_store unit counter_rw counter_reg_id) :=
  fun ks => Some (fun (_ : unit) => Bits.plus (ks tt) (nat_to_bits 4 1)).

(** The ISIR [step] of the counter rule, simplified to the register update
    (the [apply_action] wrap composes with [eval]'s wrap, hence the double
    [wrap], which is idempotent and absorbed by [Nat.mod_mod] in the proof). *)
Lemma counter_step_simpl :
  forall s i mem v,
    s 0 = Some v ->
    step SParallel [counter_plus1_rule] (fun _ => 4) (fun _ => 4) s i mem
    = Some (fun id => if id =? 0 then Some (wrap 4 (wrap 4 (v + 1))) else s id, mem).
Proof.
  intros s i mem v Hv.
  unfold step, counter_plus1_rule, fire, grants, granted_actions, apply_actions, apply_action.
  cbn.
  rewrite Hv. reflexivity.
Qed.

(** The ISIR [step] is undefined when register 0 is uninitialized. *)
Lemma counter_step_undefined :
  forall s i mem,
    s 0 = None ->
    step SParallel [counter_plus1_rule] (fun _ => 4) (fun _ => 4) s i mem = None.
Proof.
  intros s i mem Hs0.
  unfold step, counter_plus1_rule, fire, grants, granted_actions, apply_actions, apply_action.
  cbn.
  rewrite Hs0. reflexivity.
Qed.

(** The counter Kōika step preserves [R_state] — the value-refinement half. *)
Theorem counter_value_refinement :
  value_refinement unit counter_rw counter_reg_id counter_step_koika
                   SParallel [counter_plus1_rule] (fun _ => 4).
Proof.
  unfold value_refinement, R_state, counter_step_koika, counter_rw, counter_reg_id.
  intros s s' i mem mem' ks ks' HR Hstep Hkoika.
  injection Hkoika as <-.
  specialize (HR tt).
  change (counter_reg_id tt) with 0 in HR.
  change (counter_rw 0) with 4 in HR.
  change (2 ^ 4) with 16 in HR.
  intro r. destruct r.
  destruct (s 0) as [v | ] eqn:Hs0.
  - change (bits_to_nat (ks tt) = v mod 16) in HR.
    assert (Hst := counter_step_simpl s i mem v Hs0).
    rewrite Hst in Hstep. injection Hstep as Hs' _.
    rewrite <- Hs'.
    change (bits_to_nat (Bits.plus (ks tt) (nat_to_bits 4 1)) = (wrap 4 (wrap 4 (v + 1))) mod 2 ^ 4).
    rewrite add_bits_correspondence.
    rewrite nat_bits_roundtrip.
    rewrite Nat.mod_small by (change (2 ^ 4) with 16; lia).
    rewrite HR.
    unfold wrap.
    rewrite !Nat.Div0.mod_mod by lia.
    symmetry. rewrite (Nat.Div0.add_mod v 1 (2 ^ 4)). rewrite (Nat.mod_small 1 (2 ^ 4)) by (change (2 ^ 4) with 16; lia). reflexivity.
  - rewrite (counter_step_undefined s i mem Hs0) in Hstep. discriminate.
Qed.

(** The counter Kōika step is always defined — definedness-preservation. *)
Theorem counter_definedness_preservation :
  definedness_preservation unit counter_rw counter_reg_id counter_step_koika
                           SParallel [counter_plus1_rule] (fun _ => 4).
Proof.
  unfold definedness_preservation, counter_step_koika.
  intros s i mem ks HR Hstep.
  congruence.
Qed.

(** End-to-end: the counter Kōika step refines the ISIR counter step. *)
Theorem counter_refines :
  refines unit counter_rw counter_reg_id counter_step_koika
          SParallel [counter_plus1_rule] (fun _ => 4).
Proof.
  unfold refines. split.
  - apply counter_definedness_preservation.
  - apply counter_value_refinement.
Qed.

(* ------------------------------------------------------------------ *)
(* 5. Breadth: a two's-complement subtraction rule (the GCD core)      *)
(* ------------------------------------------------------------------ *)

(** [Bits.minus] over arbitrary bit-vectors equals the ISIR two's-complement
    [wrap sz (2^sz + x - y)] — the bits-level analogue of [sub_correspondence]
    (no operand-boundedness side condition, since bit-vectors are bounded). *)
Lemma sub_bits_correspondence : forall sz (b1 b2 : Bits.bits sz),
    bits_to_nat (Bits.minus b1 b2) = wrap sz (2 ^ sz + bits_to_nat b1 - bits_to_nat b2).
Proof.
  intros sz b1 b2.
  unfold bits_to_nat, wrap, Bits.to_nat.
  rewrite Bits.to_N_minus.
  destruct sz.
  - cbn. reflexivity.
  - rewrite N2Nat.inj_mod.
    rewrite N2Nat.inj_sub by (apply N.lt_le_incl; apply Bits.to_N_bounded).
    rewrite N2Nat.inj_add.
    rewrite N2Nat.inj_pow.
    rewrite Nat2N.id.
    change (N.to_nat 2) with 2.
    reflexivity.
Qed.

(** A concrete GCD-style rule: register 0 := sub (read 0) 1, width 4. *)
Definition sub_rule : rule :=
  mkRule (ELit 1) [ AWrite 0 (EBinop BSub (ERead 0) (ELit 1)) ].

Definition sub_step_koika :
  koika_store unit counter_rw counter_reg_id
  -> option (koika_store unit counter_rw counter_reg_id) :=
  fun ks => Some (fun (_ : unit) => Bits.minus (ks tt) (nat_to_bits 4 1)).

Lemma sub_step_simpl :
  forall s i mem v,
    s 0 = Some v ->
    step SParallel [sub_rule] (fun _ => 4) (fun _ => 4) s i mem
    = Some (fun id => if id =? 0 then Some (wrap 4 (wrap 4 (2 ^ 4 + v - 1))) else s id, mem).
Proof.
  intros s i mem v Hv.
  unfold step, sub_rule, fire, grants, granted_actions, apply_actions, apply_action.
  cbn.
  rewrite Hv. reflexivity.
Qed.

Lemma sub_step_undefined :
  forall s i mem,
    s 0 = None ->
    step SParallel [sub_rule] (fun _ => 4) (fun _ => 4) s i mem = None.
Proof.
  intros s i mem Hs0.
  unfold step, sub_rule, fire, grants, granted_actions, apply_actions, apply_action.
  cbn.
  rewrite Hs0. reflexivity.
Qed.

Theorem sub_value_refinement :
  value_refinement unit counter_rw counter_reg_id sub_step_koika
                   SParallel [sub_rule] (fun _ => 4).
Proof.
  unfold value_refinement, R_state, sub_step_koika, counter_rw, counter_reg_id.
  intros s s' i mem mem' ks ks' HR Hstep Hkoika.
  injection Hkoika as <-.
  specialize (HR tt).
  change (counter_reg_id tt) with 0 in HR.
  change (counter_rw 0) with 4 in HR.
  change (2 ^ 4) with 16 in HR.
  intro r. destruct r.
  destruct (s 0) as [v | ] eqn:Hs0.
  - change (bits_to_nat (ks tt) = v mod 16) in HR.
    assert (Hst := sub_step_simpl s i mem v Hs0).
    rewrite Hst in Hstep. injection Hstep as Hs' _.
    rewrite <- Hs'.
    change (bits_to_nat (Bits.minus (ks tt) (nat_to_bits 4 1)) = (wrap 4 (wrap 4 (2 ^ 4 + v - 1))) mod 2 ^ 4).
    rewrite sub_bits_correspondence.
    rewrite nat_bits_roundtrip.
    rewrite Nat.mod_small by (change (2 ^ 4) with 16; lia).
    rewrite HR.
    unfold wrap.
    rewrite !Nat.Div0.mod_mod by lia.
    change ((15 + (v mod 16)) mod 16 = (15 + v) mod 16).
    symmetry. rewrite (Nat.Div0.add_mod 15 v 16). rewrite (Nat.mod_small 15 16) by lia. reflexivity.
  - rewrite (sub_step_undefined s i mem Hs0) in Hstep. discriminate.
Qed.

Theorem sub_definedness_preservation :
  definedness_preservation unit counter_rw counter_reg_id sub_step_koika
                           SParallel [sub_rule] (fun _ => 4).
Proof.
  unfold definedness_preservation, sub_step_koika.
  intros s i mem ks HR Hstep.
  congruence.
Qed.

(** End-to-end: the GCD-style `sub` rule refines its ISIR step. *)
Theorem sub_refines :
  refines unit counter_rw counter_reg_id sub_step_koika
          SParallel [sub_rule] (fun _ => 4).
Proof.
  unfold refines. split.
  - apply sub_definedness_preservation.
  - apply sub_value_refinement.
Qed.
