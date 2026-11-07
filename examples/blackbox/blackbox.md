# blackbox specification

## Inputs

| Name | Type |
|------|------|
| `x` | bits<8> |
| `enable` | bool |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `y` | register | bits<8> | 0 |

## Behavior (rules)

- **activate** — when enable, set `y` to sigmoid(`x`).

## Properties

- **y_bounded** (safety): always, `y` < 256.
- **activate_passes_sigmoid** (transition): after each step, `y` equals sigmoid(x).
