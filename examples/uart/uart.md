# uart specification

## Inputs

| Name | Type |
|------|------|
| `rx` | bool |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `fsm_state` | register | bits<2> | 0 |
| `sample_cnt` | register | bits<3> | 0 |
| `bit_cnt` | register | bits<3> | 0 |
| `rx_shift` | register | bits<8> | 0 |
| `rx_prev` | register | bool | true |
| `data_out_reg` | register | bits<8> | 0 |
| `data_valid_reg` | register | bool | false |

## Behavior (rules)

- **edge_detect** — when true, set `rx_prev` to `rx`.
- **detect_start** — when `fsm_state` equals 0 and not (`rx`) and `rx_prev`, set `fsm_state` to 1; set `sample_cnt` to 0; set `bit_cnt` to 0; set `data_valid_reg` to false.
- **verify_start** — when `fsm_state` equals 1 and `sample_cnt` equals 2, set `fsm_state` to if not (`rx`), then 2, otherwise 0; set `sample_cnt` to 0.
- **sample_data** — when `fsm_state` equals 2 and `sample_cnt` equals 2, set `rx_shift` to `rx_shift`[6:0] × 2 + if `rx`, then 1, otherwise 0; set `bit_cnt` to `bit_cnt` + 1; set `fsm_state` to if `bit_cnt` equals 7, then 3, otherwise 2; set `sample_cnt` to 0.
- **sample_stop** — when `fsm_state` equals 3 and `sample_cnt` equals 2, set `data_out_reg` to `rx_shift`; set `data_valid_reg` to `rx`; set `fsm_state` to 0; set `sample_cnt` to 0.
- **inc_sample** — when not (`fsm_state` equals 1 and `sample_cnt` equals 2 or `fsm_state` equals 2 and `sample_cnt` equals 2 or `fsm_state` equals 3 and `sample_cnt` equals 2), set `sample_cnt` to `sample_cnt` + 1.

## Properties

- **valid_pulse** (safety): always, if `data_valid_reg`, then `fsm_state` equals 0.
- **data_out_equals_rx_shift** (safety): always, `data_out_reg` equals `rx_shift`.
- **rx_prev_bool** (safety): always, `rx_prev` equals true or `rx_prev` equals false.
- **data_valid_reg_bool** (safety): always, `data_valid_reg` equals true or `data_valid_reg` equals false.
- **rx_edge_sampled** (transition): after each step, `rx_prev` equals prev(rx).
- **start_bit_detected** (transition): after each step, `fsm_state` equals 1 and `sample_cnt` equals 0 and `bit_cnt` equals 0 and `data_valid_reg` equals false.
- **start_bit_verified** (transition): after each step, `fsm_state` equals if not (prev(rx)), then 2, otherwise 0 and `sample_cnt` equals 0.
- **data_bit_sampled** (transition): after each step, `rx_shift` equals prev(rx_shift)[6:0] × 2 + if prev(rx), then 1, otherwise 0 and `bit_cnt` equals prev(bit_cnt) + 1 and `fsm_state` equals if prev(bit_cnt) equals 7, then 3, otherwise 2 and `sample_cnt` equals 0.
- **stop_bit_sampled** (transition): after each step, `data_out_reg` equals prev(rx_shift) and `data_valid_reg` equals prev(rx) and `fsm_state` equals 0 and `sample_cnt` equals 0.
- **sample_counter_increments** (transition): after each step, `sample_cnt` equals prev(sample_cnt) + 1.
