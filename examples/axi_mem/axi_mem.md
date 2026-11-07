# axi_mem specification

## Inputs

| Name | Type |
|------|------|
| `araddr` | bits<4> |
| `arvalid` | bool |
| `awaddr` | bits<4> |
| `awvalid` | bool |
| `wdata` | bits<8> |
| `wvalid` | bool |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `mem` | memory | memory(bits<8>, 16) |  |
| `rdata` | register | bits<8> | 0 |
| `rvalid` | register | bool | false |
| `bvalid` | register | bool | false |

## Behavior (rules)

- **do_read** — when arvalid, set `rdata` to mem_read(mem, araddr); set `rvalid` to true.
- **do_write** — when awvalid and wvalid, mem_write(mem, awaddr, wdata); set `bvalid` to true.

## Properties

- **rvalid_bool** (safety): always, `rvalid` equals true or `rvalid` equals false.
- **bvalid_bool** (safety): always, `bvalid` equals true or `bvalid` equals false.
