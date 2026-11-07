# mshr specification

## Inputs

| Name | Type |
|------|------|
| `alloc_valid` | bool |
| `id` | bits<2> |
| `addr` | bits<4> |
| `data` | bits<8> |
| `release` | bool |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `valid` | register | bool | false |
| `mid` | register | bits<2> | 0 |
| `maddr` | register | bits<4> | 0 |
| `mdata` | register | bits<8> | 0 |

## Behavior (rules)

- **alloc** — when alloc_valid and not (`valid`), set `valid` to true; set `mid` to id; set `maddr` to addr; set `mdata` to data.
- **rel** — when release, set `valid` to false.

## Properties

- **alloc_sets_entry** (transition): after each step, `valid` equals true and `mid` equals id.
