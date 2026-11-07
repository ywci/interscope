# multicore_chi specification

## Inputs

| Name | Type |
|------|------|
| `req_core` | bits<4> |
| `req_write` | bool |
| `req_addr` | bits<4> |
| `req_data` | bits<8> |
| `rn0_req_valid` | bool |
| `rn0_req_write` | bool |
| `rn0_req_addr` | bits<4> |
| `rn0_req_data` | bits<8> |
| `rn0_snp_valid` | bool |
| `rn0_snp_op` | bool |
| `rn0_snp_addr` | bits<4> |
| `rn0_grant_valid` | bool |
| `rn0_grant_write` | bool |
| `rn0_grant_addr` | bits<4> |
| `rn0_grant_data` | bits<8> |
| `rn1_req_valid` | bool |
| `rn1_req_write` | bool |
| `rn1_req_addr` | bits<4> |
| `rn1_req_data` | bits<8> |
| `rn1_snp_valid` | bool |
| `rn1_snp_op` | bool |
| `rn1_snp_addr` | bits<4> |
| `rn1_grant_valid` | bool |
| `rn1_grant_write` | bool |
| `rn1_grant_addr` | bits<4> |
| `rn1_grant_data` | bits<8> |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `c0_mstate_signal` | register | bits<2> | 0 |
| `c0_maddr_signal` | register | bits<4> | 0 |
| `c1_mstate_signal` | register | bits<2> | 0 |
| `c1_maddr_signal` | register | bits<4> | 0 |
| `rn0_mdata` | register | bits<8> | 0 |
| `rn0_req_out_valid` | register | bool | false |
| `rn0_req_out_write` | register | bool | false |
| `rn0_req_out_addr` | register | bits<4> | 0 |
| `rn0_req_out_data` | register | bits<8> | 0 |
| `rn0_snp_rsp_valid` | register | bool | false |
| `rn1_mdata` | register | bits<8> | 0 |
| `rn1_req_out_valid` | register | bool | false |
| `rn1_req_out_write` | register | bool | false |
| `rn1_req_out_addr` | register | bits<4> | 0 |
| `rn1_req_out_data` | register | bits<8> | 0 |
| `rn1_snp_rsp_valid` | register | bool | false |
| `home_c0_data` | register | bits<8> | 0 |
| `home_c1_data` | register | bits<8> | 0 |

## Behavior (rules)

- **rn0_issue_req** — when rn0_req_valid, set `rn0_req_out_valid` to true; set `rn0_req_out_write` to rn0_req_write; set `rn0_req_out_addr` to rn0_req_addr; set `rn0_req_out_data` to rn0_req_data.
- **rn0_complete_req** — when rn0_grant_valid, set `rn0_req_out_valid` to false.
- **rn0_respond_snp** — when rn0_snp_valid, set `rn0_snp_rsp_valid` to true; set `c0_mstate_signal` to if rn0_snp_op, then 0, otherwise if `c0_mstate_signal` equals 3, then 1, otherwise `c0_mstate_signal`.
- **rn0_clear_snp_rsp** — when not (rn0_snp_valid), set `rn0_snp_rsp_valid` to false.
- **rn0_receive_grant** — when rn0_grant_valid, set `c0_mstate_signal` to if rn0_grant_write, then 3, otherwise 1; set `c0_maddr_signal` to rn0_grant_addr; set `rn0_mdata` to rn0_grant_data.
- **rn1_issue_req** — when rn1_req_valid, set `rn1_req_out_valid` to true; set `rn1_req_out_write` to rn1_req_write; set `rn1_req_out_addr` to rn1_req_addr; set `rn1_req_out_data` to rn1_req_data.
- **rn1_complete_req** — when rn1_grant_valid, set `rn1_req_out_valid` to false.
- **rn1_respond_snp** — when rn1_snp_valid, set `rn1_snp_rsp_valid` to true; set `c1_mstate_signal` to if rn1_snp_op, then 0, otherwise if `c1_mstate_signal` equals 3, then 1, otherwise `c1_mstate_signal`.
- **rn1_clear_snp_rsp** — when not (rn1_snp_valid), set `rn1_snp_rsp_valid` to false.
- **rn1_receive_grant** — when rn1_grant_valid, set `c1_mstate_signal` to if rn1_grant_write, then 3, otherwise 1; set `c1_maddr_signal` to rn1_grant_addr; set `rn1_mdata` to rn1_grant_data.
- **home_write0** — when req_core equals 0 and req_write, set `c1_mstate_signal` to if home_has_line(`c1_mstate_signal`, `c1_maddr_signal`, req_addr) and 1 does not equal 0, then 0, otherwise `c1_mstate_signal`; set `c0_mstate_signal` to 3; set `c0_maddr_signal` to req_addr; set `home_c0_data` to req_data.
- **home_write1** — when req_core equals 1 and req_write, set `c0_mstate_signal` to if home_has_line(`c0_mstate_signal`, `c0_maddr_signal`, req_addr) and 0 does not equal 1, then 0, otherwise `c0_mstate_signal`; set `c1_mstate_signal` to 3; set `c1_maddr_signal` to req_addr; set `home_c1_data` to req_data.
- **home_read_hit0** — when req_core equals 0 and not (req_write) and home_has_line(`c0_mstate_signal`, `c0_maddr_signal`, req_addr), set `c0_mstate_signal` to `c0_mstate_signal`.
- **home_read_hit1** — when req_core equals 1 and not (req_write) and home_has_line(`c1_mstate_signal`, `c1_maddr_signal`, req_addr), set `c1_mstate_signal` to `c1_mstate_signal`.
- **home_read_miss0** — when req_core equals 0 and not (req_write) and not (home_has_line(`c0_mstate_signal`, `c0_maddr_signal`, req_addr)), set `c1_mstate_signal` to if home_has_line(`c1_mstate_signal`, `c1_maddr_signal`, req_addr) and 1 does not equal 0, then 1, otherwise `c1_mstate_signal`; set `c0_mstate_signal` to 1; set `c0_maddr_signal` to req_addr.
- **home_read_miss1** — when req_core equals 1 and not (req_write) and not (home_has_line(`c1_mstate_signal`, `c1_maddr_signal`, req_addr)), set `c0_mstate_signal` to if home_has_line(`c0_mstate_signal`, `c0_maddr_signal`, req_addr) and 0 does not equal 1, then 1, otherwise `c0_mstate_signal`; set `c1_mstate_signal` to 1; set `c1_maddr_signal` to req_addr.

## Properties

- **home_is_exclusive_implies_valid** (safety): always, if home_is_exclusive(`c0_mstate_signal`), then `c0_mstate_signal` does not equal 0.
- **home_is_modified_implies_valid** (safety): always, if home_is_modified(`c0_mstate_signal`), then `c0_mstate_signal` does not equal 0.
- **rn0_has_line_holds_line** (safety): always, if rn0_has_line(`c0_mstate_signal`, `rn0_req_out_addr`, `rn0_req_out_addr`), then `c0_mstate_signal` does not equal 0.
- **rn0_is_modified_implies_valid** (safety): always, if rn0_is_modified(`c0_mstate_signal`), then `c0_mstate_signal` does not equal 0.
- **rn1_has_line_holds_line** (safety): always, if rn1_has_line(`c0_mstate_signal`, `rn1_req_out_addr`, `rn1_req_out_addr`), then `c0_mstate_signal` does not equal 0.
- **rn1_is_modified_implies_valid** (safety): always, if rn1_is_modified(`c0_mstate_signal`), then `c0_mstate_signal` does not equal 0.
- **single_writer** (safety): always, not (`c0_mstate_signal` equals 3 and `c1_mstate_signal` equals 3 and `c0_maddr_signal` equals `c1_maddr_signal`).
- **m_exclusive** (safety): always, not (`c0_mstate_signal` equals 3 and `c1_mstate_signal` does not equal 0 and `c1_maddr_signal` equals `c0_maddr_signal`) and not (`c1_mstate_signal` equals 3 and `c0_mstate_signal` does not equal 0 and `c0_maddr_signal` equals `c1_maddr_signal`).
- **e_exclusive** (safety): always, not (`c0_mstate_signal` equals 2 and `c1_mstate_signal` does not equal 0 and `c1_maddr_signal` equals `c0_maddr_signal`) and not (`c1_mstate_signal` equals 2 and `c0_mstate_signal` does not equal 0 and `c0_maddr_signal` equals `c1_maddr_signal`).
