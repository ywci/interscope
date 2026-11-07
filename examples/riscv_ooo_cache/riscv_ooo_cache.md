# riscv_ooo_cache specification

## Inputs

| Name | Type |
|------|------|
| `rdata` | bits<32> |
| `rvalid` | bool |
| `arready` | bool |
| `store_addr` | bits<32> |
| `store_data` | bits<32> |
| `store_valid` | bool |
| `load_addr` | bits<32> |
| `load_valid` | bool |
| `bvalid` | bool |
| `load_rdata` | bits<32> |
| `load_rvalid` | bool |
| `ppn_in` | bits<20> |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `rob0_instr` | register | bits<32> | 0 |
| `rob0_valid` | register | bool | false |
| `rob0_done` | register | bool | false |
| `rob1_instr` | register | bits<32> | 0 |
| `rob1_valid` | register | bool | false |
| `rob1_done` | register | bool | false |
| `rob0_data` | register | bits<32> | 0 |
| `rob0_store` | register | bool | false |
| `rob1_data` | register | bits<32> | 0 |
| `rob1_store` | register | bool | false |
| `rob0_load` | register | bool | false |
| `rob1_load` | register | bool | false |
| `head` | register | bool | false |
| `tail` | register | bool | false |
| `arch` | register | bits<32> | 0 |
| `PC` | register | bits<32> | 0 |
| `ctr` | register | bits<2> | 0 |
| `flush` | register | bool | false |
| `ic_v0` | register | bool | false |
| `ic_t0` | register | bits<20> | 0 |
| `ic_d0` | register | bits<32> | 0 |
| `ic_v1` | register | bool | false |
| `ic_t1` | register | bits<20> | 0 |
| `ic_d1` | register | bits<32> | 0 |
| `ic_lru` | register | bool | false |
| `l2_v0` | register | bool | false |
| `l2_t0` | register | bits<20> | 0 |
| `l2_d0` | register | bits<32> | 0 |
| `l2_v1` | register | bool | false |
| `l2_t1` | register | bits<20> | 0 |
| `l2_d1` | register | bits<32> | 0 |
| `l2_lru` | register | bool | false |
| `araddr` | register | bits<32> | 0 |
| `arvalid` | register | bool | false |
| `awaddr` | register | bits<32> | 0 |
| `awvalid` | register | bool | false |
| `wdata` | register | bits<32> | 0 |
| `wvalid` | register | bool | false |
| `load_araddr` | register | bits<32> | 0 |
| `load_arvalid` | register | bool | false |
| `load_result` | register | bits<32> | 0 |
| `load_rob0` | register | bool | false |
| `dc_v0` | register | bool | false |
| `dc_t0` | register | bits<20> | 0 |
| `dc_d0` | register | bits<32> | 0 |
| `dc_v1` | register | bool | false |
| `dc_t1` | register | bits<20> | 0 |
| `dc_d1` | register | bits<32> | 0 |
| `dc_lru` | register | bool | false |
| `tlb0_vpn` | register | bits<20> | 0 |
| `tlb0_ppn` | register | bits<20> | 0 |
| `tlb0_valid` | register | bool | false |
| `tlb1_vpn` | register | bits<20> | 0 |
| `tlb1_ppn` | register | bits<20> | 0 |
| `tlb1_valid` | register | bool | false |
| `tlb_lru` | register | bool | false |
| `tlb_ppn` | register | bits<20> | 0 |

## Behavior (rules)

- **tlb_fill** — when not (set_hit(`tlb0_valid`, `tlb0_vpn`, `tlb1_valid`, `tlb1_vpn`, vpn(`PC`))), set `tlb0_vpn` to if `tlb_lru`, then vpn(`PC`), otherwise `tlb0_vpn`; set `tlb0_ppn` to if `tlb_lru`, then ppn_in, otherwise `tlb0_ppn`; set `tlb0_valid` to if `tlb_lru`, then true, otherwise `tlb0_valid`; set `tlb1_vpn` to if not (`tlb_lru`), then vpn(`PC`), otherwise `tlb1_vpn`; set `tlb1_ppn` to if not (`tlb_lru`), then ppn_in, otherwise `tlb1_ppn`; set `tlb1_valid` to if not (`tlb_lru`), then true, otherwise `tlb1_valid`; set `tlb_lru` to not (`tlb_lru`); set `tlb_ppn` to ppn_in.
- **tlb_hit** — when set_hit(`tlb0_valid`, `tlb0_vpn`, `tlb1_valid`, `tlb1_vpn`, vpn(`PC`)), set `tlb_ppn` to if way_hit(`tlb0_valid`, `tlb0_vpn`, vpn(`PC`)), then `tlb0_ppn`, otherwise `tlb1_ppn`; set `tlb_lru` to if way_hit(`tlb0_valid`, `tlb0_vpn`, vpn(`PC`)), then false, otherwise true.
- **fetch** — when not (set_hit(`ic_v0`, `ic_t0`, `ic_v1`, `ic_t1`, `tlb_ppn`)) and not (set_hit(`l2_v0`, `l2_t0`, `l2_v1`, `l2_t1`, `tlb_ppn`)) and not (`arvalid`), set `arvalid` to true; set `araddr` to translate(`PC`, `tlb_ppn`).
- **mem_response** — when `arvalid` and rvalid, set `l2_v0` to if `l2_lru`, then true, otherwise `l2_v0`; set `l2_t0` to if `l2_lru`, then vpn(`araddr`), otherwise `l2_t0`; set `l2_d0` to if `l2_lru`, then rdata, otherwise `l2_d0`; set `l2_v1` to if not (`l2_lru`), then true, otherwise `l2_v1`; set `l2_t1` to if not (`l2_lru`), then vpn(`araddr`), otherwise `l2_t1`; set `l2_d1` to if not (`l2_lru`), then rdata, otherwise `l2_d1`; set `l2_lru` to not (`l2_lru`); set `arvalid` to false.
- **store_issue0** — when store_valid and not (`tail`) and not (`flush`), set `rob0_instr` to store_addr; set `rob0_data` to store_data; set `rob0_store` to true; set `rob0_load` to false; set `rob0_valid` to true; set `rob0_done` to false; set `tail` to true.
- **store_issue1** — when store_valid and `tail` and not (`flush`), set `rob1_instr` to store_addr; set `rob1_data` to store_data; set `rob1_store` to true; set `rob1_load` to false; set `rob1_valid` to true; set `rob1_done` to false; set `tail` to false.
- **load_issue0** — when load_valid and not (`tail`) and not (`flush`), set `rob0_instr` to load_addr; set `rob0_data` to 0; set `rob0_store` to false; set `rob0_load` to true; set `rob0_valid` to true; set `rob0_done` to false; set `tail` to true.
- **load_issue1** — when load_valid and `tail` and not (`flush`), set `rob1_instr` to load_addr; set `rob1_data` to 0; set `rob1_store` to false; set `rob1_load` to true; set `rob1_valid` to true; set `rob1_done` to false; set `tail` to false.
- **write_response** — when bvalid and `awvalid`, set `awvalid` to false; set `wvalid` to false.
- **load_response** — when `load_arvalid` and load_rvalid, set `rob0_data` to if `load_rob0`, then load_rdata, otherwise `rob0_data`; set `rob0_done` to if `load_rob0`, then true, otherwise `rob0_done`; set `rob1_data` to if not (`load_rob0`), then load_rdata, otherwise `rob1_data`; set `rob1_done` to if not (`load_rob0`), then true, otherwise `rob1_done`; set `dc_v0` to if `dc_lru`, then true, otherwise `dc_v0`; set `dc_t0` to if `dc_lru`, then vpn(`load_araddr`), otherwise `dc_t0`; set `dc_d0` to if `dc_lru`, then load_rdata, otherwise `dc_d0`; set `dc_v1` to if not (`dc_lru`), then true, otherwise `dc_v1`; set `dc_t1` to if not (`dc_lru`), then vpn(`load_araddr`), otherwise `dc_t1`; set `dc_d1` to if not (`dc_lru`), then load_rdata, otherwise `dc_d1`; set `dc_lru` to not (`dc_lru`); set `load_arvalid` to false.
- **fill_l1** — when not (set_hit(`ic_v0`, `ic_t0`, `ic_v1`, `ic_t1`, `tlb_ppn`)) and set_hit(`l2_v0`, `l2_t0`, `l2_v1`, `l2_t1`, `tlb_ppn`), set `ic_v0` to if `ic_lru`, then true, otherwise `ic_v0`; set `ic_t0` to if `ic_lru`, then `tlb_ppn`, otherwise `ic_t0`; set `ic_d0` to if `ic_lru`, then fetch_instr(`l2_v0`, `l2_t0`, `l2_d0`, `l2_v1`, `l2_t1`, `l2_d1`, `tlb_ppn`), otherwise `ic_d0`; set `ic_v1` to if not (`ic_lru`), then true, otherwise `ic_v1`; set `ic_t1` to if not (`ic_lru`), then `tlb_ppn`, otherwise `ic_t1`; set `ic_d1` to if not (`ic_lru`), then fetch_instr(`l2_v0`, `l2_t0`, `l2_d0`, `l2_v1`, `l2_t1`, `l2_d1`, `tlb_ppn`), otherwise `ic_d1`; set `ic_lru` to not (`ic_lru`).
- **issue0** — when set_hit(`ic_v0`, `ic_t0`, `ic_v1`, `ic_t1`, `tlb_ppn`) and not (`tail`) and not (`flush`), set `rob0_instr` to fetch_instr(`ic_v0`, `ic_t0`, `ic_d0`, `ic_v1`, `ic_t1`, `ic_d1`, `tlb_ppn`); set `rob0_data` to 0; set `rob0_store` to false; set `rob0_load` to false; set `rob0_valid` to true; set `rob0_done` to false; set `tail` to true; set `ic_lru` to if way_hit(`ic_v0`, `ic_t0`, `tlb_ppn`), then false, otherwise true; set `PC` to if is_branch(fetch_instr(`ic_v0`, `ic_t0`, `ic_d0`, `ic_v1`, `ic_t1`, `ic_d1`, `tlb_ppn`)) and predict_taken(fetch_instr(`ic_v0`, `ic_t0`, `ic_d0`, `ic_v1`, `ic_t1`, `ic_d1`, `tlb_ppn`), `ctr`), then branch_target(fetch_instr(`ic_v0`, `ic_t0`, `ic_d0`, `ic_v1`, `ic_t1`, `ic_d1`, `tlb_ppn`), `PC`), otherwise `PC` + 4.
- **issue1** — when set_hit(`ic_v0`, `ic_t0`, `ic_v1`, `ic_t1`, `tlb_ppn`) and `tail` and not (`flush`), set `rob1_instr` to fetch_instr(`ic_v0`, `ic_t0`, `ic_d0`, `ic_v1`, `ic_t1`, `ic_d1`, `tlb_ppn`); set `rob1_data` to 0; set `rob1_store` to false; set `rob1_load` to false; set `rob1_valid` to true; set `rob1_done` to false; set `tail` to false; set `ic_lru` to if way_hit(`ic_v0`, `ic_t0`, `tlb_ppn`), then false, otherwise true; set `PC` to if is_branch(fetch_instr(`ic_v0`, `ic_t0`, `ic_d0`, `ic_v1`, `ic_t1`, `ic_d1`, `tlb_ppn`)) and predict_taken(fetch_instr(`ic_v0`, `ic_t0`, `ic_d0`, `ic_v1`, `ic_t1`, `ic_d1`, `tlb_ppn`), `ctr`), then branch_target(fetch_instr(`ic_v0`, `ic_t0`, `ic_d0`, `ic_v1`, `ic_t1`, `ic_d1`, `tlb_ppn`), `PC`), otherwise `PC` + 4.
- **exec0** — when `rob0_valid` and not (`rob0_done`) and not (`rob0_load`), set `rob0_done` to true.
- **exec1** — when `rob1_valid` and not (`rob1_done`) and not (`rob1_load`), set `rob1_done` to true.
- **load_hit0** — when `rob0_valid` and not (`rob0_done`) and `rob0_load` and set_hit(`dc_v0`, `dc_t0`, `dc_v1`, `dc_t1`, vpn(`rob0_instr`)) and not (`head` and store_load_alias(`rob0_instr`, `rob1_instr`, `rob1_store`)), set `rob0_data` to fetch_instr(`dc_v0`, `dc_t0`, `dc_d0`, `dc_v1`, `dc_t1`, `dc_d1`, vpn(`rob0_instr`)); set `rob0_done` to true; set `dc_lru` to if way_hit(`dc_v0`, `dc_t0`, vpn(`rob0_instr`)), then false, otherwise true.
- **load_hit1** — when `rob1_valid` and not (`rob1_done`) and `rob1_load` and set_hit(`dc_v0`, `dc_t0`, `dc_v1`, `dc_t1`, vpn(`rob1_instr`)) and not (not (`head`) and store_load_alias(`rob1_instr`, `rob0_instr`, `rob0_store`)), set `rob1_data` to fetch_instr(`dc_v0`, `dc_t0`, `dc_d0`, `dc_v1`, `dc_t1`, `dc_d1`, vpn(`rob1_instr`)); set `rob1_done` to true; set `dc_lru` to if way_hit(`dc_v0`, `dc_t0`, vpn(`rob1_instr`)), then false, otherwise true.
- **load_exec0** — when `rob0_valid` and not (`rob0_done`) and `rob0_load` and not (`load_arvalid`) and not (set_hit(`dc_v0`, `dc_t0`, `dc_v1`, `dc_t1`, vpn(`rob0_instr`))) and not (`head` and store_load_alias(`rob0_instr`, `rob1_instr`, `rob1_store`)), set `load_arvalid` to true; set `load_araddr` to `rob0_instr`; set `load_rob0` to true.
- **load_exec1** — when `rob1_valid` and not (`rob1_done`) and `rob1_load` and not (`load_arvalid`) and not (set_hit(`dc_v0`, `dc_t0`, `dc_v1`, `dc_t1`, vpn(`rob1_instr`))) and not (not (`head`) and store_load_alias(`rob1_instr`, `rob0_instr`, `rob0_store`)), set `load_arvalid` to true; set `load_araddr` to `rob1_instr`; set `load_rob0` to false.
- **load_forward0** — when `rob0_valid` and not (`rob0_done`) and `rob0_load` and `head` and store_load_alias(`rob0_instr`, `rob1_instr`, `rob1_store`), set `rob0_data` to `rob1_data`; set `rob0_done` to true.
- **load_forward1** — when `rob1_valid` and not (`rob1_done`) and `rob1_load` and not (`head`) and store_load_alias(`rob1_instr`, `rob0_instr`, `rob0_store`), set `rob1_data` to `rob0_data`; set `rob1_done` to true.
- **commit0** — when not (`head`) and `rob0_valid` and `rob0_done`, set `arch` to `rob0_instr`; set `rob0_valid` to false; set `head` to true; set `flush` to mispredicted(`rob0_instr`, `ctr`); set `ctr` to if is_branch(`rob0_instr`), then if `ctr` < 3, then `ctr` + 1, otherwise `ctr`, otherwise `ctr`; set `awvalid` to if `rob0_store`, then true, otherwise `awvalid`; set `awaddr` to if `rob0_store`, then `rob0_instr`, otherwise `awaddr`; set `wvalid` to if `rob0_store`, then true, otherwise `wvalid`; set `wdata` to if `rob0_store`, then `rob0_data`, otherwise `wdata`; set `dc_d0` to if `rob0_store` and way_hit(`dc_v0`, `dc_t0`, vpn(`rob0_instr`)), then `rob0_data`, otherwise `dc_d0`; set `dc_d1` to if `rob0_store` and way_hit(`dc_v1`, `dc_t1`, vpn(`rob0_instr`)), then `rob0_data`, otherwise `dc_d1`; set `load_result` to if `rob0_load`, then `rob0_data`, otherwise `load_result`.
- **commit1** — when `head` and `rob1_valid` and `rob1_done`, set `arch` to `rob1_instr`; set `rob1_valid` to false; set `head` to false; set `flush` to mispredicted(`rob1_instr`, `ctr`); set `ctr` to if is_branch(`rob1_instr`), then if `ctr` < 3, then `ctr` + 1, otherwise `ctr`, otherwise `ctr`; set `awvalid` to if `rob1_store`, then true, otherwise `awvalid`; set `awaddr` to if `rob1_store`, then `rob1_instr`, otherwise `awaddr`; set `wvalid` to if `rob1_store`, then true, otherwise `wvalid`; set `wdata` to if `rob1_store`, then `rob1_data`, otherwise `wdata`; set `dc_d0` to if `rob1_store` and way_hit(`dc_v0`, `dc_t0`, vpn(`rob1_instr`)), then `rob1_data`, otherwise `dc_d0`; set `dc_d1` to if `rob1_store` and way_hit(`dc_v1`, `dc_t1`, vpn(`rob1_instr`)), then `rob1_data`, otherwise `dc_d1`; set `load_result` to if `rob1_load`, then `rob1_data`, otherwise `load_result`.
- **recover** — when `flush`, set `flush` to false; set `rob1_valid` to false; set `rob0_valid` to if `head`, then `rob0_valid`, otherwise false.

## Properties

- **ic_lru_bool** (safety): always, `ic_lru` equals true or `ic_lru` equals false.
- **l2_lru_bool** (safety): always, `l2_lru` equals true or `l2_lru` equals false.
- **tlb_lru_bool** (safety): always, `tlb_lru` equals true or `tlb_lru` equals false.
- **tlb_hit_way0_updates_lru** (transition): after each step, if way_hit(prev(tlb0_valid), prev(tlb0_vpn), vpn(prev(PC))), then `tlb_lru` equals false.
- **tlb_miss_fills_lru_way0** (transition): after each step, if prev(tlb_lru), then `tlb0_valid` equals true.
- **dc_lru_bool** (safety): always, `dc_lru` equals true or `dc_lru` equals false.
- **load_dc_hit** (transition): after each step, `rob0_done` equals true and `rob0_data` equals fetch_instr(prev(dc_v0), prev(dc_t0), prev(dc_d0), prev(dc_v1), prev(dc_t1), prev(dc_d1), vpn(prev(rob0_instr))).
- **load_dc_miss_fills** (transition): after each step, if prev(dc_lru), then `dc_v0` equals true.
- **store_writes_dc** (transition): after each step, if prev(rob0_store) and way_hit(prev(dc_v0), prev(dc_t0), vpn(prev(rob0_instr))), then `dc_d0` equals prev(rob0_data).
- **fetch_sets_arvalid** (transition): after each step, `arvalid` equals true.
- **fetch_sets_araddr** (transition): after each step, `araddr` equals translate(prev(PC), prev(tlb_ppn)).
- **fill_l1_tags_with_ppn** (transition): after each step, if prev(ic_lru), then `ic_t0` equals prev(tlb_ppn).
- **mem_response_fills_l2_way0** (transition): after each step, if prev(l2_lru), then `l2_v0` equals true and `l2_d0` equals rdata.
- **mem_response_fills_l2_way1** (transition): after each step, if not (prev(l2_lru)), then `l2_v1` equals true and `l2_d1` equals rdata.
- **mem_response_clears_arvalid** (transition): after each step, `arvalid` equals false.
- **store_allocates_rob** (transition): after each step, `rob0_valid` equals true and `rob0_store` equals true.
- **store_data_in_rob** (transition): after each step, `rob0_instr` equals store_addr and `rob0_data` equals store_data.
- **store_commit_issues_write** (transition): after each step, if prev(rob0_store), then `awvalid` equals true and `wvalid` equals true.
- **store_commit_sets_awaddr** (transition): after each step, if prev(rob0_store), then `awaddr` equals prev(rob0_instr).
- **load_allocates_rob** (transition): after each step, `rob0_valid` equals true and `rob0_load` equals true.
- **load_addr_in_rob** (transition): after each step, `rob0_instr` equals load_addr.
- **load_exec_issues_read** (transition): after each step, `load_arvalid` equals true and `load_araddr` equals prev(rob0_instr).
- **load_response_completes_load** (transition): after each step, if prev(load_rob0), then `rob0_done` equals true.
- **load_commit_writes_back** (transition): after each step, if prev(rob0_load), then `load_result` equals prev(rob0_data).
- **store_load_forward** (transition): after each step, `rob0_data` equals prev(rob1_data) and `rob0_done` equals true.
- **forwarded_load_no_read** (transition): after each step, `load_arvalid` equals prev(load_arvalid).
- **write_response_completes** (transition): after each step, `awvalid` equals false.
- **fill_l1_fills_way0** (transition): after each step, if prev(ic_lru), then `ic_v0` equals true.
- **fill_l1_fills_way1** (transition): after each step, if not (prev(ic_lru)), then `ic_v1` equals true.
- **issue_hit_delivers_rob0** (transition): after each step, `rob0_instr` equals fetch_instr(prev(ic_v0), prev(ic_t0), prev(ic_d0), prev(ic_v1), prev(ic_t1), prev(ic_d1), prev(tlb_ppn)).
- **issue_way0_hit_updates_lru** (transition): after each step, if way_hit(prev(ic_v0), prev(ic_t0), prev(tlb_ppn)), then `ic_lru` equals false.
- **l1_hit_leaves_l2_lru** (transition): after each step, `l2_lru` equals prev(l2_lru).
- **commit_in_order** (transition): after each step, prev(head) equals true.
