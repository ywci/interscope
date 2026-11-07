# bpu specification

## Inputs

| Name | Type |
|------|------|
| `taken` | bool |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `ctr` | register | bits<2> | 1 |
| `predict` | register | bool | false |

## Behavior (rules)

- **update** — when true, set `ctr` to if taken, then if `ctr` < 3, then `ctr` + 1, otherwise 3, otherwise if `ctr` > 0, then `ctr` − 1, otherwise 0; set `predict` to `ctr` ≥ 2.

## Properties

- **predict_bool** (safety): always, `predict` equals true or `predict` equals false.
- **ctr_bounded** (safety): always, `ctr` ≥ 0 and `ctr` ≤ 3.
