# calculator specification

## Inputs

| Name | Type |
|------|------|
| `opcode` | bits<2> |
| `data_in` | bits<8> |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `sp` | register | bits<4> | 0 |
| `top` | register | bits<8> | 0 |
| `error` | register | bool | false |

## Behavior (rules)

- **execute** — when true, set `top` to if `opcode` equals 0, then data_in, otherwise `top`; set `error` to `opcode` equals 0 and `sp` equals 8 or `opcode` equals 3 and `sp` equals 0 or `opcode` equals 1 or `opcode` equals 2 and `sp` < 2; set `sp` to if `opcode` equals 0, then if `sp` < 8, then `sp` + 1, otherwise `sp`, otherwise if `opcode` equals 3, then if `sp` > 0, then `sp` − 1, otherwise `sp`, otherwise if `opcode` equals 1 or `opcode` equals 2, then if `sp` ≥ 2, then `sp` − 1, otherwise `sp`, otherwise `sp`.

## Properties

- **sp_in_range** (safety): always, `sp` ≥ 0 and `sp` ≤ 8.
- **error_is_bool** (safety): always, `error` equals true or `error` equals false.
- **error_on_push_full** (transition): after each step, if opcode equals 0 and prev(sp) equals 8, then `error` equals true.
- **error_on_pop_empty** (transition): after each step, if opcode equals 3 and prev(sp) equals 0, then `error` equals true.
