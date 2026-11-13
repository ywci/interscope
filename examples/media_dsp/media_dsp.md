# media_dsp specification

## Inputs

| Name | Type |
|------|------|
| `a` | bits<8> |
| `b` | bits<8> |
| `x` | bits<8> |
| `y` | bits<8> |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `sum_reg` | register | bits<16> | 0 |
| `prod_reg` | register | bits<16> | 0 |

## Behavior (rules)

- **accumulate** — when true, .

## Properties

- **sum_bounded** (combinational): for all inputs, sum16(a, b) ≤ 510 equals t.
- **product_bounded** (combinational): for all inputs, prod16(x, y) ≤ 65025 equals t.
