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
- **fsm_state_self** (safety): always, `fsm_state` equals `fsm_state`.
- **sample_cnt_nonneg** (safety): always, `sample_cnt` ≥ 0.
- **bit_cnt_nonneg** (safety): always, `bit_cnt` ≥ 0.
- **rx_shift_self** (safety): always, `rx_shift` equals `rx_shift`.
- **rx_prev_bool** (safety): always, `rx_prev` equals true or `rx_prev` equals false.
- **data_out_reg_self** (safety): always, `data_out_reg` equals `data_out_reg`.
- **data_valid_reg_bool** (safety): always, `data_valid_reg` equals true or `data_valid_reg` equals false.
