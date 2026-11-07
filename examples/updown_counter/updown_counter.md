# updown_counter specification

## Inputs

| Name | Type |
|------|------|
| `load_en` | bool |
| `load_value` | bits<8> |
| `up` | bool |
| `down` | bool |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `count` | register | bits<8> | 0 |
| `max_value` | register | bits<8> | 0 |

## Behavior (rules)

- **load** — when load_en, set `count` to `load_value`; set `max_value` to `load_value`.
- **inc** — when up and not (load_en) and `count` < `max_value`, set `count` to `count` + 1.
- **dec** — when down and not (load_en) and `count` > 0, set `count` to `count` − 1.

## Properties

- **count_le_max** (safety): always, `count` ≤ `max_value`.
- **count_nonneg** (safety): always, `count` ≥ 0.
- **inc_increments** (transition): after each step, `count` equals prev(count) + 1.
- **dec_decrements** (transition): after each step, `count` equals prev(count) − 1.
