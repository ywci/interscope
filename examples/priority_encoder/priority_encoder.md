# priority_encoder specification

## Inputs

| Name | Type |
|------|------|
| `data` | bits<8> |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `enc` | register | bits<3> | 0 |
| `valid` | register | bool | false |

## Behavior (rules)

- **encode** — when true, set `enc` to if `data`[7:7] equals 1, then 7, otherwise if `data`[6:6] equals 1, then 6, otherwise if `data`[5:5] equals 1, then 5, otherwise if `data`[4:4] equals 1, then 4, otherwise if `data`[3:3] equals 1, then 3, otherwise if `data`[2:2] equals 1, then 2, otherwise if `data`[1:1] equals 1, then 1, otherwise if `data`[0:0] equals 1, then 0, otherwise 0; set `valid` to `data` does not equal 0.

## Properties

- **enc_in_range** (safety): always, `enc` ≥ 0 and `enc` ≤ 7.
- **valid_is_bool** (safety): always, `valid` equals true or `valid` equals false.
- **enc_correct** (transition): after each step, `enc` equals prio_enc(data) and `valid` equals data does not equal 0.
