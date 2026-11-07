# gcd specification

## Inputs

| Name | Type |
|------|------|
| `start` | bool |
| `x` | bits<16> |
| `y` | bits<16> |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `a` | register | bits<16> | 0 |
| `b` | register | bits<16> | 0 |
| `done` | register | bool | false |
| `result` | register | bits<16> | 0 |

## Behavior (rules)

- **load** — when start, set `a` to `x`; set `b` to `y`; set `done` to false.
- **step_a** — when not (`done`) and `a` > `b`, set `a` to `a` − `b`.
- **step_b** — when not (`done`) and `b` > `a`, set `b` to `b` − `a`.
- **finish** — when not (`done`) and `a` equals `b`, set `done` to true; set `result` to `a`.

## Properties

- **operands_nonneg** (safety): always, `a` ≥ 0 and `b` ≥ 0.
- **done_implies_equal** (safety): always, if `done`, then `a` equals `b`.
- **done_implies_result_eq_a** (safety): always, if `done`, then `result` equals `a`.
- **gcd_commutes** (combinational): for all inputs, gcd_sub(x, y) equals gcd_sub(y, x).
- **gcd_diag** (combinational): for all inputs, gcd_sub(x, x) equals x.
- **gcd_sub_computes** (combinational): for all inputs, gcd_sub(10, 6) equals 2.
- **gcd_sub_step** (combinational): for all inputs, gcd_sub(10, 6) equals gcd_sub(4, 6).
