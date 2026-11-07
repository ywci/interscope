# fir specification

## Inputs

| Name | Type |
|------|------|
| `data_in` | bits<16> |
| `valid_in` | bool |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `shift0` | register | bits<16> | 0 |
| `shift1` | register | bits<16> | 0 |
| `shift2` | register | bits<16> | 0 |
| `shift3` | register | bits<16> | 0 |
| `coeff0` | register | bits<16> | 0 |
| `coeff1` | register | bits<16> | 0 |
| `coeff2` | register | bits<16> | 0 |
| `coeff3` | register | bits<16> | 0 |
| `acc` | register | bits<16> | 0 |
| `valid_pipe` | register | bool | false |

## Behavior (rules)

- **shift_and_mac** — when valid_in, set `shift3` to `shift2`; set `shift2` to `shift1`; set `shift1` to `shift0`; set `shift0` to data_in; set `acc` to `shift0` × `coeff0` + `shift1` × `coeff1` + `shift2` × `coeff2` + `shift3` × `coeff3`; set `valid_pipe` to true.
- **bypass** — when not (valid_in), set `valid_pipe` to false.

## Properties

- **acc_bounded** (safety): always, `acc` ≥ 0 and `acc` ≤ 65535.
