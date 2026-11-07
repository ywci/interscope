# core_comp specification

## Inputs

| Name | Type |
|------|------|
| `req_core` | bits<4> |
| `issue_valid` | bool |
| `rd` | bits<2> |
| `op` | bool |
| `store` | bool |
| `a` | bits<8> |
| `b` | bits<8> |
| `alu_op` | bits<3> |
| `addr` | bits<4> |
| `d_is_physical` | bool |
| `taken` | bool |
| `req_write` | bool |
| `req_addr` | bits<4> |
| `req_data` | bits<8> |
| `stall` | bool |
| `branch_target` | bits<4> |
| `araddr` | bits<4> |
| `arvalid` | bool |
| `awaddr` | bits<4> |
| `awvalid` | bool |
| `wdata` | bits<8> |
| `wvalid` | bool |
| `va` | bits<32> |
| `alloc_valid` | bool |
| `id` | bits<2> |
| `release0` | bool |
| `release1` | bool |
| `ooo_lsu_l1d_is_physical` | bool |
| `ooo_lsu_l1d_req_data` | bits<8> |
| `cache_l2_mshr_arb_req2_valid` | bool |
| `cache_l2_mshr_arb_req3_valid` | bool |
| `cache_l2_mshr_arb_req4_valid` | bool |
| `cache_l2_mshr_arb_req5_valid` | bool |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `pc_signal` | register | bits<4> | 0 |
| `i_pa_signal` | register | bits<4> | 0 |
| `pa_signal` | register | bits<4> | 0 |
| `d_vpn_signal` | register | bits<2> | 0 |
| `ptw_mem_addr_signal` | register | bits<4> | 0 |
| `ptw_active_signal` | register | bool | false |
| `ptw_mem_data_signal` | register | bits<8> | 0 |
| `l1d_addr_signal` | register | bits<4> | 0 |
| `l1d_write_signal` | register | bool | false |
| `l1d_phys_signal` | register | bool | false |
| `i_miss_signal` | register | bool | false |
| `d_miss_signal` | register | bool | false |
| `tlb_miss_signal` | register | bool | false |
| `miss_valid_signal` | register | bool | false |
| `miss_addr_signal` | register | bits<4> | 0 |
| `pc` | register | bits<4> | 0 |
| `mmu_ppn_fill` | register | bits<4> | 0 |
| `mmu_ptw_ppn` | register | bits<4> | 0 |
| `mmu_itlb_way0_vpn` | register | bits<4> | 0 |
| `mmu_itlb_way0_ppn` | register | bits<4> | 0 |
| `mmu_itlb_way0_valid` | register | bool | false |
| `mmu_itlb_way1_vpn` | register | bits<4> | 0 |
| `mmu_itlb_way1_ppn` | register | bits<4> | 0 |
| `mmu_itlb_way1_valid` | register | bool | false |
| `mmu_itlb_lru` | register | bool | false |
| `mmu_dtlb_way0_vpn` | register | bits<4> | 0 |
| `mmu_dtlb_way0_ppn` | register | bits<4> | 0 |
| `mmu_dtlb_way0_valid` | register | bool | false |
| `mmu_dtlb_way1_vpn` | register | bits<4> | 0 |
| `mmu_dtlb_way1_ppn` | register | bits<4> | 0 |
| `mmu_dtlb_way1_valid` | register | bool | false |
| `mmu_dtlb_lru` | register | bool | false |
| `mmu_ptw_root_ppn` | register | bits<4> | 0 |
| `mmu_ptw_walk_state` | register | bits<2> | 0 |
| `mmu_ptw_pte1` | register | bits<8> | 0 |
| `mmu_ptw_pte0` | register | bits<8> | 0 |
| `mmu_ptw_result_pa` | register | bits<8> | 0 |
| `fetch_bpu_ctr` | register | bits<2> | 1 |
| `fetch_bpu_predict` | register | bool | false |
| `ooo_rat0` | register | bits<3> | 0 |
| `ooo_rat1` | register | bits<3> | 1 |
| `ooo_rat2` | register | bits<3> | 2 |
| `ooo_rat3` | register | bits<3> | 3 |
| `ooo_prf0_busy` | register | bool | true |
| `ooo_prf1_busy` | register | bool | true |
| `ooo_prf2_busy` | register | bool | true |
| `ooo_prf3_busy` | register | bool | true |
| `ooo_prf4_busy` | register | bool | false |
| `ooo_prf5_busy` | register | bool | false |
| `ooo_rob0_valid` | register | bool | false |
| `ooo_rob0_rd` | register | bits<2> | 0 |
| `ooo_rob0_old` | register | bits<3> | 0 |
| `ooo_rob0_done` | register | bool | false |
| `ooo_rob1_valid` | register | bool | false |
| `ooo_rob1_rd` | register | bits<2> | 0 |
| `ooo_rob1_old` | register | bits<3> | 0 |
| `ooo_rob1_done` | register | bool | false |
| `ooo_head` | register | bool | false |
| `ooo_result` | register | bits<8> | 0 |
| `ooo_sb_valid` | register | bool | false |
| `ooo_sb_addr` | register | bits<4> | 0 |
| `ooo_sb_data` | register | bits<8> | 0 |
| `ooo_alu_result_reg` | register | bits<8> | 0 |
| `ooo_alu_zero_reg` | register | bool | false |
| `ooo_alu_overflow_reg` | register | bool | false |
| `ooo_alu_valid` | register | bool | false |
| `ooo_alu_op_reg` | register | bits<3> | 0 |
| `ooo_alu_a_reg` | register | bits<8> | 0 |
| `ooo_alu_b_reg` | register | bits<8> | 0 |
| `ooo_lsu_mem` | memory | memory(bits<8>, 16) |  |
| `ooo_lsu_resp_data` | register | bits<8> | 0 |
| `ooo_lsu_resp_valid` | register | bool | false |
| `ooo_lsu_l1d_s0` | register | bits<2> | 0 |
| `ooo_lsu_l1d_a0` | register | bits<4> | 0 |
| `ooo_lsu_l1d_s1` | register | bits<2> | 0 |
| `ooo_lsu_l1d_a1` | register | bits<4> | 0 |
| `ooo_lsu_l1d_lru` | register | bool | false |
| `ooo_lsu_l1d_data0` | register | bits<8> | 0 |
| `ooo_lsu_l1d_data1` | register | bits<8> | 0 |
| `ooo_lsu_l1d_rdata` | register | bits<8> | 0 |
| `cache_const_false` | register | bool | false |
| `cache_l1d_rdata_signal` | register | bits<8> | 0 |
| `cache_l1i_s0` | register | bits<2> | 0 |
| `cache_l1i_a0` | register | bits<4> | 0 |
| `cache_l1i_s1` | register | bits<2> | 0 |
| `cache_l1i_a1` | register | bits<4> | 0 |
| `cache_l1i_lru` | register | bool | false |
| `cache_l1i_data0` | register | bits<8> | 0 |
| `cache_l1i_data1` | register | bits<8> | 0 |
| `cache_l1i_rdata` | register | bits<8> | 0 |
| `cache_l1d_s0` | register | bits<2> | 0 |
| `cache_l1d_a0` | register | bits<4> | 0 |
| `cache_l1d_s1` | register | bits<2> | 0 |
| `cache_l1d_a1` | register | bits<4> | 0 |
| `cache_l1d_lru` | register | bool | false |
| `cache_l1d_data0` | register | bits<8> | 0 |
| `cache_l1d_data1` | register | bits<8> | 0 |
| `cache_l2_s0` | register | bits<2> | 0 |
| `cache_l2_a0` | register | bits<4> | 0 |
| `cache_l2_s1` | register | bits<2> | 0 |
| `cache_l2_a1` | register | bits<4> | 0 |
| `cache_l2_lru` | register | bool | false |
| `cache_l2_mem` | memory | memory(bits<8>, 16) |  |
| `cache_l2_mshr_mshr0_valid` | register | bool | false |
| `cache_l2_mshr_mshr0_mid` | register | bits<2> | 0 |
| `cache_l2_mshr_mshr0_maddr` | register | bits<4> | 0 |
| `cache_l2_mshr_mshr0_mdata` | register | bits<8> | 0 |
| `cache_l2_mshr_mshr1_valid` | register | bool | false |
| `cache_l2_mshr_mshr1_mid` | register | bits<2> | 0 |
| `cache_l2_mshr_mshr1_maddr` | register | bits<4> | 0 |
| `cache_l2_mshr_mshr1_mdata` | register | bits<8> | 0 |
| `cache_l2_mshr_arb_grant` | register | bits<3> | 0 |
| `cache_l2_mshr_arb_grant_valid` | register | bool | false |
| `axi_mem_mem` | memory | memory(bits<8>, 16) |  |
| `axi_mem_rdata` | register | bits<8> | 0 |
| `axi_mem_rvalid` | register | bool | false |
| `axi_mem_bvalid` | register | bool | false |

## Behavior (rules)

- **slice_d_vpn** — when true, set `d_vpn_signal` to addr[1:0].
- **mux_l1d_addr** — when true, set `l1d_addr_signal` to if `ptw_active_signal`, then `ptw_mem_addr_signal`, otherwise pa_signal.
- **mux_l1d_write** — when true, set `l1d_write_signal` to not (`ptw_active_signal`) and req_write.
- **mux_l1d_phys** — when true, set `l1d_phys_signal` to `ptw_active_signal` or d_is_physical.
- **retire** — when req_core equals 0, set `pc` to `pc` + 1.
- **mmu_combine_miss** — when true, set `tlb_miss_signal` to `i_miss_signal` or `d_miss_signal`.
- **mmu_slice_ppn** — when true, set `mmu_ppn_fill` to `mmu_ptw_ppn`.
- **mmu_ptw_is_active** — when true, set `ptw_active_signal` to `mmu_ptw_walk_state` does not equal 0.
- **mmu_itlb_hit0** — when mmu_itlb_way_hit(`mmu_itlb_way0_valid`, `mmu_itlb_way0_vpn`, pc_signal), set `i_pa_signal` to `mmu_itlb_way0_ppn`; set `mmu_itlb_lru` to true; set `i_miss_signal` to false.
- **mmu_itlb_hit1** — when mmu_itlb_way_hit(`mmu_itlb_way1_valid`, `mmu_itlb_way1_vpn`, pc_signal), set `i_pa_signal` to `mmu_itlb_way1_ppn`; set `mmu_itlb_lru` to false; set `i_miss_signal` to false.
- **mmu_itlb_fill0** — when not (mmu_itlb_way_hit(`mmu_itlb_way0_valid`, `mmu_itlb_way0_vpn`, pc_signal)) and not (mmu_itlb_way_hit(`mmu_itlb_way1_valid`, `mmu_itlb_way1_vpn`, pc_signal)) and not (`mmu_itlb_lru`), set `mmu_itlb_way0_vpn` to pc_signal; set `mmu_itlb_way0_ppn` to mmu_ppn_fill; set `mmu_itlb_way0_valid` to true; set `mmu_itlb_lru` to true; set `i_miss_signal` to true.
- **mmu_itlb_fill1** — when not (mmu_itlb_way_hit(`mmu_itlb_way0_valid`, `mmu_itlb_way0_vpn`, pc_signal)) and not (mmu_itlb_way_hit(`mmu_itlb_way1_valid`, `mmu_itlb_way1_vpn`, pc_signal)) and `mmu_itlb_lru`, set `mmu_itlb_way1_vpn` to pc_signal; set `mmu_itlb_way1_ppn` to mmu_ppn_fill; set `mmu_itlb_way1_valid` to true; set `mmu_itlb_lru` to false; set `i_miss_signal` to true.
- **mmu_dtlb_hit0** — when mmu_dtlb_way_hit(`mmu_dtlb_way0_valid`, `mmu_dtlb_way0_vpn`, addr), set `pa_signal` to `mmu_dtlb_way0_ppn`; set `mmu_dtlb_lru` to true; set `d_miss_signal` to false.
- **mmu_dtlb_hit1** — when mmu_dtlb_way_hit(`mmu_dtlb_way1_valid`, `mmu_dtlb_way1_vpn`, addr), set `pa_signal` to `mmu_dtlb_way1_ppn`; set `mmu_dtlb_lru` to false; set `d_miss_signal` to false.
- **mmu_dtlb_fill0** — when not (mmu_dtlb_way_hit(`mmu_dtlb_way0_valid`, `mmu_dtlb_way0_vpn`, addr)) and not (mmu_dtlb_way_hit(`mmu_dtlb_way1_valid`, `mmu_dtlb_way1_vpn`, addr)) and not (`mmu_dtlb_lru`), set `mmu_dtlb_way0_vpn` to addr; set `mmu_dtlb_way0_ppn` to mmu_ppn_fill; set `mmu_dtlb_way0_valid` to true; set `mmu_dtlb_lru` to true; set `d_miss_signal` to true.
- **mmu_dtlb_fill1** — when not (mmu_dtlb_way_hit(`mmu_dtlb_way0_valid`, `mmu_dtlb_way0_vpn`, addr)) and not (mmu_dtlb_way_hit(`mmu_dtlb_way1_valid`, `mmu_dtlb_way1_vpn`, addr)) and `mmu_dtlb_lru`, set `mmu_dtlb_way1_vpn` to addr; set `mmu_dtlb_way1_ppn` to mmu_ppn_fill; set `mmu_dtlb_way1_valid` to true; set `mmu_dtlb_lru` to false; set `d_miss_signal` to true.
- **mmu_ptw_walk_start** — when `mmu_ptw_walk_state` equals 0 and tlb_miss_signal, set `ptw_mem_addr_signal` to concat(`mmu_ptw_root_ppn`[1:0], mmu_ptw_vpn1(va), 2); set `mmu_ptw_walk_state` to 1.
- **mmu_ptw_walk_l0** — when `mmu_ptw_walk_state` equals 1, set `mmu_ptw_pte1` to ptw_mem_data_signal; set `ptw_mem_addr_signal` to concat(mmu_ptw_pte_ppn(ptw_mem_data_signal)[1:0], mmu_ptw_vpn0(va), 2); set `mmu_ptw_walk_state` to 2.
- **mmu_ptw_walk_finish** — when `mmu_ptw_walk_state` equals 2, set `mmu_ptw_pte0` to ptw_mem_data_signal; set `mmu_ptw_ppn` to mmu_ptw_pte_ppn(ptw_mem_data_signal); set `mmu_ptw_result_pa` to concat(mmu_ptw_pte_ppn(ptw_mem_data_signal), mmu_ptw_offset(va), 4); set `mmu_ptw_walk_state` to 3.
- **mmu_ptw_walk_reset** — when `mmu_ptw_walk_state` equals 3, set `mmu_ptw_walk_state` to 0.
- **fetch_advance** — when true, set `pc_signal` to if stall, then `pc_signal`, otherwise if `fetch_bpu_predict`, then branch_target, otherwise `pc_signal` + 1.
- **fetch_bpu_update** — when true, set `fetch_bpu_ctr` to if taken, then if `fetch_bpu_ctr` < 3, then `fetch_bpu_ctr` + 1, otherwise 3, otherwise if `fetch_bpu_ctr` > 0, then `fetch_bpu_ctr` − 1, otherwise 0; set `fetch_bpu_predict` to `fetch_bpu_ctr` ≥ 2.
- **ooo_issue0** — when issue_valid and not (`ooo_rob0_valid`), set `ooo_rat0` to if rd equals 0, then 4, otherwise `ooo_rat0`; set `ooo_rat1` to if rd equals 1, then 4, otherwise `ooo_rat1`; set `ooo_rat2` to if rd equals 2, then 4, otherwise `ooo_rat2`; set `ooo_rat3` to if rd equals 3, then 4, otherwise `ooo_rat3`; set `ooo_prf4_busy` to true; set `ooo_rob0_valid` to true; set `ooo_rob0_rd` to rd; set `ooo_rob0_old` to if rd equals 0, then `ooo_rat0`, otherwise if rd equals 1, then `ooo_rat1`, otherwise if rd equals 2, then `ooo_rat2`, otherwise `ooo_rat3`; set `ooo_rob0_done` to false.
- **ooo_issue1** — when issue_valid and `ooo_rob0_valid` and not (`ooo_rob1_valid`), set `ooo_rat0` to if rd equals 0, then 5, otherwise `ooo_rat0`; set `ooo_rat1` to if rd equals 1, then 5, otherwise `ooo_rat1`; set `ooo_rat2` to if rd equals 2, then 5, otherwise `ooo_rat2`; set `ooo_rat3` to if rd equals 3, then 5, otherwise `ooo_rat3`; set `ooo_prf5_busy` to true; set `ooo_rob1_valid` to true; set `ooo_rob1_rd` to rd; set `ooo_rob1_old` to if rd equals 0, then `ooo_rat0`, otherwise if rd equals 1, then `ooo_rat1`, otherwise if rd equals 2, then `ooo_rat2`, otherwise `ooo_rat3`; set `ooo_rob1_done` to false.
- **ooo_store_buf** — when issue_valid and op and store, set `ooo_sb_valid` to true; set `ooo_sb_addr` to addr; set `ooo_sb_data` to a.
- **ooo_execute** — when true, set `ooo_result` to if op, then if store, then `ooo_lsu_resp_data`, otherwise if `ooo_sb_valid` and `ooo_sb_addr` equals addr, then `ooo_sb_data`, otherwise `ooo_lsu_resp_data`, otherwise `ooo_alu_result_reg`.
- **ooo_commit0** — when `ooo_head` equals false and `ooo_rob0_done`, set `ooo_prf0_busy` to if `ooo_rob0_old` equals 0, then false, otherwise `ooo_prf0_busy`; set `ooo_prf1_busy` to if `ooo_rob0_old` equals 1, then false, otherwise `ooo_prf1_busy`; set `ooo_prf2_busy` to if `ooo_rob0_old` equals 2, then false, otherwise `ooo_prf2_busy`; set `ooo_prf3_busy` to if `ooo_rob0_old` equals 3, then false, otherwise `ooo_prf3_busy`; set `ooo_prf4_busy` to if `ooo_rob0_old` equals 4, then false, otherwise `ooo_prf4_busy`; set `ooo_prf5_busy` to if `ooo_rob0_old` equals 5, then false, otherwise `ooo_prf5_busy`; set `ooo_rob0_valid` to false; set `ooo_rob0_done` to false; set `ooo_head` to true.
- **ooo_commit1** — when `ooo_head` equals true and `ooo_rob1_done`, set `ooo_prf0_busy` to if `ooo_rob1_old` equals 0, then false, otherwise `ooo_prf0_busy`; set `ooo_prf1_busy` to if `ooo_rob1_old` equals 1, then false, otherwise `ooo_prf1_busy`; set `ooo_prf2_busy` to if `ooo_rob1_old` equals 2, then false, otherwise `ooo_prf2_busy`; set `ooo_prf3_busy` to if `ooo_rob1_old` equals 3, then false, otherwise `ooo_prf3_busy`; set `ooo_prf4_busy` to if `ooo_rob1_old` equals 4, then false, otherwise `ooo_prf4_busy`; set `ooo_prf5_busy` to if `ooo_rob1_old` equals 5, then false, otherwise `ooo_prf5_busy`; set `ooo_rob1_valid` to false; set `ooo_rob1_done` to false; set `ooo_head` to false.
- **ooo_alu_load_inputs** — when true, set `ooo_alu_op_reg` to `alu_op`; set `ooo_alu_a_reg` to `a`; set `ooo_alu_b_reg` to `b`.
- **ooo_alu_execute** — when true, set `ooo_alu_result_reg` to if `ooo_alu_op_reg` equals 0, then `ooo_alu_a_reg` + `ooo_alu_b_reg`, otherwise if `ooo_alu_op_reg` equals 1, then `ooo_alu_a_reg` − `ooo_alu_b_reg`, otherwise if `ooo_alu_op_reg` equals 2, then `ooo_alu_a_reg` and `ooo_alu_b_reg`, otherwise if `ooo_alu_op_reg` equals 3, then `ooo_alu_a_reg` or `ooo_alu_b_reg`, otherwise if `ooo_alu_op_reg` equals 4, then if `ooo_alu_a_reg` equals `ooo_alu_b_reg`, then 0, otherwise if `ooo_alu_a_reg` < `ooo_alu_b_reg`, then 1, otherwise 2, otherwise if `ooo_alu_op_reg` equals 5, then `ooo_alu_a_reg` xor `ooo_alu_b_reg`, otherwise if `ooo_alu_op_reg` equals 6, then `ooo_alu_a_reg` shifted left by `ooo_alu_b_reg`[2:0], otherwise if `ooo_alu_op_reg` equals 7, then `ooo_alu_a_reg` shifted right by `ooo_alu_b_reg`[2:0], otherwise 0; set `ooo_alu_overflow_reg` to if `ooo_alu_op_reg` equals 0, then `ooo_alu_a_reg`[7:7] equals `ooo_alu_b_reg`[7:7] and `ooo_alu_a_reg`[7:7] does not equal `ooo_alu_a_reg` + `ooo_alu_b_reg`[7:7], otherwise if `ooo_alu_op_reg` equals 1, then `ooo_alu_a_reg`[7:7] does not equal `ooo_alu_b_reg`[7:7] and `ooo_alu_a_reg`[7:7] equals `ooo_alu_a_reg` − `ooo_alu_b_reg`[7:7], otherwise false; set `ooo_alu_zero_reg` to if `ooo_alu_op_reg` equals 0, then `ooo_alu_a_reg` + `ooo_alu_b_reg`, otherwise if `ooo_alu_op_reg` equals 1, then `ooo_alu_a_reg` − `ooo_alu_b_reg`, otherwise if `ooo_alu_op_reg` equals 2, then `ooo_alu_a_reg` and `ooo_alu_b_reg`, otherwise if `ooo_alu_op_reg` equals 3, then `ooo_alu_a_reg` or `ooo_alu_b_reg`, otherwise if `ooo_alu_op_reg` equals 4, then if `ooo_alu_a_reg` equals `ooo_alu_b_reg`, then 0, otherwise if `ooo_alu_a_reg` < `ooo_alu_b_reg`, then 1, otherwise 2, otherwise if `ooo_alu_op_reg` equals 5, then `ooo_alu_a_reg` xor `ooo_alu_b_reg`, otherwise if `ooo_alu_op_reg` equals 6, then `ooo_alu_a_reg` shifted left by `ooo_alu_b_reg`[2:0], otherwise if `ooo_alu_op_reg` equals 7, then `ooo_alu_a_reg` shifted right by `ooo_alu_b_reg`[2:0], otherwise 0 equals 0; set `ooo_alu_valid` to true.
- **ooo_lsu_store** — when 0 equals 0 and store, mem_write(ooo_lsu_mem, addr, a); set `ooo_lsu_resp_valid` to true.
- **ooo_lsu_load** — when 0 equals 0 and not (store), set `ooo_lsu_resp_data` to mem_read(ooo_lsu_mem, addr); set `ooo_lsu_resp_valid` to true.
- **ooo_lsu_l1d_write_hit0** — when 0 equals 0 and store and ooo_lsu_l1d_has_line(`ooo_lsu_l1d_s0`, `ooo_lsu_l1d_a0`, addr), set `ooo_lsu_l1d_s0` to 3; set `ooo_lsu_l1d_data0` to ooo_lsu_l1d_req_data; set `ooo_lsu_l1d_lru` to true.
- **ooo_lsu_l1d_write_hit1** — when 0 equals 0 and store and not (ooo_lsu_l1d_has_line(`ooo_lsu_l1d_s0`, `ooo_lsu_l1d_a0`, addr)) and ooo_lsu_l1d_has_line(`ooo_lsu_l1d_s1`, `ooo_lsu_l1d_a1`, addr), set `ooo_lsu_l1d_s1` to 3; set `ooo_lsu_l1d_data1` to ooo_lsu_l1d_req_data; set `ooo_lsu_l1d_lru` to false.
- **ooo_lsu_l1d_write_miss0** — when 0 equals 0 and store and not (ooo_lsu_l1d_has_line(`ooo_lsu_l1d_s0`, `ooo_lsu_l1d_a0`, addr)) and not (ooo_lsu_l1d_has_line(`ooo_lsu_l1d_s1`, `ooo_lsu_l1d_a1`, addr)) and not (`ooo_lsu_l1d_lru`), set `ooo_lsu_l1d_s0` to 3; set `ooo_lsu_l1d_a0` to addr; set `ooo_lsu_l1d_data0` to ooo_lsu_l1d_req_data; set `ooo_lsu_l1d_lru` to true.
- **ooo_lsu_l1d_write_miss1** — when 0 equals 0 and store and not (ooo_lsu_l1d_has_line(`ooo_lsu_l1d_s0`, `ooo_lsu_l1d_a0`, addr)) and not (ooo_lsu_l1d_has_line(`ooo_lsu_l1d_s1`, `ooo_lsu_l1d_a1`, addr)) and `ooo_lsu_l1d_lru`, set `ooo_lsu_l1d_s1` to 3; set `ooo_lsu_l1d_a1` to addr; set `ooo_lsu_l1d_data1` to ooo_lsu_l1d_req_data; set `ooo_lsu_l1d_lru` to false.
- **ooo_lsu_l1d_read_hit0** — when 0 equals 0 and not (store) and ooo_lsu_l1d_has_line(`ooo_lsu_l1d_s0`, `ooo_lsu_l1d_a0`, addr), set `ooo_lsu_l1d_rdata` to `ooo_lsu_l1d_data0`; set `ooo_lsu_l1d_lru` to true.
- **ooo_lsu_l1d_read_hit1** — when 0 equals 0 and not (store) and not (ooo_lsu_l1d_has_line(`ooo_lsu_l1d_s0`, `ooo_lsu_l1d_a0`, addr)) and ooo_lsu_l1d_has_line(`ooo_lsu_l1d_s1`, `ooo_lsu_l1d_a1`, addr), set `ooo_lsu_l1d_rdata` to `ooo_lsu_l1d_data1`; set `ooo_lsu_l1d_lru` to false.
- **ooo_lsu_l1d_read_miss0** — when 0 equals 0 and not (store) and not (ooo_lsu_l1d_has_line(`ooo_lsu_l1d_s0`, `ooo_lsu_l1d_a0`, addr)) and not (ooo_lsu_l1d_has_line(`ooo_lsu_l1d_s1`, `ooo_lsu_l1d_a1`, addr)) and not (`ooo_lsu_l1d_lru`), set `ooo_lsu_l1d_s0` to 1; set `ooo_lsu_l1d_a0` to addr.
- **ooo_lsu_l1d_read_miss1** — when 0 equals 0 and not (store) and not (ooo_lsu_l1d_has_line(`ooo_lsu_l1d_s0`, `ooo_lsu_l1d_a0`, addr)) and not (ooo_lsu_l1d_has_line(`ooo_lsu_l1d_s1`, `ooo_lsu_l1d_a1`, addr)) and `ooo_lsu_l1d_lru`, set `ooo_lsu_l1d_s1` to 1; set `ooo_lsu_l1d_a1` to addr.
- **ooo_lsu_l1d_snoop_inv0** — when 0 does not equal 0 and store and ooo_lsu_l1d_has_line(`ooo_lsu_l1d_s0`, `ooo_lsu_l1d_a0`, addr), set `ooo_lsu_l1d_s0` to 0.
- **ooo_lsu_l1d_snoop_inv1** — when 0 does not equal 0 and store and ooo_lsu_l1d_has_line(`ooo_lsu_l1d_s1`, `ooo_lsu_l1d_a1`, addr), set `ooo_lsu_l1d_s1` to 0.
- **ooo_lsu_l1d_snoop_dg0** — when 0 does not equal 0 and not (store) and ooo_lsu_l1d_has_line(`ooo_lsu_l1d_s0`, `ooo_lsu_l1d_a0`, addr), set `ooo_lsu_l1d_s0` to 1.
- **ooo_lsu_l1d_snoop_dg1** — when 0 does not equal 0 and not (store) and ooo_lsu_l1d_has_line(`ooo_lsu_l1d_s1`, `ooo_lsu_l1d_a1`, addr), set `ooo_lsu_l1d_s1` to 1.
- **cache_l1i_write_hit0** — when 0 equals 0 and cache_const_false and cache_l1i_has_line(`cache_l1i_s0`, `cache_l1i_a0`, i_pa_signal), set `cache_l1i_s0` to 3; set `cache_l1i_data0` to 0; set `cache_l1i_lru` to true.
- **cache_l1i_write_hit1** — when 0 equals 0 and cache_const_false and not (cache_l1i_has_line(`cache_l1i_s0`, `cache_l1i_a0`, i_pa_signal)) and cache_l1i_has_line(`cache_l1i_s1`, `cache_l1i_a1`, i_pa_signal), set `cache_l1i_s1` to 3; set `cache_l1i_data1` to 0; set `cache_l1i_lru` to false.
- **cache_l1i_write_miss0** — when 0 equals 0 and cache_const_false and not (cache_l1i_has_line(`cache_l1i_s0`, `cache_l1i_a0`, i_pa_signal)) and not (cache_l1i_has_line(`cache_l1i_s1`, `cache_l1i_a1`, i_pa_signal)) and not (`cache_l1i_lru`), set `cache_l1i_s0` to 3; set `cache_l1i_a0` to i_pa_signal; set `cache_l1i_data0` to 0; set `cache_l1i_lru` to true.
- **cache_l1i_write_miss1** — when 0 equals 0 and cache_const_false and not (cache_l1i_has_line(`cache_l1i_s0`, `cache_l1i_a0`, i_pa_signal)) and not (cache_l1i_has_line(`cache_l1i_s1`, `cache_l1i_a1`, i_pa_signal)) and `cache_l1i_lru`, set `cache_l1i_s1` to 3; set `cache_l1i_a1` to i_pa_signal; set `cache_l1i_data1` to 0; set `cache_l1i_lru` to false.
- **cache_l1i_read_hit0** — when 0 equals 0 and not (cache_const_false) and cache_l1i_has_line(`cache_l1i_s0`, `cache_l1i_a0`, i_pa_signal), set `cache_l1i_rdata` to `cache_l1i_data0`; set `cache_l1i_lru` to true.
- **cache_l1i_read_hit1** — when 0 equals 0 and not (cache_const_false) and not (cache_l1i_has_line(`cache_l1i_s0`, `cache_l1i_a0`, i_pa_signal)) and cache_l1i_has_line(`cache_l1i_s1`, `cache_l1i_a1`, i_pa_signal), set `cache_l1i_rdata` to `cache_l1i_data1`; set `cache_l1i_lru` to false.
- **cache_l1i_read_miss0** — when 0 equals 0 and not (cache_const_false) and not (cache_l1i_has_line(`cache_l1i_s0`, `cache_l1i_a0`, i_pa_signal)) and not (cache_l1i_has_line(`cache_l1i_s1`, `cache_l1i_a1`, i_pa_signal)) and not (`cache_l1i_lru`), set `cache_l1i_s0` to 1; set `cache_l1i_a0` to i_pa_signal.
- **cache_l1i_read_miss1** — when 0 equals 0 and not (cache_const_false) and not (cache_l1i_has_line(`cache_l1i_s0`, `cache_l1i_a0`, i_pa_signal)) and not (cache_l1i_has_line(`cache_l1i_s1`, `cache_l1i_a1`, i_pa_signal)) and `cache_l1i_lru`, set `cache_l1i_s1` to 1; set `cache_l1i_a1` to i_pa_signal.
- **cache_l1i_snoop_inv0** — when 0 does not equal 0 and cache_const_false and cache_l1i_has_line(`cache_l1i_s0`, `cache_l1i_a0`, i_pa_signal), set `cache_l1i_s0` to 0.
- **cache_l1i_snoop_inv1** — when 0 does not equal 0 and cache_const_false and cache_l1i_has_line(`cache_l1i_s1`, `cache_l1i_a1`, i_pa_signal), set `cache_l1i_s1` to 0.
- **cache_l1i_snoop_dg0** — when 0 does not equal 0 and not (cache_const_false) and cache_l1i_has_line(`cache_l1i_s0`, `cache_l1i_a0`, i_pa_signal), set `cache_l1i_s0` to 1.
- **cache_l1i_snoop_dg1** — when 0 does not equal 0 and not (cache_const_false) and cache_l1i_has_line(`cache_l1i_s1`, `cache_l1i_a1`, i_pa_signal), set `cache_l1i_s1` to 1.
- **cache_l1d_write_hit0** — when req_core equals 0 and l1d_write_signal and cache_l1d_has_line(`cache_l1d_s0`, `cache_l1d_a0`, l1d_addr_signal), set `cache_l1d_s0` to 3; set `cache_l1d_data0` to req_data; set `cache_l1d_lru` to true.
- **cache_l1d_write_hit1** — when req_core equals 0 and l1d_write_signal and not (cache_l1d_has_line(`cache_l1d_s0`, `cache_l1d_a0`, l1d_addr_signal)) and cache_l1d_has_line(`cache_l1d_s1`, `cache_l1d_a1`, l1d_addr_signal), set `cache_l1d_s1` to 3; set `cache_l1d_data1` to req_data; set `cache_l1d_lru` to false.
- **cache_l1d_write_miss0** — when req_core equals 0 and l1d_write_signal and not (cache_l1d_has_line(`cache_l1d_s0`, `cache_l1d_a0`, l1d_addr_signal)) and not (cache_l1d_has_line(`cache_l1d_s1`, `cache_l1d_a1`, l1d_addr_signal)) and not (`cache_l1d_lru`), set `cache_l1d_s0` to 3; set `cache_l1d_a0` to l1d_addr_signal; set `cache_l1d_data0` to req_data; set `cache_l1d_lru` to true.
- **cache_l1d_write_miss1** — when req_core equals 0 and l1d_write_signal and not (cache_l1d_has_line(`cache_l1d_s0`, `cache_l1d_a0`, l1d_addr_signal)) and not (cache_l1d_has_line(`cache_l1d_s1`, `cache_l1d_a1`, l1d_addr_signal)) and `cache_l1d_lru`, set `cache_l1d_s1` to 3; set `cache_l1d_a1` to l1d_addr_signal; set `cache_l1d_data1` to req_data; set `cache_l1d_lru` to false.
- **cache_l1d_read_hit0** — when req_core equals 0 and not (l1d_write_signal) and cache_l1d_has_line(`cache_l1d_s0`, `cache_l1d_a0`, l1d_addr_signal), set `cache_l1d_rdata_signal` to `cache_l1d_data0`; set `cache_l1d_lru` to true.
- **cache_l1d_read_hit1** — when req_core equals 0 and not (l1d_write_signal) and not (cache_l1d_has_line(`cache_l1d_s0`, `cache_l1d_a0`, l1d_addr_signal)) and cache_l1d_has_line(`cache_l1d_s1`, `cache_l1d_a1`, l1d_addr_signal), set `cache_l1d_rdata_signal` to `cache_l1d_data1`; set `cache_l1d_lru` to false.
- **cache_l1d_read_miss0** — when req_core equals 0 and not (l1d_write_signal) and not (cache_l1d_has_line(`cache_l1d_s0`, `cache_l1d_a0`, l1d_addr_signal)) and not (cache_l1d_has_line(`cache_l1d_s1`, `cache_l1d_a1`, l1d_addr_signal)) and not (`cache_l1d_lru`), set `cache_l1d_s0` to 1; set `cache_l1d_a0` to l1d_addr_signal.
- **cache_l1d_read_miss1** — when req_core equals 0 and not (l1d_write_signal) and not (cache_l1d_has_line(`cache_l1d_s0`, `cache_l1d_a0`, l1d_addr_signal)) and not (cache_l1d_has_line(`cache_l1d_s1`, `cache_l1d_a1`, l1d_addr_signal)) and `cache_l1d_lru`, set `cache_l1d_s1` to 1; set `cache_l1d_a1` to l1d_addr_signal.
- **cache_l1d_snoop_inv0** — when req_core does not equal 0 and l1d_write_signal and cache_l1d_has_line(`cache_l1d_s0`, `cache_l1d_a0`, l1d_addr_signal), set `cache_l1d_s0` to 0.
- **cache_l1d_snoop_inv1** — when req_core does not equal 0 and l1d_write_signal and cache_l1d_has_line(`cache_l1d_s1`, `cache_l1d_a1`, l1d_addr_signal), set `cache_l1d_s1` to 0.
- **cache_l1d_snoop_dg0** — when req_core does not equal 0 and not (l1d_write_signal) and cache_l1d_has_line(`cache_l1d_s0`, `cache_l1d_a0`, l1d_addr_signal), set `cache_l1d_s0` to 1.
- **cache_l1d_snoop_dg1** — when req_core does not equal 0 and not (l1d_write_signal) and cache_l1d_has_line(`cache_l1d_s1`, `cache_l1d_a1`, l1d_addr_signal), set `cache_l1d_s1` to 1.
- **cache_l2_write_hit0** — when req_core equals 0 and l1d_write_signal and cache_l2_has_line(`cache_l2_s0`, `cache_l2_a0`, l1d_addr_signal), set `cache_l2_s0` to 3; set `cache_l2_lru` to true; mem_write(cache_l2_mem, l1d_addr_signal, req_data).
- **cache_l2_write_hit1** — when req_core equals 0 and l1d_write_signal and not (cache_l2_has_line(`cache_l2_s0`, `cache_l2_a0`, l1d_addr_signal)) and cache_l2_has_line(`cache_l2_s1`, `cache_l2_a1`, l1d_addr_signal), set `cache_l2_s1` to 3; set `cache_l2_lru` to false; mem_write(cache_l2_mem, l1d_addr_signal, req_data).
- **cache_l2_write_miss0** — when req_core equals 0 and l1d_write_signal and not (cache_l2_has_line(`cache_l2_s0`, `cache_l2_a0`, l1d_addr_signal)) and not (cache_l2_has_line(`cache_l2_s1`, `cache_l2_a1`, l1d_addr_signal)) and not (`cache_l2_lru`), set `cache_l2_s0` to 3; set `cache_l2_a0` to l1d_addr_signal; set `cache_l2_lru` to true; mem_write(cache_l2_mem, l1d_addr_signal, req_data); set `miss_valid_signal` to true; set `miss_addr_signal` to l1d_addr_signal.
- **cache_l2_write_miss1** — when req_core equals 0 and l1d_write_signal and not (cache_l2_has_line(`cache_l2_s0`, `cache_l2_a0`, l1d_addr_signal)) and not (cache_l2_has_line(`cache_l2_s1`, `cache_l2_a1`, l1d_addr_signal)) and `cache_l2_lru`, set `cache_l2_s1` to 3; set `cache_l2_a1` to l1d_addr_signal; set `cache_l2_lru` to false; mem_write(cache_l2_mem, l1d_addr_signal, req_data); set `miss_valid_signal` to true; set `miss_addr_signal` to l1d_addr_signal.
- **cache_l2_read_miss0** — when req_core equals 0 and not (l1d_write_signal) and not (cache_l2_has_line(`cache_l2_s0`, `cache_l2_a0`, l1d_addr_signal)) and not (cache_l2_has_line(`cache_l2_s1`, `cache_l2_a1`, l1d_addr_signal)) and not (`cache_l2_lru`), set `cache_l2_s0` to 1; set `cache_l2_a0` to l1d_addr_signal; set `miss_valid_signal` to true; set `miss_addr_signal` to l1d_addr_signal.
- **cache_l2_read_miss1** — when req_core equals 0 and not (l1d_write_signal) and not (cache_l2_has_line(`cache_l2_s0`, `cache_l2_a0`, l1d_addr_signal)) and not (cache_l2_has_line(`cache_l2_s1`, `cache_l2_a1`, l1d_addr_signal)) and `cache_l2_lru`, set `cache_l2_s1` to 1; set `cache_l2_a1` to l1d_addr_signal; set `miss_valid_signal` to true; set `miss_addr_signal` to l1d_addr_signal.
- **cache_l2_snoop_inv0** — when req_core does not equal 0 and l1d_write_signal and cache_l2_has_line(`cache_l2_s0`, `cache_l2_a0`, l1d_addr_signal), set `cache_l2_s0` to 0.
- **cache_l2_snoop_inv1** — when req_core does not equal 0 and l1d_write_signal and cache_l2_has_line(`cache_l2_s1`, `cache_l2_a1`, l1d_addr_signal), set `cache_l2_s1` to 0.
- **cache_l2_snoop_dg0** — when req_core does not equal 0 and not (l1d_write_signal) and cache_l2_has_line(`cache_l2_s0`, `cache_l2_a0`, l1d_addr_signal), set `cache_l2_s0` to 1.
- **cache_l2_snoop_dg1** — when req_core does not equal 0 and not (l1d_write_signal) and cache_l2_has_line(`cache_l2_s1`, `cache_l2_a1`, l1d_addr_signal), set `cache_l2_s1` to 1.
- **cache_l2_mshr_mshr0_alloc** — when miss_valid_signal and not (`cache_l2_mshr_mshr0_valid`), set `cache_l2_mshr_mshr0_valid` to true; set `cache_l2_mshr_mshr0_mid` to 0; set `cache_l2_mshr_mshr0_maddr` to l1d_addr_signal; set `cache_l2_mshr_mshr0_mdata` to req_data.
- **cache_l2_mshr_mshr0_rel** — when release0, set `cache_l2_mshr_mshr0_valid` to false.
- **cache_l2_mshr_mshr1_alloc** — when miss_valid_signal and not (`cache_l2_mshr_mshr1_valid`), set `cache_l2_mshr_mshr1_valid` to true; set `cache_l2_mshr_mshr1_mid` to 0; set `cache_l2_mshr_mshr1_maddr` to l1d_addr_signal; set `cache_l2_mshr_mshr1_mdata` to req_data.
- **cache_l2_mshr_mshr1_rel** — when release1, set `cache_l2_mshr_mshr1_valid` to false.
- **cache_l2_mshr_arb_arbitrate** — when true, set `cache_l2_mshr_arb_grant` to if miss_valid_signal, then 0, otherwise if miss_valid_signal, then 1, otherwise if cache_l2_mshr_arb_req2_valid, then 2, otherwise if cache_l2_mshr_arb_req3_valid, then 3, otherwise if cache_l2_mshr_arb_req4_valid, then 4, otherwise if cache_l2_mshr_arb_req5_valid, then 5, otherwise 0; set `cache_l2_mshr_arb_grant_valid` to miss_valid_signal or miss_valid_signal or cache_l2_mshr_arb_req2_valid or cache_l2_mshr_arb_req3_valid or cache_l2_mshr_arb_req4_valid or cache_l2_mshr_arb_req5_valid.
- **axi_mem_do_read** — when miss_valid_signal, set `axi_mem_rdata` to mem_read(axi_mem_mem, miss_addr_signal); set `axi_mem_rvalid` to true.
- **axi_mem_do_write** — when awvalid and wvalid, mem_write(axi_mem_mem, awaddr, wdata); set `axi_mem_bvalid` to true.

## Properties

- **cache_l1d_is_modified_implies_valid** (safety): always, if cache_l1d_is_modified(`cache_l1d_s0`), then `cache_l1d_s0` does not equal 0.
- **cache_l1d_phys_index_bounded** (safety): always, cache_l1d_phys_index(`cache_l1d_a0`) ≤ 3.
- **cache_l1i_is_modified_implies_valid** (safety): always, if cache_l1i_is_modified(`cache_l1i_s0`), then `cache_l1i_s0` does not equal 0.
- **cache_l1i_phys_index_bounded** (safety): always, cache_l1i_phys_index(`cache_l1i_a0`) ≤ 3.
- **ooo_lsu_l1d_is_modified_implies_valid** (safety): always, if ooo_lsu_l1d_is_modified(`ooo_lsu_l1d_s0`), then `ooo_lsu_l1d_s0` does not equal 0.
- **ooo_lsu_l1d_phys_index_bounded** (safety): always, ooo_lsu_l1d_phys_index(`ooo_lsu_l1d_a0`) ≤ 3.
- **pc_increments** (transition): after each step, `pc` equals prev(pc) + 1.
- **itlb_hit_sets_i_pa** (transition): after each step, `i_pa_signal` equals `mmu_itlb_way0_ppn`.
- **dtlb_hit_sets_pa** (transition): after each step, `pa_signal` equals `mmu_dtlb_way0_ppn`.
- **l2_miss_issues_axi** (transition): after each step, `miss_valid_signal` equals true.
- **tlb_miss_triggers_ptw** (transition): after each step, `tlb_miss_signal` equals `i_miss_signal` or `d_miss_signal`.
- **ptw_read_is_pipt** (transition): after each step, if `ptw_active_signal`, then `l1d_phys_signal` equals true.
