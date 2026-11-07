# noc_router specification

## Inputs

| Name | Type |
|------|------|
| `req0_valid` | bool |
| `req0_write` | bool |
| `req0_addr` | bits<4> |
| `req0_data` | bits<8> |
| `req1_valid` | bool |
| `req1_write` | bool |
| `req1_addr` | bits<4> |
| `req1_data` | bits<8> |
| `snp0_valid` | bool |
| `snp0_core` | bool |
| `snp0_addr` | bits<4> |
| `snp0_op` | bool |
| `snp1_valid` | bool |
| `snp1_core` | bool |
| `snp1_addr` | bits<4> |
| `snp1_op` | bool |
| `grant0_valid` | bool |
| `grant0_core` | bool |
| `grant0_write` | bool |
| `grant0_addr` | bits<4> |
| `grant0_data` | bits<8> |
| `grant1_valid` | bool |
| `grant1_core` | bool |
| `grant1_write` | bool |
| `grant1_addr` | bits<4> |
| `grant1_data` | bits<8> |
| `rsp0_valid` | bool |
| `rsp0_core` | bool |
| `rsp0_op` | bool |
| `rsp1_valid` | bool |
| `rsp1_core` | bool |
| `rsp1_op` | bool |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
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
| `sr0_valid` | register | bool | false |
| `sr0_op` | register | bool | false |
| `sr0_addr` | register | bits<4> | 0 |
| `sr1_valid` | register | bool | false |
| `sr1_op` | register | bool | false |
| `sr1_addr` | register | bits<4> | 0 |
| `gr0_valid` | register | bool | false |
| `gr0_write` | register | bool | false |
| `gr0_addr` | register | bits<4> | 0 |
| `gr0_data` | register | bits<8> | 0 |
| `gr1_valid` | register | bool | false |
| `gr1_write` | register | bool | false |
| `gr1_addr` | register | bits<4> | 0 |
| `gr1_data` | register | bits<8> | 0 |
| `pending_slice` | register | bool | false |
| `ps0_valid` | register | bool | false |
| `ps0_core` | register | bool | false |
| `ps0_op` | register | bool | false |
| `ps1_valid` | register | bool | false |
| `ps1_core` | register | bool | false |
| `ps1_op` | register | bool | false |

## Behavior (rules)

- **route_req0** — when true, set `rs0_valid` to `req0_valid` and `req0_addr`[0:0] equals 0; set `rs0_core` to false; set `rs0_write` to `req0_write`; set `rs0_addr` to `req0_addr`; set `rs0_data` to `req0_data`; set `rs1_valid` to `req0_valid` and `req0_addr`[0:0] equals 1; set `rs1_core` to false; set `rs1_write` to `req0_write`; set `rs1_addr` to `req0_addr`; set `rs1_data` to `req0_data`.
- **route_req1** — when true, set `rs0_valid` to `rs0_valid` or `req1_valid` and `req1_addr`[0:0] equals 0; set `rs1_valid` to `rs1_valid` or `req1_valid` and `req1_addr`[0:0] equals 1; set `rs0_core` to if `req1_valid` and `req1_addr`[0:0] equals 0, then true, otherwise `rs0_core`; set `rs1_core` to if `req1_valid` and `req1_addr`[0:0] equals 1, then true, otherwise `rs1_core`; set `rs0_write` to if `req1_valid` and `req1_addr`[0:0] equals 0, then `req1_write`, otherwise `rs0_write`; set `rs1_write` to if `req1_valid` and `req1_addr`[0:0] equals 1, then `req1_write`, otherwise `rs1_write`; set `rs0_addr` to if `req1_valid` and `req1_addr`[0:0] equals 0, then `req1_addr`, otherwise `rs0_addr`; set `rs1_addr` to if `req1_valid` and `req1_addr`[0:0] equals 1, then `req1_addr`, otherwise `rs1_addr`; set `rs0_data` to if `req1_valid` and `req1_addr`[0:0] equals 0, then `req1_data`, otherwise `rs0_data`; set `rs1_data` to if `req1_valid` and `req1_addr`[0:0] equals 1, then `req1_data`, otherwise `rs1_data`.
- **route_snp0** — when true, set `sr0_valid` to `snp0_valid` and not (`snp0_core`); set `sr0_op` to `snp0_op`; set `sr0_addr` to `snp0_addr`; set `sr1_valid` to `snp0_valid` and `snp0_core`; set `sr1_op` to `snp0_op`; set `sr1_addr` to `snp0_addr`.
- **route_snp1** — when true, set `sr0_valid` to `sr0_valid` or `snp1_valid` and not (`snp1_core`); set `sr1_valid` to `sr1_valid` or `snp1_valid` and `snp1_core`; set `sr0_op` to if `snp1_valid` and not (`snp1_core`), then `snp1_op`, otherwise `sr0_op`; set `sr1_op` to if `snp1_valid` and `snp1_core`, then `snp1_op`, otherwise `sr1_op`; set `sr0_addr` to if `snp1_valid` and not (`snp1_core`), then `snp1_addr`, otherwise `sr0_addr`; set `sr1_addr` to if `snp1_valid` and `snp1_core`, then `snp1_addr`, otherwise `sr1_addr`; set `pending_slice` to if `snp1_valid`, then true, otherwise if `snp0_valid`, then false, otherwise `pending_slice`.
- **route_grant0** — when true, set `gr0_valid` to `grant0_valid` and not (`grant0_core`); set `gr0_write` to `grant0_write`; set `gr0_addr` to `grant0_addr`; set `gr0_data` to `grant0_data`; set `gr1_valid` to `grant0_valid` and `grant0_core`; set `gr1_write` to `grant0_write`; set `gr1_addr` to `grant0_addr`; set `gr1_data` to `grant0_data`.
- **route_grant1** — when true, set `gr0_valid` to `gr0_valid` or `grant1_valid` and not (`grant1_core`); set `gr1_valid` to `gr1_valid` or `grant1_valid` and `grant1_core`; set `gr0_write` to if `grant1_valid` and not (`grant1_core`), then `grant1_write`, otherwise `gr0_write`; set `gr1_write` to if `grant1_valid` and `grant1_core`, then `grant1_write`, otherwise `gr1_write`; set `gr0_addr` to if `grant1_valid` and not (`grant1_core`), then `grant1_addr`, otherwise `gr0_addr`; set `gr1_addr` to if `grant1_valid` and `grant1_core`, then `grant1_addr`, otherwise `gr1_addr`; set `gr0_data` to if `grant1_valid` and not (`grant1_core`), then `grant1_data`, otherwise `gr0_data`; set `gr1_data` to if `grant1_valid` and `grant1_core`, then `grant1_data`, otherwise `gr1_data`.
- **route_rsp** — when true, set `ps0_valid` to `rsp0_valid` or `rsp1_valid` and not (`pending_slice`); set `ps0_core` to if `rsp1_valid`, then `rsp1_core`, otherwise `rsp0_core`; set `ps0_op` to if `rsp1_valid`, then `rsp1_op`, otherwise `rsp0_op`; set `ps1_valid` to `rsp0_valid` or `rsp1_valid` and `pending_slice`; set `ps1_core` to if `rsp1_valid`, then `rsp1_core`, otherwise `rsp0_core`; set `ps1_op` to if `rsp1_valid`, then `rsp1_op`, otherwise `rsp0_op`.
