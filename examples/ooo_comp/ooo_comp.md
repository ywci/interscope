# ooo_comp specification

## Inputs

| Name | Type |
|------|------|
| `issue_valid` | bool |
| `rd` | bits<2> |
| `op` | bool |
| `alu_op` | bits<3> |
| `store` | bool |
| `a` | bits<8> |
| `b` | bits<8> |
| `addr` | bits<4> |
| `lsu_l1d_is_physical` | bool |
| `lsu_l1d_req_data` | bits<8> |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `rat0` | register | bits<3> | 0 |
| `rat1` | register | bits<3> | 1 |
| `rat2` | register | bits<3> | 2 |
| `rat3` | register | bits<3> | 3 |
| `prf0_busy` | register | bool | true |
| `prf1_busy` | register | bool | true |
| `prf2_busy` | register | bool | true |
| `prf3_busy` | register | bool | true |
| `prf4_busy` | register | bool | false |
| `prf5_busy` | register | bool | false |
| `rob0_valid` | register | bool | false |
| `rob0_rd` | register | bits<2> | 0 |
| `rob0_old` | register | bits<3> | 0 |
| `rob0_done` | register | bool | false |
| `rob1_valid` | register | bool | false |
| `rob1_rd` | register | bits<2> | 0 |
| `rob1_old` | register | bits<3> | 0 |
| `rob1_done` | register | bool | false |
| `head` | register | bool | false |
| `result` | register | bits<8> | 0 |
| `sb_valid` | register | bool | false |
| `sb_addr` | register | bits<4> | 0 |
| `sb_data` | register | bits<8> | 0 |
| `alu_result_reg` | register | bits<8> | 0 |
| `alu_zero_reg` | register | bool | false |
| `alu_overflow_reg` | register | bool | false |
| `alu_valid` | register | bool | false |
| `alu_op_reg` | register | bits<3> | 0 |
| `alu_a_reg` | register | bits<8> | 0 |
| `alu_b_reg` | register | bits<8> | 0 |
| `lsu_mem` | memory | memory(bits<8>, 16) |  |
| `lsu_resp_data` | register | bits<8> | 0 |
| `lsu_resp_valid` | register | bool | false |
| `lsu_l1d_s0` | register | bits<2> | 0 |
| `lsu_l1d_a0` | register | bits<4> | 0 |
| `lsu_l1d_s1` | register | bits<2> | 0 |
| `lsu_l1d_a1` | register | bits<4> | 0 |
| `lsu_l1d_lru` | register | bool | false |
| `lsu_l1d_data0` | register | bits<8> | 0 |
| `lsu_l1d_data1` | register | bits<8> | 0 |
| `lsu_l1d_rdata` | register | bits<8> | 0 |

## Behavior (rules)

- **issue0** — when issue_valid and not (`rob0_valid`), set `rat0` to if rd equals 0, then 4, otherwise `rat0`; set `rat1` to if rd equals 1, then 4, otherwise `rat1`; set `rat2` to if rd equals 2, then 4, otherwise `rat2`; set `rat3` to if rd equals 3, then 4, otherwise `rat3`; set `prf4_busy` to true; set `rob0_valid` to true; set `rob0_rd` to rd; set `rob0_old` to if rd equals 0, then `rat0`, otherwise if rd equals 1, then `rat1`, otherwise if rd equals 2, then `rat2`, otherwise `rat3`; set `rob0_done` to false.
- **issue1** — when issue_valid and `rob0_valid` and not (`rob1_valid`), set `rat0` to if rd equals 0, then 5, otherwise `rat0`; set `rat1` to if rd equals 1, then 5, otherwise `rat1`; set `rat2` to if rd equals 2, then 5, otherwise `rat2`; set `rat3` to if rd equals 3, then 5, otherwise `rat3`; set `prf5_busy` to true; set `rob1_valid` to true; set `rob1_rd` to rd; set `rob1_old` to if rd equals 0, then `rat0`, otherwise if rd equals 1, then `rat1`, otherwise if rd equals 2, then `rat2`, otherwise `rat3`; set `rob1_done` to false.
- **store_buf** — when issue_valid and op and store, set `sb_valid` to true; set `sb_addr` to addr; set `sb_data` to a.
- **execute** — when true, set `result` to if op, then if store, then `lsu_resp_data`, otherwise if `sb_valid` and `sb_addr` equals addr, then `sb_data`, otherwise `lsu_resp_data`, otherwise `alu_result_reg`.
- **commit0** — when `head` equals false and `rob0_done`, set `prf0_busy` to if `rob0_old` equals 0, then false, otherwise `prf0_busy`; set `prf1_busy` to if `rob0_old` equals 1, then false, otherwise `prf1_busy`; set `prf2_busy` to if `rob0_old` equals 2, then false, otherwise `prf2_busy`; set `prf3_busy` to if `rob0_old` equals 3, then false, otherwise `prf3_busy`; set `prf4_busy` to if `rob0_old` equals 4, then false, otherwise `prf4_busy`; set `prf5_busy` to if `rob0_old` equals 5, then false, otherwise `prf5_busy`; set `rob0_valid` to false; set `rob0_done` to false; set `head` to true.
- **commit1** — when `head` equals true and `rob1_done`, set `prf0_busy` to if `rob1_old` equals 0, then false, otherwise `prf0_busy`; set `prf1_busy` to if `rob1_old` equals 1, then false, otherwise `prf1_busy`; set `prf2_busy` to if `rob1_old` equals 2, then false, otherwise `prf2_busy`; set `prf3_busy` to if `rob1_old` equals 3, then false, otherwise `prf3_busy`; set `prf4_busy` to if `rob1_old` equals 4, then false, otherwise `prf4_busy`; set `prf5_busy` to if `rob1_old` equals 5, then false, otherwise `prf5_busy`; set `rob1_valid` to false; set `rob1_done` to false; set `head` to false.
- **alu_load_inputs** — when true, set `alu_op_reg` to `alu_op`; set `alu_a_reg` to `a`; set `alu_b_reg` to `b`.
- **alu_execute** — when true, set `alu_result_reg` to if `alu_op_reg` equals 0, then `alu_a_reg` + `alu_b_reg`, otherwise if `alu_op_reg` equals 1, then `alu_a_reg` − `alu_b_reg`, otherwise if `alu_op_reg` equals 2, then `alu_a_reg` and `alu_b_reg`, otherwise if `alu_op_reg` equals 3, then `alu_a_reg` or `alu_b_reg`, otherwise if `alu_op_reg` equals 4, then if `alu_a_reg` equals `alu_b_reg`, then 0, otherwise if `alu_a_reg` < `alu_b_reg`, then 1, otherwise 2, otherwise if `alu_op_reg` equals 5, then `alu_a_reg` xor `alu_b_reg`, otherwise if `alu_op_reg` equals 6, then `alu_a_reg` shifted left by `alu_b_reg`[2:0], otherwise if `alu_op_reg` equals 7, then `alu_a_reg` shifted right by `alu_b_reg`[2:0], otherwise 0; set `alu_overflow_reg` to if `alu_op_reg` equals 0, then `alu_a_reg`[7:7] equals `alu_b_reg`[7:7] and `alu_a_reg`[7:7] does not equal `alu_a_reg` + `alu_b_reg`[7:7], otherwise if `alu_op_reg` equals 1, then `alu_a_reg`[7:7] does not equal `alu_b_reg`[7:7] and `alu_a_reg`[7:7] equals `alu_a_reg` − `alu_b_reg`[7:7], otherwise false; set `alu_zero_reg` to if `alu_op_reg` equals 0, then `alu_a_reg` + `alu_b_reg`, otherwise if `alu_op_reg` equals 1, then `alu_a_reg` − `alu_b_reg`, otherwise if `alu_op_reg` equals 2, then `alu_a_reg` and `alu_b_reg`, otherwise if `alu_op_reg` equals 3, then `alu_a_reg` or `alu_b_reg`, otherwise if `alu_op_reg` equals 4, then if `alu_a_reg` equals `alu_b_reg`, then 0, otherwise if `alu_a_reg` < `alu_b_reg`, then 1, otherwise 2, otherwise if `alu_op_reg` equals 5, then `alu_a_reg` xor `alu_b_reg`, otherwise if `alu_op_reg` equals 6, then `alu_a_reg` shifted left by `alu_b_reg`[2:0], otherwise if `alu_op_reg` equals 7, then `alu_a_reg` shifted right by `alu_b_reg`[2:0], otherwise 0 equals 0; set `alu_valid` to true.
- **lsu_store** — when 0 equals 0 and store, mem_write(lsu_mem, addr, a); set `lsu_resp_valid` to true.
- **lsu_load** — when 0 equals 0 and not (store), set `lsu_resp_data` to mem_read(lsu_mem, addr); set `lsu_resp_valid` to true.
- **lsu_l1d_write_hit0** — when 0 equals 0 and store and lsu_l1d_has_line(`lsu_l1d_s0`, `lsu_l1d_a0`, addr), set `lsu_l1d_s0` to 3; set `lsu_l1d_data0` to lsu_l1d_req_data; set `lsu_l1d_lru` to true.
- **lsu_l1d_write_hit1** — when 0 equals 0 and store and not (lsu_l1d_has_line(`lsu_l1d_s0`, `lsu_l1d_a0`, addr)) and lsu_l1d_has_line(`lsu_l1d_s1`, `lsu_l1d_a1`, addr), set `lsu_l1d_s1` to 3; set `lsu_l1d_data1` to lsu_l1d_req_data; set `lsu_l1d_lru` to false.
- **lsu_l1d_write_miss0** — when 0 equals 0 and store and not (lsu_l1d_has_line(`lsu_l1d_s0`, `lsu_l1d_a0`, addr)) and not (lsu_l1d_has_line(`lsu_l1d_s1`, `lsu_l1d_a1`, addr)) and not (`lsu_l1d_lru`), set `lsu_l1d_s0` to 3; set `lsu_l1d_a0` to addr; set `lsu_l1d_data0` to lsu_l1d_req_data; set `lsu_l1d_lru` to true.
- **lsu_l1d_write_miss1** — when 0 equals 0 and store and not (lsu_l1d_has_line(`lsu_l1d_s0`, `lsu_l1d_a0`, addr)) and not (lsu_l1d_has_line(`lsu_l1d_s1`, `lsu_l1d_a1`, addr)) and `lsu_l1d_lru`, set `lsu_l1d_s1` to 3; set `lsu_l1d_a1` to addr; set `lsu_l1d_data1` to lsu_l1d_req_data; set `lsu_l1d_lru` to false.
- **lsu_l1d_read_hit0** — when 0 equals 0 and not (store) and lsu_l1d_has_line(`lsu_l1d_s0`, `lsu_l1d_a0`, addr), set `lsu_l1d_rdata` to `lsu_l1d_data0`; set `lsu_l1d_lru` to true.
- **lsu_l1d_read_hit1** — when 0 equals 0 and not (store) and not (lsu_l1d_has_line(`lsu_l1d_s0`, `lsu_l1d_a0`, addr)) and lsu_l1d_has_line(`lsu_l1d_s1`, `lsu_l1d_a1`, addr), set `lsu_l1d_rdata` to `lsu_l1d_data1`; set `lsu_l1d_lru` to false.
- **lsu_l1d_read_miss0** — when 0 equals 0 and not (store) and not (lsu_l1d_has_line(`lsu_l1d_s0`, `lsu_l1d_a0`, addr)) and not (lsu_l1d_has_line(`lsu_l1d_s1`, `lsu_l1d_a1`, addr)) and not (`lsu_l1d_lru`), set `lsu_l1d_s0` to 1; set `lsu_l1d_a0` to addr.
- **lsu_l1d_read_miss1** — when 0 equals 0 and not (store) and not (lsu_l1d_has_line(`lsu_l1d_s0`, `lsu_l1d_a0`, addr)) and not (lsu_l1d_has_line(`lsu_l1d_s1`, `lsu_l1d_a1`, addr)) and `lsu_l1d_lru`, set `lsu_l1d_s1` to 1; set `lsu_l1d_a1` to addr.
- **lsu_l1d_snoop_inv0** — when 0 does not equal 0 and store and lsu_l1d_has_line(`lsu_l1d_s0`, `lsu_l1d_a0`, addr), set `lsu_l1d_s0` to 0.
- **lsu_l1d_snoop_inv1** — when 0 does not equal 0 and store and lsu_l1d_has_line(`lsu_l1d_s1`, `lsu_l1d_a1`, addr), set `lsu_l1d_s1` to 0.
- **lsu_l1d_snoop_dg0** — when 0 does not equal 0 and not (store) and lsu_l1d_has_line(`lsu_l1d_s0`, `lsu_l1d_a0`, addr), set `lsu_l1d_s0` to 1.
- **lsu_l1d_snoop_dg1** — when 0 does not equal 0 and not (store) and lsu_l1d_has_line(`lsu_l1d_s1`, `lsu_l1d_a1`, addr), set `lsu_l1d_s1` to 1.

## Properties

- **commit_in_order** (transition): after each step, `head` equals true and `rob0_valid` equals false.
- **store_load_forward** (transition): after each step, if op and not (store) and `sb_valid` and `sb_addr` equals addr, then `result` equals `sb_data`.
- **rat_bounded** (safety): always, `rat0` ≥ 0 and `rat0` ≤ 5 and `rat1` ≥ 0 and `rat1` ≤ 5 and `rat2` ≥ 0 and `rat2` ≤ 5 and `rat3` ≥ 0 and `rat3` ≤ 5.
- **alu_zero_flag_correct** (safety): always, if `alu_valid`, then `alu_zero_reg` equals `alu_result_reg` equals 0.
- **alu_add_overflow_correct** (safety): always, if `alu_op_reg` equals 0, then `alu_overflow_reg` equals `alu_a_reg`[7:7] equals `alu_b_reg`[7:7] and `alu_a_reg`[7:7] does not equal `alu_a_reg` + `alu_b_reg`[7:7].
- **alu_sub_overflow_correct** (safety): always, if `alu_op_reg` equals 1, then `alu_overflow_reg` equals `alu_a_reg`[7:7] does not equal `alu_b_reg`[7:7] and `alu_a_reg`[7:7] equals `alu_a_reg` − `alu_b_reg`[7:7].
- **alu_overflow_implies_result_neq_sum** (safety): always, if `alu_valid` and `alu_op_reg` equals 0 and `alu_overflow_reg`, then `alu_result_reg` does not equal `alu_a_reg` + `alu_b_reg`.
- **alu_sub_overflow_implies_result_neq_diff** (safety): always, if `alu_valid` and `alu_op_reg` equals 1 and `alu_overflow_reg`, then `alu_result_reg` does not equal `alu_a_reg` − `alu_b_reg`.
- **alu_result_reg_self** (safety): always, `alu_result_reg` equals `alu_result_reg`.
- **alu_zero_reg_is_bool** (safety): always, `alu_zero_reg` equals true or `alu_zero_reg` equals false.
- **alu_overflow_reg_is_bool** (safety): always, `alu_overflow_reg` equals true or `alu_overflow_reg` equals false.
- **alu_valid_is_bool** (safety): always, `alu_valid` equals true or `alu_valid` equals false.
- **alu_add_correctness** (combinational): for all inputs, if 0 equals 0, then a + b, otherwise if 0 equals 1, then a − b, otherwise if 0 equals 2, then a and b, otherwise if 0 equals 3, then a or b, otherwise if 0 equals 4, then if a equals b, then 0, otherwise if a < b, then 1, otherwise 2, otherwise if 0 equals 5, then a xor b, otherwise if 0 equals 6, then a shifted left by b[2:0], otherwise if 0 equals 7, then a shifted right by b[2:0], otherwise 0 equals a + b.
- **alu_sub_correctness** (combinational): for all inputs, if 1 equals 0, then a + b, otherwise if 1 equals 1, then a − b, otherwise if 1 equals 2, then a and b, otherwise if 1 equals 3, then a or b, otherwise if 1 equals 4, then if a equals b, then 0, otherwise if a < b, then 1, otherwise 2, otherwise if 1 equals 5, then a xor b, otherwise if 1 equals 6, then a shifted left by b[2:0], otherwise if 1 equals 7, then a shifted right by b[2:0], otherwise 0 equals a − b.
- **alu_and_correctness** (combinational): for all inputs, if 2 equals 0, then a + b, otherwise if 2 equals 1, then a − b, otherwise if 2 equals 2, then a and b, otherwise if 2 equals 3, then a or b, otherwise if 2 equals 4, then if a equals b, then 0, otherwise if a < b, then 1, otherwise 2, otherwise if 2 equals 5, then a xor b, otherwise if 2 equals 6, then a shifted left by b[2:0], otherwise if 2 equals 7, then a shifted right by b[2:0], otherwise 0 equals a and b.
- **alu_or_correctness** (combinational): for all inputs, if 3 equals 0, then a + b, otherwise if 3 equals 1, then a − b, otherwise if 3 equals 2, then a and b, otherwise if 3 equals 3, then a or b, otherwise if 3 equals 4, then if a equals b, then 0, otherwise if a < b, then 1, otherwise 2, otherwise if 3 equals 5, then a xor b, otherwise if 3 equals 6, then a shifted left by b[2:0], otherwise if 3 equals 7, then a shifted right by b[2:0], otherwise 0 equals a or b.
- **alu_cmp_correctness** (combinational): for all inputs, if 4 equals 0, then a + b, otherwise if 4 equals 1, then a − b, otherwise if 4 equals 2, then a and b, otherwise if 4 equals 3, then a or b, otherwise if 4 equals 4, then if a equals b, then 0, otherwise if a < b, then 1, otherwise 2, otherwise if 4 equals 5, then a xor b, otherwise if 4 equals 6, then a shifted left by b[2:0], otherwise if 4 equals 7, then a shifted right by b[2:0], otherwise 0 equals if a equals b, then 0, otherwise if a < b, then 1, otherwise 2.
- **alu_xor_correctness** (combinational): for all inputs, if 5 equals 0, then a + b, otherwise if 5 equals 1, then a − b, otherwise if 5 equals 2, then a and b, otherwise if 5 equals 3, then a or b, otherwise if 5 equals 4, then if a equals b, then 0, otherwise if a < b, then 1, otherwise 2, otherwise if 5 equals 5, then a xor b, otherwise if 5 equals 6, then a shifted left by b[2:0], otherwise if 5 equals 7, then a shifted right by b[2:0], otherwise 0 equals a xor b.
- **alu_shl_correctness** (combinational): for all inputs, if 6 equals 0, then a + b, otherwise if 6 equals 1, then a − b, otherwise if 6 equals 2, then a and b, otherwise if 6 equals 3, then a or b, otherwise if 6 equals 4, then if a equals b, then 0, otherwise if a < b, then 1, otherwise 2, otherwise if 6 equals 5, then a xor b, otherwise if 6 equals 6, then a shifted left by b[2:0], otherwise if 6 equals 7, then a shifted right by b[2:0], otherwise 0 equals a shifted left by b[2:0].
- **alu_shr_correctness** (combinational): for all inputs, if 7 equals 0, then a + b, otherwise if 7 equals 1, then a − b, otherwise if 7 equals 2, then a and b, otherwise if 7 equals 3, then a or b, otherwise if 7 equals 4, then if a equals b, then 0, otherwise if a < b, then 1, otherwise 2, otherwise if 7 equals 5, then a xor b, otherwise if 7 equals 6, then a shifted left by b[2:0], otherwise if 7 equals 7, then a shifted right by b[2:0], otherwise 0 equals a shifted right by b[2:0].
- **lsu_resp_valid_bool** (safety): always, `lsu_resp_valid` equals true or `lsu_resp_valid` equals false.
- **lsu_load_returns_mem** (transition): after each step, `lsu_resp_data` equals mem_read(lsu_mem, addr).
- **lsu_l1d_states_valid** (safety): always, `lsu_l1d_s0` ≥ 0 and `lsu_l1d_s0` ≤ 3 and `lsu_l1d_s1` ≥ 0 and `lsu_l1d_s1` ≤ 3.
- **lsu_l1d_physical_tag_used** (transition): after each step, `lsu_l1d_a0` equals addr.
- **lsu_l1d_modified_way_holds_line** (safety): always, if lsu_l1d_is_modified(`lsu_l1d_s0`), then lsu_l1d_has_line(`lsu_l1d_s0`, `lsu_l1d_a0`, `lsu_l1d_a0`).
- **lsu_l1d_phys_index_bounded** (safety): always, lsu_l1d_phys_index(addr) ≤ 3.
