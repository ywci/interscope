# axi4_lite specification

## Inputs

| Name | Type |
|------|------|
| `awaddr` | bits<2> |
| `awvalid` | bool |
| `wdata` | bits<32> |
| `wvalid` | bool |
| `bready` | bool |
| `araddr` | bits<2> |
| `arvalid` | bool |
| `rready` | bool |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `reg0` | register | bits<32> | 0 |
| `reg1` | register | bits<32> | 0 |
| `reg2` | register | bits<32> | 0 |
| `reg3` | register | bits<32> | 0 |
| `bvalid` | register | bool | false |
| `rvalid` | register | bool | false |
| `rdata` | register | bits<32> | 0 |

## Behavior (rules)

- **step** — when true, set `reg0` to if awvalid and wvalid and awaddr equals 0, then wdata, otherwise `reg0`; set `reg1` to if awvalid and wvalid and awaddr equals 1, then wdata, otherwise `reg1`; set `reg2` to if awvalid and wvalid and awaddr equals 2, then wdata, otherwise `reg2`; set `reg3` to if awvalid and wvalid and awaddr equals 3, then wdata, otherwise `reg3`; set `bvalid` to if awvalid and wvalid, then true, otherwise if `bvalid` and bready, then false, otherwise `bvalid`; set `rdata` to if arvalid, then read_reg(araddr, `reg0`, `reg1`, `reg2`, `reg3`), otherwise `rdata`; set `rvalid` to if arvalid, then true, otherwise if `rvalid` and rready, then false, otherwise `rvalid`.

## Properties

- **write_reg0** (transition): after each step, if awvalid and wvalid and awaddr equals 0, then `reg0` equals wdata.
- **write_reg1** (transition): after each step, if awvalid and wvalid and awaddr equals 1, then `reg1` equals wdata.
- **write_reg2** (transition): after each step, if awvalid and wvalid and awaddr equals 2, then `reg2` equals wdata.
- **write_reg3** (transition): after each step, if awvalid and wvalid and awaddr equals 3, then `reg3` equals wdata.
- **write_responds** (transition): after each step, if awvalid and wvalid, then `bvalid` equals true.
- **read_responds** (transition): after each step, if arvalid, then `rvalid` equals true.
- **read_data_correct** (transition): after each step, if arvalid, then `rdata` equals read_reg(araddr, prev(reg0), prev(reg1), prev(reg2), prev(reg3)).
- **bvalid_held_until_bready** (transition): after each step, if prev(bvalid) and not (bready), then `bvalid` equals true.
- **rvalid_held_until_rready** (transition): after each step, if prev(rvalid) and not (rready), then `rvalid` equals true.
