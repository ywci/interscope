# div specification

## Inputs

| Name | Type |
|------|------|
| `start` | bool |
| `dividend` | bits<16> |
| `divisor` | bits<16> |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `rem` | register | bits<16> | 0 |
| `quot` | register | bits<16> | 0 |
| `divisor_reg` | register | bits<16> | 0 |
| `dividend_init` | register | bits<16> | 0 |
| `count` | register | bits<5> | 0 |
| `done` | register | bool | false |
| `quotient` | register | bits<16> | 0 |
| `remainder` | register | bits<16> | 0 |

## Behavior (rules)

- **load** — when start, set `rem` to 0; set `quot` to `dividend`; set `divisor_reg` to `divisor`; set `dividend_init` to `dividend`; set `count` to 16; set `done` to false.
- **sub_step** — when not (`done`) and `count` > 0 and `rem` × 2 + `quot`[15:15] ≥ `divisor_reg`, set `rem` to `rem` × 2 + `quot`[15:15] − `divisor_reg`; set `quot` to `quot` × 2 + 1; set `count` to `count` − 1.
- **shift_step** — when not (`done`) and `count` > 0 and `rem` × 2 + `quot`[15:15] < `divisor_reg`, set `rem` to `rem` × 2 + `quot`[15:15]; set `quot` to `quot` × 2; set `count` to `count` − 1.
- **finish** — when not (`done`) and `count` equals 0, set `done` to true; set `quotient` to `quot`; set `remainder` to `rem`.

## Properties

- **count_in_range** (safety): always, `count` ≥ 0 and `count` ≤ 16.
- **rem_nonneg** (safety): always, `rem` ≥ 0.
- **quot_nonneg** (safety): always, `quot` ≥ 0.
- **done_implies_count_zero** (safety): always, if `done`, then `count` equals 0.
- **remainder_lt_divisor** (safety): always, if `divisor_reg` > 0, then `rem` < `divisor_reg`.
