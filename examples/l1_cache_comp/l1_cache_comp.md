# l1_cache_comp specification

## Inputs

| Name | Type |
|------|------|
| `req_core` | bits<4> |
| `req_write` | bool |
| `req_addr` | bits<4> |
| `req_vpn` | bits<2> |
| `is_physical` | bool |
| `req_data` | bits<8> |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `s0` | register | bits<2> | 0 |
| `a0` | register | bits<4> | 0 |
| `s1` | register | bits<2> | 0 |
| `a1` | register | bits<4> | 0 |
| `lru` | register | bool | false |
| `data0` | register | bits<8> | 0 |
| `data1` | register | bits<8> | 0 |
| `rdata` | register | bits<8> | 0 |

## Behavior (rules)

- **write_hit0** — when req_core equals 0 and req_write and has_line(`s0`, `a0`, req_addr), set `s0` to 3; set `data0` to req_data; set `lru` to true.
- **write_hit1** — when req_core equals 0 and req_write and not (has_line(`s0`, `a0`, req_addr)) and has_line(`s1`, `a1`, req_addr), set `s1` to 3; set `data1` to req_data; set `lru` to false.
- **write_miss0** — when req_core equals 0 and req_write and not (has_line(`s0`, `a0`, req_addr)) and not (has_line(`s1`, `a1`, req_addr)) and not (`lru`), set `s0` to 3; set `a0` to req_addr; set `data0` to req_data; set `lru` to true.
- **write_miss1** — when req_core equals 0 and req_write and not (has_line(`s0`, `a0`, req_addr)) and not (has_line(`s1`, `a1`, req_addr)) and `lru`, set `s1` to 3; set `a1` to req_addr; set `data1` to req_data; set `lru` to false.
- **read_hit0** — when req_core equals 0 and not (req_write) and has_line(`s0`, `a0`, req_addr), set `rdata` to `data0`; set `lru` to true.
- **read_hit1** — when req_core equals 0 and not (req_write) and not (has_line(`s0`, `a0`, req_addr)) and has_line(`s1`, `a1`, req_addr), set `rdata` to `data1`; set `lru` to false.
- **read_miss0** — when req_core equals 0 and not (req_write) and not (has_line(`s0`, `a0`, req_addr)) and not (has_line(`s1`, `a1`, req_addr)) and not (`lru`), set `s0` to 1; set `a0` to req_addr.
- **read_miss1** — when req_core equals 0 and not (req_write) and not (has_line(`s0`, `a0`, req_addr)) and not (has_line(`s1`, `a1`, req_addr)) and `lru`, set `s1` to 1; set `a1` to req_addr.
- **snoop_inv0** — when req_core does not equal 0 and req_write and has_line(`s0`, `a0`, req_addr), set `s0` to 0.
- **snoop_inv1** — when req_core does not equal 0 and req_write and has_line(`s1`, `a1`, req_addr), set `s1` to 0.
- **snoop_dg0** — when req_core does not equal 0 and not (req_write) and has_line(`s0`, `a0`, req_addr), set `s0` to 1.
- **snoop_dg1** — when req_core does not equal 0 and not (req_write) and has_line(`s1`, `a1`, req_addr), set `s1` to 1.

## Properties

- **states_valid** (safety): always, `s0` ≥ 0 and `s0` ≤ 3 and `s1` ≥ 0 and `s1` ≤ 3.
- **physical_tag_used** (transition): after each step, `a0` equals req_addr.
- **modified_way_holds_line** (safety): always, if is_modified(`s0`), then has_line(`s0`, `a0`, `a0`).
- **phys_index_bounded** (safety): always, phys_index(req_addr) ≤ 3.
