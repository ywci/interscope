# fsm_done specification

## Inputs

| Name | Type |
|------|------|
| `start` | bool |
| `a` | bits<8> |
| `b` | bits<8> |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `fsm` | register | bits<2> | 0 |
| `done` | register | bool | false |

## Behavior (rules)

- **start_go** — when start and not (`done`), set `fsm` to 1.
- **tick** — when not (start) and `fsm` < 3, set `fsm` to `fsm` + 1.
- **update_done** — when true, set `done` to `fsm` equals 3.

## Properties

- **done_implies_complete** (safety): always, if `done`, then `fsm` equals 3.
