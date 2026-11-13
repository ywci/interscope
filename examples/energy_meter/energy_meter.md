# energy_meter specification

## Inputs

| Name | Type |
|------|------|
| `valid` | bool |
| `sample` | bits<8> |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `energy` | register | bits<16> | 0 |

## Behavior (rules)

- **measure** — when valid, .

## Properties

- **energy_bounded** (combinational): for all inputs, square(sample) ≤ 65025 equals t.
