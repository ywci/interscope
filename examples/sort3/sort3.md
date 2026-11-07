# sort3 specification

## Inputs

| Name | Type |
|------|------|
| `a_in` | bits<8> |
| `b_in` | bits<8> |
| `c_in` | bits<8> |
| `load` | bool |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `lo` | register | bits<8> | 0 |
| `mid` | register | bits<8> | 0 |
| `hi` | register | bits<8> | 0 |

## Behavior (rules)

- **sort** — when load, set `lo` to min3(a_in, b_in, c_in); set `mid` to mid3(a_in, b_in, c_in); set `hi` to max3(a_in, b_in, c_in).

## Properties

- **sorted** (safety): always, `lo` ≤ `mid` and `mid` ≤ `hi`.
- **permutation_sum** (transition): after each step, `lo` + `mid` + `hi` equals a_in + b_in + c_in.
- **lo_min3** (transition): after each step, `lo` equals min3(a_in, b_in, c_in).
- **mid_mid3** (transition): after each step, `mid` equals mid3(a_in, b_in, c_in).
- **hi_max3** (transition): after each step, `hi` equals max3(a_in, b_in, c_in).
