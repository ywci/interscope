# chi_home specification

## Inputs

| Name | Type |
|------|------|
| `req_valid` | bool |
| `req_write` | bool |
| `req_addr` | bits<4> |
| `req_core` | bool |
| `req_data` | bits<8> |
| `snp_rsp_valid` | bool |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `c0_state` | register | bits<2> | 0 |
| `c0_addr` | register | bits<4> | 0 |
| `c1_state` | register | bits<2> | 0 |
| `c1_addr` | register | bits<4> | 0 |
| `pending` | register | bool | false |
| `pending_core` | register | bool | false |
| `pending_write` | register | bool | false |
| `pending_addr` | register | bits<4> | 0 |
| `snooped` | register | bool | false |
| `req_credits` | register | bits<2> | 2 |
| `snp_valid` | register | bool | false |
| `snp_core` | register | bool | false |
| `snp_addr` | register | bits<4> | 0 |
| `snp_op` | register | bool | false |
| `grant_valid` | register | bool | false |
| `grant_core` | register | bool | false |
| `grant_write` | register | bool | false |
| `grant_addr` | register | bits<4> | 0 |

## Behavior (rules)

- **request** — when not (`pending`) and req_valid and `req_credits` does not equal 0, set `pending` to true; set `pending_core` to req_core; set `pending_write` to req_write; set `pending_addr` to req_addr; set `snooped` to false; set `req_credits` to `req_credits` − 1; set `snp_valid` to true; set `snp_core` to not (req_core); set `snp_addr` to req_addr; set `snp_op` to req_write.
- **snoop** — when `pending` and not (`snooped`) and snp_rsp_valid, set `snooped` to true; set `snp_valid` to false; set `c0_state` to if `snp_core` equals false, then if `snp_op`, then 0, otherwise 1, otherwise `c0_state`; set `c1_state` to if `snp_core` equals true, then if `snp_op`, then 0, otherwise 1, otherwise `c1_state`.
- **grant** — when `pending` and `snooped`, set `grant_valid` to true; set `grant_core` to `pending_core`; set `grant_write` to `pending_write`; set `grant_addr` to `pending_addr`; set `c0_state` to if `pending_core` equals false, then if `pending_write`, then 3, otherwise 1, otherwise `c0_state`; set `c0_addr` to if `pending_core` equals false, then `pending_addr`, otherwise `c0_addr`; set `c1_state` to if `pending_core` equals true, then if `pending_write`, then 3, otherwise 1, otherwise `c1_state`; set `c1_addr` to if `pending_core` equals true, then `pending_addr`, otherwise `c1_addr`; set `pending` to false; set `snooped` to false; set `req_credits` to `req_credits` + 1.
- **clear_grant** — when not (`pending` and `snooped`), set `grant_valid` to false.

## Properties

- **has_line_holds_line** (safety): always, if has_line(`c0_state`, `c0_addr`, `c0_addr`), then `c0_state` does not equal 0.
