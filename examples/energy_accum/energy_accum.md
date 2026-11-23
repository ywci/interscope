# energy_accum specification

## Inputs

| Name | Type |
|------|------|
| `valid` | bool |
| `sample` | bits<8> |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `energy` | register | bits<32> | 0 |

## Behavior (rules)

- **measure** — when valid, set `energy` to square(sample).

## Properties

- **energy_squares_sample** (transition): after each step, `energy` equals square(prev(sample)).
- **energy_equals_sample_squared** (safety): always, `energy` equals square(sample).
