# mul specification

## Inputs

| Name | Type |
|------|------|
| `start` | bool |
| `x` | bits<16> |
| `y` | bits<16> |
| `z` | bits<16> |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `multiplicand` | register | bits<16> | 0 |
| `multiplier` | register | bits<16> | 0 |
| `acc` | register | bits<32> | 0 |
| `count` | register | bits<5> | 0 |
| `done` | register | bool | false |
| `product` | register | bits<32> | 0 |

## Behavior (rules)

- **load** — when start, set `multiplicand` to `x`; set `multiplier` to `y`; set `acc` to 0; set `count` to 0; set `done` to false.
- **add_step** — when not (`done`) and `count` < 16 and mod(`multiplier`, 2) equals 1, set `acc` to `acc` + `multiplicand`; set `multiplier` to div(`multiplier`, 2); set `count` to `count` + 1.
- **shift_step** — when not (`done`) and `count` < 16 and mod(`multiplier`, 2) equals 0, set `multiplier` to div(`multiplier`, 2); set `count` to `count` + 1.
- **finish** — when not (`done`) and `count` ≥ 16, set `done` to true; set `product` to `acc`.

## Properties

- **count_in_range** (safety): always, `count` ≥ 0 and `count` ≤ 16.
- **acc_nonneg** (safety): always, `acc` ≥ 0.
- **mul_commutative** (combinational): for all inputs, mul_exact(x, y) equals mul_exact(y, x).
- **mul_distributive** (combinational): for all inputs, mul_exact(x, y + z) equals mul_exact(x, y) + mul_exact(x, z).
- **mul_zero** (combinational): for all inputs, mul_exact(x, 0) equals 0.
- **mul_one** (combinational): for all inputs, mul_exact(x, 1) equals x.
- **truncation_definitional** (combinational): for all inputs, mul_truncated_result(x, y) equals mul_exact(x, y)[15:0].
- **overflow_definitional** (combinational): for all inputs, mul_truncated_ovf(x, y) equals mul_exact(x, y)[31:16] does not equal 0.
- **unsigned_max_bound** (combinational): for all inputs, mul_exact(x, y) ≤ 65025 equals true.
