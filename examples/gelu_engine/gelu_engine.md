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

- **out_equals_gelu_x** (safety): always, `out` equals gelu(x).
- **out_applies_gelu** (transition): after each step, `out` equals gelu(x).
