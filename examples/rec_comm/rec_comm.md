# rec_comm specification

## Inputs

| Name | Type |
|------|------|
| `a` | bits<8> |
| `b` | bits<8> |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `out` | register | bits<8> | 0 |

## Behavior (rules)

- **compute** — when true, .

## Properties

- **rec_commutes** (combinational): for all inputs, rec(a + b, a, b) equals rec(b + a, b, a).
