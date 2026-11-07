# mshr_comp specification

## Inputs

| Name | Type |
|------|------|
| `alloc_valid` | bool |
| `id` | bits<2> |
| `addr` | bits<4> |
| `data` | bits<8> |
| `release0` | bool |
| `release1` | bool |
| `arb_req2_valid` | bool |
| `arb_req3_valid` | bool |
| `arb_req4_valid` | bool |
| `arb_req5_valid` | bool |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `mshr0_valid` | register | bool | false |
| `mshr0_mid` | register | bits<2> | 0 |
| `mshr0_maddr` | register | bits<4> | 0 |
| `mshr0_mdata` | register | bits<8> | 0 |
| `mshr1_valid` | register | bool | false |
| `mshr1_mid` | register | bits<2> | 0 |
| `mshr1_maddr` | register | bits<4> | 0 |
| `mshr1_mdata` | register | bits<8> | 0 |
| `arb_grant` | register | bits<3> | 0 |
| `arb_grant_valid` | register | bool | false |

## Behavior (rules)

- **mshr0_alloc** — when alloc_valid and not (`mshr0_valid`), set `mshr0_valid` to true; set `mshr0_mid` to id; set `mshr0_maddr` to addr; set `mshr0_mdata` to data.
- **mshr0_rel** — when release0, set `mshr0_valid` to false.
- **mshr1_alloc** — when alloc_valid and not (`mshr1_valid`), set `mshr1_valid` to true; set `mshr1_mid` to id; set `mshr1_maddr` to addr; set `mshr1_mdata` to data.
- **mshr1_rel** — when release1, set `mshr1_valid` to false.
- **arb_arbitrate** — when true, set `arb_grant` to if alloc_valid, then 0, otherwise if alloc_valid, then 1, otherwise if arb_req2_valid, then 2, otherwise if arb_req3_valid, then 3, otherwise if arb_req4_valid, then 4, otherwise if arb_req5_valid, then 5, otherwise 0; set `arb_grant_valid` to alloc_valid or alloc_valid or arb_req2_valid or arb_req3_valid or arb_req4_valid or arb_req5_valid.

## Properties

- **arb_grants_on_alloc** (transition): after each step, if alloc_valid, then `arb_grant_valid` equals true.
