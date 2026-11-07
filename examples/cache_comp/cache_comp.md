# cache_comp specification

## Inputs

| Name | Type |
|------|------|
| `i_addr` | bits<4> |
| `d_core` | bits<4> |
| `d_write` | bool |
| `d_addr` | bits<4> |
| `d_vpn` | bits<2> |
| `d_is_physical` | bool |
| `d_data` | bits<8> |
| `mshr_release0` | bool |
| `mshr_release1` | bool |
| `l2_mshr_arb_req2_valid` | bool |
| `l2_mshr_arb_req3_valid` | bool |
| `l2_mshr_arb_req4_valid` | bool |
| `l2_mshr_arb_req5_valid` | bool |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `const_false` | register | bool | false |
| `l2_miss_valid` | register | bool | false |
| `l2_miss_addr` | register | bits<4> | 0 |
| `l1d_rdata_signal` | register | bits<8> | 0 |
| `l1i_s0` | register | bits<2> | 0 |
| `l1i_a0` | register | bits<4> | 0 |
| `l1i_s1` | register | bits<2> | 0 |
| `l1i_a1` | register | bits<4> | 0 |
| `l1i_lru` | register | bool | false |
| `l1i_data0` | register | bits<8> | 0 |
| `l1i_data1` | register | bits<8> | 0 |
| `l1i_rdata` | register | bits<8> | 0 |
| `l1d_s0` | register | bits<2> | 0 |
| `l1d_a0` | register | bits<4> | 0 |
| `l1d_s1` | register | bits<2> | 0 |
| `l1d_a1` | register | bits<4> | 0 |
| `l1d_lru` | register | bool | false |
| `l1d_data0` | register | bits<8> | 0 |
| `l1d_data1` | register | bits<8> | 0 |
| `l2_s0` | register | bits<2> | 0 |
| `l2_a0` | register | bits<4> | 0 |
| `l2_s1` | register | bits<2> | 0 |
| `l2_a1` | register | bits<4> | 0 |
| `l2_lru` | register | bool | false |
| `l2_mem` | memory | memory(bits<8>, 16) |  |
| `l2_mshr_mshr0_valid` | register | bool | false |
| `l2_mshr_mshr0_mid` | register | bits<2> | 0 |
| `l2_mshr_mshr0_maddr` | register | bits<4> | 0 |
| `l2_mshr_mshr0_mdata` | register | bits<8> | 0 |
| `l2_mshr_mshr1_valid` | register | bool | false |
| `l2_mshr_mshr1_mid` | register | bits<2> | 0 |
| `l2_mshr_mshr1_maddr` | register | bits<4> | 0 |
| `l2_mshr_mshr1_mdata` | register | bits<8> | 0 |
| `l2_mshr_arb_grant` | register | bits<3> | 0 |
| `l2_mshr_arb_grant_valid` | register | bool | false |

## Behavior (rules)

- **l1i_write_hit0** — when 0 equals 0 and const_false and l1i_has_line(`l1i_s0`, `l1i_a0`, i_addr), set `l1i_s0` to 3; set `l1i_data0` to 0; set `l1i_lru` to true.
- **l1i_write_hit1** — when 0 equals 0 and const_false and not (l1i_has_line(`l1i_s0`, `l1i_a0`, i_addr)) and l1i_has_line(`l1i_s1`, `l1i_a1`, i_addr), set `l1i_s1` to 3; set `l1i_data1` to 0; set `l1i_lru` to false.
- **l1i_write_miss0** — when 0 equals 0 and const_false and not (l1i_has_line(`l1i_s0`, `l1i_a0`, i_addr)) and not (l1i_has_line(`l1i_s1`, `l1i_a1`, i_addr)) and not (`l1i_lru`), set `l1i_s0` to 3; set `l1i_a0` to i_addr; set `l1i_data0` to 0; set `l1i_lru` to true.
- **l1i_write_miss1** — when 0 equals 0 and const_false and not (l1i_has_line(`l1i_s0`, `l1i_a0`, i_addr)) and not (l1i_has_line(`l1i_s1`, `l1i_a1`, i_addr)) and `l1i_lru`, set `l1i_s1` to 3; set `l1i_a1` to i_addr; set `l1i_data1` to 0; set `l1i_lru` to false.
- **l1i_read_hit0** — when 0 equals 0 and not (const_false) and l1i_has_line(`l1i_s0`, `l1i_a0`, i_addr), set `l1i_rdata` to `l1i_data0`; set `l1i_lru` to true.
- **l1i_read_hit1** — when 0 equals 0 and not (const_false) and not (l1i_has_line(`l1i_s0`, `l1i_a0`, i_addr)) and l1i_has_line(`l1i_s1`, `l1i_a1`, i_addr), set `l1i_rdata` to `l1i_data1`; set `l1i_lru` to false.
- **l1i_read_miss0** — when 0 equals 0 and not (const_false) and not (l1i_has_line(`l1i_s0`, `l1i_a0`, i_addr)) and not (l1i_has_line(`l1i_s1`, `l1i_a1`, i_addr)) and not (`l1i_lru`), set `l1i_s0` to 1; set `l1i_a0` to i_addr.
- **l1i_read_miss1** — when 0 equals 0 and not (const_false) and not (l1i_has_line(`l1i_s0`, `l1i_a0`, i_addr)) and not (l1i_has_line(`l1i_s1`, `l1i_a1`, i_addr)) and `l1i_lru`, set `l1i_s1` to 1; set `l1i_a1` to i_addr.
- **l1i_snoop_inv0** — when 0 does not equal 0 and const_false and l1i_has_line(`l1i_s0`, `l1i_a0`, i_addr), set `l1i_s0` to 0.
- **l1i_snoop_inv1** — when 0 does not equal 0 and const_false and l1i_has_line(`l1i_s1`, `l1i_a1`, i_addr), set `l1i_s1` to 0.
- **l1i_snoop_dg0** — when 0 does not equal 0 and not (const_false) and l1i_has_line(`l1i_s0`, `l1i_a0`, i_addr), set `l1i_s0` to 1.
- **l1i_snoop_dg1** — when 0 does not equal 0 and not (const_false) and l1i_has_line(`l1i_s1`, `l1i_a1`, i_addr), set `l1i_s1` to 1.
- **l1d_write_hit0** — when d_core equals 0 and d_write and l1d_has_line(`l1d_s0`, `l1d_a0`, d_addr), set `l1d_s0` to 3; set `l1d_data0` to d_data; set `l1d_lru` to true.
- **l1d_write_hit1** — when d_core equals 0 and d_write and not (l1d_has_line(`l1d_s0`, `l1d_a0`, d_addr)) and l1d_has_line(`l1d_s1`, `l1d_a1`, d_addr), set `l1d_s1` to 3; set `l1d_data1` to d_data; set `l1d_lru` to false.
- **l1d_write_miss0** — when d_core equals 0 and d_write and not (l1d_has_line(`l1d_s0`, `l1d_a0`, d_addr)) and not (l1d_has_line(`l1d_s1`, `l1d_a1`, d_addr)) and not (`l1d_lru`), set `l1d_s0` to 3; set `l1d_a0` to d_addr; set `l1d_data0` to d_data; set `l1d_lru` to true.
- **l1d_write_miss1** — when d_core equals 0 and d_write and not (l1d_has_line(`l1d_s0`, `l1d_a0`, d_addr)) and not (l1d_has_line(`l1d_s1`, `l1d_a1`, d_addr)) and `l1d_lru`, set `l1d_s1` to 3; set `l1d_a1` to d_addr; set `l1d_data1` to d_data; set `l1d_lru` to false.
- **l1d_read_hit0** — when d_core equals 0 and not (d_write) and l1d_has_line(`l1d_s0`, `l1d_a0`, d_addr), set `l1d_rdata_signal` to `l1d_data0`; set `l1d_lru` to true.
- **l1d_read_hit1** — when d_core equals 0 and not (d_write) and not (l1d_has_line(`l1d_s0`, `l1d_a0`, d_addr)) and l1d_has_line(`l1d_s1`, `l1d_a1`, d_addr), set `l1d_rdata_signal` to `l1d_data1`; set `l1d_lru` to false.
- **l1d_read_miss0** — when d_core equals 0 and not (d_write) and not (l1d_has_line(`l1d_s0`, `l1d_a0`, d_addr)) and not (l1d_has_line(`l1d_s1`, `l1d_a1`, d_addr)) and not (`l1d_lru`), set `l1d_s0` to 1; set `l1d_a0` to d_addr.
- **l1d_read_miss1** — when d_core equals 0 and not (d_write) and not (l1d_has_line(`l1d_s0`, `l1d_a0`, d_addr)) and not (l1d_has_line(`l1d_s1`, `l1d_a1`, d_addr)) and `l1d_lru`, set `l1d_s1` to 1; set `l1d_a1` to d_addr.
- **l1d_snoop_inv0** — when d_core does not equal 0 and d_write and l1d_has_line(`l1d_s0`, `l1d_a0`, d_addr), set `l1d_s0` to 0.
- **l1d_snoop_inv1** — when d_core does not equal 0 and d_write and l1d_has_line(`l1d_s1`, `l1d_a1`, d_addr), set `l1d_s1` to 0.
- **l1d_snoop_dg0** — when d_core does not equal 0 and not (d_write) and l1d_has_line(`l1d_s0`, `l1d_a0`, d_addr), set `l1d_s0` to 1.
- **l1d_snoop_dg1** — when d_core does not equal 0 and not (d_write) and l1d_has_line(`l1d_s1`, `l1d_a1`, d_addr), set `l1d_s1` to 1.
- **l2_write_hit0** — when d_core equals 0 and d_write and l2_has_line(`l2_s0`, `l2_a0`, d_addr), set `l2_s0` to 3; set `l2_lru` to true; mem_write(l2_mem, d_addr, d_data).
- **l2_write_hit1** — when d_core equals 0 and d_write and not (l2_has_line(`l2_s0`, `l2_a0`, d_addr)) and l2_has_line(`l2_s1`, `l2_a1`, d_addr), set `l2_s1` to 3; set `l2_lru` to false; mem_write(l2_mem, d_addr, d_data).
- **l2_write_miss0** — when d_core equals 0 and d_write and not (l2_has_line(`l2_s0`, `l2_a0`, d_addr)) and not (l2_has_line(`l2_s1`, `l2_a1`, d_addr)) and not (`l2_lru`), set `l2_s0` to 3; set `l2_a0` to d_addr; set `l2_lru` to true; mem_write(l2_mem, d_addr, d_data); set `l2_miss_valid` to true; set `l2_miss_addr` to d_addr.
- **l2_write_miss1** — when d_core equals 0 and d_write and not (l2_has_line(`l2_s0`, `l2_a0`, d_addr)) and not (l2_has_line(`l2_s1`, `l2_a1`, d_addr)) and `l2_lru`, set `l2_s1` to 3; set `l2_a1` to d_addr; set `l2_lru` to false; mem_write(l2_mem, d_addr, d_data); set `l2_miss_valid` to true; set `l2_miss_addr` to d_addr.
- **l2_read_miss0** — when d_core equals 0 and not (d_write) and not (l2_has_line(`l2_s0`, `l2_a0`, d_addr)) and not (l2_has_line(`l2_s1`, `l2_a1`, d_addr)) and not (`l2_lru`), set `l2_s0` to 1; set `l2_a0` to d_addr; set `l2_miss_valid` to true; set `l2_miss_addr` to d_addr.
- **l2_read_miss1** — when d_core equals 0 and not (d_write) and not (l2_has_line(`l2_s0`, `l2_a0`, d_addr)) and not (l2_has_line(`l2_s1`, `l2_a1`, d_addr)) and `l2_lru`, set `l2_s1` to 1; set `l2_a1` to d_addr; set `l2_miss_valid` to true; set `l2_miss_addr` to d_addr.
- **l2_snoop_inv0** — when d_core does not equal 0 and d_write and l2_has_line(`l2_s0`, `l2_a0`, d_addr), set `l2_s0` to 0.
- **l2_snoop_inv1** — when d_core does not equal 0 and d_write and l2_has_line(`l2_s1`, `l2_a1`, d_addr), set `l2_s1` to 0.
- **l2_snoop_dg0** — when d_core does not equal 0 and not (d_write) and l2_has_line(`l2_s0`, `l2_a0`, d_addr), set `l2_s0` to 1.
- **l2_snoop_dg1** — when d_core does not equal 0 and not (d_write) and l2_has_line(`l2_s1`, `l2_a1`, d_addr), set `l2_s1` to 1.
- **l2_mshr_mshr0_alloc** — when l2_miss_valid and not (`l2_mshr_mshr0_valid`), set `l2_mshr_mshr0_valid` to true; set `l2_mshr_mshr0_mid` to 0; set `l2_mshr_mshr0_maddr` to d_addr; set `l2_mshr_mshr0_mdata` to d_data.
- **l2_mshr_mshr0_rel** — when mshr_release0, set `l2_mshr_mshr0_valid` to false.
- **l2_mshr_mshr1_alloc** — when l2_miss_valid and not (`l2_mshr_mshr1_valid`), set `l2_mshr_mshr1_valid` to true; set `l2_mshr_mshr1_mid` to 0; set `l2_mshr_mshr1_maddr` to d_addr; set `l2_mshr_mshr1_mdata` to d_data.
- **l2_mshr_mshr1_rel** — when mshr_release1, set `l2_mshr_mshr1_valid` to false.
- **l2_mshr_arb_arbitrate** — when true, set `l2_mshr_arb_grant` to if l2_miss_valid, then 0, otherwise if l2_miss_valid, then 1, otherwise if l2_mshr_arb_req2_valid, then 2, otherwise if l2_mshr_arb_req3_valid, then 3, otherwise if l2_mshr_arb_req4_valid, then 4, otherwise if l2_mshr_arb_req5_valid, then 5, otherwise 0; set `l2_mshr_arb_grant_valid` to l2_miss_valid or l2_miss_valid or l2_mshr_arb_req2_valid or l2_mshr_arb_req3_valid or l2_mshr_arb_req4_valid or l2_mshr_arb_req5_valid.

## Properties

- **l1d_is_modified_implies_valid** (safety): always, if l1d_is_modified(`l1d_s0`), then `l1d_s0` does not equal 0.
- **l1d_phys_index_bounded** (safety): always, l1d_phys_index(`l1d_a0`) ≤ 3.
- **l1i_is_modified_implies_valid** (safety): always, if l1i_is_modified(`l1i_s0`), then `l1i_s0` does not equal 0.
- **l1i_phys_index_bounded** (safety): always, l1i_phys_index(`l1i_a0`) ≤ 3.
- **l1d_states_valid** (safety): always, `l1d_s0` ≥ 0 and `l1d_s0` ≤ 3 and `l1d_s1` ≥ 0 and `l1d_s1` ≤ 3.
