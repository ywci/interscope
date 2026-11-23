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

- **push** — when push and `sp` < 8, mem_write(mem, `sp`[2:0], data_in); set `sp` to `sp` + 1.
- **pop** — when pop and `sp` > 0, set `data_out` to mem_read(mem, `sp` − 1[2:0]); set `sp` to `sp` − 1.
- **update_flags** — when true, set `full` to `sp` equals 8; set `empty` to `sp` equals 0.

## Properties

- **full_iff_sp_eq_depth** (safety): always, full equals `sp` equals 8.
- **push_increments** (transition): after each step, `sp` equals prev(sp) + 1.
- **pop_decrements** (transition): after each step, `sp` equals prev(sp) − 1.
- **flags_track_sp** (transition): after each step, full equals prev(sp) equals 8 and empty equals prev(sp) equals 0.
- **pop_returns_data** (transition): after each step, `data_out` equals mem_read(mem, prev(sp) − 1[2:0]).
