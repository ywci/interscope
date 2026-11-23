# popcount specification

## Inputs

| Name | Type |
|------|------|
| `start` | bool |
| `data` | bits<8> |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `value` | register | bits<8> | 0 |
| `count` | register | bits<4> | 0 |
| `index` | register | bits<4> | 0 |
| `done` | register | bool | false |

## Behavior (rules)

- **load** — when start, set `value` to `data`; set `count` to 0; set `index` to 0; set `done` to false.
- **count_bit** — when not (`done`) and `index` < 8 and mod(`value`, 2) equals 1, set `count` to `count` + 1; set `value` to div(`value`, 2); set `index` to `index` + 1.
- **shift_bit** — when not (`done`) and `index` < 8 and mod(`value`, 2) equals 0, set `value` to div(`value`, 2); set `index` to `index` + 1.
- **finish** — when not (`done`) and `index` ≥ 8, set `done` to true.

## Properties

- **count_le_index** (safety): always, count ≤ `index`.
- **done_iff_index_eq_8** (safety): always, done equals `index` equals 8.
- **popcount_loads_value** (transition): after each step, `value` equals prev(data) and count equals 0 and `index` equals 0 and done equals false.
- **set_bit_counted** (transition): after each step, count equals prev(count) + 1 and `value` equals div(prev(value), 2) and `index` equals prev(index) + 1.
- **clear_bit_shifted** (transition): after each step, `value` equals div(prev(value), 2) and `index` equals prev(index) + 1.
- **popcount_finishes** (transition): after each step, done equals true.
