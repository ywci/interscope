# buffer_chain specification

## Inputs

| Name | Type |
|------|------|
| `d0` | bits<4> |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `wire0` | register | bits<4> |  |
| `out1` | register | bits<4> |  |

## Behavior (rules)

- **bufA_update** — when true, set `wire0` to d0.
- **bufB_update** — when true, set `out1` to wire0.

## Properties

- **bufA_passes_d0** (transition): after each step, `wire0` equals d0.
- **bufB_passes_wire0** (transition): after each step, `out1` equals prev(wire0).
- **bufA_q_nonneg** (safety): always, `wire0` ≥ 0.
- **bufA_q_passes_d** (transition): after each step, `wire0` equals d0.
- **bufB_q_nonneg** (safety): always, `out1` ≥ 0.
- **bufB_q_passes_d** (transition): after each step, `out1` equals wire0.
