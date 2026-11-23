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

- **acc_equals_weighted_sum** (safety): always, `acc` equals `shift0` × `coeff0` + `shift1` × `coeff1` + `shift2` × `coeff2` + `shift3` × `coeff3`.
- **fir_shifts_and_accumulates** (transition): after each step, `shift3` equals prev(shift2) and `shift2` equals prev(shift1) and `shift1` equals prev(shift0) and `shift0` equals data_in and `acc` equals prev(shift0) × prev(coeff0) + prev(shift1) × prev(coeff1) + prev(shift2) × prev(coeff2) + prev(shift3) × prev(coeff3) and `valid_pipe` equals true.
- **pipe_bypasses_when_idle** (transition): after each step, `valid_pipe` equals false.
