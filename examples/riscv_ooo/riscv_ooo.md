# riscv_ooo specification

## Inputs

| Name | Type |
|------|------|
| `instr` | bits<32> |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `rob0_instr` | register | bits<32> | 0 |
| `rob0_valid` | register | bool | false |
| `rob0_done` | register | bool | false |
| `rob1_instr` | register | bits<32> | 0 |
| `rob1_valid` | register | bool | false |
| `rob1_done` | register | bool | false |
| `head` | register | bool | false |
| `tail` | register | bool | false |
| `arch` | register | bits<32> | 0 |
| `PC` | register | bits<32> | 0 |
| `ctr` | register | bits<2> | 0 |
| `flush` | register | bool | false |

## Behavior (rules)

- **issue0** — when not (`tail`) and not (`flush`), set `rob0_instr` to `instr`; set `rob0_valid` to true; set `rob0_done` to false; set `tail` to true; set `PC` to if is_branch(`instr`) and predict_taken(`instr`, `ctr`), then branch_target(`instr`, `PC`), otherwise `PC` + 4.
- **issue1** — when `tail` and not (`flush`), set `rob1_instr` to `instr`; set `rob1_valid` to true; set `rob1_done` to false; set `tail` to false; set `PC` to if is_branch(`instr`) and predict_taken(`instr`, `ctr`), then branch_target(`instr`, `PC`), otherwise `PC` + 4.
- **exec0** — when `rob0_valid` and not (`rob0_done`), set `rob0_done` to true.
- **exec1** — when `rob1_valid` and not (`rob1_done`), set `rob1_done` to true.
- **commit0** — when not (`head`) and `rob0_valid` and `rob0_done`, set `arch` to `rob0_instr`; set `rob0_valid` to false; set `head` to true; set `flush` to mispredicted(`rob0_instr`, `ctr`); set `ctr` to if is_branch(`rob0_instr`), then if `ctr` < 3, then `ctr` + 1, otherwise `ctr`, otherwise `ctr`.
- **commit1** — when `head` and `rob1_valid` and `rob1_done`, set `arch` to `rob1_instr`; set `rob1_valid` to false; set `head` to false; set `flush` to mispredicted(`rob1_instr`, `ctr`); set `ctr` to if is_branch(`rob1_instr`), then if `ctr` < 3, then `ctr` + 1, otherwise `ctr`, otherwise `ctr`.
- **recover** — when `flush`, set `flush` to false; set `rob1_valid` to false; set `rob0_valid` to if `head`, then `rob0_valid`, otherwise false.

## Properties

- **head_bool** (safety): always, `head` equals true or `head` equals false.
- **tail_bool** (safety): always, `tail` equals true or `tail` equals false.
- **ctr_bounded** (safety): always, `ctr` ≤ 3.
- **exec1_independent** (transition): after each step, `rob1_done` equals true.
- **commit_in_order** (transition): after each step, prev(head) equals true.
- **branch_detected** (combinational): for all inputs, is_branch(instr) equals instr[6:0] equals 99.
- **flush_detected** (transition): after each step, `flush` equals mispredicted(prev(rob0_instr), prev(ctr)).
