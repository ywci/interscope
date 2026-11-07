# buffer specification

## Inputs

| Name | Type |
|------|------|
| `d` | bits<4> |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `q` | register | bits<4> | 0 |

## Behavior (rules)

- **update** — when true, set `q` to d.

## Properties

- **q_nonneg** (safety): always, `q` ≥ 0.
- **q_passes_d** (transition): after each step, `q` equals d.
