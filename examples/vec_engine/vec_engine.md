# vec_engine specification

## Inputs

| Name | Type |
|------|------|
| `op` | bits<2> |
| `a` | bits<8> |
| `b` | bits<8> |
| `valid` | bool |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `out` | register | bits<32> | 0 |
| `mac_acc` | register | bits<32> | 0 |
| `mac_acc_out` | register | bits<32> | 0 |

## Behavior (rules)

- **compute** — when valid, set `out` to clamp8(if op equals 0, then a + b, otherwise `mac_acc_out`).
- **mac_unit_accumulate** — when valid, set `mac_acc` to `mac_acc` + `a` × `b`; set `mac_acc_out` to `mac_acc` + `a` × `b`.

## Properties

- **out_bounded** (safety): always, `out` ≤ 255.
- **out_nonneg** (safety): always, `out` ≥ 0.
