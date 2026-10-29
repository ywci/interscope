(* ISIR.isir
 *
 * Formal operational semantics of the ISIR executable subset.
 *
 * This module mirrors the Python reference interpreter
 * (src/isir/verification/reference_semantics.py + src/isir/utils/expr.py),
 * so that agreement between the two is real evidence rather than an artifact
 * of shared lowering code.
 *
 * Design notes
 * ------------
 * - A value is a natural number; its bit width is carried by the storage
 *   declaration (register/input/memory width map), not by the value itself.
 *   Arithmetic wraps modulo 2^width, exactly like eval_expr's `_wrap`.
 * - Names (register ids, input ids, memory ids, rule names) are naturals here;
 *   the Python lowering assigns these ids from the string names in the .isir
 *   file.  This keeps decidable equality trivial and the semantics
 *   self-contained (no string comparison).
 * - The scheduler is a first-class object (parallel / sequential /
 *   conflict_free).  conflict_free is modeled as parallel (both admit all
 *   enabled rules) under the static disjoint-write assumption that the
 *   lowering checks.
 *
 * Out of scope for this first cut (documented, not silently assumed):
 *   - mul / div / mod / concat / min / max are not yet evaluated;
 *     the evaluator returns None (undefined) for them.
 *   - partial_spec non-determinism is represented by an uninterpreted
 *     function returning None, to be refined in a later pass.
 *)

Require Import Coq.Arith.PeanoNat.
Require Import Coq.Bool.Bool.
Require Import Coq.Lists.List.
Require Import Coq.NArith.NArith.
Import ListNotations.

Open Scope nat_scope.

(* ------------------------------------------------------------------ *)
(* 1. Values and width wrapping                                        *)
(* ------------------------------------------------------------------ *)

Definition value : Type := nat.

(** Wraps [v] to [width] bits, matching `v & ((1 << width) - 1)`. *)
Definition wrap (width : nat) (v : value) : value :=
  match width with
  | 0 => 0
  | S _ => v mod (2 ^ width)
  end.

(* ------------------------------------------------------------------ *)
(* 2. Bitwise operators (via binary naturals, total and structural)    *)
(* ------------------------------------------------------------------ *)

Definition nat_and (a b : nat) : nat := N.to_nat (N.land (N.of_nat a) (N.of_nat b)).
Definition nat_or  (a b : nat) : nat := N.to_nat (N.lor  (N.of_nat a) (N.of_nat b)).
Definition nat_xor (a b : nat) : nat := N.to_nat (N.lxor (N.of_nat a) (N.of_nat b)).

(* ------------------------------------------------------------------ *)
(* 3. Operators                                                        *)
(* ------------------------------------------------------------------ *)

Inductive binop : Type :=
| BAdd | BSub | BAnd | BOr | BXor
| BEq | BNeq | BLt | BLe | BGt | BGe
| BShl | BShr.

Inductive unop : Type :=
| UNot.

(* ------------------------------------------------------------------ *)
(* 4. Expressions (S-expressions)                                      *)
(* ------------------------------------------------------------------ *)

Inductive expr : Type :=
| ELit : value -> expr                (* integer / boolean literal *)
| EVar : nat -> expr                  (* input id *)
| ERead : nat -> expr                 (* register id *)
| EMemRead : nat -> expr -> expr      (* memory id, address expression *)
| EUnop : unop -> expr -> expr
| EBinop : binop -> expr -> expr -> expr
| EIte : expr -> expr -> expr -> expr
| ESlice : expr -> nat -> nat -> expr (* (slice e high low) *)
| EPartial : nat -> expr.            (* partial_spec: non-deterministic value of width n *)

(* ------------------------------------------------------------------ *)
(* 5. Environments                                                     *)
(* ------------------------------------------------------------------ *)

(** Functional maps: id -> value (option for unbound ids). *)
Definition state : Type := nat -> option value.
Definition inputs : Type := nat -> option value.
Definition memory : Type := nat -> option value.
Definition memories : Type := nat -> option memory.

(** Width maps: id -> width (bits). *)
Definition widths : Type := nat -> nat.

Definition default_width : nat := 1.

(* ------------------------------------------------------------------ *)
(* 6. Expression evaluation                                            *)
(* ------------------------------------------------------------------ *)

Definition bool_to_nat (b : bool) : value := if b then 1 else 0.

(** [eval e w st inp mem] evaluates [e] with wrap width [w].
    Returns [None] for undefined behavior (unbound id, or an operator not
    yet modeled). *)
Fixpoint eval (e : expr) (w : nat) (st : state) (inp : inputs) (mem : memories) : option value :=
  match e with
  | ELit n => Some n
  | EVar id => inp id
  | ERead id => st id
  | EMemRead mid addr =>
      match eval addr w st inp mem with
      | None => None
      | Some a =>
          match mem mid with
          | None => None
          | Some m => m a
          end
      end
  | EUnop UNot x =>
      match eval x w st inp mem with
      | None => None
      | Some v => Some (if v =? 0 then 1 else 0)
      end
  | EBinop op a b =>
      match eval a w st inp mem, eval b w st inp mem with
      | None, _ => None
      | _, None => None
      | Some x, Some y =>
          match op with
          | BAdd => Some (wrap w (x + y))
          | BSub => Some (wrap w (2 ^ w + x - y))  (* two's-complement (matches Kōika Bits.minus + the reference) *)
          | BAnd => Some (nat_and x y)
          | BOr  => Some (nat_or x y)
          | BXor => Some (nat_xor x y)
          | BEq  => Some (bool_to_nat (x =? y))
          | BNeq => Some (bool_to_nat (negb (x =? y)))
          | BLt  => Some (bool_to_nat (x <? y))
          | BLe  => Some (bool_to_nat (x <=? y))
          | BGt  => Some (bool_to_nat (y <? x))
          | BGe  => Some (bool_to_nat (y <=? x))
          | BShl => Some (wrap w (x * 2 ^ y))
          | BShr => Some (wrap w (x / 2 ^ y))
          end
      end
  | EIte c t f =>
      match eval c w st inp mem with
      | None => None
      | Some 0 => eval f w st inp mem
      | Some _ => eval t w st inp mem
      end
  | ESlice x high low =>
      match eval x w st inp mem with
      | None => None
      | Some v => Some ((v / 2 ^ low) mod (2 ^ (S high - low)))
      end
  | EPartial _ => None   (* non-deterministic: see eval_nd below *)
  end.

(* ------------------------------------------------------------------ *)
(* 5b. Non-deterministic evaluation (partial_spec)                     *)
(* ------------------------------------------------------------------ *)

(** [eval_nd e w st inp mem v] means [v] is a *possible* value of [e].  For a
    deterministic expression it is the singleton result of [eval]; for
    [EPartial n] it is every value of width [n].  This is the set-valued
    semantics of explicit non-determinism: a partial_spec
    placeholder yields a value from an unconstrained set, never a silent
    default. *)
Inductive eval_nd : expr -> nat -> state -> inputs -> memories -> value -> Prop :=
| ENDDet : forall e w st inp mem v,
    eval e w st inp mem = Some v -> eval_nd e w st inp mem v
| ENDPartial : forall n w st inp mem v,
    v < 2 ^ n -> eval_nd (EPartial n) w st inp mem v.

(** A deterministic result is also a possible value (soundness of eval_nd). *)
Lemma eval_deterministic_nd :
  forall e w st inp mem v, eval e w st inp mem = Some v -> eval_nd e w st inp mem v.
Proof.
  intros. constructor. exact H.
Qed.

(** A partial_spec value is bounded by its width. *)
Lemma partial_bounded :
  forall n w st inp mem v, eval_nd (EPartial n) w st inp mem v -> v < 2 ^ n.
Proof.
  intros n w st inp mem v H. inversion H; subst.
  - discriminate.   (* eval (EPartial n) = Some v is impossible *)
  - exact H1.
Qed.

(* ------------------------------------------------------------------ *)
(* 7. Rules, actions, and scheduling                                   *)
(* ------------------------------------------------------------------ *)

Inductive action : Type :=
| AWrite : nat -> expr -> action               (* (write dest rhs) *)
| AMemWrite : nat -> expr -> expr -> action.   (* (mem_write mem addr data) *)

Record rule : Type := mkRule {
  r_condition : expr;          (* condition; ELit 1 is `true` *)
  r_actions : list action;
}.

Inductive schedule : Type :=
| SParallel
| SSequential
| SConflictFree.

(** [fire r st inp mem] is the condition's truth value (0/1), or None if
    the condition is undefined. *)
Definition fire (r : rule) (st : state) (inp : inputs) (mem : memories) : option value :=
  eval (r_condition r) 1 st inp mem.

(** Sequential grants: the first enabled rule wins; all later rules are
    suppressed (mirrors reference_semantics._grants). *)
Fixpoint grants_seq (fired : list bool) : list bool :=
  match fired with
  | [] => []
  | f :: rest =>
      if f then true :: List.map (fun _ => false) rest
      else f :: grants_seq rest
  end.

Definition grants (sched : schedule) (fired : list bool) : list bool :=
  match sched with
  | SParallel | SConflictFree => fired
  | SSequential => grants_seq fired
  end.

(* ------------------------------------------------------------------ *)
(* 8. Observable projection                                            *)
(* ------------------------------------------------------------------ *)

(** Identity for this first cut; later passes restrict to the declared
    outputs / proof-relevant signals. *)
Definition obs (st : state) : state := st.

(* ------------------------------------------------------------------ *)
(* 9. Step relation (the single-cycle transition)                      *)
(* ------------------------------------------------------------------ *)

(** Applies a single action, wrapping register writes to the destination
    width.  Returns None if the RHS is undefined. *)
Definition apply_action (rw mem_w : widths) (act : action)
                        (st : state) (inp : inputs) (mem : memories)
                        : option (state * memories) :=
  match act with
  | AWrite dest rhs =>
      match eval rhs (rw dest) st inp mem with
      | None => None
      | Some v =>
          Some (fun id => if id =? dest then Some (wrap (rw dest) v) else st id, mem)
      end
  | AMemWrite mid addr data =>
      match eval addr 1 st inp mem, eval data (mem_w mid) st inp mem with
      | None, _ => None
      | _, None => None
      | Some a, Some d =>
          let m := match mem mid with Some m0 => m0 | None => fun _ => None end in
          Some (st,
                fun id => if id =? mid
                          then Some (fun ad => if ad =? a then Some d else m ad)
                          else mem id)
      end
  end.

(** Folds a rule's actions in order; None if any action is undefined
    (a rule is atomic: it fully executes or not at all). *)
Fixpoint apply_actions (rw mem_w : widths) (acts : list action) (st : state)
                       (inp : inputs) (mem : memories) : option (state * memories) :=
  match acts with
  | [] => Some (st, mem)
  | a :: rest =>
      match apply_action rw mem_w a st inp mem with
      | None => None
      | Some (st', mem') => apply_actions rw mem_w rest st' inp mem'
      end
  end.

(** Parallel action application: the RHS reads the *original* state [st] while
    the write goes to the accumulator [acc].  This models the `parallel`
    schedule ("all enabled rules fire simultaneously"), matching
    reference_semantics.reference_step and ISIR's spec (a rule's action is
    atomic; concurrent rules read the pre-cycle state). *)
Definition apply_action_par (rw mem_w : widths) (act : action)
                            (st acc : state) (mem acc_mem : memories) (inp : inputs)
                            : option (state * memories) :=
  match act with
  | AWrite dest rhs =>
      match eval rhs (rw dest) st inp mem with
      | None => None
      | Some v =>
          Some (fun id => if id =? dest then Some (wrap (rw dest) v) else acc id, acc_mem)
      end
  | AMemWrite mid addr data =>
      match eval addr 1 st inp mem, eval data (mem_w mid) st inp mem with
      | None, _ => None
      | _, None => None
      | Some a, Some d =>
          let m := match acc_mem mid with Some m0 => m0 | None => fun _ => None end in
          Some (acc,
                fun id => if id =? mid
                          then Some (fun ad => if ad =? a then Some d else m ad)
                          else acc_mem id)
      end
  end.

(** Folds a rule's actions in parallel: every RHS reads the original state [st]
    and the writes accumulate.  None if any action is undefined. *)
Fixpoint apply_actions_par (rw mem_w : widths) (acts : list action)
                           (st acc : state) (mem acc_mem : memories) (inp : inputs)
                           : option (state * memories) :=
  match acts with
  | [] => Some (acc, acc_mem)
  | a :: rest =>
      match apply_action_par rw mem_w a st acc mem acc_mem inp with
      | None => None
      | Some (acc', acc_mem') => apply_actions_par rw mem_w rest st acc' mem acc_mem' inp
      end
  end.

(** Concatenates the actions of granted rules, in rule order. *)
Fixpoint granted_actions (rules : list rule) (gs : list bool) : list action :=
  match rules, gs with
  | [], _ => []
  | _, [] => []
  | r :: rs, g :: gs' => (if g then r_actions r else []) ++ granted_actions rs gs'
  end.

(** [step sched rules rw mem_w st inp mem] computes the next state.
    Returns None if any enabled rule's condition or action is undefined. *)
Definition step (sched : schedule) (rules : list rule) (rw mem_w : widths)
                (st : state) (inp : inputs) (mem : memories)
                : option (state * memories) :=
  let fired := List.map (fun r => fire r st inp mem) rules in
  let all_defined := List.forallb (fun f => match f with Some _ => true | None => false end) fired in
  if all_defined then
    let fired_b := List.map (fun f => match f with Some v => negb (v =? 0) | None => false end) fired in
    let gs := grants sched fired_b in
    let acts := granted_actions rules gs in
    match sched with
    | SParallel | SConflictFree => apply_actions_par rw mem_w acts st st mem mem inp
    | SSequential => apply_actions rw mem_w acts st inp mem
    end
  else None.

(* ------------------------------------------------------------------ *)
(* 10. A worked example: ALU result = a + b (wrapped to 8 bits)        *)
(* ------------------------------------------------------------------ *)

Definition R_RESULT : nat := 0.
Definition I_A : nat := 0.
Definition I_B : nat := 1.

Definition alu_add_rule : rule :=
  mkRule
    (ELit 1)                                   (* condition: true *)
    [ AWrite R_RESULT (EBinop BAdd (EVar I_A) (EVar I_B)) ].

Definition alu_reg_widths : widths := fun id => if id =? R_RESULT then 8 else default_width.
Definition alu_mem_widths : widths := fun _ => default_width.

Definition empty_state : state := fun _ => None.
Definition empty_inputs : inputs := fun _ => None.
Definition empty_memories : memories := fun _ => None.

(** a=250, b=10: 250+10 = 260 = 4 (mod 256), matching the fixed-width ISIR
    semantics. *)
Lemma alu_add_wraps :
  step SParallel [alu_add_rule] alu_reg_widths alu_mem_widths
        empty_state
        (fun id => if id =? I_A then Some 250 else if id =? I_B then Some 10 else None)
        empty_memories
  = Some (fun id => if id =? R_RESULT then Some 4 else None, empty_memories).
Proof.
  compute. reflexivity.
Qed.

(** The observable projection of the stepped state retains the result. *)
Lemma alu_add_obs :
  let (st', _) :=
    match step SParallel [alu_add_rule] alu_reg_widths alu_mem_widths
               empty_state
               (fun id => if id =? I_A then Some 250 else if id =? I_B then Some 10 else None)
               empty_memories with
    | Some p => p | None => (empty_state, empty_memories)
    end in
  obs st' R_RESULT = Some 4.
Proof.
  compute. reflexivity.
Qed.
