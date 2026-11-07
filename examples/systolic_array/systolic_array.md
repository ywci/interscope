# systolic_array specification

## Inputs

| Name | Type |
|------|------|
| `a0` | bits<8> |
| `a1` | bits<8> |
| `load_valid` | bool |
| `w_in00` | bits<8> |
| `w_in01` | bits<8> |
| `w_in10` | bits<8> |
| `w_in11` | bits<8> |
| `scale` | bits<8> |
| `shift` | bits<4> |
| `run` | bool |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `w00` | register | bits<8> | 0 |
| `w01` | register | bits<8> | 0 |
| `w10` | register | bits<8> | 0 |
| `w11` | register | bits<8> | 0 |
| `acc0` | register | bits<32> | 0 |
| `acc1` | register | bits<32> | 0 |
| `out0` | register | bits<8> | 0 |
| `out1` | register | bits<8> | 0 |

## Behavior (rules)

- **load_weights** — when load_valid, set `w00` to w_in00; set `w01` to w_in01; set `w10` to w_in10; set `w11` to w_in11.
- **mac_step** — when not (load_valid) and run, set `acc0` to `acc0` + a0 × `w00` + a1 × `w10`; set `acc1` to `acc1` + a0 × `w01` + a1 × `w11`.
- **requantize** — when run, set `out0` to min(`acc0` × scale shifted right by shift, 255); set `out1` to min(`acc1` × scale shifted right by shift, 255).

## Properties

- **acc_nonneg** (safety): always, `acc0` ≥ 0 and `acc1` ≥ 0.
- **mac_step_correct** (transition): after each step, `acc0` equals prev(acc0) + a0 × prev(w00) + a1 × prev(w10).
- **acc_monotonic** (transition): after each step, `acc0` ≥ prev(acc0) and `acc1` ≥ prev(acc1).
- **weights_stationary** (transition): after each step, `w00` equals prev(w00) and `w01` equals prev(w01) and `w10` equals prev(w10) and `w11` equals prev(w11).
- **out_bounded** (safety): always, `out0` ≤ 255 and `out1` ≤ 255.
- **out_nonneg** (safety): always, `out0` ≥ 0 and `out1` ≥ 0.
