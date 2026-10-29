(* ISIR.koika.koika_correspondence
 *
 * This module defines:
 *   - the value/width correspondence `nat <-> bits sz` (and its round-trip
 *     property: a bit-vector of width sz wraps to `mod 2^sz`, matching
 *     ISIR.isir's `wrap`);
 *   - `R_state`  : ISIR register store <-> Kōika bit-vector register store;
 *   - `R_schedule` : ISIR schedule <-> Kōika single-rule scheduler;
 *   - `supported_expr` / `supported_rule` : the operator subset the Kōika
 *     RTL lowering can emit (slice/mul/div/mod/mem_* are OUTSIDE);
 *   - `R_rule`   : the supported-subset correspondence (semantic preservation
 *     of condition + actions is the refinement obligation, deferred here).
 *
 * Encoding gaps documented but not encoded:
 *   - `koika_to_rtl._internalize_inputs` latches inputs in a register, shifting
 *     input-dependent state one cycle; the correspondence below relates the
 *     post-internalization registers, not the raw input ports.
 *   - The lowering merges every ISIR rule into one `Step_merged` action; the
 *     per-rule correspondence is therefore stated against the merged action.
 *)

Require Import ISIR.isir.
Require Import Koika.Frontend.
Require Import Koika.Types.
Require Import Koika.Vect.

Open Scope nat_scope.

(* The Kōika `Frontend` re-exports `rule`/`action` notations that clash with
   ISIR.isir's `rule`/`action`, so we refer to the ISIR ones qualified. *)
Local Notation isir_rule := ISIR.isir.rule.
Local Notation isir_action := ISIR.isir.action.

(* ------------------------------------------------------------------ *)
(* 1. Value/width correspondence: nat <-> bits sz                       *)
(* ------------------------------------------------------------------ *)

Definition nat_to_bits (sz : nat) (n : value) : Bits.bits sz := Bits.of_nat sz n.
Definition bits_to_nat {sz : nat} (bs : Bits.bits sz) : value := Bits.to_nat bs.

(** A bit-vector of width [sz] round-trips a nat modulo 2^sz, i.e. the Kōika
    `bits_t sz` arithmetic wraps exactly like ISIR.isir's `wrap`. *)
Lemma nat_bits_roundtrip :
  forall sz n, bits_to_nat (nat_to_bits sz n) = n mod 2 ^ sz.
Proof.
  intros sz n.
  unfold bits_to_nat, nat_to_bits, Bits.to_nat, Bits.of_nat.
  rewrite Bits.to_N_of_N_mod.
  rewrite N2Nat.inj_mod.
  rewrite Nat2N.id.
  rewrite N2Nat.inj_pow.
  rewrite Nat2N.id.
  reflexivity.
Qed.

(* ------------------------------------------------------------------ *)
(* 2. R_state: register-store correspondence                           *)
(* ------------------------------------------------------------------ *)

(** The Kōika register store specialized to bit-vector registers.  This is the
    RTL-synthesis subset: koika_to_rtl emits `R r := bits_t w` for every
    register (no structs/arrays/enums reach RTL). *)
Definition koika_store (reg_t : Type) (rw : nat -> nat) (reg_id : reg_t -> nat) : Type :=
  forall r, Bits.bits (rw (reg_id r)).

(** [R_state] relates an ISIR functional register store to a Kōika bit-vector
    register store: for every register, the Kōika value's nat reading equals the
    ISIR value wrapped to the register width. *)
Definition R_state (reg_t : Type) (rw : nat -> nat) (reg_id : reg_t -> nat)
                   (st : state) (ks : koika_store reg_t rw reg_id) : Prop :=
  forall r, match st (reg_id r) with
            | Some v => bits_to_nat (ks r) = v mod 2 ^ (rw (reg_id r))
            | None => True
            end.

(* ------------------------------------------------------------------ *)
(* 3. R_schedule: scheduler correspondence                             *)
(* ------------------------------------------------------------------ *)

(** The lowering merges every ISIR rule into one `Step_merged` action and
    schedules it with `Step_merged |> Done`.  So any ISIR schedule mode maps
    to a single-rule Kōika scheduler; the per-mode differences are pre-resolved
    by the rule-merging pass. *)
Section ScheduleCorrespondence.
  Context (rule_name_t : Type).

  Definition R_schedule (is : schedule) (sched : Koika.Syntax.scheduler unit rule_name_t) : Prop :=
    exists r, sched = @Koika.Syntax.Cons unit rule_name_t r (@Koika.Syntax.Done unit rule_name_t).
End ScheduleCorrespondence.

(* ------------------------------------------------------------------ *)
(* 4. Supported operator subset (the explicit R_rule boundary)         *)
(* ------------------------------------------------------------------ *)

(** The operators koika_to_rtl.py can lower.  `slice` (ESlice) and memory reads
    (EMemRead) are OUTSIDE; `mul`/`div`/`mod` are absent from ISIR.isir's binop
    and therefore structurally impossible here. *)
Fixpoint supported_expr (e : expr) : bool :=
  match e with
  | ELit _ | EVar _ | ERead _ => true
  | EMemRead _ _ => false
  | EUnop _ x => supported_expr x
  | EBinop _ a b => supported_expr a && supported_expr b
  | EIte c t f => supported_expr c && supported_expr t && supported_expr f
  | ESlice _ _ _ => false
  | EPartial _ => true   (* partial_spec: lowered as an extcall (supported) *)
  end.

Definition supported_action (a : isir_action) : bool :=
  match a with
  | AWrite _ rhs => supported_expr rhs
  | AMemWrite _ _ _ => false   (* mem_write is unsupported *)
  end.

Definition supported_rule (r : isir_rule) : bool :=
  supported_expr (r_condition r) && forallb supported_action (r_actions r).

(* ------------------------------------------------------------------ *)
(* 5. R_rule: the supported-subset correspondence                      *)
(* ------------------------------------------------------------------ *)

Section RuleCorrespondence.
  Context (reg_t ext_fn_t : Type).

  (** [R_rule] holds iff the ISIR rule is in the supported subset.  Full
      semantic preservation (condition + action effects on obs) is the
      refinement obligation, stated against this subset. *)
  Definition R_rule (r : isir_rule) (ua : uaction reg_t ext_fn_t) : Prop :=
    supported_rule r = true.
End RuleCorrespondence.

(* ------------------------------------------------------------------ *)
(* 6. Worked examples                                                  *)
(* ------------------------------------------------------------------ *)

(** The ALU add rule from ISIR.isir is supported, so R_rule holds for any
    Kōika action. *)
Lemma alu_rule_supported :
  forall (reg_t ext_fn_t : Type) (ua : uaction reg_t ext_fn_t),
    R_rule reg_t ext_fn_t alu_add_rule ua.
Proof.
  intros. compute. reflexivity.
Qed.

(** A slice-using rule is outside R_rule (unsupported). *)
Definition slice_rule : isir_rule :=
  mkRule (ELit 1) [ AWrite 0 (ESlice (EVar 0) 7 0) ].

Lemma slice_rule_unsupported :
  forall (reg_t ext_fn_t : Type) (ua : uaction reg_t ext_fn_t),
    R_rule reg_t ext_fn_t slice_rule ua -> False.
Proof.
  intros reg_t ext_fn_t ua H. compute in H. discriminate.
Qed.

(* ------------------------------------------------------------------ *)
(* 7. Input-latency correspondence (encoding gap: _internalize_inputs) *)
(* ------------------------------------------------------------------ *)

(** `koika_to_rtl._internalize_inputs` turns every ISIR input into a Kōika
    register, because the Kōika `reg_t` is register-only and cannot express
    combinational inputs.  The Kōika store therefore also contains *input
    registers*, distinguished from the regular registers by the id map. *)

Definition koika_input_store (in_t : Type) (iw : nat -> nat) (in_id : in_t -> nat) : Type :=
  forall x, Bits.bits (iw (in_id x)).

(** [R_input] relates the ISIR combinational inputs to the Kōika input
    registers: same `nat <-> bits sz` width correspondence as [R_state]. *)
Definition R_input (in_t : Type) (iw : nat -> nat) (in_id : in_t -> nat)
                   (i : inputs) (kin : koika_input_store in_t iw in_id) : Prop :=
  forall x, match i (in_id x) with
            | Some v => bits_to_nat (kin x) = v mod 2 ^ (iw (in_id x))
            | None => True
            end.

(** Internalize the current inputs into a Kōika input store (unbound inputs
    become zero, matching the register's initial value 0). *)
Definition internalize_inputs (in_t : Type) (iw : nat -> nat) (in_id : in_t -> nat)
                              (i : inputs) : koika_input_store in_t iw in_id :=
  fun x => match i (in_id x) with
           | Some v => nat_to_bits (iw (in_id x)) v
           | None => Bits.zeroes (iw (in_id x))
           end.

(** Internalizing the inputs is consistent with [R_input]. *)
Lemma internalize_inputs_R_input :
  forall (in_t : Type) (iw : nat -> nat) (in_id : in_t -> nat) (i : inputs),
    R_input in_t iw in_id i (internalize_inputs in_t iw in_id i).
Proof.
  intros in_t iw in_id i. unfold R_input, internalize_inputs. intros x.
  destruct (i (in_id x)) as [v | ] eqn:E.
  - rewrite nat_bits_roundtrip. reflexivity.
  - reflexivity.
Qed.

(** Combined correspondence: regular registers ([R_state]) plus input registers
    ([R_input]). *)
Definition R_state_in (reg_t in_t : Type) (rw iw : nat -> nat)
                      (reg_id : reg_t -> nat) (in_id : in_t -> nat)
                      (st : state) (i : inputs)
                      (ks : koika_store reg_t rw reg_id)
                      (kin : koika_input_store in_t iw in_id) : Prop :=
  R_state reg_t rw reg_id st ks /\ R_input in_t iw in_id i kin.

(** The 1-cycle latency.  The Kōika input register is latched on the clock, so
    at cycle [k] it holds the input [i[k-1]], not [i[k]].  Equivalently, the
    Kōika state one step after internalizing input [i] corresponds to the ISIR
    state reached by stepping with combinational input [i]:

        R_state_in st i ks kin  ->  R_state_in (step_isir st i) i' (step_koika ks) (i' latched)

    i.e. the input register advances to the *next* input [i'] externally while
    the rule advances the regular registers.  This trace shift is stated as the
    relation [R_latched_step] below; its preservation is the obligation. *)

Definition R_latched_step
  (reg_t in_t : Type) (rw iw : nat -> nat)
  (reg_id : reg_t -> nat) (in_id : in_t -> nat)
  (st st' : state) (i i' : inputs)
  (ks ks' : koika_store reg_t rw reg_id)
  (kin kin' : koika_input_store in_t iw in_id) : Prop :=
  R_state_in reg_t in_t rw iw reg_id in_id st i ks kin ->
  R_state_in reg_t in_t rw iw reg_id in_id st' i' ks' kin'.

(** The worked example: internalizing the ALU inputs a=250, b=10 satisfies
    [R_input] against those inputs. *)
Definition alu_inputs : inputs :=
  fun id => if id =? I_A then Some 250 else if id =? I_B then Some 10 else None.

Definition alu_input_widths : nat -> nat := fun _ => 8.

Lemma alu_inputs_R_input :
  forall (in_t : Type) (in_id : in_t -> nat),
    R_input in_t alu_input_widths in_id alu_inputs
             (internalize_inputs in_t alu_input_widths in_id alu_inputs).
Proof.
  intros. apply internalize_inputs_R_input.
Qed.
