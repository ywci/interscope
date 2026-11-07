# saturating_counter specification

## Inputs

| Name | Type |
|------|------|
| `inc` | bool |
| `dec` | bool |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `count` | register | bits<4> | 0 |

## Behavior (rules)

- **inc_step** — when inc and not (dec), set `count` to if `count` < 8, then `count` + 1, otherwise `count`.
- **dec_step** — when dec and not (inc), set `count` to if `count` > 0, then `count` − 1, otherwise `count`.

## Properties

- **count_in_range** (safety): always, `count` ≥ 0 and `count` ≤ 8.
- **inc_saturates_at_8** (transition): after each step, `count` equals if prev(count) < 8, then prev(count) + 1, otherwise prev(count).
- **dec_saturates_at_0** (transition): after each step, `count` equals if prev(count) > 0, then prev(count) − 1, otherwise prev(count).
