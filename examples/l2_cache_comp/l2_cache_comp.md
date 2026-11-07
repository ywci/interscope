# l2_cache_comp specification

## Inputs

| Name | Type |
|------|------|
| `req_core` | bits<4> |
| `req_write` | bool |
| `req_addr` | bits<4> |
| `req_vpn` | bits<2> |
| `req_data` | bits<8> |
| `mshr_release0` | bool |
| `mshr_release1` | bool |
| `mshr_arb_req2_valid` | bool |
| `mshr_arb_req3_valid` | bool |
| `mshr_arb_req4_valid` | bool |
| `mshr_arb_req5_valid` | bool |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `s0` | register | bits<2> | 0 |
| `a0` | register | bits<4> | 0 |
| `s1` | register | bits<2> | 0 |
| `a1` | register | bits<4> | 0 |
| `lru` | register | bool | false |
| `mem` | memory | memory(bits<8>, 16) |  |
| `miss_valid` | register | bool | false |
| `miss_addr` | register | bits<4> | 0 |
| `mshr_mshr0_valid` | register | bool | false |
| `mshr_mshr0_mid` | register | bits<2> | 0 |
| `mshr_mshr0_maddr` | register | bits<4> | 0 |
| `mshr_mshr0_mdata` | register | bits<8> | 0 |
| `mshr_mshr1_valid` | register | bool | false |
| `mshr_mshr1_mid` | register | bits<2> | 0 |
| `mshr_mshr1_maddr` | register | bits<4> | 0 |
| `mshr_mshr1_mdata` | register | bits<8> | 0 |
| `mshr_arb_grant` | register | bits<3> | 0 |
| `mshr_arb_grant_valid` | register | bool | false |

## Behavior (rules)

- **write_hit0** — when req_core equals 0 and req_write and has_line(`s0`, `a0`, req_addr), set `s0` to 3; set `lru` to true; mem_write(mem, req_addr, req_data).
- **write_hit1** — when req_core equals 0 and req_write and not (has_line(`s0`, `a0`, req_addr)) and has_line(`s1`, `a1`, req_addr), set `s1` to 3; set `lru` to false; mem_write(mem, req_addr, req_data).
- **write_miss0** — when req_core equals 0 and req_write and not (has_line(`s0`, `a0`, req_addr)) and not (has_line(`s1`, `a1`, req_addr)) and not (`lru`), set `s0` to 3; set `a0` to req_addr; set `lru` to true; mem_write(mem, req_addr, req_data); set `miss_valid` to true; set `miss_addr` to req_addr.
- **write_miss1** — when req_core equals 0 and req_write and not (has_line(`s0`, `a0`, req_addr)) and not (has_line(`s1`, `a1`, req_addr)) and `lru`, set `s1` to 3; set `a1` to req_addr; set `lru` to false; mem_write(mem, req_addr, req_data); set `miss_valid` to true; set `miss_addr` to req_addr.
- **read_miss0** — when req_core equals 0 and not (req_write) and not (has_line(`s0`, `a0`, req_addr)) and not (has_line(`s1`, `a1`, req_addr)) and not (`lru`), set `s0` to 1; set `a0` to req_addr; set `miss_valid` to true; set `miss_addr` to req_addr.
- **read_miss1** — when req_core equals 0 and not (req_write) and not (has_line(`s0`, `a0`, req_addr)) and not (has_line(`s1`, `a1`, req_addr)) and `lru`, set `s1` to 1; set `a1` to req_addr; set `miss_valid` to true; set `miss_addr` to req_addr.
- **snoop_inv0** — when req_core does not equal 0 and req_write and has_line(`s0`, `a0`, req_addr), set `s0` to 0.
- **snoop_inv1** — when req_core does not equal 0 and req_write and has_line(`s1`, `a1`, req_addr), set `s1` to 0.
- **snoop_dg0** — when req_core does not equal 0 and not (req_write) and has_line(`s0`, `a0`, req_addr), set `s0` to 1.
- **snoop_dg1** — when req_core does not equal 0 and not (req_write) and has_line(`s1`, `a1`, req_addr), set `s1` to 1.
- **mshr_mshr0_alloc** — when miss_valid and not (`mshr_mshr0_valid`), set `mshr_mshr0_valid` to true; set `mshr_mshr0_mid` to 0; set `mshr_mshr0_maddr` to req_addr; set `mshr_mshr0_mdata` to req_data.
- **mshr_mshr0_rel** — when mshr_release0, set `mshr_mshr0_valid` to false.
- **mshr_mshr1_alloc** — when miss_valid and not (`mshr_mshr1_valid`), set `mshr_mshr1_valid` to true; set `mshr_mshr1_mid` to 0; set `mshr_mshr1_maddr` to req_addr; set `mshr_mshr1_mdata` to req_data.
- **mshr_mshr1_rel** — when mshr_release1, set `mshr_mshr1_valid` to false.
- **mshr_arb_arbitrate** — when true, set `mshr_arb_grant` to if miss_valid, then 0, otherwise if miss_valid, then 1, otherwise if mshr_arb_req2_valid, then 2, otherwise if mshr_arb_req3_valid, then 3, otherwise if mshr_arb_req4_valid, then 4, otherwise if mshr_arb_req5_valid, then 5, otherwise 0; set `mshr_arb_grant_valid` to miss_valid or miss_valid or mshr_arb_req2_valid or mshr_arb_req3_valid or mshr_arb_req4_valid or mshr_arb_req5_valid.

## Properties

- **states_valid** (safety): always, `s0` ≥ 0 and `s0` ≤ 3 and `s1` ≥ 0 and `s1` ≤ 3.
