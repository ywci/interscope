# mac specification

## Inputs

| Name | Type |
|------|------|
| `a` | bits<8> |
| `b` | bits<8> |
| `enable` | bool |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `acc` | register | bits<32> | 0 |

## Behavior (rules)

- **accumulate** — when enable, set `acc` to `acc` + `a` × `b`; set `acc_out` to `acc` + `a` × `b`.

## Properties

- **acc_nonneg** (safety): always, `acc` ≥ 0.
- **accumulate_mac** (transition): after each step, `acc` equals prev(acc) + a × b.
- **acc_monotonic** (transition): after each step, `acc` ≥ prev(acc).
