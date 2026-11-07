# acc specification

## Inputs

| Name | Type |
|------|------|
| `data_in` | bits<32> |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `acc` | register | bits<32> | 0 |
| `tmp` | register | bits<32> | 0 |
| `stage1_val` | register | bits<32> | 0 |
| `stage1_valid` | register | bool | false |
| `stage2_val` | register | bits<32> | 0 |
| `stage2_valid` | register | bool | false |
| `fwd_val` | register | bits<32> | 0 |
| `fwd_valid` | register | bool | false |

## Behavior (rules)

- **stage1** — when true, set `stage1_valid` to true; set `stage1_val` to if `fwd_valid`, then `fwd_val`, otherwise `data_in`; set `fwd_valid` to false.
- **stage2** — when `stage1_valid`, set `stage2_valid` to true; set `stage2_val` to `acc` + `stage1_val`; set `fwd_valid` to true; set `fwd_val` to `acc` + `stage1_val`; set `stage1_valid` to false.
- **stage3** — when `stage2_valid`, set `acc` to `stage2_val`; set `tmp` to `stage2_val`; set `stage2_valid` to false.

## Properties

- **result_nonneg** (safety): always, `tmp` ≥ 0.
- **acc_nonneg** (safety): always, `acc` ≥ 0.
