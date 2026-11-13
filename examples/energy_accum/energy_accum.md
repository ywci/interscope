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

- **energy_step** (transition): after each step, `energy` equals square(prev(sample)).
- **energy_bounded** (safety): always, `energy` ≤ 65025.
