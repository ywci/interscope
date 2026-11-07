# saturating_adder specification

## Inputs

| Name | Type |
|------|------|
| `x` | bits<8> |
| `y` | bits<8> |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `result` | register | bits<8> | 0 |
| `overflow` | register | bool | false |

## Behavior (rules)

- **add** — when true, set `result` to if x + y ≥ 256, then 255, otherwise x + y; set `overflow` to x + y ≥ 256.

## Properties

- **result_le_cap** (safety): always, `result` ≤ 255.
- **overflow_is_bool** (safety): always, `overflow` equals true or `overflow` equals false.
- **result_is_min** (transition): after each step, `result` equals saturate(x + y, 255) and `overflow` equals x + y ≥ 256.
