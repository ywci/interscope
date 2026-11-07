# fibonacci specification

## Inputs

| Name | Type |
|------|------|
| `advance` | bool |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `fib_prev` | register | bits<16> | 0 |
| `fib_curr` | register | bits<16> | 1 |

## Behavior (rules)

- **advance** — when advance, set `fib_prev` to `fib_curr`; set `fib_curr` to `fib_prev` + `fib_curr`.

## Properties

- **fib_monotonic** (safety): always, `fib_prev` ≤ `fib_curr`.
- **fib_nonneg** (safety): always, `fib_prev` ≥ 0 and `fib_curr` ≥ 0.
- **advance_latches** (transition): after each step, `fib_prev` equals prev(fib_curr).
- **advance_recurrence** (transition): after each step, `fib_curr` equals prev(fib_prev) + prev(fib_curr).
