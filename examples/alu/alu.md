# alu specification

## Inputs

| Name | Type |
|------|------|
| `op` | bits<3> |
| `a` | bits<8> |
| `b` | bits<8> |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `result_reg` | register | bits<8> | 0 |
| `zero_reg` | register | bool | false |
| `overflow_reg` | register | bool | false |
| `valid` | register | bool | false |
| `op_reg` | register | bits<3> | 0 |
| `a_reg` | register | bits<8> | 0 |
| `b_reg` | register | bits<8> | 0 |

## Behavior (rules)

- **load_inputs** — when true, set `op_reg` to `op`; set `a_reg` to `a`; set `b_reg` to `b`.
- **execute** — when true, set `result_reg` to if `op_reg` equals 0, then `a_reg` + `b_reg`, otherwise if `op_reg` equals 1, then `a_reg` − `b_reg`, otherwise if `op_reg` equals 2, then `a_reg` and `b_reg`, otherwise if `op_reg` equals 3, then `a_reg` or `b_reg`, otherwise if `op_reg` equals 4, then if `a_reg` equals `b_reg`, then 0, otherwise if `a_reg` < `b_reg`, then 1, otherwise 2, otherwise if `op_reg` equals 5, then `a_reg` xor `b_reg`, otherwise if `op_reg` equals 6, then `a_reg` shifted left by `b_reg`[2:0], otherwise if `op_reg` equals 7, then `a_reg` shifted right by `b_reg`[2:0], otherwise 0; set `overflow_reg` to if `op_reg` equals 0, then `a_reg`[7:7] equals `b_reg`[7:7] and `a_reg`[7:7] does not equal `a_reg` + `b_reg`[7:7], otherwise if `op_reg` equals 1, then `a_reg`[7:7] does not equal `b_reg`[7:7] and `a_reg`[7:7] equals `a_reg` − `b_reg`[7:7], otherwise false; set `zero_reg` to if `op_reg` equals 0, then `a_reg` + `b_reg`, otherwise if `op_reg` equals 1, then `a_reg` − `b_reg`, otherwise if `op_reg` equals 2, then `a_reg` and `b_reg`, otherwise if `op_reg` equals 3, then `a_reg` or `b_reg`, otherwise if `op_reg` equals 4, then if `a_reg` equals `b_reg`, then 0, otherwise if `a_reg` < `b_reg`, then 1, otherwise 2, otherwise if `op_reg` equals 5, then `a_reg` xor `b_reg`, otherwise if `op_reg` equals 6, then `a_reg` shifted left by `b_reg`[2:0], otherwise if `op_reg` equals 7, then `a_reg` shifted right by `b_reg`[2:0], otherwise 0 equals 0; set `valid` to true.

## Properties

- **zero_flag_correct** (safety): always, if `valid`, then `zero_reg` equals `result_reg` equals 0.
- **add_overflow_correct** (safety): always, if `op_reg` equals 0, then `overflow_reg` equals `a_reg`[7:7] equals `b_reg`[7:7] and `a_reg`[7:7] does not equal `a_reg` + `b_reg`[7:7].
- **sub_overflow_correct** (safety): always, if `op_reg` equals 1, then `overflow_reg` equals `a_reg`[7:7] does not equal `b_reg`[7:7] and `a_reg`[7:7] equals `a_reg` − `b_reg`[7:7].
- **overflow_implies_result_neq_sum** (safety): always, if `valid` and `op_reg` equals 0 and `overflow_reg`, then `result_reg` does not equal `a_reg` + `b_reg`.
- **sub_overflow_implies_result_neq_diff** (safety): always, if `valid` and `op_reg` equals 1 and `overflow_reg`, then `result_reg` does not equal `a_reg` − `b_reg`.
- **result_reg_self** (safety): always, `result_reg` equals `result_reg`.
- **zero_reg_is_bool** (safety): always, `zero_reg` equals true or `zero_reg` equals false.
- **overflow_reg_is_bool** (safety): always, `overflow_reg` equals true or `overflow_reg` equals false.
- **valid_is_bool** (safety): always, `valid` equals true or `valid` equals false.
- **add_correctness** (combinational): for all inputs, if 0 equals 0, then a + b, otherwise if 0 equals 1, then a − b, otherwise if 0 equals 2, then a and b, otherwise if 0 equals 3, then a or b, otherwise if 0 equals 4, then if a equals b, then 0, otherwise if a < b, then 1, otherwise 2, otherwise if 0 equals 5, then a xor b, otherwise if 0 equals 6, then a shifted left by b[2:0], otherwise if 0 equals 7, then a shifted right by b[2:0], otherwise 0 equals a + b.
- **sub_correctness** (combinational): for all inputs, if 1 equals 0, then a + b, otherwise if 1 equals 1, then a − b, otherwise if 1 equals 2, then a and b, otherwise if 1 equals 3, then a or b, otherwise if 1 equals 4, then if a equals b, then 0, otherwise if a < b, then 1, otherwise 2, otherwise if 1 equals 5, then a xor b, otherwise if 1 equals 6, then a shifted left by b[2:0], otherwise if 1 equals 7, then a shifted right by b[2:0], otherwise 0 equals a − b.
- **and_correctness** (combinational): for all inputs, if 2 equals 0, then a + b, otherwise if 2 equals 1, then a − b, otherwise if 2 equals 2, then a and b, otherwise if 2 equals 3, then a or b, otherwise if 2 equals 4, then if a equals b, then 0, otherwise if a < b, then 1, otherwise 2, otherwise if 2 equals 5, then a xor b, otherwise if 2 equals 6, then a shifted left by b[2:0], otherwise if 2 equals 7, then a shifted right by b[2:0], otherwise 0 equals a and b.
- **or_correctness** (combinational): for all inputs, if 3 equals 0, then a + b, otherwise if 3 equals 1, then a − b, otherwise if 3 equals 2, then a and b, otherwise if 3 equals 3, then a or b, otherwise if 3 equals 4, then if a equals b, then 0, otherwise if a < b, then 1, otherwise 2, otherwise if 3 equals 5, then a xor b, otherwise if 3 equals 6, then a shifted left by b[2:0], otherwise if 3 equals 7, then a shifted right by b[2:0], otherwise 0 equals a or b.
- **cmp_correctness** (combinational): for all inputs, if 4 equals 0, then a + b, otherwise if 4 equals 1, then a − b, otherwise if 4 equals 2, then a and b, otherwise if 4 equals 3, then a or b, otherwise if 4 equals 4, then if a equals b, then 0, otherwise if a < b, then 1, otherwise 2, otherwise if 4 equals 5, then a xor b, otherwise if 4 equals 6, then a shifted left by b[2:0], otherwise if 4 equals 7, then a shifted right by b[2:0], otherwise 0 equals if a equals b, then 0, otherwise if a < b, then 1, otherwise 2.
- **xor_correctness** (combinational): for all inputs, if 5 equals 0, then a + b, otherwise if 5 equals 1, then a − b, otherwise if 5 equals 2, then a and b, otherwise if 5 equals 3, then a or b, otherwise if 5 equals 4, then if a equals b, then 0, otherwise if a < b, then 1, otherwise 2, otherwise if 5 equals 5, then a xor b, otherwise if 5 equals 6, then a shifted left by b[2:0], otherwise if 5 equals 7, then a shifted right by b[2:0], otherwise 0 equals a xor b.
- **shl_correctness** (combinational): for all inputs, if 6 equals 0, then a + b, otherwise if 6 equals 1, then a − b, otherwise if 6 equals 2, then a and b, otherwise if 6 equals 3, then a or b, otherwise if 6 equals 4, then if a equals b, then 0, otherwise if a < b, then 1, otherwise 2, otherwise if 6 equals 5, then a xor b, otherwise if 6 equals 6, then a shifted left by b[2:0], otherwise if 6 equals 7, then a shifted right by b[2:0], otherwise 0 equals a shifted left by b[2:0].
- **shr_correctness** (combinational): for all inputs, if 7 equals 0, then a + b, otherwise if 7 equals 1, then a − b, otherwise if 7 equals 2, then a and b, otherwise if 7 equals 3, then a or b, otherwise if 7 equals 4, then if a equals b, then 0, otherwise if a < b, then 1, otherwise 2, otherwise if 7 equals 5, then a xor b, otherwise if 7 equals 6, then a shifted left by b[2:0], otherwise if 7 equals 7, then a shifted right by b[2:0], otherwise 0 equals a shifted right by b[2:0].
