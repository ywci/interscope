# chi_noc_multicore specification

## Inputs

| Name | Type |
|------|------|
| `core_req0_valid` | bool |
| `core_req0_write` | bool |
| `core_req0_addr` | bits<4> |
| `core_req0_data` | bits<8> |
| `core_req1_valid` | bool |
| `core_req1_write` | bool |
| `core_req1_addr` | bits<4> |
| `core_req1_data` | bits<8> |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `req0_valid` | register | bool | false |
| `req0_write` | register | bool | false |
| `req0_addr` | register | bits<4> | 0 |
| `req0_data` | register | bits<8> | 0 |
| `req1_valid` | register | bool | false |
| `req1_write` | register | bool | false |
| `req1_addr` | register | bits<4> | 0 |
| `req1_data` | register | bits<8> | 0 |
| `rs0_valid` | register | bool | false |
| `rs0_core` | register | bool | false |
| `rs0_write` | register | bool | false |
| `rs0_addr` | register | bits<4> | 0 |
| `rs0_data` | register | bits<8> | 0 |
| `rs1_valid` | register | bool | false |
| `rs1_core` | register | bool | false |
| `rs1_write` | register | bool | false |
| `rs1_addr` | register | bits<4> | 0 |
| `rs1_data` | register | bits<8> | 0 |
| `snp0_valid` | register | bool | false |
| `snp0_core` | register | bool | false |
| `snp0_addr` | register | bits<4> | 0 |
| `snp0_op` | register | bool | false |
| `snp1_valid` | register | bool | false |
| `snp1_core` | register | bool | false |
| `snp1_addr` | register | bits<4> | 0 |
| `snp1_op` | register | bool | false |
| `sr0_valid` | register | bool | false |
| `sr0_op` | register | bool | false |
| `sr0_addr` | register | bits<4> | 0 |
| `sr1_valid` | register | bool | false |
| `sr1_op` | register | bool | false |
| `sr1_addr` | register | bits<4> | 0 |
| `grant0_valid` | register | bool | false |
| `grant0_core` | register | bool | false |
| `grant0_write` | register | bool | false |
| `grant0_addr` | register | bits<4> | 0 |
| `grant0_data` | register | bits<8> | 0 |
| `grant1_valid` | register | bool | false |
| `grant1_core` | register | bool | false |
| `grant1_write` | register | bool | false |
| `grant1_addr` | register | bits<4> | 0 |
| `grant1_data` | register | bits<8> | 0 |
| `gr0_valid` | register | bool | false |
| `gr0_write` | register | bool | false |
| `gr0_addr` | register | bits<4> | 0 |
| `gr0_data` | register | bits<8> | 0 |
| `gr1_valid` | register | bool | false |
| `gr1_write` | register | bool | false |
| `gr1_addr` | register | bits<4> | 0 |
| `gr1_data` | register | bits<8> | 0 |
| `rsp0_core_sig` | register | bool | false |
| `rsp0_op_sig` | register | bool | false |
| `rsp1_core_sig` | register | bool | true |
| `rsp1_op_sig` | register | bool | false |
| `rsp0_valid` | register | bool | false |
| `rsp1_valid` | register | bool | false |
| `ps0_valid` | register | bool | false |
| `ps0_core` | register | bool | false |
| `ps0_op` | register | bool | false |
| `ps1_valid` | register | bool | false |
| `ps1_core` | register | bool | false |
| `ps1_op` | register | bool | false |
| `c0_mstate` | register | bits<2> | 0 |
| `c0_maddr` | register | bits<4> | 0 |
| `c1_mstate` | register | bits<2> | 0 |
| `c1_maddr` | register | bits<4> | 0 |
| `rn0_mdata` | register | bits<8> | 0 |
| `rn0_l1_req_write` | register | bool | false |
| `rn0_l1_req_addr` | register | bits<4> | 0 |
| `rn0_l1_req_data` | register | bits<8> | 0 |
| `rn0_l1_s0` | register | bits<2> | 0 |
| `rn0_l1_a0` | register | bits<4> | 0 |
| `rn0_l1_s1` | register | bits<2> | 0 |
| `rn0_l1_a1` | register | bits<4> | 0 |
| `rn0_l1_lru` | register | bool | false |
| `rn0_l1_data0` | register | bits<8> | 0 |
| `rn0_l1_data1` | register | bits<8> | 0 |
| `rn0_l1_rdata` | register | bits<8> | 0 |
| `rn1_mdata` | register | bits<8> | 0 |
| `rn1_l1_req_write` | register | bool | false |
| `rn1_l1_req_addr` | register | bits<4> | 0 |
| `rn1_l1_req_data` | register | bits<8> | 0 |
| `rn1_l1_s0` | register | bits<2> | 0 |
| `rn1_l1_a0` | register | bits<4> | 0 |
| `rn1_l1_s1` | register | bits<2> | 0 |
| `rn1_l1_a1` | register | bits<4> | 0 |
| `rn1_l1_lru` | register | bool | false |
| `rn1_l1_data0` | register | bits<8> | 0 |
| `rn1_l1_data1` | register | bits<8> | 0 |
| `rn1_l1_rdata` | register | bits<8> | 0 |
| `router_pending_slice` | register | bool | false |
| `slice0_c0_state` | register | bits<2> | 0 |
| `slice0_c0_addr` | register | bits<4> | 0 |
| `slice0_c1_state` | register | bits<2> | 0 |
| `slice0_c1_addr` | register | bits<4> | 0 |
| `slice0_s0` | register | bits<2> | 0 |
| `slice0_a0` | register | bits<4> | 0 |
| `slice0_d0` | register | bits<8> | 0 |
| `slice0_s1` | register | bits<2> | 0 |
| `slice0_a1` | register | bits<4> | 0 |
| `slice0_d1` | register | bits<8> | 0 |
| `slice0_lru` | register | bool | false |
| `slice0_pending` | register | bool | false |
| `slice0_snooped` | register | bool | false |
| `slice0_pending_core` | register | bool | false |
| `slice0_pending_write` | register | bool | false |
| `slice0_pending_addr` | register | bits<4> | 0 |
| `slice0_pending_data` | register | bits<8> | 0 |
| `slice0_req_credits` | register | bits<2> | 2 |
| `slice1_c0_state` | register | bits<2> | 0 |
| `slice1_c0_addr` | register | bits<4> | 0 |
| `slice1_c1_state` | register | bits<2> | 0 |
| `slice1_c1_addr` | register | bits<4> | 0 |
| `slice1_s0` | register | bits<2> | 0 |
| `slice1_a0` | register | bits<4> | 0 |
| `slice1_d0` | register | bits<8> | 0 |
| `slice1_s1` | register | bits<2> | 0 |
| `slice1_a1` | register | bits<4> | 0 |
| `slice1_d1` | register | bits<8> | 0 |
| `slice1_lru` | register | bool | false |
| `slice1_pending` | register | bool | false |
| `slice1_snooped` | register | bool | false |
| `slice1_pending_core` | register | bool | false |
| `slice1_pending_write` | register | bool | false |
| `slice1_pending_addr` | register | bits<4> | 0 |
| `slice1_pending_data` | register | bits<8> | 0 |
| `slice1_req_credits` | register | bits<2> | 2 |

## Behavior (rules)

- **rn0_issue_req** — when core_req0_valid, set `req0_valid` to true; set `req0_write` to core_req0_write; set `req0_addr` to core_req0_addr; set `req0_data` to core_req0_data; set `rn0_l1_req_write` to core_req0_write; set `rn0_l1_req_addr` to core_req0_addr; set `rn0_l1_req_data` to core_req0_data.
- **rn0_complete_req** — when gr0_valid, set `req0_valid` to false.
- **rn0_respond_snp** — when sr0_valid, set `rsp0_valid` to true; set `c0_mstate` to if sr0_op, then 0, otherwise if `c0_mstate` equals 3, then 1, otherwise `c0_mstate`.
- **rn0_clear_snp_rsp** — when not (sr0_valid), set `rsp0_valid` to false.
- **rn0_receive_grant** — when gr0_valid, set `c0_mstate` to if gr0_write, then 3, otherwise 1; set `c0_maddr` to gr0_addr; set `rn0_mdata` to gr0_data; set `rn0_l1_req_write` to true; set `rn0_l1_req_addr` to gr0_addr; set `rn0_l1_req_data` to gr0_data.
- **rn0_l1_write_hit0** — when 0 equals 0 and rn0_l1_req_write and rn0_l1_has_line(`rn0_l1_s0`, `rn0_l1_a0`, rn0_l1_req_addr), set `rn0_l1_s0` to 3; set `rn0_l1_data0` to rn0_l1_req_data; set `rn0_l1_lru` to true.
- **rn0_l1_write_hit1** — when 0 equals 0 and rn0_l1_req_write and not (rn0_l1_has_line(`rn0_l1_s0`, `rn0_l1_a0`, rn0_l1_req_addr)) and rn0_l1_has_line(`rn0_l1_s1`, `rn0_l1_a1`, rn0_l1_req_addr), set `rn0_l1_s1` to 3; set `rn0_l1_data1` to rn0_l1_req_data; set `rn0_l1_lru` to false.
- **rn0_l1_write_miss0** — when 0 equals 0 and rn0_l1_req_write and not (rn0_l1_has_line(`rn0_l1_s0`, `rn0_l1_a0`, rn0_l1_req_addr)) and not (rn0_l1_has_line(`rn0_l1_s1`, `rn0_l1_a1`, rn0_l1_req_addr)) and not (`rn0_l1_lru`), set `rn0_l1_s0` to 3; set `rn0_l1_a0` to rn0_l1_req_addr; set `rn0_l1_data0` to rn0_l1_req_data; set `rn0_l1_lru` to true.
- **rn0_l1_write_miss1** — when 0 equals 0 and rn0_l1_req_write and not (rn0_l1_has_line(`rn0_l1_s0`, `rn0_l1_a0`, rn0_l1_req_addr)) and not (rn0_l1_has_line(`rn0_l1_s1`, `rn0_l1_a1`, rn0_l1_req_addr)) and `rn0_l1_lru`, set `rn0_l1_s1` to 3; set `rn0_l1_a1` to rn0_l1_req_addr; set `rn0_l1_data1` to rn0_l1_req_data; set `rn0_l1_lru` to false.
- **rn0_l1_read_hit0** — when 0 equals 0 and not (rn0_l1_req_write) and rn0_l1_has_line(`rn0_l1_s0`, `rn0_l1_a0`, rn0_l1_req_addr), set `rn0_l1_rdata` to `rn0_l1_data0`; set `rn0_l1_lru` to true.
- **rn0_l1_read_hit1** — when 0 equals 0 and not (rn0_l1_req_write) and not (rn0_l1_has_line(`rn0_l1_s0`, `rn0_l1_a0`, rn0_l1_req_addr)) and rn0_l1_has_line(`rn0_l1_s1`, `rn0_l1_a1`, rn0_l1_req_addr), set `rn0_l1_rdata` to `rn0_l1_data1`; set `rn0_l1_lru` to false.
- **rn0_l1_read_miss0** — when 0 equals 0 and not (rn0_l1_req_write) and not (rn0_l1_has_line(`rn0_l1_s0`, `rn0_l1_a0`, rn0_l1_req_addr)) and not (rn0_l1_has_line(`rn0_l1_s1`, `rn0_l1_a1`, rn0_l1_req_addr)) and not (`rn0_l1_lru`), set `rn0_l1_s0` to 1; set `rn0_l1_a0` to rn0_l1_req_addr.
- **rn0_l1_read_miss1** — when 0 equals 0 and not (rn0_l1_req_write) and not (rn0_l1_has_line(`rn0_l1_s0`, `rn0_l1_a0`, rn0_l1_req_addr)) and not (rn0_l1_has_line(`rn0_l1_s1`, `rn0_l1_a1`, rn0_l1_req_addr)) and `rn0_l1_lru`, set `rn0_l1_s1` to 1; set `rn0_l1_a1` to rn0_l1_req_addr.
- **rn0_l1_snoop_inv0** — when 0 does not equal 0 and rn0_l1_req_write and rn0_l1_has_line(`rn0_l1_s0`, `rn0_l1_a0`, rn0_l1_req_addr), set `rn0_l1_s0` to 0.
- **rn0_l1_snoop_inv1** — when 0 does not equal 0 and rn0_l1_req_write and rn0_l1_has_line(`rn0_l1_s1`, `rn0_l1_a1`, rn0_l1_req_addr), set `rn0_l1_s1` to 0.
- **rn0_l1_snoop_dg0** — when 0 does not equal 0 and not (rn0_l1_req_write) and rn0_l1_has_line(`rn0_l1_s0`, `rn0_l1_a0`, rn0_l1_req_addr), set `rn0_l1_s0` to 1.
- **rn0_l1_snoop_dg1** — when 0 does not equal 0 and not (rn0_l1_req_write) and rn0_l1_has_line(`rn0_l1_s1`, `rn0_l1_a1`, rn0_l1_req_addr), set `rn0_l1_s1` to 1.
- **rn1_issue_req** — when core_req1_valid, set `req1_valid` to true; set `req1_write` to core_req1_write; set `req1_addr` to core_req1_addr; set `req1_data` to core_req1_data; set `rn1_l1_req_write` to core_req1_write; set `rn1_l1_req_addr` to core_req1_addr; set `rn1_l1_req_data` to core_req1_data.
- **rn1_complete_req** — when gr1_valid, set `req1_valid` to false.
- **rn1_respond_snp** — when sr1_valid, set `rsp1_valid` to true; set `c1_mstate` to if sr1_op, then 0, otherwise if `c1_mstate` equals 3, then 1, otherwise `c1_mstate`.
- **rn1_clear_snp_rsp** — when not (sr1_valid), set `rsp1_valid` to false.
- **rn1_receive_grant** — when gr1_valid, set `c1_mstate` to if gr1_write, then 3, otherwise 1; set `c1_maddr` to gr1_addr; set `rn1_mdata` to gr1_data; set `rn1_l1_req_write` to true; set `rn1_l1_req_addr` to gr1_addr; set `rn1_l1_req_data` to gr1_data.
- **rn1_l1_write_hit0** — when 0 equals 0 and rn1_l1_req_write and rn1_l1_has_line(`rn1_l1_s0`, `rn1_l1_a0`, rn1_l1_req_addr), set `rn1_l1_s0` to 3; set `rn1_l1_data0` to rn1_l1_req_data; set `rn1_l1_lru` to true.
- **rn1_l1_write_hit1** — when 0 equals 0 and rn1_l1_req_write and not (rn1_l1_has_line(`rn1_l1_s0`, `rn1_l1_a0`, rn1_l1_req_addr)) and rn1_l1_has_line(`rn1_l1_s1`, `rn1_l1_a1`, rn1_l1_req_addr), set `rn1_l1_s1` to 3; set `rn1_l1_data1` to rn1_l1_req_data; set `rn1_l1_lru` to false.
- **rn1_l1_write_miss0** — when 0 equals 0 and rn1_l1_req_write and not (rn1_l1_has_line(`rn1_l1_s0`, `rn1_l1_a0`, rn1_l1_req_addr)) and not (rn1_l1_has_line(`rn1_l1_s1`, `rn1_l1_a1`, rn1_l1_req_addr)) and not (`rn1_l1_lru`), set `rn1_l1_s0` to 3; set `rn1_l1_a0` to rn1_l1_req_addr; set `rn1_l1_data0` to rn1_l1_req_data; set `rn1_l1_lru` to true.
- **rn1_l1_write_miss1** — when 0 equals 0 and rn1_l1_req_write and not (rn1_l1_has_line(`rn1_l1_s0`, `rn1_l1_a0`, rn1_l1_req_addr)) and not (rn1_l1_has_line(`rn1_l1_s1`, `rn1_l1_a1`, rn1_l1_req_addr)) and `rn1_l1_lru`, set `rn1_l1_s1` to 3; set `rn1_l1_a1` to rn1_l1_req_addr; set `rn1_l1_data1` to rn1_l1_req_data; set `rn1_l1_lru` to false.
- **rn1_l1_read_hit0** — when 0 equals 0 and not (rn1_l1_req_write) and rn1_l1_has_line(`rn1_l1_s0`, `rn1_l1_a0`, rn1_l1_req_addr), set `rn1_l1_rdata` to `rn1_l1_data0`; set `rn1_l1_lru` to true.
- **rn1_l1_read_hit1** — when 0 equals 0 and not (rn1_l1_req_write) and not (rn1_l1_has_line(`rn1_l1_s0`, `rn1_l1_a0`, rn1_l1_req_addr)) and rn1_l1_has_line(`rn1_l1_s1`, `rn1_l1_a1`, rn1_l1_req_addr), set `rn1_l1_rdata` to `rn1_l1_data1`; set `rn1_l1_lru` to false.
- **rn1_l1_read_miss0** — when 0 equals 0 and not (rn1_l1_req_write) and not (rn1_l1_has_line(`rn1_l1_s0`, `rn1_l1_a0`, rn1_l1_req_addr)) and not (rn1_l1_has_line(`rn1_l1_s1`, `rn1_l1_a1`, rn1_l1_req_addr)) and not (`rn1_l1_lru`), set `rn1_l1_s0` to 1; set `rn1_l1_a0` to rn1_l1_req_addr.
- **rn1_l1_read_miss1** — when 0 equals 0 and not (rn1_l1_req_write) and not (rn1_l1_has_line(`rn1_l1_s0`, `rn1_l1_a0`, rn1_l1_req_addr)) and not (rn1_l1_has_line(`rn1_l1_s1`, `rn1_l1_a1`, rn1_l1_req_addr)) and `rn1_l1_lru`, set `rn1_l1_s1` to 1; set `rn1_l1_a1` to rn1_l1_req_addr.
- **rn1_l1_snoop_inv0** — when 0 does not equal 0 and rn1_l1_req_write and rn1_l1_has_line(`rn1_l1_s0`, `rn1_l1_a0`, rn1_l1_req_addr), set `rn1_l1_s0` to 0.
- **rn1_l1_snoop_inv1** — when 0 does not equal 0 and rn1_l1_req_write and rn1_l1_has_line(`rn1_l1_s1`, `rn1_l1_a1`, rn1_l1_req_addr), set `rn1_l1_s1` to 0.
- **rn1_l1_snoop_dg0** — when 0 does not equal 0 and not (rn1_l1_req_write) and rn1_l1_has_line(`rn1_l1_s0`, `rn1_l1_a0`, rn1_l1_req_addr), set `rn1_l1_s0` to 1.
- **rn1_l1_snoop_dg1** — when 0 does not equal 0 and not (rn1_l1_req_write) and rn1_l1_has_line(`rn1_l1_s1`, `rn1_l1_a1`, rn1_l1_req_addr), set `rn1_l1_s1` to 1.
- **router_route_req0** — when true, set `rs0_valid` to `req0_valid` and `req0_addr`[0:0] equals 0; set `rs0_core` to false; set `rs0_write` to `req0_write`; set `rs0_addr` to `req0_addr`; set `rs0_data` to `req0_data`; set `rs1_valid` to `req0_valid` and `req0_addr`[0:0] equals 1; set `rs1_core` to false; set `rs1_write` to `req0_write`; set `rs1_addr` to `req0_addr`; set `rs1_data` to `req0_data`.
- **router_route_req1** — when true, set `rs0_valid` to `rs0_valid` or `req1_valid` and `req1_addr`[0:0] equals 0; set `rs1_valid` to `rs1_valid` or `req1_valid` and `req1_addr`[0:0] equals 1; set `rs0_core` to if `req1_valid` and `req1_addr`[0:0] equals 0, then true, otherwise `rs0_core`; set `rs1_core` to if `req1_valid` and `req1_addr`[0:0] equals 1, then true, otherwise `rs1_core`; set `rs0_write` to if `req1_valid` and `req1_addr`[0:0] equals 0, then `req1_write`, otherwise `rs0_write`; set `rs1_write` to if `req1_valid` and `req1_addr`[0:0] equals 1, then `req1_write`, otherwise `rs1_write`; set `rs0_addr` to if `req1_valid` and `req1_addr`[0:0] equals 0, then `req1_addr`, otherwise `rs0_addr`; set `rs1_addr` to if `req1_valid` and `req1_addr`[0:0] equals 1, then `req1_addr`, otherwise `rs1_addr`; set `rs0_data` to if `req1_valid` and `req1_addr`[0:0] equals 0, then `req1_data`, otherwise `rs0_data`; set `rs1_data` to if `req1_valid` and `req1_addr`[0:0] equals 1, then `req1_data`, otherwise `rs1_data`.
- **router_route_snp0** — when true, set `sr0_valid` to `snp0_valid` and not (`snp0_core`); set `sr0_op` to `snp0_op`; set `sr0_addr` to `snp0_addr`; set `sr1_valid` to `snp0_valid` and `snp0_core`; set `sr1_op` to `snp0_op`; set `sr1_addr` to `snp0_addr`.
- **router_route_snp1** — when true, set `sr0_valid` to `sr0_valid` or `snp1_valid` and not (`snp1_core`); set `sr1_valid` to `sr1_valid` or `snp1_valid` and `snp1_core`; set `sr0_op` to if `snp1_valid` and not (`snp1_core`), then `snp1_op`, otherwise `sr0_op`; set `sr1_op` to if `snp1_valid` and `snp1_core`, then `snp1_op`, otherwise `sr1_op`; set `sr0_addr` to if `snp1_valid` and not (`snp1_core`), then `snp1_addr`, otherwise `sr0_addr`; set `sr1_addr` to if `snp1_valid` and `snp1_core`, then `snp1_addr`, otherwise `sr1_addr`; set `router_pending_slice` to if `snp1_valid`, then true, otherwise if `snp0_valid`, then false, otherwise `router_pending_slice`.
- **router_route_grant0** — when true, set `gr0_valid` to `grant0_valid` and not (`grant0_core`); set `gr0_write` to `grant0_write`; set `gr0_addr` to `grant0_addr`; set `gr0_data` to `grant0_data`; set `gr1_valid` to `grant0_valid` and `grant0_core`; set `gr1_write` to `grant0_write`; set `gr1_addr` to `grant0_addr`; set `gr1_data` to `grant0_data`.
- **router_route_grant1** — when true, set `gr0_valid` to `gr0_valid` or `grant1_valid` and not (`grant1_core`); set `gr1_valid` to `gr1_valid` or `grant1_valid` and `grant1_core`; set `gr0_write` to if `grant1_valid` and not (`grant1_core`), then `grant1_write`, otherwise `gr0_write`; set `gr1_write` to if `grant1_valid` and `grant1_core`, then `grant1_write`, otherwise `gr1_write`; set `gr0_addr` to if `grant1_valid` and not (`grant1_core`), then `grant1_addr`, otherwise `gr0_addr`; set `gr1_addr` to if `grant1_valid` and `grant1_core`, then `grant1_addr`, otherwise `gr1_addr`; set `gr0_data` to if `grant1_valid` and not (`grant1_core`), then `grant1_data`, otherwise `gr0_data`; set `gr1_data` to if `grant1_valid` and `grant1_core`, then `grant1_data`, otherwise `gr1_data`.
- **router_route_rsp** — when true, set `ps0_valid` to `rsp0_valid` or `rsp1_valid` and not (`router_pending_slice`); set `ps0_core` to if `rsp1_valid`, then `rsp1_core_sig`, otherwise `rsp0_core_sig`; set `ps0_op` to if `rsp1_valid`, then `rsp1_op_sig`, otherwise `rsp0_op_sig`; set `ps1_valid` to `rsp0_valid` or `rsp1_valid` and `router_pending_slice`; set `ps1_core` to if `rsp1_valid`, then `rsp1_core_sig`, otherwise `rsp0_core_sig`; set `ps1_op` to if `rsp1_valid`, then `rsp1_op_sig`, otherwise `rsp0_op_sig`.
- **slice0_request** — when not (`slice0_pending`) and rs0_valid and `slice0_req_credits` does not equal 0, set `slice0_pending` to true; set `slice0_pending_core` to rs0_core; set `slice0_pending_write` to rs0_write; set `slice0_pending_addr` to rs0_addr; set `slice0_pending_data` to rs0_data; set `slice0_snooped` to false; set `slice0_req_credits` to `slice0_req_credits` − 1; set `snp0_valid` to true; set `snp0_core` to not (rs0_core); set `snp0_addr` to rs0_addr; set `snp0_op` to rs0_write.
- **slice0_snoop** — when `slice0_pending` and not (`slice0_snooped`) and ps0_valid, set `slice0_snooped` to true; set `snp0_valid` to false; set `slice0_c0_state` to if `snp0_core` equals false, then if `snp0_op`, then 0, otherwise 1, otherwise `slice0_c0_state`; set `slice0_c1_state` to if `snp0_core` equals true, then if `snp0_op`, then 0, otherwise 1, otherwise `slice0_c1_state`.
- **slice0_grant** — when `slice0_pending` and `slice0_snooped`, set `grant0_valid` to true; set `grant0_core` to `slice0_pending_core`; set `grant0_write` to `slice0_pending_write`; set `grant0_addr` to `slice0_pending_addr`; set `grant0_data` to `slice0_pending_data`; set `slice0_c0_state` to if `slice0_pending_core` equals false, then if `slice0_pending_write`, then 3, otherwise 1, otherwise `slice0_c0_state`; set `slice0_c0_addr` to if `slice0_pending_core` equals false, then `slice0_pending_addr`, otherwise `slice0_c0_addr`; set `slice0_c1_state` to if `slice0_pending_core` equals true, then if `slice0_pending_write`, then 3, otherwise 1, otherwise `slice0_c1_state`; set `slice0_c1_addr` to if `slice0_pending_core` equals true, then `slice0_pending_addr`, otherwise `slice0_c1_addr`; set `slice0_s0` to if `slice0_lru` equals false, then if `slice0_pending_write`, then 3, otherwise 2, otherwise `slice0_s0`; set `slice0_a0` to if `slice0_lru` equals false, then `slice0_pending_addr`, otherwise `slice0_a0`; set `slice0_d0` to if `slice0_lru` equals false, then rs0_data, otherwise `slice0_d0`; set `slice0_s1` to if `slice0_lru` equals true, then if `slice0_pending_write`, then 3, otherwise 2, otherwise `slice0_s1`; set `slice0_a1` to if `slice0_lru` equals true, then `slice0_pending_addr`, otherwise `slice0_a1`; set `slice0_d1` to if `slice0_lru` equals true, then rs0_data, otherwise `slice0_d1`; set `slice0_lru` to not (`slice0_lru`); set `slice0_pending` to false; set `slice0_snooped` to false; set `slice0_req_credits` to `slice0_req_credits` + 1.
- **slice0_clear_grant** — when not (`slice0_pending` and `slice0_snooped`), set `grant0_valid` to false.
- **slice1_request** — when not (`slice1_pending`) and rs1_valid and `slice1_req_credits` does not equal 0, set `slice1_pending` to true; set `slice1_pending_core` to rs1_core; set `slice1_pending_write` to rs1_write; set `slice1_pending_addr` to rs1_addr; set `slice1_pending_data` to rs1_data; set `slice1_snooped` to false; set `slice1_req_credits` to `slice1_req_credits` − 1; set `snp1_valid` to true; set `snp1_core` to not (rs1_core); set `snp1_addr` to rs1_addr; set `snp1_op` to rs1_write.
- **slice1_snoop** — when `slice1_pending` and not (`slice1_snooped`) and ps1_valid, set `slice1_snooped` to true; set `snp1_valid` to false; set `slice1_c0_state` to if `snp1_core` equals false, then if `snp1_op`, then 0, otherwise 1, otherwise `slice1_c0_state`; set `slice1_c1_state` to if `snp1_core` equals true, then if `snp1_op`, then 0, otherwise 1, otherwise `slice1_c1_state`.
- **slice1_grant** — when `slice1_pending` and `slice1_snooped`, set `grant1_valid` to true; set `grant1_core` to `slice1_pending_core`; set `grant1_write` to `slice1_pending_write`; set `grant1_addr` to `slice1_pending_addr`; set `grant1_data` to `slice1_pending_data`; set `slice1_c0_state` to if `slice1_pending_core` equals false, then if `slice1_pending_write`, then 3, otherwise 1, otherwise `slice1_c0_state`; set `slice1_c0_addr` to if `slice1_pending_core` equals false, then `slice1_pending_addr`, otherwise `slice1_c0_addr`; set `slice1_c1_state` to if `slice1_pending_core` equals true, then if `slice1_pending_write`, then 3, otherwise 1, otherwise `slice1_c1_state`; set `slice1_c1_addr` to if `slice1_pending_core` equals true, then `slice1_pending_addr`, otherwise `slice1_c1_addr`; set `slice1_s0` to if `slice1_lru` equals false, then if `slice1_pending_write`, then 3, otherwise 2, otherwise `slice1_s0`; set `slice1_a0` to if `slice1_lru` equals false, then `slice1_pending_addr`, otherwise `slice1_a0`; set `slice1_d0` to if `slice1_lru` equals false, then rs1_data, otherwise `slice1_d0`; set `slice1_s1` to if `slice1_lru` equals true, then if `slice1_pending_write`, then 3, otherwise 2, otherwise `slice1_s1`; set `slice1_a1` to if `slice1_lru` equals true, then `slice1_pending_addr`, otherwise `slice1_a1`; set `slice1_d1` to if `slice1_lru` equals true, then rs1_data, otherwise `slice1_d1`; set `slice1_lru` to not (`slice1_lru`); set `slice1_pending` to false; set `slice1_snooped` to false; set `slice1_req_credits` to `slice1_req_credits` + 1.
- **slice1_clear_grant** — when not (`slice1_pending` and `slice1_snooped`), set `grant1_valid` to false.

## Properties

- **rn0_has_line_holds_line** (safety): always, if rn0_has_line(`rn0_l1_s0`, `rn0_l1_req_addr`, `rn0_l1_req_addr`), then `rn0_l1_s0` does not equal 0.
- **rn0_is_modified_implies_valid** (safety): always, if rn0_is_modified(`rn0_l1_s0`), then `rn0_l1_s0` does not equal 0.
- **rn0_l1_is_modified_implies_valid** (safety): always, if rn0_l1_is_modified(`rn0_l1_s0`), then `rn0_l1_s0` does not equal 0.
- **rn0_l1_phys_index_bounded** (safety): always, rn0_l1_phys_index(`rn0_l1_req_addr`) ≤ 3.
- **rn1_has_line_holds_line** (safety): always, if rn1_has_line(`rn1_l1_s0`, `rn1_l1_req_addr`, `rn1_l1_req_addr`), then `rn1_l1_s0` does not equal 0.
- **rn1_is_modified_implies_valid** (safety): always, if rn1_is_modified(`rn1_l1_s0`), then `rn1_l1_s0` does not equal 0.
- **rn1_l1_is_modified_implies_valid** (safety): always, if rn1_l1_is_modified(`rn1_l1_s0`), then `rn1_l1_s0` does not equal 0.
- **rn1_l1_phys_index_bounded** (safety): always, rn1_l1_phys_index(`rn1_l1_req_addr`) ≤ 3.
- **slice0_has_line_holds_line** (safety): always, if slice0_has_line(`slice0_c0_state`, `slice0_c0_addr`, `slice0_c0_addr`), then `slice0_c0_state` does not equal 0.
- **slice0_is_modified_implies_valid** (safety): always, if slice0_is_modified(`slice0_c0_state`), then `slice0_c0_state` does not equal 0.
- **slice1_has_line_holds_line** (safety): always, if slice1_has_line(`slice1_c0_state`, `slice1_c0_addr`, `slice1_c0_addr`), then `slice1_c0_state` does not equal 0.
- **slice1_is_modified_implies_valid** (safety): always, if slice1_is_modified(`slice1_c0_state`), then `slice1_c0_state` does not equal 0.
