# softmax_engine specification

## Inputs

| Name | Type |
|------|------|
| `x` | bits<8> |
| `valid` | bool |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `row_max` | register | bits<8> | 0 |
| `out` | register | bits<8> | 0 |
| `max_finder_min_val` | register | bits<8> | 0 |
| `max_finder_first` | register | bool | true |
| `max_finder_count` | register | bits<8> | 0 |

## Behavior (rules)

- **shift** — when valid, set `out` to min(x − `row_max`, 255).
- **max_finder_update** — when valid, set `max_finder_min_val` to if `max_finder_first`, then x, otherwise if x < `max_finder_min_val`, then x, otherwise `max_finder_min_val`; set `row_max` to if `max_finder_first`, then x, otherwise if x > `row_max`, then x, otherwise `row_max`; set `max_finder_count` to `max_finder_count` + 1; set `max_finder_first` to false.

## Properties

- **out_bounded** (safety): always, `out` ≤ 255.
- **out_nonneg** (safety): always, `out` ≥ 0.
