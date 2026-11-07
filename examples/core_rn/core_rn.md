# core_rn specification

## Inputs

| Name | Type |
|------|------|
| `core_req_valid` | bool |
| `core_req_write` | bool |
| `core_req_addr` | bits<4> |
| `core_req_data` | bits<8> |
| `snp_valid` | bool |
| `snp_op` | bool |
| `snp_addr` | bits<4> |
| `grant_valid` | bool |
| `grant_write` | bool |
| `grant_addr` | bits<4> |
| `grant_data` | bits<8> |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `mstate` | register | bits<2> | 0 |
| `maddr` | register | bits<4> | 0 |
| `mdata` | register | bits<8> | 0 |
| `req_out_valid` | register | bool | false |
| `req_out_write` | register | bool | false |
| `req_out_addr` | register | bits<4> | 0 |
| `req_out_data` | register | bits<8> | 0 |
| `snp_rsp_valid` | register | bool | false |
| `l1_req_write` | register | bool | false |
| `l1_req_addr` | register | bits<4> | 0 |
| `l1_req_data` | register | bits<8> | 0 |
| `l1_s0` | register | bits<2> | 0 |
| `l1_a0` | register | bits<4> | 0 |
| `l1_s1` | register | bits<2> | 0 |
| `l1_a1` | register | bits<4> | 0 |
| `l1_lru` | register | bool | false |
| `l1_data0` | register | bits<8> | 0 |
| `l1_data1` | register | bits<8> | 0 |
| `l1_rdata` | register | bits<8> | 0 |

## Behavior (rules)

- **issue_req** — when core_req_valid, set `req_out_valid` to true; set `req_out_write` to core_req_write; set `req_out_addr` to core_req_addr; set `req_out_data` to core_req_data; set `l1_req_write` to core_req_write; set `l1_req_addr` to core_req_addr; set `l1_req_data` to core_req_data.
- **complete_req** — when grant_valid, set `req_out_valid` to false.
- **respond_snp** — when snp_valid, set `snp_rsp_valid` to true; set `mstate` to if snp_op, then 0, otherwise if `mstate` equals 3, then 1, otherwise `mstate`.
- **clear_snp_rsp** — when not (snp_valid), set `snp_rsp_valid` to false.
- **receive_grant** — when grant_valid, set `mstate` to if grant_write, then 3, otherwise 1; set `maddr` to grant_addr; set `mdata` to grant_data; set `l1_req_write` to true; set `l1_req_addr` to grant_addr; set `l1_req_data` to grant_data.
- **l1_write_hit0** — when 0 equals 0 and l1_req_write and l1_has_line(`l1_s0`, `l1_a0`, l1_req_addr), set `l1_s0` to 3; set `l1_data0` to l1_req_data; set `l1_lru` to true.
- **l1_write_hit1** — when 0 equals 0 and l1_req_write and not (l1_has_line(`l1_s0`, `l1_a0`, l1_req_addr)) and l1_has_line(`l1_s1`, `l1_a1`, l1_req_addr), set `l1_s1` to 3; set `l1_data1` to l1_req_data; set `l1_lru` to false.
- **l1_write_miss0** — when 0 equals 0 and l1_req_write and not (l1_has_line(`l1_s0`, `l1_a0`, l1_req_addr)) and not (l1_has_line(`l1_s1`, `l1_a1`, l1_req_addr)) and not (`l1_lru`), set `l1_s0` to 3; set `l1_a0` to l1_req_addr; set `l1_data0` to l1_req_data; set `l1_lru` to true.
- **l1_write_miss1** — when 0 equals 0 and l1_req_write and not (l1_has_line(`l1_s0`, `l1_a0`, l1_req_addr)) and not (l1_has_line(`l1_s1`, `l1_a1`, l1_req_addr)) and `l1_lru`, set `l1_s1` to 3; set `l1_a1` to l1_req_addr; set `l1_data1` to l1_req_data; set `l1_lru` to false.
- **l1_read_hit0** — when 0 equals 0 and not (l1_req_write) and l1_has_line(`l1_s0`, `l1_a0`, l1_req_addr), set `l1_rdata` to `l1_data0`; set `l1_lru` to true.
- **l1_read_hit1** — when 0 equals 0 and not (l1_req_write) and not (l1_has_line(`l1_s0`, `l1_a0`, l1_req_addr)) and l1_has_line(`l1_s1`, `l1_a1`, l1_req_addr), set `l1_rdata` to `l1_data1`; set `l1_lru` to false.
- **l1_read_miss0** — when 0 equals 0 and not (l1_req_write) and not (l1_has_line(`l1_s0`, `l1_a0`, l1_req_addr)) and not (l1_has_line(`l1_s1`, `l1_a1`, l1_req_addr)) and not (`l1_lru`), set `l1_s0` to 1; set `l1_a0` to l1_req_addr.
- **l1_read_miss1** — when 0 equals 0 and not (l1_req_write) and not (l1_has_line(`l1_s0`, `l1_a0`, l1_req_addr)) and not (l1_has_line(`l1_s1`, `l1_a1`, l1_req_addr)) and `l1_lru`, set `l1_s1` to 1; set `l1_a1` to l1_req_addr.
- **l1_snoop_inv0** — when 0 does not equal 0 and l1_req_write and l1_has_line(`l1_s0`, `l1_a0`, l1_req_addr), set `l1_s0` to 0.
- **l1_snoop_inv1** — when 0 does not equal 0 and l1_req_write and l1_has_line(`l1_s1`, `l1_a1`, l1_req_addr), set `l1_s1` to 0.
- **l1_snoop_dg0** — when 0 does not equal 0 and not (l1_req_write) and l1_has_line(`l1_s0`, `l1_a0`, l1_req_addr), set `l1_s0` to 1.
- **l1_snoop_dg1** — when 0 does not equal 0 and not (l1_req_write) and l1_has_line(`l1_s1`, `l1_a1`, l1_req_addr), set `l1_s1` to 1.

## Properties

- **has_line_holds_line** (safety): always, if has_line(`mstate`, `maddr`, `maddr`), then `mstate` does not equal 0.
- **is_modified_implies_valid** (safety): always, if is_modified(`mstate`), then `mstate` does not equal 0.
- **l1_is_modified_implies_valid** (safety): always, if l1_is_modified(`l1_s0`), then `l1_s0` does not equal 0.
- **l1_phys_index_bounded** (safety): always, l1_phys_index(`l1_req_addr`) ≤ 3.
- **states_valid** (safety): always, `mstate` ≥ 0 and `mstate` ≤ 3.
