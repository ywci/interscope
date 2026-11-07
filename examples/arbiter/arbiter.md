# arbiter specification

## Inputs

| Name | Type |
|------|------|
| `req0_valid` | bool |
| `req1_valid` | bool |
| `req2_valid` | bool |
| `req3_valid` | bool |
| `req4_valid` | bool |
| `req5_valid` | bool |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `grant` | register | bits<3> | 0 |
| `grant_valid` | register | bool | false |

## Behavior (rules)

- **arbitrate** — when true, set `grant` to if req0_valid, then 0, otherwise if req1_valid, then 1, otherwise if req2_valid, then 2, otherwise if req3_valid, then 3, otherwise if req4_valid, then 4, otherwise if req5_valid, then 5, otherwise 0; set `grant_valid` to req0_valid or req1_valid or req2_valid or req3_valid or req4_valid or req5_valid.

## Properties

- **grant0_when_req0** (transition): after each step, if req0_valid, then `grant` equals 0.
- **grant_valid_when_any** (transition): after each step, `grant_valid` equals req0_valid or req1_valid or req2_valid or req3_valid or req4_valid or req5_valid.
