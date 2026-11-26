# ashr specification

## Inputs

| Name | Type |
|------|------|
| `x` | bits<8> |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `y` | register | bits<8> | 0 |

## Behavior (rules)

- **shift** — when true, set `y` to ashr(x, 1).
