# sort2 specification

## Inputs

| Name | Type |
|------|------|
| `a_in` | bits<8> |
| `b_in` | bits<8> |
| `load` | bool |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `lo` | register | bits<8> | 0 |
| `hi` | register | bits<8> | 0 |

## Behavior (rules)

- **sort** — when load, set `lo` to if a_in ≤ b_in, then a_in, otherwise b_in; set `hi` to if a_in ≤ b_in, then b_in, otherwise a_in.

## Properties

- **sorted** (safety): always, `lo` ≤ `hi`.
- **lo_hi_correct** (transition): after each step, `lo` equals min2(a_in, b_in) and `hi` equals max2(a_in, b_in).
