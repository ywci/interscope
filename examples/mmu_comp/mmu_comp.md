# mmu_comp specification

## Inputs

| Name | Type |
|------|------|
| `i_vpn` | bits<4> |
| `d_vpn` | bits<4> |
| `va` | bits<8> |
| `ptw_mem_data` | bits<8> |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `ptw_mem_addr` | register | bits<4> | 0 |
| `ptw_active` | register | bool | false |
| `ppn_fill` | register | bits<4> | 0 |
| `i_ppn` | register | bits<4> | 0 |
| `d_ppn` | register | bits<4> | 0 |
| `i_miss` | register | bool | false |
| `d_miss` | register | bool | false |
| `miss_signal` | register | bool | false |
| `ptw_ppn` | register | bits<4> | 0 |
| `itlb_way0_vpn` | register | bits<4> | 0 |
| `itlb_way0_ppn` | register | bits<4> | 0 |
| `itlb_way0_valid` | register | bool | false |
| `itlb_way1_vpn` | register | bits<4> | 0 |
| `itlb_way1_ppn` | register | bits<4> | 0 |
| `itlb_way1_valid` | register | bool | false |
| `itlb_lru` | register | bool | false |
| `dtlb_way0_vpn` | register | bits<4> | 0 |
| `dtlb_way0_ppn` | register | bits<4> | 0 |
| `dtlb_way0_valid` | register | bool | false |
| `dtlb_way1_vpn` | register | bits<4> | 0 |
| `dtlb_way1_ppn` | register | bits<4> | 0 |
| `dtlb_way1_valid` | register | bool | false |
| `dtlb_lru` | register | bool | false |
| `ptw_root_ppn` | register | bits<4> | 0 |
| `ptw_walk_state` | register | bits<2> | 0 |
| `ptw_pte1` | register | bits<8> | 0 |
| `ptw_pte0` | register | bits<8> | 0 |
| `ptw_result_pa` | register | bits<8> | 0 |

## Behavior (rules)

- **combine_miss** — when true, set `miss_signal` to `i_miss` or `d_miss`.
- **slice_ppn** — when true, set `ppn_fill` to `ptw_ppn`.
- **ptw_is_active** — when true, set `ptw_active` to `ptw_walk_state` does not equal 0.
- **itlb_hit0** — when itlb_way_hit(`itlb_way0_valid`, `itlb_way0_vpn`, i_vpn), set `i_ppn` to `itlb_way0_ppn`; set `itlb_lru` to true; set `i_miss` to false.
- **itlb_hit1** — when itlb_way_hit(`itlb_way1_valid`, `itlb_way1_vpn`, i_vpn), set `i_ppn` to `itlb_way1_ppn`; set `itlb_lru` to false; set `i_miss` to false.
- **itlb_fill0** — when not (itlb_way_hit(`itlb_way0_valid`, `itlb_way0_vpn`, i_vpn)) and not (itlb_way_hit(`itlb_way1_valid`, `itlb_way1_vpn`, i_vpn)) and not (`itlb_lru`), set `itlb_way0_vpn` to i_vpn; set `itlb_way0_ppn` to ppn_fill; set `itlb_way0_valid` to true; set `itlb_lru` to true; set `i_miss` to true.
- **itlb_fill1** — when not (itlb_way_hit(`itlb_way0_valid`, `itlb_way0_vpn`, i_vpn)) and not (itlb_way_hit(`itlb_way1_valid`, `itlb_way1_vpn`, i_vpn)) and `itlb_lru`, set `itlb_way1_vpn` to i_vpn; set `itlb_way1_ppn` to ppn_fill; set `itlb_way1_valid` to true; set `itlb_lru` to false; set `i_miss` to true.
- **dtlb_hit0** — when dtlb_way_hit(`dtlb_way0_valid`, `dtlb_way0_vpn`, d_vpn), set `d_ppn` to `dtlb_way0_ppn`; set `dtlb_lru` to true; set `d_miss` to false.
- **dtlb_hit1** — when dtlb_way_hit(`dtlb_way1_valid`, `dtlb_way1_vpn`, d_vpn), set `d_ppn` to `dtlb_way1_ppn`; set `dtlb_lru` to false; set `d_miss` to false.
- **dtlb_fill0** — when not (dtlb_way_hit(`dtlb_way0_valid`, `dtlb_way0_vpn`, d_vpn)) and not (dtlb_way_hit(`dtlb_way1_valid`, `dtlb_way1_vpn`, d_vpn)) and not (`dtlb_lru`), set `dtlb_way0_vpn` to d_vpn; set `dtlb_way0_ppn` to ppn_fill; set `dtlb_way0_valid` to true; set `dtlb_lru` to true; set `d_miss` to true.
- **dtlb_fill1** — when not (dtlb_way_hit(`dtlb_way0_valid`, `dtlb_way0_vpn`, d_vpn)) and not (dtlb_way_hit(`dtlb_way1_valid`, `dtlb_way1_vpn`, d_vpn)) and `dtlb_lru`, set `dtlb_way1_vpn` to d_vpn; set `dtlb_way1_ppn` to ppn_fill; set `dtlb_way1_valid` to true; set `dtlb_lru` to false; set `d_miss` to true.
- **ptw_walk_start** — when `ptw_walk_state` equals 0 and miss_signal, set `ptw_mem_addr` to concat(`ptw_root_ppn`[1:0], ptw_vpn1(va), 2); set `ptw_walk_state` to 1.
- **ptw_walk_l0** — when `ptw_walk_state` equals 1, set `ptw_pte1` to ptw_mem_data; set `ptw_mem_addr` to concat(ptw_pte_ppn(ptw_mem_data)[1:0], ptw_vpn0(va), 2); set `ptw_walk_state` to 2.
- **ptw_walk_finish** — when `ptw_walk_state` equals 2, set `ptw_pte0` to ptw_mem_data; set `ptw_ppn` to ptw_pte_ppn(ptw_mem_data); set `ptw_result_pa` to concat(ptw_pte_ppn(ptw_mem_data), ptw_offset(va), 4); set `ptw_walk_state` to 3.
- **ptw_walk_reset** — when `ptw_walk_state` equals 3, set `ptw_walk_state` to 0.

## Properties

- **itlb_hit_sets_i_ppn** (transition): after each step, `i_ppn` equals `itlb_way0_ppn`.
- **dtlb_hit_sets_d_ppn** (transition): after each step, `d_ppn` equals `dtlb_way0_ppn`.
- **walk_on_miss** (transition): after each step, `miss_signal` equals `i_miss` or `d_miss`.
- **fill_from_leaf** (transition): after each step, `ppn_fill` equals `ptw_ppn`.
