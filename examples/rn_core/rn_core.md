# rn_core specification

## Inputs

| Name | Type |
|------|------|
| `req_valid` | bool |
| `req_write` | bool |
| `req_addr` | bits<4> |
| `req_data` | bits<8> |
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

## Behavior (rules)

- **issue_req** — when req_valid, set `req_out_valid` to true; set `req_out_write` to req_write; set `req_out_addr` to req_addr; set `req_out_data` to req_data.
- **complete_req** — when grant_valid, set `req_out_valid` to false.
- **respond_snp** — when snp_valid, set `snp_rsp_valid` to true; set `mstate` to if snp_op, then 0, otherwise if `mstate` equals 3, then 1, otherwise `mstate`.
- **clear_snp_rsp** — when not (snp_valid), set `snp_rsp_valid` to false.
- **receive_grant** — when grant_valid, set `mstate` to if grant_write, then 3, otherwise 1; set `maddr` to grant_addr; set `mdata` to grant_data.

## Properties

- **has_line_holds_line** (safety): always, if has_line(`mstate`, `maddr`, `maddr`), then `mstate` does not equal 0.
- **is_modified_implies_valid** (safety): always, if is_modified(`mstate`), then `mstate` does not equal 0.
- **states_valid** (safety): always, `mstate` ≥ 0 and `mstate` ≤ 3.
