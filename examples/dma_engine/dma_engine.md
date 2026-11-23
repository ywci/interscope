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

- **busy_iff_remaining_nonzero** (safety): always, `busy` equals `remaining` does not equal 0.
- **burst_initializes** (transition): after each step, `addr` equals min(base_addr, 255) and `remaining` equals min(burst_len, 15) and `is_store` equals direction and `busy` equals true.
- **burst_advances** (transition): after each step, `addr` equals min(prev(addr) + 1, 255) and `remaining` equals prev(remaining) − 1.
- **burst_completes** (transition): after each step, `busy` equals false.
