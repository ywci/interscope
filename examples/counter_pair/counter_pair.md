# counter_pair specification

## Inputs

| Name | Type |
|------|------|
| `inc_lo` | bool |
| `inc_hi` | bool |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `lo_count` | register | bits<4> | 0 |
| `hi_count` | register | bits<4> | 0 |
| `lo_overflow_flag` | register | bool | false |
| `hi_overflow_flag` | register | bool | false |

## Behavior (rules)

- **lo_increment** — when inc_lo and `lo_count` < 15, set `lo_count` to `lo_count` + 1; set `lo_overflow_flag` to `lo_count` equals 15.
- **hi_increment** — when inc_hi and `hi_count` < 15, set `hi_count` to `hi_count` + 1; set `hi_overflow_flag` to `hi_count` equals 15.

## Properties

- **lo_count_bounded** (safety): always, `lo_count` ≤ 15.
- **hi_count_bounded** (safety): always, `hi_count` ≤ 15.
- **lo_counter_bound** (safety): always, `lo_count` ≤ 15.
- **lo_no_overflow_when_not_full** (safety): always, if not (`lo_count` equals 15), then not (`lo_overflow_flag`).
- **lo_count_increments** (transition): after each step, `lo_count` equals prev(lo_count) + 1 and `lo_overflow_flag` equals prev(lo_count) equals 15.
- **hi_counter_bound** (safety): always, `hi_count` ≤ 15.
- **hi_no_overflow_when_not_full** (safety): always, if not (`hi_count` equals 15), then not (`hi_overflow_flag`).
- **hi_count_increments** (transition): after each step, `hi_count` equals prev(hi_count) + 1 and `hi_overflow_flag` equals prev(hi_count) equals 15.
