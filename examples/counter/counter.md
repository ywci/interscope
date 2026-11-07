# counter specification

## Inputs

| Name | Type |
|------|------|
| `inc` | bool |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `count` | register | bits<4> | 0 |
| `overflow_flag` | register | bool | false |

## Behavior (rules)

- **increment** — when inc and `count` < 15, set `count` to `count` + 1; set `overflow_flag` to `count` equals 15.

## Properties

- **counter_bound** (safety): always, `count` ≤ 15.
- **no_overflow_when_not_full** (safety): always, if not (`count` equals 15), then not (`overflow_flag`).
- **count_increments** (transition): after each step, `count` equals prev(count) + 1 and `overflow_flag` equals prev(count) equals 15.
