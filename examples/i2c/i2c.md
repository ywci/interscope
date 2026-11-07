# i2c_master specification

## Inputs

| Name | Type |
|------|------|
| `start` | bool |
| `data_in` | bits<8> |
| `sda_in` | bool |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `fsm_state` | register | bits<3> | 0 |
| `bit_idx` | register | bits<3> | 0 |
| `shift_reg` | register | bits<8> | 0 |
| `clk_div` | register | bits<2> | 0 |
| `scl_reg` | register | bool | true |
| `sda_reg` | register | bool | true |
| `done_reg` | register | bool | false |
| `error_reg` | register | bool | false |
| `busy_reg` | register | bool | false |

## Behavior (rules)

- **idle** — when `fsm_state` equals 0, set `busy_reg` to false; set `done_reg` to false; set `error_reg` to false; set `scl_reg` to true; set `sda_reg` to true; set `clk_div` to 0; set `bit_idx` to 0; set `fsm_state` to if `start`, then 1, otherwise 0.
- **start_cond** — when `fsm_state` equals 1, set `sda_reg` to false; set `scl_reg` to true; set `busy_reg` to true; set `shift_reg` to `data_in`; set `bit_idx` to 0; set `fsm_state` to 2.
- **send** — when `fsm_state` equals 2, set `clk_div` to `clk_div` + 1; set `scl_reg` to if `clk_div` equals 0, then false, otherwise if `clk_div` equals 2, then true, otherwise `scl_reg`; set `sda_reg` to if `clk_div` equals 1, then `shift_reg`[7:7] equals 1, otherwise `sda_reg`; set `shift_reg` to if `clk_div` equals 3, then `shift_reg` + `shift_reg`, otherwise `shift_reg`; set `bit_idx` to if `clk_div` equals 3, then `bit_idx` + 1, otherwise `bit_idx`; set `fsm_state` to if `bit_idx` equals 7, then 3, otherwise 2.
- **ack** — when `fsm_state` equals 3, set `scl_reg` to false; set `sda_reg` to true; set `clk_div` to `clk_div` + 1; set `error_reg` to if `clk_div` equals 1 and not (`sda_in`), then false, otherwise if `clk_div` equals 1 and `sda_in`, then true, otherwise `error_reg`; set `fsm_state` to if `clk_div` equals 3 and not (`error_reg`), then 4, otherwise if `clk_div` equals 3 and `error_reg`, then 4, otherwise 3.
- **stop** — when `fsm_state` equals 4, set `scl_reg` to true; set `sda_reg` to true; set `done_reg` to true; set `busy_reg` to false; set `fsm_state` to 0.

## Properties

- **bus_idle_high** (safety): always, if `fsm_state` equals 0, then `scl_reg` and `sda_reg`.
- **start_condition** (safety): always, if `fsm_state` equals 1, then `scl_reg` and not (`sda_reg`).
- **stop_condition** (safety): always, if `fsm_state` equals 4, then `scl_reg` and `sda_reg`.
- **busy_when_not_idle** (safety): always, if `fsm_state` does not equal 0, then `busy_reg`.
- **done_after_stop** (safety): always, if `fsm_state` equals 0, then not (`done_reg`) or `start` equals 0.
- **state_in_range** (safety): always, `fsm_state` ≥ 0 and `fsm_state` ≤ 4.
- **bit_idx_in_range** (safety): always, `bit_idx` ≥ 0 and `bit_idx` ≤ 7.
