# fpu specification

## Inputs

| Name | Type |
|------|------|
| `a` | bits<16> |
| `b` | bits<16> |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `result` | register | bits<16> | 0 |

## Behavior (rules)

- **compute** — when true, set `result` to fadd(a, b).

## Properties

- **fsub_equals_negated_fadd** (combinational): for all inputs, fsub(a, b) equals fadd(a, flip_sign_bit(b)).
- **flip_sign_involutive** (combinational): for all inputs, flip_sign_bit(flip_sign_bit(a)) equals a.
- **add_commutes** (combinational): for all inputs, abstract_finite_add(a, b) equals abstract_finite_add(b, a).
- **mul_commutes** (combinational): for all inputs, abstract_finite_mul(a, b) equals abstract_finite_mul(b, a).
- **signed_infinity_pattern** (combinational): for all inputs, concat(sign(a), 32640, 15) equals sign(a) × 32768 + 32640.
- **signed_zero_pattern** (combinational): for all inputs, sign(a) × 32768 equals concat(sign(a), 0, 15).
- **quiet_nan_pattern** (combinational): for all inputs, 32640 or 64 equals 32704.
- **fmul_inf_zero_is_nan** (combinational): for all inputs, fmul(signed_infinity(0), signed_zero(0)) equals 32704.
- **fdiv_inf_inf_is_nan** (combinational): for all inputs, fdiv(signed_infinity(0), signed_infinity(0)) equals 32704.
- **fsqrt_negative_inf_is_nan** (combinational): for all inputs, fsqrt(signed_infinity(1)) equals 32704.
