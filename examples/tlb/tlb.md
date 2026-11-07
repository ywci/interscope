# tlb specification

## Inputs

| Name | Type |
|------|------|
| `vpn` | bits<4> |
| `ppn_in` | bits<4> |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `way0_vpn` | register | bits<4> | 0 |
| `way0_ppn` | register | bits<4> | 0 |
| `way0_valid` | register | bool | false |
| `way1_vpn` | register | bits<4> | 0 |
| `way1_ppn` | register | bits<4> | 0 |
| `way1_valid` | register | bool | false |
| `lru` | register | bool | false |
| `tlb_ppn` | register | bits<4> | 0 |
| `miss` | register | bool | false |

## Behavior (rules)

- **hit0** — when way_hit(`way0_valid`, `way0_vpn`, vpn), set `tlb_ppn` to `way0_ppn`; set `lru` to true; set `miss` to false.
- **hit1** — when way_hit(`way1_valid`, `way1_vpn`, vpn), set `tlb_ppn` to `way1_ppn`; set `lru` to false; set `miss` to false.
- **fill0** — when not (way_hit(`way0_valid`, `way0_vpn`, vpn)) and not (way_hit(`way1_valid`, `way1_vpn`, vpn)) and not (`lru`), set `way0_vpn` to vpn; set `way0_ppn` to ppn_in; set `way0_valid` to true; set `lru` to true; set `miss` to true.
- **fill1** — when not (way_hit(`way0_valid`, `way0_vpn`, vpn)) and not (way_hit(`way1_valid`, `way1_vpn`, vpn)) and `lru`, set `way1_vpn` to vpn; set `way1_ppn` to ppn_in; set `way1_valid` to true; set `lru` to false; set `miss` to true.

## Properties

- **hit_updates_ppn** (transition): after each step, `tlb_ppn` equals `way0_ppn`.
