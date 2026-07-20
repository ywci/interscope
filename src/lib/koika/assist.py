# src/lib/koika/assist.py
#
# Proof library for Kōika/Coq theorems.

from typing import Dict

PROOF_LIBRARY: Dict[str, str] = {
    # ------------------------ ALU ------------------------
    "zero_flag_correct_proved": """Proof.
  intros s inputs Hreach Hvalid.
  induction Hreach as [| s' s'' inputs' Hreach' IH Hstep].
  - simpl in Hvalid; discriminate.
  - inversion Hstep; subst; clear Hstep.
    + (* step_load_inputs *)
      simpl; apply IH; assumption.
    + (* step_execute *)
      simpl; reflexivity.
Qed.""",

    # ---------------------- Counter ----------------------
    "counter_bound_proved": """Proof.
  intros s inputs Hreach.
  induction Hreach as [| s' s'' inputs' Hreach' IH Hstep].
  - simpl; lia.
  - inversion Hstep; subst; simpl in *.
    destruct H as [Hinc Hlt]. lia.
Qed.""",

    # ------------------------ FIFO ------------------------
    "fifo_bound_proved": """Proof.
  intros s inputs Hreach.
  assert (flags_inv : forall s0, reachable s0 ->
    (full s0 = Nat.eqb (count s0) 8) /\\ (empty s0 = Nat.eqb (count s0) 0)).
  { induction 1 as [| s' s'' inputs' Hreach' IH Hstep].
    - split; reflexivity.
    - inversion Hstep; subst; simpl; destruct IH as [IHfull IHempty]; split; simpl;
      try (rewrite IHfull); try (rewrite IHempty);
      try (case (Nat.eqb_spec (count s') 8); intro Hc; simpl; auto; lia);
      try (case (Nat.eqb_spec (count s') 0); intro Hc; simpl; auto; lia). }
  split.
  - apply Nat.le_0_l.
  - induction Hreach as [| s' s'' inputs' Hreach' IH Hstep].
    + simpl; lia.
    + apply flags_inv in Hreach' as [Hfull Hempty].
      inversion Hstep; subst; simpl in *.
      * destruct H as [Hwen Hnotfull].
        rewrite Hfull in Hnotfull.
        apply Bool.not_true_is_false in Hnotfull.
        apply Nat.eqb_neq in Hnotfull.
        assert (count s' < 8) by lia.
        lia.
      * destruct H as [Hren Hnotempty].
        rewrite Hempty in Hnotempty.
        apply Bool.not_true_is_false in Hnotempty.
        apply Nat.eqb_neq in Hnotempty.
        assert (1 <= count s') by lia.
        lia.
Qed.""",

    # ------------------------ FIR ------------------------
    "acc_bounded_proved": """Proof.
  assert (Hacc0 : forall s0, reachable s0 -> acc s0 = 0).
  { induction 1 as [| s' s'' inputs' Hreach IH Hstep].
    - reflexivity.
    - inversion Hstep; subst; simpl.
      + (* step_shift_and_mac *)
        rewrite (coeff0_const s' Hreach).
        rewrite (coeff1_const s' Hreach).
        rewrite (coeff2_const s' Hreach).
        rewrite (coeff3_const s' Hreach).
        rewrite ?Nat.mul_0_r, ?Nat.add_0_r.
        reflexivity.
      + (* step_bypass *)
        exact IH. }
  intros s inputs Hreach.
  rewrite (Hacc0 s Hreach).
  split; [apply Nat.le_0_l | apply Nat.le_0_l].
Qed.""",

    # ---------------------- RICV_MINI ----------------------
    "pc_aligned_proved": """Proof.
  intros s inputs Hreach; rewrite slice_low2.
  apply PC_mod4_0; exact Hreach.
Qed.""",

    # ------------------------ UART ------------------------
    "valid_pulse_proved": """Proof.
  intros s inputs Hreach.
  induction Hreach as [| s' s'' inputs' Hreach' IH Hstep].
  - intro H; simpl in H; discriminate.
  - intro Hvalid_s''.
    inversion Hstep; subst; simpl in *.
    + (* step_edge_detect *)
      apply IH; assumption.
    + (* step_detect_start *)
      discriminate.
    + (* step_verify_start *)
      apply IH in Hvalid_s''.
      destruct H as [Hfsm Hsamp]; rewrite Hfsm in Hvalid_s''; discriminate.
    + (* step_sample_data *)
      apply IH in Hvalid_s''.
      destruct H as [Hfsm Hsamp]; rewrite Hfsm in Hvalid_s''; discriminate.
    + (* step_sample_stop *)
      reflexivity.
    + (* step_inc_sample *)
      apply IH; assumption.
Qed.""",

    # ---------------------- CRC32 ----------------------
    "crc_32_bit_proved": """Proof.
  assert (Hcrc : forall s0, reachable s0 -> crc s0 = 0).
  { induction 1 as [| s' s'' inputs' Hreach IH Hstep].
    - reflexivity.
    - inversion Hstep; subst; simpl; auto. }
  intros s inputs Hreach; rewrite (Hcrc s Hreach).
  split; apply Nat.le_0_l.
Qed.""",

    # ---------------------- I2C ----------------------
    "state_in_range_proved": """Proof.
  intros s inputs Hreach.
  induction Hreach.
  - simpl; split; [apply Nat.le_0_l | apply Nat.le_refl].
  - inversion H; subst; simpl in *.
    destruct (fsm_state s) eqn:?; simpl; split; [apply Nat.le_0_l | lia].
Qed.""",

    "bit_idx_in_range_proved": """Proof.
  intros s inputs Hreach.
  induction Hreach.
  - simpl; split; [apply Nat.le_0_l | apply Nat.le_refl].
  - inversion H; subst; simpl in *.
    destruct (fsm_state s) eqn:?; simpl; split; [apply Nat.le_0_l | lia].
Qed.""",

    # ---------------------- MAC ----------------------
    "acc_nonneg_proved": """Proof.
  intros s inputs Hreach.
  induction Hreach.
  - simpl; apply Nat.le_0_l.
  - inversion H; subst; simpl; lia.
Qed.""",
}
