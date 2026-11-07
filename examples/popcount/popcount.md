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

- **count_le_index** (safety): always, `count` ≤ `index`.
- **count_nonneg** (safety): always, `count` ≥ 0.
