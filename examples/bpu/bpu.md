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
- **predict_equals_taken_threshold** (safety): always, `predict` equals `ctr` ≥ 2.
- **predictor_tracks_taken** (transition): after each step, `ctr` equals if taken, then if prev(ctr) < 3, then prev(ctr) + 1, otherwise 3, otherwise if prev(ctr) > 0, then prev(ctr) − 1, otherwise 0 and `predict` equals prev(ctr) ≥ 2.
