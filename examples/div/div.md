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

- **done_implies_remainder_equals_rem** (safety): always, if done, then remainder equals `rem`.
- **done_implies_quotient_equals_quot** (safety): always, if done, then quotient equals `quot`.
- **done_implies_count_zero** (safety): always, if done, then `count` equals 0.
- **remainder_lt_divisor** (safety): always, if `divisor_reg` > 0, then `rem` < `divisor_reg`.
- **divider_loads_operands** (transition): after each step, `rem` equals 0 and `quot` equals prev(dividend) and `divisor_reg` equals prev(divisor) and `dividend_init` equals prev(dividend) and `count` equals 16 and done equals false.
- **remainder_subtracts_divisor** (transition): after each step, `rem` equals prev(rem) × 2 + prev(quot)[15:15] − prev(divisor_reg) and `quot` equals prev(quot) × 2 + 1 and `count` equals prev(count) − 1.
- **remainder_shifts_left** (transition): after each step, `rem` equals prev(rem) × 2 + prev(quot)[15:15] and `quot` equals prev(quot) × 2 and `count` equals prev(count) − 1.
- **division_finalizes_result** (transition): after each step, done equals true and quotient equals prev(quot) and remainder equals prev(rem).
