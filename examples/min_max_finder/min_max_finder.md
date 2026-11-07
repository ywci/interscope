# min_max_finder specification

## Inputs

| Name | Type |
|------|------|
| `valid` | bool |
| `data` | bits<8> |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `min_val` | register | bits<8> | 0 |
| `max_val` | register | bits<8> | 0 |
| `first` | register | bool | true |
| `count` | register | bits<8> | 0 |

## Behavior (rules)

- **update** — when valid, set `min_val` to if `first`, then data, otherwise if data < `min_val`, then data, otherwise `min_val`; set `max_val` to if `first`, then data, otherwise if data > `max_val`, then data, otherwise `max_val`; set `count` to `count` + 1; set `first` to false.

## Properties

- **min_le_max** (safety): always, `min_val` ≤ `max_val`.
- **count_nonneg** (safety): always, `count` ≥ 0.
