# riscv_mini specification

## Inputs

| Name | Type |
|------|------|
| `instr` | bits<32> |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `PC` | register | bits<32> | 0 |
| `regfile_0` | register | bits<32> | 0 |
| `regfile_1` | register | bits<32> | 0 |
| `regfile_2` | register | bits<32> | 0 |
| `regfile_3` | register | bits<32> | 0 |
| `if_id_instr` | register | bits<32> | 0 |
| `id_ex_instr` | register | bits<32> | 0 |
| `result_reg` | register | bits<32> | 0 |
| `forward` | register | bool | false |
| `ctr` | register | bits<2> | 0 |
| `flush` | register | bool | false |

## Behavior (rules)

- **step** — when true, set `flush` to mispredicted(`id_ex_instr`, `ctr`); set `if_id_instr` to if `flush`, then 0, otherwise `instr`; set `id_ex_instr` to if `flush`, then 0, otherwise `if_id_instr`; set `forward` to hazard(`if_id_instr`, `id_ex_instr`); set `result_reg` to execute(`id_ex_instr`, if `forward`, then `result_reg`, otherwise `regfile_1`, `regfile_2`); set `PC` to if `flush`, then branch_target(`id_ex_instr`, `PC`), otherwise if is_branch(`if_id_instr`) and predict_taken(`if_id_instr`, `ctr`), then branch_target(`if_id_instr`, `PC`), otherwise `PC` + 4; set `ctr` to if is_branch(`id_ex_instr`), then if `ctr` < 3, then `ctr` + 1, otherwise `ctr`, otherwise `ctr`.

## Properties

- **fetch_latches** (transition): after each step, `if_id_instr` equals if prev(flush), then 0, otherwise instr.
- **decode_latches** (transition): after each step, `id_ex_instr` equals if prev(flush), then 0, otherwise prev(if_id_instr).
- **hazard_detected** (transition): after each step, `forward` equals hazard(prev(if_id_instr), prev(id_ex_instr)).
- **forward_uses_prev_result** (transition): after each step, if prev(forward), then `result_reg` equals execute(prev(id_ex_instr), prev(result_reg), prev(regfile_2)).
- **no_forward_uses_regfile** (transition): after each step, if not (prev(forward)), then `result_reg` equals execute(prev(id_ex_instr), prev(regfile_1), prev(regfile_2)).
- **branch_detected** (combinational): for all inputs, is_branch(instr) equals instr[6:0] equals 99.
- **pc_predicts** (transition): after each step, `PC` equals if prev(flush), then branch_target(prev(id_ex_instr), prev(PC)), otherwise if is_branch(prev(if_id_instr)) and predict_taken(prev(if_id_instr), prev(ctr)), then branch_target(prev(if_id_instr), prev(PC)), otherwise prev(PC) + 4.
- **ctr_bounded** (safety): always, `ctr` ≤ 3.
- **flush_detected** (transition): after each step, `flush` equals mispredicted(prev(id_ex_instr), prev(ctr)).
- **flush_clears_fetch** (transition): after each step, if prev(flush), then `if_id_instr` equals 0.
- **flush_clears_decode** (transition): after each step, if prev(flush), then `id_ex_instr` equals 0.
- **flush_redirects_pc** (transition): after each step, if prev(flush), then `PC` equals branch_target(prev(id_ex_instr), prev(PC)).
- **pc_nonneg_after_3** (bounded): `PC` ≥ 0.
- **pc_self** (safety): always, `PC` equals `PC`.
- **regfile_0_self** (safety): always, `regfile_0` equals `regfile_0`.
- **regfile_1_self** (safety): always, `regfile_1` equals `regfile_1`.
- **regfile_2_self** (safety): always, `regfile_2` equals `regfile_2`.
- **regfile_3_self** (safety): always, `regfile_3` equals `regfile_3`.
- **result_reg_self** (safety): always, `result_reg` equals `result_reg`.
- **PC_nonneg** (safety): always, `PC` ≥ 0.
- **regfile_0_const** (invariant): always, `regfile_0` equals 0.
- **regfile_1_const** (invariant): always, `regfile_1` equals 0.
- **regfile_2_const** (invariant): always, `regfile_2` equals 0.
- **regfile_3_const** (invariant): always, `regfile_3` equals 0.
