# dma_engine specification

## Inputs

| Name | Type |
|------|------|
| `start` | bool |
| `direction` | bool |
| `base_addr` | bits<8> |
| `burst_len` | bits<4> |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `addr` | register | bits<8> | 0 |
| `remaining` | register | bits<4> | 0 |
| `is_store` | register | bool | false |
| `busy` | register | bool | false |

## Behavior (rules)

- **start_burst** — when start and not (`busy`), set `addr` to min(base_addr, 255); set `remaining` to min(burst_len, 15); set `is_store` to direction; set `busy` to true.
- **burst_step** — when `busy` and `remaining` does not equal 0, set `addr` to min(`addr` + 1, 255); set `remaining` to `remaining` − 1.
- **complete_burst** — when `busy` and `remaining` equals 0, set `busy` to false.

## Properties

- **addr_bounded** (safety): always, `addr` ≤ 255.
- **remaining_bounded** (safety): always, `remaining` ≤ 15.
