# stack specification

## Inputs

| Name | Type |
|------|------|
| `push` | bool |
| `pop` | bool |
| `data_in` | bits<32> |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `mem` | memory | memory(bits<32>, 8) |  |
| `sp` | register | bits<4> | 0 |
| `data_out` | register | bits<32> | 0 |
| `full` | register | bool | false |
| `empty` | register | bool | true |

## Behavior (rules)

- **push** — when push and `sp` < 8, mem_write(mem, `sp`, data_in); set `sp` to `sp` + 1.
- **pop** — when pop and `sp` > 0, set `data_out` to mem_read(mem, `sp` − 1); set `sp` to `sp` − 1.
- **update_flags** — when true, set `full` to `sp` equals 8; set `empty` to `sp` equals 0.

## Properties

- **sp_in_range** (safety): always, `sp` ≥ 0 and `sp` ≤ 8.
- **full_is_bool** (safety): always, `full` equals true or `full` equals false.
- **empty_is_bool** (safety): always, `empty` equals true or `empty` equals false.
