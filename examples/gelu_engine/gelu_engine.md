# gelu_engine specification

## Inputs

| Name | Type |
|------|------|
| `x` | bits<8> |
| `valid` | bool |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `out` | register | bits<8> | 0 |

## Behavior (rules)

- **compute** — when valid, set `out` to gelu(x).

## Properties

- **out_bounded** (safety): always, `out` ≤ 255.
- **out_nonneg** (safety): always, `out` ≥ 0.
