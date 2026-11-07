# l2_slice specification

## Inputs

| Name | Type |
|------|------|
| `req_valid` | bool |
| `req_core` | bool |
| `req_write` | bool |
| `req_addr` | bits<4> |
| `req_data` | bits<8> |
| `rsp_valid` | bool |
| `rsp_core` | bool |
| `rsp_op` | bool |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `c0_state` | register | bits<2> | 0 |
| `c0_addr` | register | bits<4> | 0 |
| `c1_state` | register | bits<2> | 0 |
| `c1_addr` | register | bits<4> | 0 |
| `s0` | register | bits<2> | 0 |
| `a0` | register | bits<4> | 0 |
| `d0` | register | bits<8> | 0 |
| `s1` | register | bits<2> | 0 |
| `a1` | register | bits<4> | 0 |
| `d1` | register | bits<8> | 0 |
| `lru` | register | bool | false |
| `pending` | register | bool | false |
| `snooped` | register | bool | false |
| `pending_core` | register | bool | false |
| `pending_write` | register | bool | false |
| `pending_addr` | register | bits<4> | 0 |
| `pending_data` | register | bits<8> | 0 |
| `req_credits` | register | bits<2> | 2 |
| `snp_valid` | register | bool | false |
| `snp_core` | register | bool | false |
| `snp_addr` | register | bits<4> | 0 |
| `snp_op` | register | bool | false |
| `grant_valid` | register | bool | false |
| `grant_core` | register | bool | false |
| `grant_write` | register | bool | false |
| `grant_addr` | register | bits<4> | 0 |
| `grant_data` | register | bits<8> | 0 |

## Behavior (rules)

- **request** — when not (`pending`) and req_valid and `req_credits` does not equal 0, set `pending` to true; set `pending_core` to req_core; set `pending_write` to req_write; set `pending_addr` to req_addr; set `pending_data` to req_data; set `snooped` to false; set `req_credits` to `req_credits` − 1; set `snp_valid` to true; set `snp_core` to not (req_core); set `snp_addr` to req_addr; set `snp_op` to req_write.
- **snoop** — when `pending` and not (`snooped`) and rsp_valid, set `snooped` to true; set `snp_valid` to false; set `c0_state` to if `snp_core` equals false, then if `snp_op`, then 0, otherwise 1, otherwise `c0_state`; set `c1_state` to if `snp_core` equals true, then if `snp_op`, then 0, otherwise 1, otherwise `c1_state`.
- **grant** — when `pending` and `snooped`, set `grant_valid` to true; set `grant_core` to `pending_core`; set `grant_write` to `pending_write`; set `grant_addr` to `pending_addr`; set `grant_data` to `pending_data`; set `c0_state` to if `pending_core` equals false, then if `pending_write`, then 3, otherwise 1, otherwise `c0_state`; set `c0_addr` to if `pending_core` equals false, then `pending_addr`, otherwise `c0_addr`; set `c1_state` to if `pending_core` equals true, then if `pending_write`, then 3, otherwise 1, otherwise `c1_state`; set `c1_addr` to if `pending_core` equals true, then `pending_addr`, otherwise `c1_addr`; set `s0` to if `lru` equals false, then if `pending_write`, then 3, otherwise 2, otherwise `s0`; set `a0` to if `lru` equals false, then `pending_addr`, otherwise `a0`; set `d0` to if `lru` equals false, then req_data, otherwise `d0`; set `s1` to if `lru` equals true, then if `pending_write`, then 3, otherwise 2, otherwise `s1`; set `a1` to if `lru` equals true, then `pending_addr`, otherwise `a1`; set `d1` to if `lru` equals true, then req_data, otherwise `d1`; set `lru` to not (`lru`); set `pending` to false; set `snooped` to false; set `req_credits` to `req_credits` + 1.
- **clear_grant** — when not (`pending` and `snooped`), set `grant_valid` to false.

## Properties

- **has_line_holds_line** (safety): always, if has_line(`c0_state`, `c0_addr`, `c0_addr`), then `c0_state` does not equal 0.
- **single_writer** (safety): always, not (is_modified(`c0_state`) and is_modified(`c1_state`) and `c0_addr` equals `c1_addr`).
- **l2_states_valid** (safety): always, `s0` ≥ 0 and `s0` ≤ 3 and `s1` ≥ 0 and `s1` ≤ 3.
