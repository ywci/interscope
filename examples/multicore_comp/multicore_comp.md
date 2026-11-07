# multicore_comp specification

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
| `d_is_physical` | bool |
| `alloc_valid` | bool |
| `id` | bits<2> |
| `release0` | bool |
| `release1` | bool |
| `core0_ooo_lsu_l1d_is_physical` | bool |
| `core0_ooo_lsu_l1d_req_data` | bits<8> |
| `core0_cache_l2_mshr_arb_req2_valid` | bool |
| `core0_cache_l2_mshr_arb_req3_valid` | bool |
| `core0_cache_l2_mshr_arb_req4_valid` | bool |
| `core0_cache_l2_mshr_arb_req5_valid` | bool |
| `core1_ooo_lsu_l1d_is_physical` | bool |
| `core1_ooo_lsu_l1d_req_data` | bits<8> |
| `core1_cache_l2_mshr_arb_req2_valid` | bool |
| `core1_cache_l2_mshr_arb_req3_valid` | bool |
| `core1_cache_l2_mshr_arb_req4_valid` | bool |
| `core1_cache_l2_mshr_arb_req5_valid` | bool |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `core0_pc_signal` | register | bits<4> | 0 |
| `core0_i_pa_signal` | register | bits<4> | 0 |
| `core0_pa_signal` | register | bits<4> | 0 |
| `core0_d_vpn_signal` | register | bits<2> | 0 |
| `core0_ptw_mem_addr_signal` | register | bits<4> | 0 |
| `core0_ptw_active_signal` | register | bool | false |
| `core0_ptw_mem_data_signal` | register | bits<8> | 0 |
| `core0_l1d_addr_signal` | register | bits<4> | 0 |
| `core0_l1d_write_signal` | register | bool | false |
| `core0_l1d_phys_signal` | register | bool | false |
| `core0_i_miss_signal` | register | bool | false |
| `core0_d_miss_signal` | register | bool | false |
| `core0_tlb_miss_signal` | register | bool | false |
| `core0_miss_valid_signal` | register | bool | false |
| `core0_miss_addr_signal` | register | bits<4> | 0 |
| `core0_pc` | register | bits<4> | 0 |
| `core0_mmu_ppn_fill` | register | bits<4> | 0 |
| `core0_mmu_ptw_ppn` | register | bits<4> | 0 |
| `core0_mmu_itlb_way0_vpn` | register | bits<4> | 0 |
| `core0_mmu_itlb_way0_ppn` | register | bits<4> | 0 |
| `core0_mmu_itlb_way0_valid` | register | bool | false |
| `core0_mmu_itlb_way1_vpn` | register | bits<4> | 0 |
| `core0_mmu_itlb_way1_ppn` | register | bits<4> | 0 |
| `core0_mmu_itlb_way1_valid` | register | bool | false |
| `core0_mmu_itlb_lru` | register | bool | false |
| `core0_mmu_dtlb_way0_vpn` | register | bits<4> | 0 |
| `core0_mmu_dtlb_way0_ppn` | register | bits<4> | 0 |
| `core0_mmu_dtlb_way0_valid` | register | bool | false |
| `core0_mmu_dtlb_way1_vpn` | register | bits<4> | 0 |
| `core0_mmu_dtlb_way1_ppn` | register | bits<4> | 0 |
| `core0_mmu_dtlb_way1_valid` | register | bool | false |
| `core0_mmu_dtlb_lru` | register | bool | false |
| `core0_mmu_ptw_root_ppn` | register | bits<4> | 0 |
| `core0_mmu_ptw_walk_state` | register | bits<2> | 0 |
| `core0_mmu_ptw_pte1` | register | bits<8> | 0 |
| `core0_mmu_ptw_pte0` | register | bits<8> | 0 |
| `core0_mmu_ptw_result_pa` | register | bits<8> | 0 |
| `core0_fetch_bpu_ctr` | register | bits<2> | 1 |
| `core0_fetch_bpu_predict` | register | bool | false |
| `core0_ooo_rat0` | register | bits<3> | 0 |
| `core0_ooo_rat1` | register | bits<3> | 1 |
| `core0_ooo_rat2` | register | bits<3> | 2 |
| `core0_ooo_rat3` | register | bits<3> | 3 |
| `core0_ooo_prf0_busy` | register | bool | true |
| `core0_ooo_prf1_busy` | register | bool | true |
| `core0_ooo_prf2_busy` | register | bool | true |
| `core0_ooo_prf3_busy` | register | bool | true |
| `core0_ooo_prf4_busy` | register | bool | false |
| `core0_ooo_prf5_busy` | register | bool | false |
| `core0_ooo_rob0_valid` | register | bool | false |
| `core0_ooo_rob0_rd` | register | bits<2> | 0 |
| `core0_ooo_rob0_old` | register | bits<3> | 0 |
| `core0_ooo_rob0_done` | register | bool | false |
| `core0_ooo_rob1_valid` | register | bool | false |
| `core0_ooo_rob1_rd` | register | bits<2> | 0 |
| `core0_ooo_rob1_old` | register | bits<3> | 0 |
| `core0_ooo_rob1_done` | register | bool | false |
| `core0_ooo_head` | register | bool | false |
| `core0_ooo_result` | register | bits<8> | 0 |
| `core0_ooo_sb_valid` | register | bool | false |
| `core0_ooo_sb_addr` | register | bits<4> | 0 |
| `core0_ooo_sb_data` | register | bits<8> | 0 |
| `core0_ooo_alu_result_reg` | register | bits<8> | 0 |
| `core0_ooo_alu_zero_reg` | register | bool | false |
| `core0_ooo_alu_overflow_reg` | register | bool | false |
| `core0_ooo_alu_valid` | register | bool | false |
| `core0_ooo_alu_op_reg` | register | bits<3> | 0 |
| `core0_ooo_alu_a_reg` | register | bits<8> | 0 |
| `core0_ooo_alu_b_reg` | register | bits<8> | 0 |
| `core0_ooo_lsu_mem` | memory | memory(bits<8>, 16) |  |
| `core0_ooo_lsu_resp_data` | register | bits<8> | 0 |
| `core0_ooo_lsu_resp_valid` | register | bool | false |
| `core0_ooo_lsu_l1d_s0` | register | bits<2> | 0 |
| `core0_ooo_lsu_l1d_a0` | register | bits<4> | 0 |
| `core0_ooo_lsu_l1d_s1` | register | bits<2> | 0 |
| `core0_ooo_lsu_l1d_a1` | register | bits<4> | 0 |
| `core0_ooo_lsu_l1d_lru` | register | bool | false |
| `core0_ooo_lsu_l1d_data0` | register | bits<8> | 0 |
| `core0_ooo_lsu_l1d_data1` | register | bits<8> | 0 |
| `core0_ooo_lsu_l1d_rdata` | register | bits<8> | 0 |
| `core0_cache_const_false` | register | bool | false |
| `core0_cache_l1d_rdata_signal` | register | bits<8> | 0 |
| `core0_cache_l1i_s0` | register | bits<2> | 0 |
| `core0_cache_l1i_a0` | register | bits<4> | 0 |
| `core0_cache_l1i_s1` | register | bits<2> | 0 |
| `core0_cache_l1i_a1` | register | bits<4> | 0 |
| `core0_cache_l1i_lru` | register | bool | false |
| `core0_cache_l1i_data0` | register | bits<8> | 0 |
| `core0_cache_l1i_data1` | register | bits<8> | 0 |
| `core0_cache_l1i_rdata` | register | bits<8> | 0 |
| `core0_cache_l1d_s0` | register | bits<2> | 0 |
| `core0_cache_l1d_a0` | register | bits<4> | 0 |
| `core0_cache_l1d_s1` | register | bits<2> | 0 |
| `core0_cache_l1d_a1` | register | bits<4> | 0 |
| `core0_cache_l1d_lru` | register | bool | false |
| `core0_cache_l1d_data0` | register | bits<8> | 0 |
| `core0_cache_l1d_data1` | register | bits<8> | 0 |
| `core0_cache_l2_s0` | register | bits<2> | 0 |
| `core0_cache_l2_a0` | register | bits<4> | 0 |
| `core0_cache_l2_s1` | register | bits<2> | 0 |
| `core0_cache_l2_a1` | register | bits<4> | 0 |
| `core0_cache_l2_lru` | register | bool | false |
| `core0_cache_l2_mem` | memory | memory(bits<8>, 16) |  |
| `core0_cache_l2_mshr_mshr0_valid` | register | bool | false |
| `core0_cache_l2_mshr_mshr0_mid` | register | bits<2> | 0 |
| `core0_cache_l2_mshr_mshr0_maddr` | register | bits<4> | 0 |
| `core0_cache_l2_mshr_mshr0_mdata` | register | bits<8> | 0 |
| `core0_cache_l2_mshr_mshr1_valid` | register | bool | false |
| `core0_cache_l2_mshr_mshr1_mid` | register | bits<2> | 0 |
| `core0_cache_l2_mshr_mshr1_maddr` | register | bits<4> | 0 |
| `core0_cache_l2_mshr_mshr1_mdata` | register | bits<8> | 0 |
| `core0_cache_l2_mshr_arb_grant` | register | bits<3> | 0 |
| `core0_cache_l2_mshr_arb_grant_valid` | register | bool | false |
| `core0_axi_mem_mem` | memory | memory(bits<8>, 16) |  |
| `core0_axi_mem_rdata` | register | bits<8> | 0 |
| `core0_axi_mem_rvalid` | register | bool | false |
| `core0_axi_mem_bvalid` | register | bool | false |
| `core1_pc_signal` | register | bits<4> | 0 |
| `core1_i_pa_signal` | register | bits<4> | 0 |
| `core1_pa_signal` | register | bits<4> | 0 |
| `core1_d_vpn_signal` | register | bits<2> | 0 |
| `core1_ptw_mem_addr_signal` | register | bits<4> | 0 |
| `core1_ptw_active_signal` | register | bool | false |
| `core1_ptw_mem_data_signal` | register | bits<8> | 0 |
| `core1_l1d_addr_signal` | register | bits<4> | 0 |
| `core1_l1d_write_signal` | register | bool | false |
| `core1_l1d_phys_signal` | register | bool | false |
| `core1_i_miss_signal` | register | bool | false |
| `core1_d_miss_signal` | register | bool | false |
| `core1_tlb_miss_signal` | register | bool | false |
| `core1_miss_valid_signal` | register | bool | false |
| `core1_miss_addr_signal` | register | bits<4> | 0 |
| `core1_pc` | register | bits<4> | 0 |
| `core1_mmu_ppn_fill` | register | bits<4> | 0 |
| `core1_mmu_ptw_ppn` | register | bits<4> | 0 |
| `core1_mmu_itlb_way0_vpn` | register | bits<4> | 0 |
| `core1_mmu_itlb_way0_ppn` | register | bits<4> | 0 |
| `core1_mmu_itlb_way0_valid` | register | bool | false |
| `core1_mmu_itlb_way1_vpn` | register | bits<4> | 0 |
| `core1_mmu_itlb_way1_ppn` | register | bits<4> | 0 |
| `core1_mmu_itlb_way1_valid` | register | bool | false |
| `core1_mmu_itlb_lru` | register | bool | false |
| `core1_mmu_dtlb_way0_vpn` | register | bits<4> | 0 |
| `core1_mmu_dtlb_way0_ppn` | register | bits<4> | 0 |
| `core1_mmu_dtlb_way0_valid` | register | bool | false |
| `core1_mmu_dtlb_way1_vpn` | register | bits<4> | 0 |
| `core1_mmu_dtlb_way1_ppn` | register | bits<4> | 0 |
| `core1_mmu_dtlb_way1_valid` | register | bool | false |
| `core1_mmu_dtlb_lru` | register | bool | false |
| `core1_mmu_ptw_root_ppn` | register | bits<4> | 0 |
| `core1_mmu_ptw_walk_state` | register | bits<2> | 0 |
| `core1_mmu_ptw_pte1` | register | bits<8> | 0 |
| `core1_mmu_ptw_pte0` | register | bits<8> | 0 |
| `core1_mmu_ptw_result_pa` | register | bits<8> | 0 |
| `core1_fetch_bpu_ctr` | register | bits<2> | 1 |
| `core1_fetch_bpu_predict` | register | bool | false |
| `core1_ooo_rat0` | register | bits<3> | 0 |
| `core1_ooo_rat1` | register | bits<3> | 1 |
| `core1_ooo_rat2` | register | bits<3> | 2 |
| `core1_ooo_rat3` | register | bits<3> | 3 |
| `core1_ooo_prf0_busy` | register | bool | true |
| `core1_ooo_prf1_busy` | register | bool | true |
| `core1_ooo_prf2_busy` | register | bool | true |
| `core1_ooo_prf3_busy` | register | bool | true |
| `core1_ooo_prf4_busy` | register | bool | false |
| `core1_ooo_prf5_busy` | register | bool | false |
| `core1_ooo_rob0_valid` | register | bool | false |
| `core1_ooo_rob0_rd` | register | bits<2> | 0 |
| `core1_ooo_rob0_old` | register | bits<3> | 0 |
| `core1_ooo_rob0_done` | register | bool | false |
| `core1_ooo_rob1_valid` | register | bool | false |
| `core1_ooo_rob1_rd` | register | bits<2> | 0 |
| `core1_ooo_rob1_old` | register | bits<3> | 0 |
| `core1_ooo_rob1_done` | register | bool | false |
| `core1_ooo_head` | register | bool | false |
| `core1_ooo_result` | register | bits<8> | 0 |
| `core1_ooo_sb_valid` | register | bool | false |
| `core1_ooo_sb_addr` | register | bits<4> | 0 |
| `core1_ooo_sb_data` | register | bits<8> | 0 |
| `core1_ooo_alu_result_reg` | register | bits<8> | 0 |
| `core1_ooo_alu_zero_reg` | register | bool | false |
| `core1_ooo_alu_overflow_reg` | register | bool | false |
| `core1_ooo_alu_valid` | register | bool | false |
| `core1_ooo_alu_op_reg` | register | bits<3> | 0 |
| `core1_ooo_alu_a_reg` | register | bits<8> | 0 |
| `core1_ooo_alu_b_reg` | register | bits<8> | 0 |
| `core1_ooo_lsu_mem` | memory | memory(bits<8>, 16) |  |
| `core1_ooo_lsu_resp_data` | register | bits<8> | 0 |
| `core1_ooo_lsu_resp_valid` | register | bool | false |
| `core1_ooo_lsu_l1d_s0` | register | bits<2> | 0 |
| `core1_ooo_lsu_l1d_a0` | register | bits<4> | 0 |
| `core1_ooo_lsu_l1d_s1` | register | bits<2> | 0 |
| `core1_ooo_lsu_l1d_a1` | register | bits<4> | 0 |
| `core1_ooo_lsu_l1d_lru` | register | bool | false |
| `core1_ooo_lsu_l1d_data0` | register | bits<8> | 0 |
| `core1_ooo_lsu_l1d_data1` | register | bits<8> | 0 |
| `core1_ooo_lsu_l1d_rdata` | register | bits<8> | 0 |
| `core1_cache_const_false` | register | bool | false |
| `core1_cache_l1d_rdata_signal` | register | bits<8> | 0 |
| `core1_cache_l1i_s0` | register | bits<2> | 0 |
| `core1_cache_l1i_a0` | register | bits<4> | 0 |
| `core1_cache_l1i_s1` | register | bits<2> | 0 |
| `core1_cache_l1i_a1` | register | bits<4> | 0 |
| `core1_cache_l1i_lru` | register | bool | false |
| `core1_cache_l1i_data0` | register | bits<8> | 0 |
| `core1_cache_l1i_data1` | register | bits<8> | 0 |
| `core1_cache_l1i_rdata` | register | bits<8> | 0 |
| `core1_cache_l1d_s0` | register | bits<2> | 0 |
| `core1_cache_l1d_a0` | register | bits<4> | 0 |
| `core1_cache_l1d_s1` | register | bits<2> | 0 |
| `core1_cache_l1d_a1` | register | bits<4> | 0 |
| `core1_cache_l1d_lru` | register | bool | false |
| `core1_cache_l1d_data0` | register | bits<8> | 0 |
| `core1_cache_l1d_data1` | register | bits<8> | 0 |
| `core1_cache_l2_s0` | register | bits<2> | 0 |
| `core1_cache_l2_a0` | register | bits<4> | 0 |
| `core1_cache_l2_s1` | register | bits<2> | 0 |
| `core1_cache_l2_a1` | register | bits<4> | 0 |
| `core1_cache_l2_lru` | register | bool | false |
| `core1_cache_l2_mem` | memory | memory(bits<8>, 16) |  |
| `core1_cache_l2_mshr_mshr0_valid` | register | bool | false |
| `core1_cache_l2_mshr_mshr0_mid` | register | bits<2> | 0 |
| `core1_cache_l2_mshr_mshr0_maddr` | register | bits<4> | 0 |
| `core1_cache_l2_mshr_mshr0_mdata` | register | bits<8> | 0 |
| `core1_cache_l2_mshr_mshr1_valid` | register | bool | false |
| `core1_cache_l2_mshr_mshr1_mid` | register | bits<2> | 0 |
| `core1_cache_l2_mshr_mshr1_maddr` | register | bits<4> | 0 |
| `core1_cache_l2_mshr_mshr1_mdata` | register | bits<8> | 0 |
| `core1_cache_l2_mshr_arb_grant` | register | bits<3> | 0 |
| `core1_cache_l2_mshr_arb_grant_valid` | register | bool | false |
| `core1_axi_mem_mem` | memory | memory(bits<8>, 16) |  |
| `core1_axi_mem_rdata` | register | bits<8> | 0 |
| `core1_axi_mem_rvalid` | register | bool | false |
| `core1_axi_mem_bvalid` | register | bool | false |
| `home_c0_state` | register | bits<2> | 0 |
| `home_c0_addr` | register | bits<4> | 0 |
| `home_c0_data` | register | bits<8> | 0 |
| `home_c1_state` | register | bits<2> | 0 |
| `home_c1_addr` | register | bits<4> | 0 |
| `home_c1_data` | register | bits<8> | 0 |
| `axi_mem_mem` | memory | memory(bits<8>, 16) |  |
| `axi_mem_rdata` | register | bits<8> | 0 |
| `axi_mem_rvalid` | register | bool | false |
| `axi_mem_bvalid` | register | bool | false |

## Behavior (rules)

- **core0_slice_d_vpn** — when true, set `core0_d_vpn_signal` to addr[1:0].
- **core0_mux_l1d_addr** — when true, set `core0_l1d_addr_signal` to if `core0_ptw_active_signal`, then `core0_ptw_mem_addr_signal`, otherwise core0_pa_signal.
- **core0_mux_l1d_write** — when true, set `core0_l1d_write_signal` to not (`core0_ptw_active_signal`) and req_write.
- **core0_mux_l1d_phys** — when true, set `core0_l1d_phys_signal` to `core0_ptw_active_signal` or d_is_physical.
- **core0_retire** — when req_core equals 0, set `core0_pc` to `core0_pc` + 1.
- **core0_mmu_combine_miss** — when true, set `core0_tlb_miss_signal` to `core0_i_miss_signal` or `core0_d_miss_signal`.
- **core0_mmu_slice_ppn** — when true, set `core0_mmu_ppn_fill` to `core0_mmu_ptw_ppn`.
- **core0_mmu_ptw_is_active** — when true, set `core0_ptw_active_signal` to `core0_mmu_ptw_walk_state` does not equal 0.
- **core0_mmu_itlb_hit0** — when core0_mmu_itlb_way_hit(`core0_mmu_itlb_way0_valid`, `core0_mmu_itlb_way0_vpn`, core0_pc_signal), set `core0_i_pa_signal` to `core0_mmu_itlb_way0_ppn`; set `core0_mmu_itlb_lru` to true; set `core0_i_miss_signal` to false.
- **core0_mmu_itlb_hit1** — when core0_mmu_itlb_way_hit(`core0_mmu_itlb_way1_valid`, `core0_mmu_itlb_way1_vpn`, core0_pc_signal), set `core0_i_pa_signal` to `core0_mmu_itlb_way1_ppn`; set `core0_mmu_itlb_lru` to false; set `core0_i_miss_signal` to false.
- **core0_mmu_itlb_fill0** — when not (core0_mmu_itlb_way_hit(`core0_mmu_itlb_way0_valid`, `core0_mmu_itlb_way0_vpn`, core0_pc_signal)) and not (core0_mmu_itlb_way_hit(`core0_mmu_itlb_way1_valid`, `core0_mmu_itlb_way1_vpn`, core0_pc_signal)) and not (`core0_mmu_itlb_lru`), set `core0_mmu_itlb_way0_vpn` to core0_pc_signal; set `core0_mmu_itlb_way0_ppn` to core0_mmu_ppn_fill; set `core0_mmu_itlb_way0_valid` to true; set `core0_mmu_itlb_lru` to true; set `core0_i_miss_signal` to true.
- **core0_mmu_itlb_fill1** — when not (core0_mmu_itlb_way_hit(`core0_mmu_itlb_way0_valid`, `core0_mmu_itlb_way0_vpn`, core0_pc_signal)) and not (core0_mmu_itlb_way_hit(`core0_mmu_itlb_way1_valid`, `core0_mmu_itlb_way1_vpn`, core0_pc_signal)) and `core0_mmu_itlb_lru`, set `core0_mmu_itlb_way1_vpn` to core0_pc_signal; set `core0_mmu_itlb_way1_ppn` to core0_mmu_ppn_fill; set `core0_mmu_itlb_way1_valid` to true; set `core0_mmu_itlb_lru` to false; set `core0_i_miss_signal` to true.
- **core0_mmu_dtlb_hit0** — when core0_mmu_dtlb_way_hit(`core0_mmu_dtlb_way0_valid`, `core0_mmu_dtlb_way0_vpn`, addr), set `core0_pa_signal` to `core0_mmu_dtlb_way0_ppn`; set `core0_mmu_dtlb_lru` to true; set `core0_d_miss_signal` to false.
- **core0_mmu_dtlb_hit1** — when core0_mmu_dtlb_way_hit(`core0_mmu_dtlb_way1_valid`, `core0_mmu_dtlb_way1_vpn`, addr), set `core0_pa_signal` to `core0_mmu_dtlb_way1_ppn`; set `core0_mmu_dtlb_lru` to false; set `core0_d_miss_signal` to false.
- **core0_mmu_dtlb_fill0** — when not (core0_mmu_dtlb_way_hit(`core0_mmu_dtlb_way0_valid`, `core0_mmu_dtlb_way0_vpn`, addr)) and not (core0_mmu_dtlb_way_hit(`core0_mmu_dtlb_way1_valid`, `core0_mmu_dtlb_way1_vpn`, addr)) and not (`core0_mmu_dtlb_lru`), set `core0_mmu_dtlb_way0_vpn` to addr; set `core0_mmu_dtlb_way0_ppn` to core0_mmu_ppn_fill; set `core0_mmu_dtlb_way0_valid` to true; set `core0_mmu_dtlb_lru` to true; set `core0_d_miss_signal` to true.
- **core0_mmu_dtlb_fill1** — when not (core0_mmu_dtlb_way_hit(`core0_mmu_dtlb_way0_valid`, `core0_mmu_dtlb_way0_vpn`, addr)) and not (core0_mmu_dtlb_way_hit(`core0_mmu_dtlb_way1_valid`, `core0_mmu_dtlb_way1_vpn`, addr)) and `core0_mmu_dtlb_lru`, set `core0_mmu_dtlb_way1_vpn` to addr; set `core0_mmu_dtlb_way1_ppn` to core0_mmu_ppn_fill; set `core0_mmu_dtlb_way1_valid` to true; set `core0_mmu_dtlb_lru` to false; set `core0_d_miss_signal` to true.
- **core0_mmu_ptw_walk_start** — when `core0_mmu_ptw_walk_state` equals 0 and core0_tlb_miss_signal, set `core0_ptw_mem_addr_signal` to concat(`core0_mmu_ptw_root_ppn`[1:0], core0_mmu_ptw_vpn1(va), 2); set `core0_mmu_ptw_walk_state` to 1.
- **core0_mmu_ptw_walk_l0** — when `core0_mmu_ptw_walk_state` equals 1, set `core0_mmu_ptw_pte1` to core0_ptw_mem_data_signal; set `core0_ptw_mem_addr_signal` to concat(core0_mmu_ptw_pte_ppn(core0_ptw_mem_data_signal)[1:0], core0_mmu_ptw_vpn0(va), 2); set `core0_mmu_ptw_walk_state` to 2.
- **core0_mmu_ptw_walk_finish** — when `core0_mmu_ptw_walk_state` equals 2, set `core0_mmu_ptw_pte0` to core0_ptw_mem_data_signal; set `core0_mmu_ptw_ppn` to core0_mmu_ptw_pte_ppn(core0_ptw_mem_data_signal); set `core0_mmu_ptw_result_pa` to concat(core0_mmu_ptw_pte_ppn(core0_ptw_mem_data_signal), core0_mmu_ptw_offset(va), 4); set `core0_mmu_ptw_walk_state` to 3.
- **core0_mmu_ptw_walk_reset** — when `core0_mmu_ptw_walk_state` equals 3, set `core0_mmu_ptw_walk_state` to 0.
- **core0_fetch_advance** — when true, set `core0_pc_signal` to if stall, then `core0_pc_signal`, otherwise if `core0_fetch_bpu_predict`, then branch_target, otherwise `core0_pc_signal` + 1.
- **core0_fetch_bpu_update** — when true, set `core0_fetch_bpu_ctr` to if taken, then if `core0_fetch_bpu_ctr` < 3, then `core0_fetch_bpu_ctr` + 1, otherwise 3, otherwise if `core0_fetch_bpu_ctr` > 0, then `core0_fetch_bpu_ctr` − 1, otherwise 0; set `core0_fetch_bpu_predict` to `core0_fetch_bpu_ctr` ≥ 2.
- **core0_ooo_issue0** — when issue_valid and not (`core0_ooo_rob0_valid`), set `core0_ooo_rat0` to if rd equals 0, then 4, otherwise `core0_ooo_rat0`; set `core0_ooo_rat1` to if rd equals 1, then 4, otherwise `core0_ooo_rat1`; set `core0_ooo_rat2` to if rd equals 2, then 4, otherwise `core0_ooo_rat2`; set `core0_ooo_rat3` to if rd equals 3, then 4, otherwise `core0_ooo_rat3`; set `core0_ooo_prf4_busy` to true; set `core0_ooo_rob0_valid` to true; set `core0_ooo_rob0_rd` to rd; set `core0_ooo_rob0_old` to if rd equals 0, then `core0_ooo_rat0`, otherwise if rd equals 1, then `core0_ooo_rat1`, otherwise if rd equals 2, then `core0_ooo_rat2`, otherwise `core0_ooo_rat3`; set `core0_ooo_rob0_done` to false.
- **core0_ooo_issue1** — when issue_valid and `core0_ooo_rob0_valid` and not (`core0_ooo_rob1_valid`), set `core0_ooo_rat0` to if rd equals 0, then 5, otherwise `core0_ooo_rat0`; set `core0_ooo_rat1` to if rd equals 1, then 5, otherwise `core0_ooo_rat1`; set `core0_ooo_rat2` to if rd equals 2, then 5, otherwise `core0_ooo_rat2`; set `core0_ooo_rat3` to if rd equals 3, then 5, otherwise `core0_ooo_rat3`; set `core0_ooo_prf5_busy` to true; set `core0_ooo_rob1_valid` to true; set `core0_ooo_rob1_rd` to rd; set `core0_ooo_rob1_old` to if rd equals 0, then `core0_ooo_rat0`, otherwise if rd equals 1, then `core0_ooo_rat1`, otherwise if rd equals 2, then `core0_ooo_rat2`, otherwise `core0_ooo_rat3`; set `core0_ooo_rob1_done` to false.
- **core0_ooo_store_buf** — when issue_valid and op and store, set `core0_ooo_sb_valid` to true; set `core0_ooo_sb_addr` to addr; set `core0_ooo_sb_data` to a.
- **core0_ooo_execute** — when true, set `core0_ooo_result` to if op, then if store, then `core0_ooo_lsu_resp_data`, otherwise if `core0_ooo_sb_valid` and `core0_ooo_sb_addr` equals addr, then `core0_ooo_sb_data`, otherwise `core0_ooo_lsu_resp_data`, otherwise `core0_ooo_alu_result_reg`.
- **core0_ooo_commit0** — when `core0_ooo_head` equals false and `core0_ooo_rob0_done`, set `core0_ooo_prf0_busy` to if `core0_ooo_rob0_old` equals 0, then false, otherwise `core0_ooo_prf0_busy`; set `core0_ooo_prf1_busy` to if `core0_ooo_rob0_old` equals 1, then false, otherwise `core0_ooo_prf1_busy`; set `core0_ooo_prf2_busy` to if `core0_ooo_rob0_old` equals 2, then false, otherwise `core0_ooo_prf2_busy`; set `core0_ooo_prf3_busy` to if `core0_ooo_rob0_old` equals 3, then false, otherwise `core0_ooo_prf3_busy`; set `core0_ooo_prf4_busy` to if `core0_ooo_rob0_old` equals 4, then false, otherwise `core0_ooo_prf4_busy`; set `core0_ooo_prf5_busy` to if `core0_ooo_rob0_old` equals 5, then false, otherwise `core0_ooo_prf5_busy`; set `core0_ooo_rob0_valid` to false; set `core0_ooo_rob0_done` to false; set `core0_ooo_head` to true.
- **core0_ooo_commit1** — when `core0_ooo_head` equals true and `core0_ooo_rob1_done`, set `core0_ooo_prf0_busy` to if `core0_ooo_rob1_old` equals 0, then false, otherwise `core0_ooo_prf0_busy`; set `core0_ooo_prf1_busy` to if `core0_ooo_rob1_old` equals 1, then false, otherwise `core0_ooo_prf1_busy`; set `core0_ooo_prf2_busy` to if `core0_ooo_rob1_old` equals 2, then false, otherwise `core0_ooo_prf2_busy`; set `core0_ooo_prf3_busy` to if `core0_ooo_rob1_old` equals 3, then false, otherwise `core0_ooo_prf3_busy`; set `core0_ooo_prf4_busy` to if `core0_ooo_rob1_old` equals 4, then false, otherwise `core0_ooo_prf4_busy`; set `core0_ooo_prf5_busy` to if `core0_ooo_rob1_old` equals 5, then false, otherwise `core0_ooo_prf5_busy`; set `core0_ooo_rob1_valid` to false; set `core0_ooo_rob1_done` to false; set `core0_ooo_head` to false.
- **core0_ooo_alu_load_inputs** — when true, set `core0_ooo_alu_op_reg` to `alu_op`; set `core0_ooo_alu_a_reg` to `a`; set `core0_ooo_alu_b_reg` to `b`.
- **core0_ooo_alu_execute** — when true, set `core0_ooo_alu_result_reg` to if `core0_ooo_alu_op_reg` equals 0, then `core0_ooo_alu_a_reg` + `core0_ooo_alu_b_reg`, otherwise if `core0_ooo_alu_op_reg` equals 1, then `core0_ooo_alu_a_reg` − `core0_ooo_alu_b_reg`, otherwise if `core0_ooo_alu_op_reg` equals 2, then `core0_ooo_alu_a_reg` and `core0_ooo_alu_b_reg`, otherwise if `core0_ooo_alu_op_reg` equals 3, then `core0_ooo_alu_a_reg` or `core0_ooo_alu_b_reg`, otherwise if `core0_ooo_alu_op_reg` equals 4, then if `core0_ooo_alu_a_reg` equals `core0_ooo_alu_b_reg`, then 0, otherwise if `core0_ooo_alu_a_reg` < `core0_ooo_alu_b_reg`, then 1, otherwise 2, otherwise if `core0_ooo_alu_op_reg` equals 5, then `core0_ooo_alu_a_reg` xor `core0_ooo_alu_b_reg`, otherwise if `core0_ooo_alu_op_reg` equals 6, then `core0_ooo_alu_a_reg` shifted left by `core0_ooo_alu_b_reg`[2:0], otherwise if `core0_ooo_alu_op_reg` equals 7, then `core0_ooo_alu_a_reg` shifted right by `core0_ooo_alu_b_reg`[2:0], otherwise 0; set `core0_ooo_alu_overflow_reg` to if `core0_ooo_alu_op_reg` equals 0, then `core0_ooo_alu_a_reg`[7:7] equals `core0_ooo_alu_b_reg`[7:7] and `core0_ooo_alu_a_reg`[7:7] does not equal `core0_ooo_alu_a_reg` + `core0_ooo_alu_b_reg`[7:7], otherwise if `core0_ooo_alu_op_reg` equals 1, then `core0_ooo_alu_a_reg`[7:7] does not equal `core0_ooo_alu_b_reg`[7:7] and `core0_ooo_alu_a_reg`[7:7] equals `core0_ooo_alu_a_reg` − `core0_ooo_alu_b_reg`[7:7], otherwise false; set `core0_ooo_alu_zero_reg` to if `core0_ooo_alu_op_reg` equals 0, then `core0_ooo_alu_a_reg` + `core0_ooo_alu_b_reg`, otherwise if `core0_ooo_alu_op_reg` equals 1, then `core0_ooo_alu_a_reg` − `core0_ooo_alu_b_reg`, otherwise if `core0_ooo_alu_op_reg` equals 2, then `core0_ooo_alu_a_reg` and `core0_ooo_alu_b_reg`, otherwise if `core0_ooo_alu_op_reg` equals 3, then `core0_ooo_alu_a_reg` or `core0_ooo_alu_b_reg`, otherwise if `core0_ooo_alu_op_reg` equals 4, then if `core0_ooo_alu_a_reg` equals `core0_ooo_alu_b_reg`, then 0, otherwise if `core0_ooo_alu_a_reg` < `core0_ooo_alu_b_reg`, then 1, otherwise 2, otherwise if `core0_ooo_alu_op_reg` equals 5, then `core0_ooo_alu_a_reg` xor `core0_ooo_alu_b_reg`, otherwise if `core0_ooo_alu_op_reg` equals 6, then `core0_ooo_alu_a_reg` shifted left by `core0_ooo_alu_b_reg`[2:0], otherwise if `core0_ooo_alu_op_reg` equals 7, then `core0_ooo_alu_a_reg` shifted right by `core0_ooo_alu_b_reg`[2:0], otherwise 0 equals 0; set `core0_ooo_alu_valid` to true.
- **core0_ooo_lsu_store** — when 0 equals 0 and store, mem_write(core0_ooo_lsu_mem, addr, a); set `core0_ooo_lsu_resp_valid` to true.
- **core0_ooo_lsu_load** — when 0 equals 0 and not (store), set `core0_ooo_lsu_resp_data` to mem_read(core0_ooo_lsu_mem, addr); set `core0_ooo_lsu_resp_valid` to true.
- **core0_ooo_lsu_l1d_write_hit0** — when 0 equals 0 and store and core0_ooo_lsu_l1d_has_line(`core0_ooo_lsu_l1d_s0`, `core0_ooo_lsu_l1d_a0`, addr), set `core0_ooo_lsu_l1d_s0` to 3; set `core0_ooo_lsu_l1d_data0` to core0_ooo_lsu_l1d_req_data; set `core0_ooo_lsu_l1d_lru` to true.
- **core0_ooo_lsu_l1d_write_hit1** — when 0 equals 0 and store and not (core0_ooo_lsu_l1d_has_line(`core0_ooo_lsu_l1d_s0`, `core0_ooo_lsu_l1d_a0`, addr)) and core0_ooo_lsu_l1d_has_line(`core0_ooo_lsu_l1d_s1`, `core0_ooo_lsu_l1d_a1`, addr), set `core0_ooo_lsu_l1d_s1` to 3; set `core0_ooo_lsu_l1d_data1` to core0_ooo_lsu_l1d_req_data; set `core0_ooo_lsu_l1d_lru` to false.
- **core0_ooo_lsu_l1d_write_miss0** — when 0 equals 0 and store and not (core0_ooo_lsu_l1d_has_line(`core0_ooo_lsu_l1d_s0`, `core0_ooo_lsu_l1d_a0`, addr)) and not (core0_ooo_lsu_l1d_has_line(`core0_ooo_lsu_l1d_s1`, `core0_ooo_lsu_l1d_a1`, addr)) and not (`core0_ooo_lsu_l1d_lru`), set `core0_ooo_lsu_l1d_s0` to 3; set `core0_ooo_lsu_l1d_a0` to addr; set `core0_ooo_lsu_l1d_data0` to core0_ooo_lsu_l1d_req_data; set `core0_ooo_lsu_l1d_lru` to true.
- **core0_ooo_lsu_l1d_write_miss1** — when 0 equals 0 and store and not (core0_ooo_lsu_l1d_has_line(`core0_ooo_lsu_l1d_s0`, `core0_ooo_lsu_l1d_a0`, addr)) and not (core0_ooo_lsu_l1d_has_line(`core0_ooo_lsu_l1d_s1`, `core0_ooo_lsu_l1d_a1`, addr)) and `core0_ooo_lsu_l1d_lru`, set `core0_ooo_lsu_l1d_s1` to 3; set `core0_ooo_lsu_l1d_a1` to addr; set `core0_ooo_lsu_l1d_data1` to core0_ooo_lsu_l1d_req_data; set `core0_ooo_lsu_l1d_lru` to false.
- **core0_ooo_lsu_l1d_read_hit0** — when 0 equals 0 and not (store) and core0_ooo_lsu_l1d_has_line(`core0_ooo_lsu_l1d_s0`, `core0_ooo_lsu_l1d_a0`, addr), set `core0_ooo_lsu_l1d_rdata` to `core0_ooo_lsu_l1d_data0`; set `core0_ooo_lsu_l1d_lru` to true.
- **core0_ooo_lsu_l1d_read_hit1** — when 0 equals 0 and not (store) and not (core0_ooo_lsu_l1d_has_line(`core0_ooo_lsu_l1d_s0`, `core0_ooo_lsu_l1d_a0`, addr)) and core0_ooo_lsu_l1d_has_line(`core0_ooo_lsu_l1d_s1`, `core0_ooo_lsu_l1d_a1`, addr), set `core0_ooo_lsu_l1d_rdata` to `core0_ooo_lsu_l1d_data1`; set `core0_ooo_lsu_l1d_lru` to false.
- **core0_ooo_lsu_l1d_read_miss0** — when 0 equals 0 and not (store) and not (core0_ooo_lsu_l1d_has_line(`core0_ooo_lsu_l1d_s0`, `core0_ooo_lsu_l1d_a0`, addr)) and not (core0_ooo_lsu_l1d_has_line(`core0_ooo_lsu_l1d_s1`, `core0_ooo_lsu_l1d_a1`, addr)) and not (`core0_ooo_lsu_l1d_lru`), set `core0_ooo_lsu_l1d_s0` to 1; set `core0_ooo_lsu_l1d_a0` to addr.
- **core0_ooo_lsu_l1d_read_miss1** — when 0 equals 0 and not (store) and not (core0_ooo_lsu_l1d_has_line(`core0_ooo_lsu_l1d_s0`, `core0_ooo_lsu_l1d_a0`, addr)) and not (core0_ooo_lsu_l1d_has_line(`core0_ooo_lsu_l1d_s1`, `core0_ooo_lsu_l1d_a1`, addr)) and `core0_ooo_lsu_l1d_lru`, set `core0_ooo_lsu_l1d_s1` to 1; set `core0_ooo_lsu_l1d_a1` to addr.
- **core0_ooo_lsu_l1d_snoop_inv0** — when 0 does not equal 0 and store and core0_ooo_lsu_l1d_has_line(`core0_ooo_lsu_l1d_s0`, `core0_ooo_lsu_l1d_a0`, addr), set `core0_ooo_lsu_l1d_s0` to 0.
- **core0_ooo_lsu_l1d_snoop_inv1** — when 0 does not equal 0 and store and core0_ooo_lsu_l1d_has_line(`core0_ooo_lsu_l1d_s1`, `core0_ooo_lsu_l1d_a1`, addr), set `core0_ooo_lsu_l1d_s1` to 0.
- **core0_ooo_lsu_l1d_snoop_dg0** — when 0 does not equal 0 and not (store) and core0_ooo_lsu_l1d_has_line(`core0_ooo_lsu_l1d_s0`, `core0_ooo_lsu_l1d_a0`, addr), set `core0_ooo_lsu_l1d_s0` to 1.
- **core0_ooo_lsu_l1d_snoop_dg1** — when 0 does not equal 0 and not (store) and core0_ooo_lsu_l1d_has_line(`core0_ooo_lsu_l1d_s1`, `core0_ooo_lsu_l1d_a1`, addr), set `core0_ooo_lsu_l1d_s1` to 1.
- **core0_cache_l1i_write_hit0** — when 0 equals 0 and core0_cache_const_false and core0_cache_l1i_has_line(`core0_cache_l1i_s0`, `core0_cache_l1i_a0`, core0_i_pa_signal), set `core0_cache_l1i_s0` to 3; set `core0_cache_l1i_data0` to 0; set `core0_cache_l1i_lru` to true.
- **core0_cache_l1i_write_hit1** — when 0 equals 0 and core0_cache_const_false and not (core0_cache_l1i_has_line(`core0_cache_l1i_s0`, `core0_cache_l1i_a0`, core0_i_pa_signal)) and core0_cache_l1i_has_line(`core0_cache_l1i_s1`, `core0_cache_l1i_a1`, core0_i_pa_signal), set `core0_cache_l1i_s1` to 3; set `core0_cache_l1i_data1` to 0; set `core0_cache_l1i_lru` to false.
- **core0_cache_l1i_write_miss0** — when 0 equals 0 and core0_cache_const_false and not (core0_cache_l1i_has_line(`core0_cache_l1i_s0`, `core0_cache_l1i_a0`, core0_i_pa_signal)) and not (core0_cache_l1i_has_line(`core0_cache_l1i_s1`, `core0_cache_l1i_a1`, core0_i_pa_signal)) and not (`core0_cache_l1i_lru`), set `core0_cache_l1i_s0` to 3; set `core0_cache_l1i_a0` to core0_i_pa_signal; set `core0_cache_l1i_data0` to 0; set `core0_cache_l1i_lru` to true.
- **core0_cache_l1i_write_miss1** — when 0 equals 0 and core0_cache_const_false and not (core0_cache_l1i_has_line(`core0_cache_l1i_s0`, `core0_cache_l1i_a0`, core0_i_pa_signal)) and not (core0_cache_l1i_has_line(`core0_cache_l1i_s1`, `core0_cache_l1i_a1`, core0_i_pa_signal)) and `core0_cache_l1i_lru`, set `core0_cache_l1i_s1` to 3; set `core0_cache_l1i_a1` to core0_i_pa_signal; set `core0_cache_l1i_data1` to 0; set `core0_cache_l1i_lru` to false.
- **core0_cache_l1i_read_hit0** — when 0 equals 0 and not (core0_cache_const_false) and core0_cache_l1i_has_line(`core0_cache_l1i_s0`, `core0_cache_l1i_a0`, core0_i_pa_signal), set `core0_cache_l1i_rdata` to `core0_cache_l1i_data0`; set `core0_cache_l1i_lru` to true.
- **core0_cache_l1i_read_hit1** — when 0 equals 0 and not (core0_cache_const_false) and not (core0_cache_l1i_has_line(`core0_cache_l1i_s0`, `core0_cache_l1i_a0`, core0_i_pa_signal)) and core0_cache_l1i_has_line(`core0_cache_l1i_s1`, `core0_cache_l1i_a1`, core0_i_pa_signal), set `core0_cache_l1i_rdata` to `core0_cache_l1i_data1`; set `core0_cache_l1i_lru` to false.
- **core0_cache_l1i_read_miss0** — when 0 equals 0 and not (core0_cache_const_false) and not (core0_cache_l1i_has_line(`core0_cache_l1i_s0`, `core0_cache_l1i_a0`, core0_i_pa_signal)) and not (core0_cache_l1i_has_line(`core0_cache_l1i_s1`, `core0_cache_l1i_a1`, core0_i_pa_signal)) and not (`core0_cache_l1i_lru`), set `core0_cache_l1i_s0` to 1; set `core0_cache_l1i_a0` to core0_i_pa_signal.
- **core0_cache_l1i_read_miss1** — when 0 equals 0 and not (core0_cache_const_false) and not (core0_cache_l1i_has_line(`core0_cache_l1i_s0`, `core0_cache_l1i_a0`, core0_i_pa_signal)) and not (core0_cache_l1i_has_line(`core0_cache_l1i_s1`, `core0_cache_l1i_a1`, core0_i_pa_signal)) and `core0_cache_l1i_lru`, set `core0_cache_l1i_s1` to 1; set `core0_cache_l1i_a1` to core0_i_pa_signal.
- **core0_cache_l1i_snoop_inv0** — when 0 does not equal 0 and core0_cache_const_false and core0_cache_l1i_has_line(`core0_cache_l1i_s0`, `core0_cache_l1i_a0`, core0_i_pa_signal), set `core0_cache_l1i_s0` to 0.
- **core0_cache_l1i_snoop_inv1** — when 0 does not equal 0 and core0_cache_const_false and core0_cache_l1i_has_line(`core0_cache_l1i_s1`, `core0_cache_l1i_a1`, core0_i_pa_signal), set `core0_cache_l1i_s1` to 0.
- **core0_cache_l1i_snoop_dg0** — when 0 does not equal 0 and not (core0_cache_const_false) and core0_cache_l1i_has_line(`core0_cache_l1i_s0`, `core0_cache_l1i_a0`, core0_i_pa_signal), set `core0_cache_l1i_s0` to 1.
- **core0_cache_l1i_snoop_dg1** — when 0 does not equal 0 and not (core0_cache_const_false) and core0_cache_l1i_has_line(`core0_cache_l1i_s1`, `core0_cache_l1i_a1`, core0_i_pa_signal), set `core0_cache_l1i_s1` to 1.
- **core0_cache_l1d_write_hit0** — when req_core equals 0 and core0_l1d_write_signal and core0_cache_l1d_has_line(`core0_cache_l1d_s0`, `core0_cache_l1d_a0`, core0_l1d_addr_signal), set `core0_cache_l1d_s0` to 3; set `core0_cache_l1d_data0` to req_data; set `core0_cache_l1d_lru` to true.
- **core0_cache_l1d_write_hit1** — when req_core equals 0 and core0_l1d_write_signal and not (core0_cache_l1d_has_line(`core0_cache_l1d_s0`, `core0_cache_l1d_a0`, core0_l1d_addr_signal)) and core0_cache_l1d_has_line(`core0_cache_l1d_s1`, `core0_cache_l1d_a1`, core0_l1d_addr_signal), set `core0_cache_l1d_s1` to 3; set `core0_cache_l1d_data1` to req_data; set `core0_cache_l1d_lru` to false.
- **core0_cache_l1d_write_miss0** — when req_core equals 0 and core0_l1d_write_signal and not (core0_cache_l1d_has_line(`core0_cache_l1d_s0`, `core0_cache_l1d_a0`, core0_l1d_addr_signal)) and not (core0_cache_l1d_has_line(`core0_cache_l1d_s1`, `core0_cache_l1d_a1`, core0_l1d_addr_signal)) and not (`core0_cache_l1d_lru`), set `core0_cache_l1d_s0` to 3; set `core0_cache_l1d_a0` to core0_l1d_addr_signal; set `core0_cache_l1d_data0` to req_data; set `core0_cache_l1d_lru` to true.
- **core0_cache_l1d_write_miss1** — when req_core equals 0 and core0_l1d_write_signal and not (core0_cache_l1d_has_line(`core0_cache_l1d_s0`, `core0_cache_l1d_a0`, core0_l1d_addr_signal)) and not (core0_cache_l1d_has_line(`core0_cache_l1d_s1`, `core0_cache_l1d_a1`, core0_l1d_addr_signal)) and `core0_cache_l1d_lru`, set `core0_cache_l1d_s1` to 3; set `core0_cache_l1d_a1` to core0_l1d_addr_signal; set `core0_cache_l1d_data1` to req_data; set `core0_cache_l1d_lru` to false.
- **core0_cache_l1d_read_hit0** — when req_core equals 0 and not (core0_l1d_write_signal) and core0_cache_l1d_has_line(`core0_cache_l1d_s0`, `core0_cache_l1d_a0`, core0_l1d_addr_signal), set `core0_cache_l1d_rdata_signal` to `core0_cache_l1d_data0`; set `core0_cache_l1d_lru` to true.
- **core0_cache_l1d_read_hit1** — when req_core equals 0 and not (core0_l1d_write_signal) and not (core0_cache_l1d_has_line(`core0_cache_l1d_s0`, `core0_cache_l1d_a0`, core0_l1d_addr_signal)) and core0_cache_l1d_has_line(`core0_cache_l1d_s1`, `core0_cache_l1d_a1`, core0_l1d_addr_signal), set `core0_cache_l1d_rdata_signal` to `core0_cache_l1d_data1`; set `core0_cache_l1d_lru` to false.
- **core0_cache_l1d_read_miss0** — when req_core equals 0 and not (core0_l1d_write_signal) and not (core0_cache_l1d_has_line(`core0_cache_l1d_s0`, `core0_cache_l1d_a0`, core0_l1d_addr_signal)) and not (core0_cache_l1d_has_line(`core0_cache_l1d_s1`, `core0_cache_l1d_a1`, core0_l1d_addr_signal)) and not (`core0_cache_l1d_lru`), set `core0_cache_l1d_s0` to 1; set `core0_cache_l1d_a0` to core0_l1d_addr_signal.
- **core0_cache_l1d_read_miss1** — when req_core equals 0 and not (core0_l1d_write_signal) and not (core0_cache_l1d_has_line(`core0_cache_l1d_s0`, `core0_cache_l1d_a0`, core0_l1d_addr_signal)) and not (core0_cache_l1d_has_line(`core0_cache_l1d_s1`, `core0_cache_l1d_a1`, core0_l1d_addr_signal)) and `core0_cache_l1d_lru`, set `core0_cache_l1d_s1` to 1; set `core0_cache_l1d_a1` to core0_l1d_addr_signal.
- **core0_cache_l1d_snoop_inv0** — when req_core does not equal 0 and core0_l1d_write_signal and core0_cache_l1d_has_line(`core0_cache_l1d_s0`, `core0_cache_l1d_a0`, core0_l1d_addr_signal), set `core0_cache_l1d_s0` to 0.
- **core0_cache_l1d_snoop_inv1** — when req_core does not equal 0 and core0_l1d_write_signal and core0_cache_l1d_has_line(`core0_cache_l1d_s1`, `core0_cache_l1d_a1`, core0_l1d_addr_signal), set `core0_cache_l1d_s1` to 0.
- **core0_cache_l1d_snoop_dg0** — when req_core does not equal 0 and not (core0_l1d_write_signal) and core0_cache_l1d_has_line(`core0_cache_l1d_s0`, `core0_cache_l1d_a0`, core0_l1d_addr_signal), set `core0_cache_l1d_s0` to 1.
- **core0_cache_l1d_snoop_dg1** — when req_core does not equal 0 and not (core0_l1d_write_signal) and core0_cache_l1d_has_line(`core0_cache_l1d_s1`, `core0_cache_l1d_a1`, core0_l1d_addr_signal), set `core0_cache_l1d_s1` to 1.
- **core0_cache_l2_write_hit0** — when req_core equals 0 and core0_l1d_write_signal and core0_cache_l2_has_line(`core0_cache_l2_s0`, `core0_cache_l2_a0`, core0_l1d_addr_signal), set `core0_cache_l2_s0` to 3; set `core0_cache_l2_lru` to true; mem_write(core0_cache_l2_mem, core0_l1d_addr_signal, req_data).
- **core0_cache_l2_write_hit1** — when req_core equals 0 and core0_l1d_write_signal and not (core0_cache_l2_has_line(`core0_cache_l2_s0`, `core0_cache_l2_a0`, core0_l1d_addr_signal)) and core0_cache_l2_has_line(`core0_cache_l2_s1`, `core0_cache_l2_a1`, core0_l1d_addr_signal), set `core0_cache_l2_s1` to 3; set `core0_cache_l2_lru` to false; mem_write(core0_cache_l2_mem, core0_l1d_addr_signal, req_data).
- **core0_cache_l2_write_miss0** — when req_core equals 0 and core0_l1d_write_signal and not (core0_cache_l2_has_line(`core0_cache_l2_s0`, `core0_cache_l2_a0`, core0_l1d_addr_signal)) and not (core0_cache_l2_has_line(`core0_cache_l2_s1`, `core0_cache_l2_a1`, core0_l1d_addr_signal)) and not (`core0_cache_l2_lru`), set `core0_cache_l2_s0` to 3; set `core0_cache_l2_a0` to core0_l1d_addr_signal; set `core0_cache_l2_lru` to true; mem_write(core0_cache_l2_mem, core0_l1d_addr_signal, req_data); set `core0_miss_valid_signal` to true; set `core0_miss_addr_signal` to core0_l1d_addr_signal.
- **core0_cache_l2_write_miss1** — when req_core equals 0 and core0_l1d_write_signal and not (core0_cache_l2_has_line(`core0_cache_l2_s0`, `core0_cache_l2_a0`, core0_l1d_addr_signal)) and not (core0_cache_l2_has_line(`core0_cache_l2_s1`, `core0_cache_l2_a1`, core0_l1d_addr_signal)) and `core0_cache_l2_lru`, set `core0_cache_l2_s1` to 3; set `core0_cache_l2_a1` to core0_l1d_addr_signal; set `core0_cache_l2_lru` to false; mem_write(core0_cache_l2_mem, core0_l1d_addr_signal, req_data); set `core0_miss_valid_signal` to true; set `core0_miss_addr_signal` to core0_l1d_addr_signal.
- **core0_cache_l2_read_miss0** — when req_core equals 0 and not (core0_l1d_write_signal) and not (core0_cache_l2_has_line(`core0_cache_l2_s0`, `core0_cache_l2_a0`, core0_l1d_addr_signal)) and not (core0_cache_l2_has_line(`core0_cache_l2_s1`, `core0_cache_l2_a1`, core0_l1d_addr_signal)) and not (`core0_cache_l2_lru`), set `core0_cache_l2_s0` to 1; set `core0_cache_l2_a0` to core0_l1d_addr_signal; set `core0_miss_valid_signal` to true; set `core0_miss_addr_signal` to core0_l1d_addr_signal.
- **core0_cache_l2_read_miss1** — when req_core equals 0 and not (core0_l1d_write_signal) and not (core0_cache_l2_has_line(`core0_cache_l2_s0`, `core0_cache_l2_a0`, core0_l1d_addr_signal)) and not (core0_cache_l2_has_line(`core0_cache_l2_s1`, `core0_cache_l2_a1`, core0_l1d_addr_signal)) and `core0_cache_l2_lru`, set `core0_cache_l2_s1` to 1; set `core0_cache_l2_a1` to core0_l1d_addr_signal; set `core0_miss_valid_signal` to true; set `core0_miss_addr_signal` to core0_l1d_addr_signal.
- **core0_cache_l2_snoop_inv0** — when req_core does not equal 0 and core0_l1d_write_signal and core0_cache_l2_has_line(`core0_cache_l2_s0`, `core0_cache_l2_a0`, core0_l1d_addr_signal), set `core0_cache_l2_s0` to 0.
- **core0_cache_l2_snoop_inv1** — when req_core does not equal 0 and core0_l1d_write_signal and core0_cache_l2_has_line(`core0_cache_l2_s1`, `core0_cache_l2_a1`, core0_l1d_addr_signal), set `core0_cache_l2_s1` to 0.
- **core0_cache_l2_snoop_dg0** — when req_core does not equal 0 and not (core0_l1d_write_signal) and core0_cache_l2_has_line(`core0_cache_l2_s0`, `core0_cache_l2_a0`, core0_l1d_addr_signal), set `core0_cache_l2_s0` to 1.
- **core0_cache_l2_snoop_dg1** — when req_core does not equal 0 and not (core0_l1d_write_signal) and core0_cache_l2_has_line(`core0_cache_l2_s1`, `core0_cache_l2_a1`, core0_l1d_addr_signal), set `core0_cache_l2_s1` to 1.
- **core0_cache_l2_mshr_mshr0_alloc** — when core0_miss_valid_signal and not (`core0_cache_l2_mshr_mshr0_valid`), set `core0_cache_l2_mshr_mshr0_valid` to true; set `core0_cache_l2_mshr_mshr0_mid` to 0; set `core0_cache_l2_mshr_mshr0_maddr` to core0_l1d_addr_signal; set `core0_cache_l2_mshr_mshr0_mdata` to req_data.
- **core0_cache_l2_mshr_mshr0_rel** — when release0, set `core0_cache_l2_mshr_mshr0_valid` to false.
- **core0_cache_l2_mshr_mshr1_alloc** — when core0_miss_valid_signal and not (`core0_cache_l2_mshr_mshr1_valid`), set `core0_cache_l2_mshr_mshr1_valid` to true; set `core0_cache_l2_mshr_mshr1_mid` to 0; set `core0_cache_l2_mshr_mshr1_maddr` to core0_l1d_addr_signal; set `core0_cache_l2_mshr_mshr1_mdata` to req_data.
- **core0_cache_l2_mshr_mshr1_rel** — when release1, set `core0_cache_l2_mshr_mshr1_valid` to false.
- **core0_cache_l2_mshr_arb_arbitrate** — when true, set `core0_cache_l2_mshr_arb_grant` to if core0_miss_valid_signal, then 0, otherwise if core0_miss_valid_signal, then 1, otherwise if core0_cache_l2_mshr_arb_req2_valid, then 2, otherwise if core0_cache_l2_mshr_arb_req3_valid, then 3, otherwise if core0_cache_l2_mshr_arb_req4_valid, then 4, otherwise if core0_cache_l2_mshr_arb_req5_valid, then 5, otherwise 0; set `core0_cache_l2_mshr_arb_grant_valid` to core0_miss_valid_signal or core0_miss_valid_signal or core0_cache_l2_mshr_arb_req2_valid or core0_cache_l2_mshr_arb_req3_valid or core0_cache_l2_mshr_arb_req4_valid or core0_cache_l2_mshr_arb_req5_valid.
- **core0_axi_mem_do_read** — when core0_miss_valid_signal, set `core0_axi_mem_rdata` to mem_read(core0_axi_mem_mem, core0_miss_addr_signal); set `core0_axi_mem_rvalid` to true.
- **core0_axi_mem_do_write** — when awvalid and wvalid, mem_write(core0_axi_mem_mem, awaddr, wdata); set `core0_axi_mem_bvalid` to true.
- **core1_slice_d_vpn** — when true, set `core1_d_vpn_signal` to addr[1:0].
- **core1_mux_l1d_addr** — when true, set `core1_l1d_addr_signal` to if `core1_ptw_active_signal`, then `core1_ptw_mem_addr_signal`, otherwise core1_pa_signal.
- **core1_mux_l1d_write** — when true, set `core1_l1d_write_signal` to not (`core1_ptw_active_signal`) and req_write.
- **core1_mux_l1d_phys** — when true, set `core1_l1d_phys_signal` to `core1_ptw_active_signal` or d_is_physical.
- **core1_retire** — when req_core equals 1, set `core1_pc` to `core1_pc` + 1.
- **core1_mmu_combine_miss** — when true, set `core1_tlb_miss_signal` to `core1_i_miss_signal` or `core1_d_miss_signal`.
- **core1_mmu_slice_ppn** — when true, set `core1_mmu_ppn_fill` to `core1_mmu_ptw_ppn`.
- **core1_mmu_ptw_is_active** — when true, set `core1_ptw_active_signal` to `core1_mmu_ptw_walk_state` does not equal 0.
- **core1_mmu_itlb_hit0** — when core1_mmu_itlb_way_hit(`core1_mmu_itlb_way0_valid`, `core1_mmu_itlb_way0_vpn`, core1_pc_signal), set `core1_i_pa_signal` to `core1_mmu_itlb_way0_ppn`; set `core1_mmu_itlb_lru` to true; set `core1_i_miss_signal` to false.
- **core1_mmu_itlb_hit1** — when core1_mmu_itlb_way_hit(`core1_mmu_itlb_way1_valid`, `core1_mmu_itlb_way1_vpn`, core1_pc_signal), set `core1_i_pa_signal` to `core1_mmu_itlb_way1_ppn`; set `core1_mmu_itlb_lru` to false; set `core1_i_miss_signal` to false.
- **core1_mmu_itlb_fill0** — when not (core1_mmu_itlb_way_hit(`core1_mmu_itlb_way0_valid`, `core1_mmu_itlb_way0_vpn`, core1_pc_signal)) and not (core1_mmu_itlb_way_hit(`core1_mmu_itlb_way1_valid`, `core1_mmu_itlb_way1_vpn`, core1_pc_signal)) and not (`core1_mmu_itlb_lru`), set `core1_mmu_itlb_way0_vpn` to core1_pc_signal; set `core1_mmu_itlb_way0_ppn` to core1_mmu_ppn_fill; set `core1_mmu_itlb_way0_valid` to true; set `core1_mmu_itlb_lru` to true; set `core1_i_miss_signal` to true.
- **core1_mmu_itlb_fill1** — when not (core1_mmu_itlb_way_hit(`core1_mmu_itlb_way0_valid`, `core1_mmu_itlb_way0_vpn`, core1_pc_signal)) and not (core1_mmu_itlb_way_hit(`core1_mmu_itlb_way1_valid`, `core1_mmu_itlb_way1_vpn`, core1_pc_signal)) and `core1_mmu_itlb_lru`, set `core1_mmu_itlb_way1_vpn` to core1_pc_signal; set `core1_mmu_itlb_way1_ppn` to core1_mmu_ppn_fill; set `core1_mmu_itlb_way1_valid` to true; set `core1_mmu_itlb_lru` to false; set `core1_i_miss_signal` to true.
- **core1_mmu_dtlb_hit0** — when core1_mmu_dtlb_way_hit(`core1_mmu_dtlb_way0_valid`, `core1_mmu_dtlb_way0_vpn`, addr), set `core1_pa_signal` to `core1_mmu_dtlb_way0_ppn`; set `core1_mmu_dtlb_lru` to true; set `core1_d_miss_signal` to false.
- **core1_mmu_dtlb_hit1** — when core1_mmu_dtlb_way_hit(`core1_mmu_dtlb_way1_valid`, `core1_mmu_dtlb_way1_vpn`, addr), set `core1_pa_signal` to `core1_mmu_dtlb_way1_ppn`; set `core1_mmu_dtlb_lru` to false; set `core1_d_miss_signal` to false.
- **core1_mmu_dtlb_fill0** — when not (core1_mmu_dtlb_way_hit(`core1_mmu_dtlb_way0_valid`, `core1_mmu_dtlb_way0_vpn`, addr)) and not (core1_mmu_dtlb_way_hit(`core1_mmu_dtlb_way1_valid`, `core1_mmu_dtlb_way1_vpn`, addr)) and not (`core1_mmu_dtlb_lru`), set `core1_mmu_dtlb_way0_vpn` to addr; set `core1_mmu_dtlb_way0_ppn` to core1_mmu_ppn_fill; set `core1_mmu_dtlb_way0_valid` to true; set `core1_mmu_dtlb_lru` to true; set `core1_d_miss_signal` to true.
- **core1_mmu_dtlb_fill1** — when not (core1_mmu_dtlb_way_hit(`core1_mmu_dtlb_way0_valid`, `core1_mmu_dtlb_way0_vpn`, addr)) and not (core1_mmu_dtlb_way_hit(`core1_mmu_dtlb_way1_valid`, `core1_mmu_dtlb_way1_vpn`, addr)) and `core1_mmu_dtlb_lru`, set `core1_mmu_dtlb_way1_vpn` to addr; set `core1_mmu_dtlb_way1_ppn` to core1_mmu_ppn_fill; set `core1_mmu_dtlb_way1_valid` to true; set `core1_mmu_dtlb_lru` to false; set `core1_d_miss_signal` to true.
- **core1_mmu_ptw_walk_start** — when `core1_mmu_ptw_walk_state` equals 0 and core1_tlb_miss_signal, set `core1_ptw_mem_addr_signal` to concat(`core1_mmu_ptw_root_ppn`[1:0], core1_mmu_ptw_vpn1(va), 2); set `core1_mmu_ptw_walk_state` to 1.
- **core1_mmu_ptw_walk_l0** — when `core1_mmu_ptw_walk_state` equals 1, set `core1_mmu_ptw_pte1` to core1_ptw_mem_data_signal; set `core1_ptw_mem_addr_signal` to concat(core1_mmu_ptw_pte_ppn(core1_ptw_mem_data_signal)[1:0], core1_mmu_ptw_vpn0(va), 2); set `core1_mmu_ptw_walk_state` to 2.
- **core1_mmu_ptw_walk_finish** — when `core1_mmu_ptw_walk_state` equals 2, set `core1_mmu_ptw_pte0` to core1_ptw_mem_data_signal; set `core1_mmu_ptw_ppn` to core1_mmu_ptw_pte_ppn(core1_ptw_mem_data_signal); set `core1_mmu_ptw_result_pa` to concat(core1_mmu_ptw_pte_ppn(core1_ptw_mem_data_signal), core1_mmu_ptw_offset(va), 4); set `core1_mmu_ptw_walk_state` to 3.
- **core1_mmu_ptw_walk_reset** — when `core1_mmu_ptw_walk_state` equals 3, set `core1_mmu_ptw_walk_state` to 0.
- **core1_fetch_advance** — when true, set `core1_pc_signal` to if stall, then `core1_pc_signal`, otherwise if `core1_fetch_bpu_predict`, then branch_target, otherwise `core1_pc_signal` + 1.
- **core1_fetch_bpu_update** — when true, set `core1_fetch_bpu_ctr` to if taken, then if `core1_fetch_bpu_ctr` < 3, then `core1_fetch_bpu_ctr` + 1, otherwise 3, otherwise if `core1_fetch_bpu_ctr` > 0, then `core1_fetch_bpu_ctr` − 1, otherwise 0; set `core1_fetch_bpu_predict` to `core1_fetch_bpu_ctr` ≥ 2.
- **core1_ooo_issue0** — when issue_valid and not (`core1_ooo_rob0_valid`), set `core1_ooo_rat0` to if rd equals 0, then 4, otherwise `core1_ooo_rat0`; set `core1_ooo_rat1` to if rd equals 1, then 4, otherwise `core1_ooo_rat1`; set `core1_ooo_rat2` to if rd equals 2, then 4, otherwise `core1_ooo_rat2`; set `core1_ooo_rat3` to if rd equals 3, then 4, otherwise `core1_ooo_rat3`; set `core1_ooo_prf4_busy` to true; set `core1_ooo_rob0_valid` to true; set `core1_ooo_rob0_rd` to rd; set `core1_ooo_rob0_old` to if rd equals 0, then `core1_ooo_rat0`, otherwise if rd equals 1, then `core1_ooo_rat1`, otherwise if rd equals 2, then `core1_ooo_rat2`, otherwise `core1_ooo_rat3`; set `core1_ooo_rob0_done` to false.
- **core1_ooo_issue1** — when issue_valid and `core1_ooo_rob0_valid` and not (`core1_ooo_rob1_valid`), set `core1_ooo_rat0` to if rd equals 0, then 5, otherwise `core1_ooo_rat0`; set `core1_ooo_rat1` to if rd equals 1, then 5, otherwise `core1_ooo_rat1`; set `core1_ooo_rat2` to if rd equals 2, then 5, otherwise `core1_ooo_rat2`; set `core1_ooo_rat3` to if rd equals 3, then 5, otherwise `core1_ooo_rat3`; set `core1_ooo_prf5_busy` to true; set `core1_ooo_rob1_valid` to true; set `core1_ooo_rob1_rd` to rd; set `core1_ooo_rob1_old` to if rd equals 0, then `core1_ooo_rat0`, otherwise if rd equals 1, then `core1_ooo_rat1`, otherwise if rd equals 2, then `core1_ooo_rat2`, otherwise `core1_ooo_rat3`; set `core1_ooo_rob1_done` to false.
- **core1_ooo_store_buf** — when issue_valid and op and store, set `core1_ooo_sb_valid` to true; set `core1_ooo_sb_addr` to addr; set `core1_ooo_sb_data` to a.
- **core1_ooo_execute** — when true, set `core1_ooo_result` to if op, then if store, then `core1_ooo_lsu_resp_data`, otherwise if `core1_ooo_sb_valid` and `core1_ooo_sb_addr` equals addr, then `core1_ooo_sb_data`, otherwise `core1_ooo_lsu_resp_data`, otherwise `core1_ooo_alu_result_reg`.
- **core1_ooo_commit0** — when `core1_ooo_head` equals false and `core1_ooo_rob0_done`, set `core1_ooo_prf0_busy` to if `core1_ooo_rob0_old` equals 0, then false, otherwise `core1_ooo_prf0_busy`; set `core1_ooo_prf1_busy` to if `core1_ooo_rob0_old` equals 1, then false, otherwise `core1_ooo_prf1_busy`; set `core1_ooo_prf2_busy` to if `core1_ooo_rob0_old` equals 2, then false, otherwise `core1_ooo_prf2_busy`; set `core1_ooo_prf3_busy` to if `core1_ooo_rob0_old` equals 3, then false, otherwise `core1_ooo_prf3_busy`; set `core1_ooo_prf4_busy` to if `core1_ooo_rob0_old` equals 4, then false, otherwise `core1_ooo_prf4_busy`; set `core1_ooo_prf5_busy` to if `core1_ooo_rob0_old` equals 5, then false, otherwise `core1_ooo_prf5_busy`; set `core1_ooo_rob0_valid` to false; set `core1_ooo_rob0_done` to false; set `core1_ooo_head` to true.
- **core1_ooo_commit1** — when `core1_ooo_head` equals true and `core1_ooo_rob1_done`, set `core1_ooo_prf0_busy` to if `core1_ooo_rob1_old` equals 0, then false, otherwise `core1_ooo_prf0_busy`; set `core1_ooo_prf1_busy` to if `core1_ooo_rob1_old` equals 1, then false, otherwise `core1_ooo_prf1_busy`; set `core1_ooo_prf2_busy` to if `core1_ooo_rob1_old` equals 2, then false, otherwise `core1_ooo_prf2_busy`; set `core1_ooo_prf3_busy` to if `core1_ooo_rob1_old` equals 3, then false, otherwise `core1_ooo_prf3_busy`; set `core1_ooo_prf4_busy` to if `core1_ooo_rob1_old` equals 4, then false, otherwise `core1_ooo_prf4_busy`; set `core1_ooo_prf5_busy` to if `core1_ooo_rob1_old` equals 5, then false, otherwise `core1_ooo_prf5_busy`; set `core1_ooo_rob1_valid` to false; set `core1_ooo_rob1_done` to false; set `core1_ooo_head` to false.
- **core1_ooo_alu_load_inputs** — when true, set `core1_ooo_alu_op_reg` to `alu_op`; set `core1_ooo_alu_a_reg` to `a`; set `core1_ooo_alu_b_reg` to `b`.
- **core1_ooo_alu_execute** — when true, set `core1_ooo_alu_result_reg` to if `core1_ooo_alu_op_reg` equals 0, then `core1_ooo_alu_a_reg` + `core1_ooo_alu_b_reg`, otherwise if `core1_ooo_alu_op_reg` equals 1, then `core1_ooo_alu_a_reg` − `core1_ooo_alu_b_reg`, otherwise if `core1_ooo_alu_op_reg` equals 2, then `core1_ooo_alu_a_reg` and `core1_ooo_alu_b_reg`, otherwise if `core1_ooo_alu_op_reg` equals 3, then `core1_ooo_alu_a_reg` or `core1_ooo_alu_b_reg`, otherwise if `core1_ooo_alu_op_reg` equals 4, then if `core1_ooo_alu_a_reg` equals `core1_ooo_alu_b_reg`, then 0, otherwise if `core1_ooo_alu_a_reg` < `core1_ooo_alu_b_reg`, then 1, otherwise 2, otherwise if `core1_ooo_alu_op_reg` equals 5, then `core1_ooo_alu_a_reg` xor `core1_ooo_alu_b_reg`, otherwise if `core1_ooo_alu_op_reg` equals 6, then `core1_ooo_alu_a_reg` shifted left by `core1_ooo_alu_b_reg`[2:0], otherwise if `core1_ooo_alu_op_reg` equals 7, then `core1_ooo_alu_a_reg` shifted right by `core1_ooo_alu_b_reg`[2:0], otherwise 0; set `core1_ooo_alu_overflow_reg` to if `core1_ooo_alu_op_reg` equals 0, then `core1_ooo_alu_a_reg`[7:7] equals `core1_ooo_alu_b_reg`[7:7] and `core1_ooo_alu_a_reg`[7:7] does not equal `core1_ooo_alu_a_reg` + `core1_ooo_alu_b_reg`[7:7], otherwise if `core1_ooo_alu_op_reg` equals 1, then `core1_ooo_alu_a_reg`[7:7] does not equal `core1_ooo_alu_b_reg`[7:7] and `core1_ooo_alu_a_reg`[7:7] equals `core1_ooo_alu_a_reg` − `core1_ooo_alu_b_reg`[7:7], otherwise false; set `core1_ooo_alu_zero_reg` to if `core1_ooo_alu_op_reg` equals 0, then `core1_ooo_alu_a_reg` + `core1_ooo_alu_b_reg`, otherwise if `core1_ooo_alu_op_reg` equals 1, then `core1_ooo_alu_a_reg` − `core1_ooo_alu_b_reg`, otherwise if `core1_ooo_alu_op_reg` equals 2, then `core1_ooo_alu_a_reg` and `core1_ooo_alu_b_reg`, otherwise if `core1_ooo_alu_op_reg` equals 3, then `core1_ooo_alu_a_reg` or `core1_ooo_alu_b_reg`, otherwise if `core1_ooo_alu_op_reg` equals 4, then if `core1_ooo_alu_a_reg` equals `core1_ooo_alu_b_reg`, then 0, otherwise if `core1_ooo_alu_a_reg` < `core1_ooo_alu_b_reg`, then 1, otherwise 2, otherwise if `core1_ooo_alu_op_reg` equals 5, then `core1_ooo_alu_a_reg` xor `core1_ooo_alu_b_reg`, otherwise if `core1_ooo_alu_op_reg` equals 6, then `core1_ooo_alu_a_reg` shifted left by `core1_ooo_alu_b_reg`[2:0], otherwise if `core1_ooo_alu_op_reg` equals 7, then `core1_ooo_alu_a_reg` shifted right by `core1_ooo_alu_b_reg`[2:0], otherwise 0 equals 0; set `core1_ooo_alu_valid` to true.
- **core1_ooo_lsu_store** — when 0 equals 0 and store, mem_write(core1_ooo_lsu_mem, addr, a); set `core1_ooo_lsu_resp_valid` to true.
- **core1_ooo_lsu_load** — when 0 equals 0 and not (store), set `core1_ooo_lsu_resp_data` to mem_read(core1_ooo_lsu_mem, addr); set `core1_ooo_lsu_resp_valid` to true.
- **core1_ooo_lsu_l1d_write_hit0** — when 0 equals 0 and store and core1_ooo_lsu_l1d_has_line(`core1_ooo_lsu_l1d_s0`, `core1_ooo_lsu_l1d_a0`, addr), set `core1_ooo_lsu_l1d_s0` to 3; set `core1_ooo_lsu_l1d_data0` to core1_ooo_lsu_l1d_req_data; set `core1_ooo_lsu_l1d_lru` to true.
- **core1_ooo_lsu_l1d_write_hit1** — when 0 equals 0 and store and not (core1_ooo_lsu_l1d_has_line(`core1_ooo_lsu_l1d_s0`, `core1_ooo_lsu_l1d_a0`, addr)) and core1_ooo_lsu_l1d_has_line(`core1_ooo_lsu_l1d_s1`, `core1_ooo_lsu_l1d_a1`, addr), set `core1_ooo_lsu_l1d_s1` to 3; set `core1_ooo_lsu_l1d_data1` to core1_ooo_lsu_l1d_req_data; set `core1_ooo_lsu_l1d_lru` to false.
- **core1_ooo_lsu_l1d_write_miss0** — when 0 equals 0 and store and not (core1_ooo_lsu_l1d_has_line(`core1_ooo_lsu_l1d_s0`, `core1_ooo_lsu_l1d_a0`, addr)) and not (core1_ooo_lsu_l1d_has_line(`core1_ooo_lsu_l1d_s1`, `core1_ooo_lsu_l1d_a1`, addr)) and not (`core1_ooo_lsu_l1d_lru`), set `core1_ooo_lsu_l1d_s0` to 3; set `core1_ooo_lsu_l1d_a0` to addr; set `core1_ooo_lsu_l1d_data0` to core1_ooo_lsu_l1d_req_data; set `core1_ooo_lsu_l1d_lru` to true.
- **core1_ooo_lsu_l1d_write_miss1** — when 0 equals 0 and store and not (core1_ooo_lsu_l1d_has_line(`core1_ooo_lsu_l1d_s0`, `core1_ooo_lsu_l1d_a0`, addr)) and not (core1_ooo_lsu_l1d_has_line(`core1_ooo_lsu_l1d_s1`, `core1_ooo_lsu_l1d_a1`, addr)) and `core1_ooo_lsu_l1d_lru`, set `core1_ooo_lsu_l1d_s1` to 3; set `core1_ooo_lsu_l1d_a1` to addr; set `core1_ooo_lsu_l1d_data1` to core1_ooo_lsu_l1d_req_data; set `core1_ooo_lsu_l1d_lru` to false.
- **core1_ooo_lsu_l1d_read_hit0** — when 0 equals 0 and not (store) and core1_ooo_lsu_l1d_has_line(`core1_ooo_lsu_l1d_s0`, `core1_ooo_lsu_l1d_a0`, addr), set `core1_ooo_lsu_l1d_rdata` to `core1_ooo_lsu_l1d_data0`; set `core1_ooo_lsu_l1d_lru` to true.
- **core1_ooo_lsu_l1d_read_hit1** — when 0 equals 0 and not (store) and not (core1_ooo_lsu_l1d_has_line(`core1_ooo_lsu_l1d_s0`, `core1_ooo_lsu_l1d_a0`, addr)) and core1_ooo_lsu_l1d_has_line(`core1_ooo_lsu_l1d_s1`, `core1_ooo_lsu_l1d_a1`, addr), set `core1_ooo_lsu_l1d_rdata` to `core1_ooo_lsu_l1d_data1`; set `core1_ooo_lsu_l1d_lru` to false.
- **core1_ooo_lsu_l1d_read_miss0** — when 0 equals 0 and not (store) and not (core1_ooo_lsu_l1d_has_line(`core1_ooo_lsu_l1d_s0`, `core1_ooo_lsu_l1d_a0`, addr)) and not (core1_ooo_lsu_l1d_has_line(`core1_ooo_lsu_l1d_s1`, `core1_ooo_lsu_l1d_a1`, addr)) and not (`core1_ooo_lsu_l1d_lru`), set `core1_ooo_lsu_l1d_s0` to 1; set `core1_ooo_lsu_l1d_a0` to addr.
- **core1_ooo_lsu_l1d_read_miss1** — when 0 equals 0 and not (store) and not (core1_ooo_lsu_l1d_has_line(`core1_ooo_lsu_l1d_s0`, `core1_ooo_lsu_l1d_a0`, addr)) and not (core1_ooo_lsu_l1d_has_line(`core1_ooo_lsu_l1d_s1`, `core1_ooo_lsu_l1d_a1`, addr)) and `core1_ooo_lsu_l1d_lru`, set `core1_ooo_lsu_l1d_s1` to 1; set `core1_ooo_lsu_l1d_a1` to addr.
- **core1_ooo_lsu_l1d_snoop_inv0** — when 0 does not equal 0 and store and core1_ooo_lsu_l1d_has_line(`core1_ooo_lsu_l1d_s0`, `core1_ooo_lsu_l1d_a0`, addr), set `core1_ooo_lsu_l1d_s0` to 0.
- **core1_ooo_lsu_l1d_snoop_inv1** — when 0 does not equal 0 and store and core1_ooo_lsu_l1d_has_line(`core1_ooo_lsu_l1d_s1`, `core1_ooo_lsu_l1d_a1`, addr), set `core1_ooo_lsu_l1d_s1` to 0.
- **core1_ooo_lsu_l1d_snoop_dg0** — when 0 does not equal 0 and not (store) and core1_ooo_lsu_l1d_has_line(`core1_ooo_lsu_l1d_s0`, `core1_ooo_lsu_l1d_a0`, addr), set `core1_ooo_lsu_l1d_s0` to 1.
- **core1_ooo_lsu_l1d_snoop_dg1** — when 0 does not equal 0 and not (store) and core1_ooo_lsu_l1d_has_line(`core1_ooo_lsu_l1d_s1`, `core1_ooo_lsu_l1d_a1`, addr), set `core1_ooo_lsu_l1d_s1` to 1.
- **core1_cache_l1i_write_hit0** — when 0 equals 1 and core1_cache_const_false and core1_cache_l1i_has_line(`core1_cache_l1i_s0`, `core1_cache_l1i_a0`, core1_i_pa_signal), set `core1_cache_l1i_s0` to 3; set `core1_cache_l1i_data0` to 0; set `core1_cache_l1i_lru` to true.
- **core1_cache_l1i_write_hit1** — when 0 equals 1 and core1_cache_const_false and not (core1_cache_l1i_has_line(`core1_cache_l1i_s0`, `core1_cache_l1i_a0`, core1_i_pa_signal)) and core1_cache_l1i_has_line(`core1_cache_l1i_s1`, `core1_cache_l1i_a1`, core1_i_pa_signal), set `core1_cache_l1i_s1` to 3; set `core1_cache_l1i_data1` to 0; set `core1_cache_l1i_lru` to false.
- **core1_cache_l1i_write_miss0** — when 0 equals 1 and core1_cache_const_false and not (core1_cache_l1i_has_line(`core1_cache_l1i_s0`, `core1_cache_l1i_a0`, core1_i_pa_signal)) and not (core1_cache_l1i_has_line(`core1_cache_l1i_s1`, `core1_cache_l1i_a1`, core1_i_pa_signal)) and not (`core1_cache_l1i_lru`), set `core1_cache_l1i_s0` to 3; set `core1_cache_l1i_a0` to core1_i_pa_signal; set `core1_cache_l1i_data0` to 0; set `core1_cache_l1i_lru` to true.
- **core1_cache_l1i_write_miss1** — when 0 equals 1 and core1_cache_const_false and not (core1_cache_l1i_has_line(`core1_cache_l1i_s0`, `core1_cache_l1i_a0`, core1_i_pa_signal)) and not (core1_cache_l1i_has_line(`core1_cache_l1i_s1`, `core1_cache_l1i_a1`, core1_i_pa_signal)) and `core1_cache_l1i_lru`, set `core1_cache_l1i_s1` to 3; set `core1_cache_l1i_a1` to core1_i_pa_signal; set `core1_cache_l1i_data1` to 0; set `core1_cache_l1i_lru` to false.
- **core1_cache_l1i_read_hit0** — when 0 equals 1 and not (core1_cache_const_false) and core1_cache_l1i_has_line(`core1_cache_l1i_s0`, `core1_cache_l1i_a0`, core1_i_pa_signal), set `core1_cache_l1i_rdata` to `core1_cache_l1i_data0`; set `core1_cache_l1i_lru` to true.
- **core1_cache_l1i_read_hit1** — when 0 equals 1 and not (core1_cache_const_false) and not (core1_cache_l1i_has_line(`core1_cache_l1i_s0`, `core1_cache_l1i_a0`, core1_i_pa_signal)) and core1_cache_l1i_has_line(`core1_cache_l1i_s1`, `core1_cache_l1i_a1`, core1_i_pa_signal), set `core1_cache_l1i_rdata` to `core1_cache_l1i_data1`; set `core1_cache_l1i_lru` to false.
- **core1_cache_l1i_read_miss0** — when 0 equals 1 and not (core1_cache_const_false) and not (core1_cache_l1i_has_line(`core1_cache_l1i_s0`, `core1_cache_l1i_a0`, core1_i_pa_signal)) and not (core1_cache_l1i_has_line(`core1_cache_l1i_s1`, `core1_cache_l1i_a1`, core1_i_pa_signal)) and not (`core1_cache_l1i_lru`), set `core1_cache_l1i_s0` to 1; set `core1_cache_l1i_a0` to core1_i_pa_signal.
- **core1_cache_l1i_read_miss1** — when 0 equals 1 and not (core1_cache_const_false) and not (core1_cache_l1i_has_line(`core1_cache_l1i_s0`, `core1_cache_l1i_a0`, core1_i_pa_signal)) and not (core1_cache_l1i_has_line(`core1_cache_l1i_s1`, `core1_cache_l1i_a1`, core1_i_pa_signal)) and `core1_cache_l1i_lru`, set `core1_cache_l1i_s1` to 1; set `core1_cache_l1i_a1` to core1_i_pa_signal.
- **core1_cache_l1i_snoop_inv0** — when 0 does not equal 1 and core1_cache_const_false and core1_cache_l1i_has_line(`core1_cache_l1i_s0`, `core1_cache_l1i_a0`, core1_i_pa_signal), set `core1_cache_l1i_s0` to 0.
- **core1_cache_l1i_snoop_inv1** — when 0 does not equal 1 and core1_cache_const_false and core1_cache_l1i_has_line(`core1_cache_l1i_s1`, `core1_cache_l1i_a1`, core1_i_pa_signal), set `core1_cache_l1i_s1` to 0.
- **core1_cache_l1i_snoop_dg0** — when 0 does not equal 1 and not (core1_cache_const_false) and core1_cache_l1i_has_line(`core1_cache_l1i_s0`, `core1_cache_l1i_a0`, core1_i_pa_signal), set `core1_cache_l1i_s0` to 1.
- **core1_cache_l1i_snoop_dg1** — when 0 does not equal 1 and not (core1_cache_const_false) and core1_cache_l1i_has_line(`core1_cache_l1i_s1`, `core1_cache_l1i_a1`, core1_i_pa_signal), set `core1_cache_l1i_s1` to 1.
- **core1_cache_l1d_write_hit0** — when req_core equals 1 and core1_l1d_write_signal and core1_cache_l1d_has_line(`core1_cache_l1d_s0`, `core1_cache_l1d_a0`, core1_l1d_addr_signal), set `core1_cache_l1d_s0` to 3; set `core1_cache_l1d_data0` to req_data; set `core1_cache_l1d_lru` to true.
- **core1_cache_l1d_write_hit1** — when req_core equals 1 and core1_l1d_write_signal and not (core1_cache_l1d_has_line(`core1_cache_l1d_s0`, `core1_cache_l1d_a0`, core1_l1d_addr_signal)) and core1_cache_l1d_has_line(`core1_cache_l1d_s1`, `core1_cache_l1d_a1`, core1_l1d_addr_signal), set `core1_cache_l1d_s1` to 3; set `core1_cache_l1d_data1` to req_data; set `core1_cache_l1d_lru` to false.
- **core1_cache_l1d_write_miss0** — when req_core equals 1 and core1_l1d_write_signal and not (core1_cache_l1d_has_line(`core1_cache_l1d_s0`, `core1_cache_l1d_a0`, core1_l1d_addr_signal)) and not (core1_cache_l1d_has_line(`core1_cache_l1d_s1`, `core1_cache_l1d_a1`, core1_l1d_addr_signal)) and not (`core1_cache_l1d_lru`), set `core1_cache_l1d_s0` to 3; set `core1_cache_l1d_a0` to core1_l1d_addr_signal; set `core1_cache_l1d_data0` to req_data; set `core1_cache_l1d_lru` to true.
- **core1_cache_l1d_write_miss1** — when req_core equals 1 and core1_l1d_write_signal and not (core1_cache_l1d_has_line(`core1_cache_l1d_s0`, `core1_cache_l1d_a0`, core1_l1d_addr_signal)) and not (core1_cache_l1d_has_line(`core1_cache_l1d_s1`, `core1_cache_l1d_a1`, core1_l1d_addr_signal)) and `core1_cache_l1d_lru`, set `core1_cache_l1d_s1` to 3; set `core1_cache_l1d_a1` to core1_l1d_addr_signal; set `core1_cache_l1d_data1` to req_data; set `core1_cache_l1d_lru` to false.
- **core1_cache_l1d_read_hit0** — when req_core equals 1 and not (core1_l1d_write_signal) and core1_cache_l1d_has_line(`core1_cache_l1d_s0`, `core1_cache_l1d_a0`, core1_l1d_addr_signal), set `core1_cache_l1d_rdata_signal` to `core1_cache_l1d_data0`; set `core1_cache_l1d_lru` to true.
- **core1_cache_l1d_read_hit1** — when req_core equals 1 and not (core1_l1d_write_signal) and not (core1_cache_l1d_has_line(`core1_cache_l1d_s0`, `core1_cache_l1d_a0`, core1_l1d_addr_signal)) and core1_cache_l1d_has_line(`core1_cache_l1d_s1`, `core1_cache_l1d_a1`, core1_l1d_addr_signal), set `core1_cache_l1d_rdata_signal` to `core1_cache_l1d_data1`; set `core1_cache_l1d_lru` to false.
- **core1_cache_l1d_read_miss0** — when req_core equals 1 and not (core1_l1d_write_signal) and not (core1_cache_l1d_has_line(`core1_cache_l1d_s0`, `core1_cache_l1d_a0`, core1_l1d_addr_signal)) and not (core1_cache_l1d_has_line(`core1_cache_l1d_s1`, `core1_cache_l1d_a1`, core1_l1d_addr_signal)) and not (`core1_cache_l1d_lru`), set `core1_cache_l1d_s0` to 1; set `core1_cache_l1d_a0` to core1_l1d_addr_signal.
- **core1_cache_l1d_read_miss1** — when req_core equals 1 and not (core1_l1d_write_signal) and not (core1_cache_l1d_has_line(`core1_cache_l1d_s0`, `core1_cache_l1d_a0`, core1_l1d_addr_signal)) and not (core1_cache_l1d_has_line(`core1_cache_l1d_s1`, `core1_cache_l1d_a1`, core1_l1d_addr_signal)) and `core1_cache_l1d_lru`, set `core1_cache_l1d_s1` to 1; set `core1_cache_l1d_a1` to core1_l1d_addr_signal.
- **core1_cache_l1d_snoop_inv0** — when req_core does not equal 1 and core1_l1d_write_signal and core1_cache_l1d_has_line(`core1_cache_l1d_s0`, `core1_cache_l1d_a0`, core1_l1d_addr_signal), set `core1_cache_l1d_s0` to 0.
- **core1_cache_l1d_snoop_inv1** — when req_core does not equal 1 and core1_l1d_write_signal and core1_cache_l1d_has_line(`core1_cache_l1d_s1`, `core1_cache_l1d_a1`, core1_l1d_addr_signal), set `core1_cache_l1d_s1` to 0.
- **core1_cache_l1d_snoop_dg0** — when req_core does not equal 1 and not (core1_l1d_write_signal) and core1_cache_l1d_has_line(`core1_cache_l1d_s0`, `core1_cache_l1d_a0`, core1_l1d_addr_signal), set `core1_cache_l1d_s0` to 1.
- **core1_cache_l1d_snoop_dg1** — when req_core does not equal 1 and not (core1_l1d_write_signal) and core1_cache_l1d_has_line(`core1_cache_l1d_s1`, `core1_cache_l1d_a1`, core1_l1d_addr_signal), set `core1_cache_l1d_s1` to 1.
- **core1_cache_l2_write_hit0** — when req_core equals 1 and core1_l1d_write_signal and core1_cache_l2_has_line(`core1_cache_l2_s0`, `core1_cache_l2_a0`, core1_l1d_addr_signal), set `core1_cache_l2_s0` to 3; set `core1_cache_l2_lru` to true; mem_write(core1_cache_l2_mem, core1_l1d_addr_signal, req_data).
- **core1_cache_l2_write_hit1** — when req_core equals 1 and core1_l1d_write_signal and not (core1_cache_l2_has_line(`core1_cache_l2_s0`, `core1_cache_l2_a0`, core1_l1d_addr_signal)) and core1_cache_l2_has_line(`core1_cache_l2_s1`, `core1_cache_l2_a1`, core1_l1d_addr_signal), set `core1_cache_l2_s1` to 3; set `core1_cache_l2_lru` to false; mem_write(core1_cache_l2_mem, core1_l1d_addr_signal, req_data).
- **core1_cache_l2_write_miss0** — when req_core equals 1 and core1_l1d_write_signal and not (core1_cache_l2_has_line(`core1_cache_l2_s0`, `core1_cache_l2_a0`, core1_l1d_addr_signal)) and not (core1_cache_l2_has_line(`core1_cache_l2_s1`, `core1_cache_l2_a1`, core1_l1d_addr_signal)) and not (`core1_cache_l2_lru`), set `core1_cache_l2_s0` to 3; set `core1_cache_l2_a0` to core1_l1d_addr_signal; set `core1_cache_l2_lru` to true; mem_write(core1_cache_l2_mem, core1_l1d_addr_signal, req_data); set `core1_miss_valid_signal` to true; set `core1_miss_addr_signal` to core1_l1d_addr_signal.
- **core1_cache_l2_write_miss1** — when req_core equals 1 and core1_l1d_write_signal and not (core1_cache_l2_has_line(`core1_cache_l2_s0`, `core1_cache_l2_a0`, core1_l1d_addr_signal)) and not (core1_cache_l2_has_line(`core1_cache_l2_s1`, `core1_cache_l2_a1`, core1_l1d_addr_signal)) and `core1_cache_l2_lru`, set `core1_cache_l2_s1` to 3; set `core1_cache_l2_a1` to core1_l1d_addr_signal; set `core1_cache_l2_lru` to false; mem_write(core1_cache_l2_mem, core1_l1d_addr_signal, req_data); set `core1_miss_valid_signal` to true; set `core1_miss_addr_signal` to core1_l1d_addr_signal.
- **core1_cache_l2_read_miss0** — when req_core equals 1 and not (core1_l1d_write_signal) and not (core1_cache_l2_has_line(`core1_cache_l2_s0`, `core1_cache_l2_a0`, core1_l1d_addr_signal)) and not (core1_cache_l2_has_line(`core1_cache_l2_s1`, `core1_cache_l2_a1`, core1_l1d_addr_signal)) and not (`core1_cache_l2_lru`), set `core1_cache_l2_s0` to 1; set `core1_cache_l2_a0` to core1_l1d_addr_signal; set `core1_miss_valid_signal` to true; set `core1_miss_addr_signal` to core1_l1d_addr_signal.
- **core1_cache_l2_read_miss1** — when req_core equals 1 and not (core1_l1d_write_signal) and not (core1_cache_l2_has_line(`core1_cache_l2_s0`, `core1_cache_l2_a0`, core1_l1d_addr_signal)) and not (core1_cache_l2_has_line(`core1_cache_l2_s1`, `core1_cache_l2_a1`, core1_l1d_addr_signal)) and `core1_cache_l2_lru`, set `core1_cache_l2_s1` to 1; set `core1_cache_l2_a1` to core1_l1d_addr_signal; set `core1_miss_valid_signal` to true; set `core1_miss_addr_signal` to core1_l1d_addr_signal.
- **core1_cache_l2_snoop_inv0** — when req_core does not equal 1 and core1_l1d_write_signal and core1_cache_l2_has_line(`core1_cache_l2_s0`, `core1_cache_l2_a0`, core1_l1d_addr_signal), set `core1_cache_l2_s0` to 0.
- **core1_cache_l2_snoop_inv1** — when req_core does not equal 1 and core1_l1d_write_signal and core1_cache_l2_has_line(`core1_cache_l2_s1`, `core1_cache_l2_a1`, core1_l1d_addr_signal), set `core1_cache_l2_s1` to 0.
- **core1_cache_l2_snoop_dg0** — when req_core does not equal 1 and not (core1_l1d_write_signal) and core1_cache_l2_has_line(`core1_cache_l2_s0`, `core1_cache_l2_a0`, core1_l1d_addr_signal), set `core1_cache_l2_s0` to 1.
- **core1_cache_l2_snoop_dg1** — when req_core does not equal 1 and not (core1_l1d_write_signal) and core1_cache_l2_has_line(`core1_cache_l2_s1`, `core1_cache_l2_a1`, core1_l1d_addr_signal), set `core1_cache_l2_s1` to 1.
- **core1_cache_l2_mshr_mshr0_alloc** — when core1_miss_valid_signal and not (`core1_cache_l2_mshr_mshr0_valid`), set `core1_cache_l2_mshr_mshr0_valid` to true; set `core1_cache_l2_mshr_mshr0_mid` to 0; set `core1_cache_l2_mshr_mshr0_maddr` to core1_l1d_addr_signal; set `core1_cache_l2_mshr_mshr0_mdata` to req_data.
- **core1_cache_l2_mshr_mshr0_rel** — when release0, set `core1_cache_l2_mshr_mshr0_valid` to false.
- **core1_cache_l2_mshr_mshr1_alloc** — when core1_miss_valid_signal and not (`core1_cache_l2_mshr_mshr1_valid`), set `core1_cache_l2_mshr_mshr1_valid` to true; set `core1_cache_l2_mshr_mshr1_mid` to 0; set `core1_cache_l2_mshr_mshr1_maddr` to core1_l1d_addr_signal; set `core1_cache_l2_mshr_mshr1_mdata` to req_data.
- **core1_cache_l2_mshr_mshr1_rel** — when release1, set `core1_cache_l2_mshr_mshr1_valid` to false.
- **core1_cache_l2_mshr_arb_arbitrate** — when true, set `core1_cache_l2_mshr_arb_grant` to if core1_miss_valid_signal, then 0, otherwise if core1_miss_valid_signal, then 1, otherwise if core1_cache_l2_mshr_arb_req2_valid, then 2, otherwise if core1_cache_l2_mshr_arb_req3_valid, then 3, otherwise if core1_cache_l2_mshr_arb_req4_valid, then 4, otherwise if core1_cache_l2_mshr_arb_req5_valid, then 5, otherwise 0; set `core1_cache_l2_mshr_arb_grant_valid` to core1_miss_valid_signal or core1_miss_valid_signal or core1_cache_l2_mshr_arb_req2_valid or core1_cache_l2_mshr_arb_req3_valid or core1_cache_l2_mshr_arb_req4_valid or core1_cache_l2_mshr_arb_req5_valid.
- **core1_axi_mem_do_read** — when core1_miss_valid_signal, set `core1_axi_mem_rdata` to mem_read(core1_axi_mem_mem, core1_miss_addr_signal); set `core1_axi_mem_rvalid` to true.
- **core1_axi_mem_do_write** — when awvalid and wvalid, mem_write(core1_axi_mem_mem, awaddr, wdata); set `core1_axi_mem_bvalid` to true.
- **home_write0** — when req_core equals 0 and req_write, set `home_c1_state` to if home_has_line(`home_c1_state`, `home_c1_addr`, req_addr) and 1 does not equal 0, then 0, otherwise `home_c1_state`; set `home_c0_state` to 3; set `home_c0_addr` to req_addr; set `home_c0_data` to req_data.
- **home_write1** — when req_core equals 1 and req_write, set `home_c0_state` to if home_has_line(`home_c0_state`, `home_c0_addr`, req_addr) and 0 does not equal 1, then 0, otherwise `home_c0_state`; set `home_c1_state` to 3; set `home_c1_addr` to req_addr; set `home_c1_data` to req_data.
- **home_read_hit0** — when req_core equals 0 and not (req_write) and home_has_line(`home_c0_state`, `home_c0_addr`, req_addr), set `home_c0_state` to `home_c0_state`.
- **home_read_hit1** — when req_core equals 1 and not (req_write) and home_has_line(`home_c1_state`, `home_c1_addr`, req_addr), set `home_c1_state` to `home_c1_state`.
- **home_read_miss0** — when req_core equals 0 and not (req_write) and not (home_has_line(`home_c0_state`, `home_c0_addr`, req_addr)), set `home_c1_state` to if home_has_line(`home_c1_state`, `home_c1_addr`, req_addr) and 1 does not equal 0, then 1, otherwise `home_c1_state`; set `home_c0_state` to 1; set `home_c0_addr` to req_addr.
- **home_read_miss1** — when req_core equals 1 and not (req_write) and not (home_has_line(`home_c1_state`, `home_c1_addr`, req_addr)), set `home_c0_state` to if home_has_line(`home_c0_state`, `home_c0_addr`, req_addr) and 0 does not equal 1, then 1, otherwise `home_c0_state`; set `home_c1_state` to 1; set `home_c1_addr` to req_addr.
- **axi_mem_do_read** — when arvalid, set `axi_mem_rdata` to mem_read(axi_mem_mem, araddr); set `axi_mem_rvalid` to true.
- **axi_mem_do_write** — when awvalid and wvalid, mem_write(axi_mem_mem, awaddr, wdata); set `axi_mem_bvalid` to true.

## Properties

- **core0_cache_l1d_is_modified_implies_valid** (safety): always, if core0_cache_l1d_is_modified(`core0_cache_l1d_s0`), then `core0_cache_l1d_s0` does not equal 0.
- **core0_cache_l1d_phys_index_bounded** (safety): always, core0_cache_l1d_phys_index(`core0_cache_l1d_a0`) ≤ 3.
- **core0_cache_l1i_is_modified_implies_valid** (safety): always, if core0_cache_l1i_is_modified(`core0_cache_l1i_s0`), then `core0_cache_l1i_s0` does not equal 0.
- **core0_cache_l1i_phys_index_bounded** (safety): always, core0_cache_l1i_phys_index(`core0_cache_l1i_a0`) ≤ 3.
- **core0_ooo_lsu_l1d_is_modified_implies_valid** (safety): always, if core0_ooo_lsu_l1d_is_modified(`core0_ooo_lsu_l1d_s0`), then `core0_ooo_lsu_l1d_s0` does not equal 0.
- **core0_ooo_lsu_l1d_phys_index_bounded** (safety): always, core0_ooo_lsu_l1d_phys_index(`core0_ooo_lsu_l1d_a0`) ≤ 3.
- **core1_cache_l1d_is_modified_implies_valid** (safety): always, if core1_cache_l1d_is_modified(`core1_cache_l1d_s0`), then `core1_cache_l1d_s0` does not equal 0.
- **core1_cache_l1d_phys_index_bounded** (safety): always, core1_cache_l1d_phys_index(`core1_cache_l1d_a0`) ≤ 3.
- **core1_cache_l1i_is_modified_implies_valid** (safety): always, if core1_cache_l1i_is_modified(`core1_cache_l1i_s0`), then `core1_cache_l1i_s0` does not equal 0.
- **core1_cache_l1i_phys_index_bounded** (safety): always, core1_cache_l1i_phys_index(`core1_cache_l1i_a0`) ≤ 3.
- **core1_ooo_lsu_l1d_is_modified_implies_valid** (safety): always, if core1_ooo_lsu_l1d_is_modified(`core1_ooo_lsu_l1d_s0`), then `core1_ooo_lsu_l1d_s0` does not equal 0.
- **core1_ooo_lsu_l1d_phys_index_bounded** (safety): always, core1_ooo_lsu_l1d_phys_index(`core1_ooo_lsu_l1d_a0`) ≤ 3.
- **e_at_holds_line** (safety): always, if e_at(`home_c0_state`, `home_c0_addr`, `home_c0_addr`), then `home_c0_state` does not equal 0.
- **has_at_holds_line** (safety): always, if has_at(`home_c0_state`, `home_c0_addr`, `home_c0_addr`), then `home_c0_state` does not equal 0.
- **home_is_exclusive_implies_valid** (safety): always, if home_is_exclusive(`home_c0_state`), then `home_c0_state` does not equal 0.
- **home_is_modified_implies_valid** (safety): always, if home_is_modified(`home_c0_state`), then `home_c0_state` does not equal 0.
- **m_at_holds_line** (safety): always, if m_at(`home_c0_state`, `home_c0_addr`, `home_c0_addr`), then `home_c0_state` does not equal 0.
- **core0_pc_increments** (transition): after each step, `core0_pc` equals prev(core0_pc) + 1.
- **core1_pc_increments** (transition): after each step, `core1_pc` equals prev(core1_pc) + 1.
- **single_writer** (safety): always, not (`home_c0_state` equals 3 and `home_c1_state` equals 3 and `home_c0_addr` equals `home_c1_addr`).
- **m_exclusive** (safety): always, not (`home_c0_state` equals 3 and `home_c1_state` does not equal 0 and `home_c1_addr` equals `home_c0_addr`) and not (`home_c1_state` equals 3 and `home_c0_state` does not equal 0 and `home_c0_addr` equals `home_c1_addr`).
- **e_exclusive** (safety): always, not (`home_c0_state` equals 2 and `home_c1_state` does not equal 0 and `home_c1_addr` equals `home_c0_addr`) and not (`home_c1_state` equals 2 and `home_c0_state` does not equal 0 and `home_c0_addr` equals `home_c1_addr`).
