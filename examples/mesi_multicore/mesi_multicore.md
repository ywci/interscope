# mesi_multicore specification

## Inputs

| Name | Type |
|------|------|
| `req_addr` | bits<4> |
| `req_data` | bits<8> |
| `req_write` | bool |
| `req_core` | bits<4> |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `c0_state` | register | bits<2> | 0 |
| `c0_addr` | register | bits<4> | 0 |
| `c0_data` | register | bits<8> | 0 |
| `c1_state` | register | bits<2> | 0 |
| `c1_addr` | register | bits<4> | 0 |
| `c1_data` | register | bits<8> | 0 |
| `mem` | memory | memory(bits<8>, 16) |  |

## Behavior (rules)

- **c0_write** — when req_core equals 0 and req_write, set `c0_state` to if has_line(`c0_state`, `c0_addr`, req_addr) and 0 does not equal 0, then 0, otherwise `c0_state`; set `c1_state` to if has_line(`c1_state`, `c1_addr`, req_addr) and 1 does not equal 0, then 0, otherwise `c1_state`; set `c0_state` to 3; set `c0_addr` to req_addr; set `c0_data` to req_data.
- **c0_read_hit** — when req_core equals 0 and not (req_write) and has_line(`c0_state`, `c0_addr`, req_addr), set `c0_state` to `c0_state`.
- **c0_read_miss** — when req_core equals 0 and not (req_write) and not (has_line(`c0_state`, `c0_addr`, req_addr)), set `c0_state` to if has_line(`c0_state`, `c0_addr`, req_addr) and 0 does not equal 0, then 1, otherwise `c0_state`; set `c1_state` to if has_line(`c1_state`, `c1_addr`, req_addr) and 1 does not equal 0, then 1, otherwise `c1_state`; set `c0_state` to if false or has_line(`c0_state`, `c0_addr`, req_addr) or has_line(`c1_state`, `c1_addr`, req_addr), then 1, otherwise 2; set `c0_addr` to req_addr; set `c0_data` to if is_modified(`c1_state`) and has_line(`c1_state`, `c1_addr`, req_addr), then `c1_data`, otherwise if is_modified(`c0_state`) and has_line(`c0_state`, `c0_addr`, req_addr), then `c0_data`, otherwise mem_read(mem, req_addr).
- **c1_write** — when req_core equals 1 and req_write, set `c0_state` to if has_line(`c0_state`, `c0_addr`, req_addr) and 0 does not equal 1, then 0, otherwise `c0_state`; set `c1_state` to if has_line(`c1_state`, `c1_addr`, req_addr) and 1 does not equal 1, then 0, otherwise `c1_state`; set `c1_state` to 3; set `c1_addr` to req_addr; set `c1_data` to req_data.
- **c1_read_hit** — when req_core equals 1 and not (req_write) and has_line(`c1_state`, `c1_addr`, req_addr), set `c1_state` to `c1_state`.
- **c1_read_miss** — when req_core equals 1 and not (req_write) and not (has_line(`c1_state`, `c1_addr`, req_addr)), set `c0_state` to if has_line(`c0_state`, `c0_addr`, req_addr) and 0 does not equal 1, then 1, otherwise `c0_state`; set `c1_state` to if has_line(`c1_state`, `c1_addr`, req_addr) and 1 does not equal 1, then 1, otherwise `c1_state`; set `c1_state` to if false or has_line(`c0_state`, `c0_addr`, req_addr) or has_line(`c1_state`, `c1_addr`, req_addr), then 1, otherwise 2; set `c1_addr` to req_addr; set `c1_data` to if is_modified(`c1_state`) and has_line(`c1_state`, `c1_addr`, req_addr), then `c1_data`, otherwise if is_modified(`c0_state`) and has_line(`c0_state`, `c0_addr`, req_addr), then `c0_data`, otherwise mem_read(mem, req_addr).

## Properties

- **single_writer** (safety): always, not (is_modified(`c0_state`) and is_modified(`c1_state`) and `c0_addr` equals `c1_addr`).
- **m_exclusive** (safety): always, not (is_modified(`c0_state`) and has_line(`c1_state`, `c1_addr`, `c0_addr`)) and not (is_modified(`c1_state`) and has_line(`c0_state`, `c0_addr`, `c1_addr`)).
- **e_exclusive** (safety): always, not (is_exclusive(`c0_state`) and has_line(`c1_state`, `c1_addr`, `c0_addr`)) and not (is_exclusive(`c1_state`) and has_line(`c0_state`, `c0_addr`, `c1_addr`)).
- **state_valid_c0** (safety): always, `c0_state` ≥ 0 and `c0_state` ≤ 3.
- **c0_write_invalidates_c1** (transition): after each step, if has_line(prev(c1_state), prev(c1_addr), req_addr), then `c1_state` equals 0.
