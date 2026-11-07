# fifo specification

## Inputs

| Name | Type |
|------|------|
| `data_in` | bits<32> |
| `write_en` | bool |
| `read_en` | bool |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `mem` | memory | memory(bits<32>, 8) |  |
| `write_ptr` | register | bits<3> | 0 |
| `read_ptr` | register | bits<3> | 0 |
| `count` | register | bits<4> | 0 |
| `data_out` | register | bits<32> | 0 |
| `full` | register | bool | false |
| `empty` | register | bool | true |

## Behavior (rules)

- **write** — when write_en and `count` < 8, mem_write(mem, `write_ptr`, data_in); set `write_ptr` to `write_ptr` + 1; set `count` to `count` + 1.
- **read** — when read_en and `count` > 0, set `data_out` to mem_read(mem, `read_ptr`); set `read_ptr` to `read_ptr` + 1; set `count` to `count` − 1.
- **update_flags** — when true, set `full` to `count` equals 8; set `empty` to `count` equals 0.

## Properties

- **no_overflow** (safety): always, if write_en and `full`, then false.
- **no_underflow** (safety): always, if read_en and `empty`, then false.
- **count_bound** (safety): always, `count` ≥ 0 and `count` ≤ 8.
- **fifo_bound** (safety): always, `count` ≥ 0 and `count` ≤ 8.
- **write_ptr_self** (safety): always, `write_ptr` equals `write_ptr`.
- **read_ptr_self** (safety): always, `read_ptr` equals `read_ptr`.
- **full_is_bool** (safety): always, `full` equals true or `full` equals false.
- **empty_is_bool** (safety): always, `empty` equals true or `empty` equals false.
- **write_ptr_nonneg** (safety): always, `write_ptr` ≥ 0.
- **read_ptr_nonneg** (safety): always, `read_ptr` ≥ 0.
