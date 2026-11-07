# fetch_comp specification

## Inputs

| Name | Type |
|------|------|
| `stall` | bool |
| `taken` | bool |
| `branch_target` | bits<4> |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `pc` | register | bits<4> | 0 |
| `bpu_ctr` | register | bits<2> | 1 |
| `bpu_predict` | register | bool | false |

## Behavior (rules)

- **advance** — when true, set `pc` to if stall, then `pc`, otherwise if `bpu_predict`, then branch_target, otherwise `pc` + 1.
- **bpu_update** — when true, set `bpu_ctr` to if taken, then if `bpu_ctr` < 3, then `bpu_ctr` + 1, otherwise 3, otherwise if `bpu_ctr` > 0, then `bpu_ctr` − 1, otherwise 0; set `bpu_predict` to `bpu_ctr` ≥ 2.

## Properties

- **pc_nonneg** (safety): always, `pc` ≥ 0.
