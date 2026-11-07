# majority_voter specification

## Inputs

| Name | Type |
|------|------|
| `a` | bool |
| `b` | bool |
| `c` | bool |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `x` | register | bool | false |
| `y` | register | bool | false |
| `z` | register | bool | false |
| `maj` | register | bool | false |

## Behavior (rules)

- **vote** — when true, set `x` to a; set `y` to b; set `z` to c; set `maj` to a and b or b and c or a and c.

## Properties

- **maj_implies_x_or_y** (safety): always, if `maj`, then `x` or `y`.
- **maj_correct** (transition): after each step, `maj` equals majority(a, b, c).
