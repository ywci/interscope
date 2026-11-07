# ptw specification

## Inputs

| Name | Type |
|------|------|
| `va` | bits<8> |
| `start` | bool |
| `mem_data` | bits<8> |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `root_ppn` | register | bits<4> | 0 |
| `walk_state` | register | bits<2> | 0 |
| `pte1` | register | bits<8> | 0 |
| `pte0` | register | bits<8> | 0 |
| `mem_addr` | register | bits<4> | 0 |
| `result_ppn` | register | bits<4> | 0 |
| `result_pa` | register | bits<8> | 0 |

## Behavior (rules)

- **walk_start** — when `walk_state` equals 0 and start, set `mem_addr` to concat(`root_ppn`[1:0], vpn1(va), 2); set `walk_state` to 1.
- **walk_l0** — when `walk_state` equals 1, set `pte1` to mem_data; set `mem_addr` to concat(pte_ppn(mem_data)[1:0], vpn0(va), 2); set `walk_state` to 2.
- **walk_finish** — when `walk_state` equals 2, set `pte0` to mem_data; set `result_ppn` to pte_ppn(mem_data); set `result_pa` to concat(pte_ppn(mem_data), offset(va), 4); set `walk_state` to 3.
- **walk_reset** — when `walk_state` equals 3, set `walk_state` to 0.

## Properties

- **ppn_from_leaf** (transition): after each step, `result_ppn` equals pte_ppn(`pte0`).
