# sram_bank specification

## Inputs

| Name | Type |
|------|------|
| `addr` | bits<3> |
| `data_in` | bits<8> |
| `write_en` | bool |
| `read_en` | bool |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `mem` | memory | memory(bits<8>, 8) |  |
| `data_out` | register | bits<8> | 0 |

## Behavior (rules)

- **write** — when write_en, mem_write(mem, addr, min(data_in, 255)).
- **read** — when read_en, set `data_out` to mem_read(mem, addr).

## Properties

- **data_out_nonneg** (safety): always, `data_out` ≥ 0.
