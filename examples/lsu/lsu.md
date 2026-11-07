# lsu specification

## Inputs

| Name | Type |
|------|------|
| `req_core` | bits<4> |
| `req_write` | bool |
| `req_addr` | bits<4> |
| `req_data` | bits<8> |
| `l1d_is_physical` | bool |
| `l1d_req_data` | bits<8> |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `mem` | memory | memory(bits<8>, 16) |  |
| `resp_data` | register | bits<8> | 0 |
| `resp_valid` | register | bool | false |
| `l1d_s0` | register | bits<2> | 0 |
| `l1d_a0` | register | bits<4> | 0 |
| `l1d_s1` | register | bits<2> | 0 |
| `l1d_a1` | register | bits<4> | 0 |
| `l1d_lru` | register | bool | false |
| `l1d_data0` | register | bits<8> | 0 |
| `l1d_data1` | register | bits<8> | 0 |
| `l1d_rdata` | register | bits<8> | 0 |

## Behavior (rules)

- **store** — when req_core equals 0 and req_write, mem_write(mem, req_addr, req_data); set `resp_valid` to true.
- **load** — when req_core equals 0 and not (req_write), set `resp_data` to mem_read(mem, req_addr); set `resp_valid` to true.
- **l1d_write_hit0** — when req_core equals 0 and req_write and l1d_has_line(`l1d_s0`, `l1d_a0`, req_addr), set `l1d_s0` to 3; set `l1d_data0` to l1d_req_data; set `l1d_lru` to true.
- **l1d_write_hit1** — when req_core equals 0 and req_write and not (l1d_has_line(`l1d_s0`, `l1d_a0`, req_addr)) and l1d_has_line(`l1d_s1`, `l1d_a1`, req_addr), set `l1d_s1` to 3; set `l1d_data1` to l1d_req_data; set `l1d_lru` to false.
- **l1d_write_miss0** — when req_core equals 0 and req_write and not (l1d_has_line(`l1d_s0`, `l1d_a0`, req_addr)) and not (l1d_has_line(`l1d_s1`, `l1d_a1`, req_addr)) and not (`l1d_lru`), set `l1d_s0` to 3; set `l1d_a0` to req_addr; set `l1d_data0` to l1d_req_data; set `l1d_lru` to true.
- **l1d_write_miss1** — when req_core equals 0 and req_write and not (l1d_has_line(`l1d_s0`, `l1d_a0`, req_addr)) and not (l1d_has_line(`l1d_s1`, `l1d_a1`, req_addr)) and `l1d_lru`, set `l1d_s1` to 3; set `l1d_a1` to req_addr; set `l1d_data1` to l1d_req_data; set `l1d_lru` to false.
- **l1d_read_hit0** — when req_core equals 0 and not (req_write) and l1d_has_line(`l1d_s0`, `l1d_a0`, req_addr), set `l1d_rdata` to `l1d_data0`; set `l1d_lru` to true.
- **l1d_read_hit1** — when req_core equals 0 and not (req_write) and not (l1d_has_line(`l1d_s0`, `l1d_a0`, req_addr)) and l1d_has_line(`l1d_s1`, `l1d_a1`, req_addr), set `l1d_rdata` to `l1d_data1`; set `l1d_lru` to false.
- **l1d_read_miss0** — when req_core equals 0 and not (req_write) and not (l1d_has_line(`l1d_s0`, `l1d_a0`, req_addr)) and not (l1d_has_line(`l1d_s1`, `l1d_a1`, req_addr)) and not (`l1d_lru`), set `l1d_s0` to 1; set `l1d_a0` to req_addr.
- **l1d_read_miss1** — when req_core equals 0 and not (req_write) and not (l1d_has_line(`l1d_s0`, `l1d_a0`, req_addr)) and not (l1d_has_line(`l1d_s1`, `l1d_a1`, req_addr)) and `l1d_lru`, set `l1d_s1` to 1; set `l1d_a1` to req_addr.
- **l1d_snoop_inv0** — when req_core does not equal 0 and req_write and l1d_has_line(`l1d_s0`, `l1d_a0`, req_addr), set `l1d_s0` to 0.
- **l1d_snoop_inv1** — when req_core does not equal 0 and req_write and l1d_has_line(`l1d_s1`, `l1d_a1`, req_addr), set `l1d_s1` to 0.
- **l1d_snoop_dg0** — when req_core does not equal 0 and not (req_write) and l1d_has_line(`l1d_s0`, `l1d_a0`, req_addr), set `l1d_s0` to 1.
- **l1d_snoop_dg1** — when req_core does not equal 0 and not (req_write) and l1d_has_line(`l1d_s1`, `l1d_a1`, req_addr), set `l1d_s1` to 1.

## Properties

- **resp_valid_bool** (safety): always, `resp_valid` equals true or `resp_valid` equals false.
- **load_returns_mem** (transition): after each step, `resp_data` equals mem_read(mem, req_addr).
- **l1d_states_valid** (safety): always, `l1d_s0` ≥ 0 and `l1d_s0` ≤ 3 and `l1d_s1` ≥ 0 and `l1d_s1` ≤ 3.
- **l1d_physical_tag_used** (transition): after each step, `l1d_a0` equals req_addr.
- **l1d_modified_way_holds_line** (safety): always, if l1d_is_modified(`l1d_s0`), then l1d_has_line(`l1d_s0`, `l1d_a0`, `l1d_a0`).
- **l1d_phys_index_bounded** (safety): always, l1d_phys_index(req_addr) ≤ 3.
