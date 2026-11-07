# chi_multicore specification

## Inputs

| Name | Type |
|------|------|
| `req_valid0` | bool |
| `req_write0` | bool |
| `req_addr0` | bits<4> |
| `req_data0` | bits<8> |
| `addr0` | bits<4> |
| `va0` | bits<8> |
| `req_valid1` | bool |
| `req_write1` | bool |
| `req_addr1` | bits<4> |
| `req_data1` | bits<8> |
| `addr1` | bits<4> |
| `va1` | bits<8> |
| `rn0_core_req_valid` | bool |
| `rn0_core_req_write` | bool |
| `rn0_core_req_addr` | bits<4> |
| `rn0_core_req_data` | bits<8> |
| `rn1_core_req_valid` | bool |
| `rn1_core_req_write` | bool |
| `rn1_core_req_addr` | bits<4> |
| `rn1_core_req_data` | bits<8> |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `req_valid_signal` | register | bool | false |
| `req_write_signal` | register | bool | false |
| `req_addr_signal` | register | bits<4> | 0 |
| `req_core_signal` | register | bool | false |
| `req_data_signal` | register | bits<8> | 0 |
| `snp_rsp_signal` | register | bool | false |
| `snp_valid_signal` | register | bool | false |
| `snp_core_signal` | register | bool | false |
| `snp_addr_signal` | register | bits<4> | 0 |
| `snp_op_signal` | register | bool | false |
| `snp0_valid_signal` | register | bool | false |
| `snp1_valid_signal` | register | bool | false |
| `grant_valid_signal` | register | bool | false |
| `grant_core_signal` | register | bool | false |
| `grant_write_signal` | register | bool | false |
| `grant_addr_signal` | register | bits<4> | 0 |
| `grant0_valid_signal` | register | bool | false |
| `grant1_valid_signal` | register | bool | false |
| `req_out0` | register | bool | false |
| `req_out0_write` | register | bool | false |
| `req_out0_addr` | register | bits<4> | 0 |
| `req_out0_data` | register | bits<8> | 0 |
| `req_out1` | register | bool | false |
| `req_out1_write` | register | bool | false |
| `req_out1_addr` | register | bits<4> | 0 |
| `req_out1_data` | register | bits<8> | 0 |
| `snp_rsp0` | register | bool | false |
| `snp_rsp1` | register | bool | false |
| `c0_mstate_signal` | register | bits<2> | 0 |
| `c0_maddr_signal` | register | bits<4> | 0 |
| `c1_mstate_signal` | register | bits<2> | 0 |
| `c1_maddr_signal` | register | bits<4> | 0 |
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
| `home_c0_state` | register | bits<2> | 0 |
| `home_c0_addr` | register | bits<4> | 0 |
| `home_c1_state` | register | bits<2> | 0 |
| `home_c1_addr` | register | bits<4> | 0 |
| `home_pending` | register | bool | false |
| `home_pending_core` | register | bool | false |
| `home_pending_write` | register | bool | false |
| `home_pending_addr` | register | bits<4> | 0 |
| `home_snooped` | register | bool | false |
| `home_req_credits` | register | bits<2> | 2 |

## Behavior (rules)

- **mux_req** — when true, set `req_valid_signal` to `req_out0` or `req_out1`; set `req_core_signal` to `req_out1`; set `req_write_signal` to if `req_out1`, then `req_out1_write`, otherwise `req_out0_write`; set `req_addr_signal` to if `req_out1`, then `req_out1_addr`, otherwise `req_out0_addr`; set `req_data_signal` to if `req_out1`, then `req_out1_data`, otherwise `req_out0_data`.
- **mux_rsp** — when true, set `snp_rsp_signal` to `snp_rsp0` or `snp_rsp1`.
- **demux_snp** — when true, set `snp0_valid_signal` to `snp_valid_signal` and not (`snp_core_signal`); set `snp1_valid_signal` to `snp_valid_signal` and `snp_core_signal`.
- **demux_grant** — when true, set `grant0_valid_signal` to `grant_valid_signal` and not (`grant_core_signal`); set `grant1_valid_signal` to `grant_valid_signal` and `grant_core_signal`.
- **rn0_issue_req** — when rn0_core_req_valid, set `req_out0` to true; set `req_out0_write` to rn0_core_req_write; set `req_out0_addr` to rn0_core_req_addr; set `req_out0_data` to rn0_core_req_data; set `rn0_l1_req_write` to rn0_core_req_write; set `rn0_l1_req_addr` to rn0_core_req_addr; set `rn0_l1_req_data` to rn0_core_req_data.
- **rn0_complete_req** — when grant0_valid_signal, set `req_out0` to false.
- **rn0_respond_snp** — when snp0_valid_signal, set `snp_rsp0` to true; set `c0_mstate_signal` to if snp_op_signal, then 0, otherwise if `c0_mstate_signal` equals 3, then 1, otherwise `c0_mstate_signal`.
- **rn0_clear_snp_rsp** — when not (snp0_valid_signal), set `snp_rsp0` to false.
- **rn0_receive_grant** — when grant0_valid_signal, set `c0_mstate_signal` to if grant_write_signal, then 3, otherwise 1; set `c0_maddr_signal` to grant_addr_signal; set `rn0_mdata` to 0; set `rn0_l1_req_write` to true; set `rn0_l1_req_addr` to grant_addr_signal; set `rn0_l1_req_data` to 0.
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
- **rn1_issue_req** — when rn1_core_req_valid, set `req_out1` to true; set `req_out1_write` to rn1_core_req_write; set `req_out1_addr` to rn1_core_req_addr; set `req_out1_data` to rn1_core_req_data; set `rn1_l1_req_write` to rn1_core_req_write; set `rn1_l1_req_addr` to rn1_core_req_addr; set `rn1_l1_req_data` to rn1_core_req_data.
- **rn1_complete_req** — when grant1_valid_signal, set `req_out1` to false.
- **rn1_respond_snp** — when snp1_valid_signal, set `snp_rsp1` to true; set `c1_mstate_signal` to if snp_op_signal, then 0, otherwise if `c1_mstate_signal` equals 3, then 1, otherwise `c1_mstate_signal`.
- **rn1_clear_snp_rsp** — when not (snp1_valid_signal), set `snp_rsp1` to false.
- **rn1_receive_grant** — when grant1_valid_signal, set `c1_mstate_signal` to if grant_write_signal, then 3, otherwise 1; set `c1_maddr_signal` to grant_addr_signal; set `rn1_mdata` to 0; set `rn1_l1_req_write` to true; set `rn1_l1_req_addr` to grant_addr_signal; set `rn1_l1_req_data` to 0.
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
- **home_request** — when not (`home_pending`) and req_valid_signal and `home_req_credits` does not equal 0, set `home_pending` to true; set `home_pending_core` to req_core_signal; set `home_pending_write` to req_write_signal; set `home_pending_addr` to req_addr_signal; set `home_snooped` to false; set `home_req_credits` to `home_req_credits` − 1; set `snp_valid_signal` to true; set `snp_core_signal` to not (req_core_signal); set `snp_addr_signal` to req_addr_signal; set `snp_op_signal` to req_write_signal.
- **home_snoop** — when `home_pending` and not (`home_snooped`) and snp_rsp_signal, set `home_snooped` to true; set `snp_valid_signal` to false; set `home_c0_state` to if `snp_core_signal` equals false, then if `snp_op_signal`, then 0, otherwise 1, otherwise `home_c0_state`; set `home_c1_state` to if `snp_core_signal` equals true, then if `snp_op_signal`, then 0, otherwise 1, otherwise `home_c1_state`.
- **home_grant** — when `home_pending` and `home_snooped`, set `grant_valid_signal` to true; set `grant_core_signal` to `home_pending_core`; set `grant_write_signal` to `home_pending_write`; set `grant_addr_signal` to `home_pending_addr`; set `home_c0_state` to if `home_pending_core` equals false, then if `home_pending_write`, then 3, otherwise 1, otherwise `home_c0_state`; set `home_c0_addr` to if `home_pending_core` equals false, then `home_pending_addr`, otherwise `home_c0_addr`; set `home_c1_state` to if `home_pending_core` equals true, then if `home_pending_write`, then 3, otherwise 1, otherwise `home_c1_state`; set `home_c1_addr` to if `home_pending_core` equals true, then `home_pending_addr`, otherwise `home_c1_addr`; set `home_pending` to false; set `home_snooped` to false; set `home_req_credits` to `home_req_credits` + 1.
- **home_clear_grant** — when not (`home_pending` and `home_snooped`), set `grant_valid_signal` to false.

## Properties

- **home_has_line_holds_line** (safety): always, if home_has_line(`home_c0_state`, `home_c0_addr`, `home_c0_addr`), then `home_c0_state` does not equal 0.
- **home_is_modified_implies_valid** (safety): always, if home_is_modified(`home_c0_state`), then `home_c0_state` does not equal 0.
- **rn0_has_line_holds_line** (safety): always, if rn0_has_line(`rn0_l1_s0`, `rn0_l1_req_addr`, `rn0_l1_req_addr`), then `rn0_l1_s0` does not equal 0.
- **rn0_is_modified_implies_valid** (safety): always, if rn0_is_modified(`rn0_l1_s0`), then `rn0_l1_s0` does not equal 0.
- **rn0_l1_is_modified_implies_valid** (safety): always, if rn0_l1_is_modified(`rn0_l1_s0`), then `rn0_l1_s0` does not equal 0.
- **rn0_l1_phys_index_bounded** (safety): always, rn0_l1_phys_index(`rn0_l1_req_addr`) ≤ 3.
- **rn1_has_line_holds_line** (safety): always, if rn1_has_line(`rn1_l1_s0`, `rn1_l1_req_addr`, `rn1_l1_req_addr`), then `rn1_l1_s0` does not equal 0.
- **rn1_is_modified_implies_valid** (safety): always, if rn1_is_modified(`rn1_l1_s0`), then `rn1_l1_s0` does not equal 0.
- **rn1_l1_is_modified_implies_valid** (safety): always, if rn1_l1_is_modified(`rn1_l1_s0`), then `rn1_l1_s0` does not equal 0.
- **rn1_l1_phys_index_bounded** (safety): always, rn1_l1_phys_index(`rn1_l1_req_addr`) ≤ 3.
