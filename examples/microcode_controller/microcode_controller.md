# microcode_controller specification

## Inputs

| Name | Type |
|------|------|
| `start` | bool |
| `all_idle` | bool |
| `ucode_opcode` | bits<3> |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `pc` | register | bits<4> | 0 |
| `running` | register | bool | false |
| `opcode_out` | register | bits<3> | 0 |

## Behavior (rules)

- **start_fetch** — when start and not (`running`), set `running` to true; set `pc` to 0.
- **decode** — when `running`, set `opcode_out` to ucode_opcode.
- **advance** — when `running` and all_idle, set `pc` to min(`pc` + 1, 15).
- **finish** — when `running` and `pc` equals 15, set `running` to false.

## Properties

- **pc_bounded** (safety): always, `pc` ≤ 15.
- **pc_nonneg** (safety): always, `pc` ≥ 0.
