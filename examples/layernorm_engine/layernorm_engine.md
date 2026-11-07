# layernorm_engine specification

## Inputs

| Name | Type |
|------|------|
| `x` | bits<8> |
| `mean` | bits<8> |
| `inv_std` | bits<8> |
| `beta` | bits<8> |
| `valid` | bool |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `out` | register | bits<8> | 0 |

## Behavior (rules)

- **normalize** — when valid, set `out` to min(x − mean × inv_std + beta, 255).

## Properties

- **out_bounded** (safety): always, `out` ≤ 255.
- **out_nonneg** (safety): always, `out` ≥ 0.
