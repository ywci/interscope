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
- **done_after_stop** (safety): always, if `fsm_state` equals 0, then not (`done_reg`) or start equals 0.
- **controller_idles** (transition): after each step, `busy_reg` equals false and `done_reg` equals false and `error_reg` equals false and `scl_reg` equals true and `sda_reg` equals true and `clk_div` equals 0 and `bit_idx` equals 0 and `fsm_state` equals if prev(start), then 1, otherwise 0.
- **start_condition_driven** (transition): after each step, `sda_reg` equals false and `scl_reg` equals true and `busy_reg` equals true and `shift_reg` equals prev(data_in) and `bit_idx` equals 0 and `fsm_state` equals 2.
- **byte_clocked_out** (transition): after each step, `clk_div` equals prev(clk_div) + 1 and `scl_reg` equals if prev(clk_div) equals 0, then false, otherwise if prev(clk_div) equals 2, then true, otherwise prev(scl_reg) and `sda_reg` equals if prev(clk_div) equals 1, then prev(shift_reg)[7:7] equals 1, otherwise prev(sda_reg) and `shift_reg` equals if prev(clk_div) equals 3, then prev(shift_reg) + prev(shift_reg), otherwise prev(shift_reg) and `bit_idx` equals if prev(clk_div) equals 3, then prev(bit_idx) + 1, otherwise prev(bit_idx) and `fsm_state` equals if prev(bit_idx) equals 7, then 3, otherwise 2.
- **ack_sampled** (transition): after each step, `scl_reg` equals false and `sda_reg` equals true and `clk_div` equals prev(clk_div) + 1 and `error_reg` equals if prev(clk_div) equals 1 and not (prev(sda_in)), then false, otherwise if prev(clk_div) equals 1 and prev(sda_in), then true, otherwise prev(error_reg) and `fsm_state` equals if prev(clk_div) equals 3 and not (prev(error_reg)), then 4, otherwise if prev(clk_div) equals 3 and prev(error_reg), then 4, otherwise 3.
- **stop_condition_driven** (transition): after each step, `scl_reg` equals true and `sda_reg` equals true and `done_reg` equals true and `busy_reg` equals false and `fsm_state` equals 0.
