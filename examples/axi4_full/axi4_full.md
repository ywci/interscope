# axi4_full specification

## Inputs

| Name | Type |
|------|------|
| `awaddr_in` | bits<8> |
| `awlen_in` | bits<8> |
| `awvalid` | bool |
| `awready` | bool |
| `wdata` | bits<32> |
| `wvalid` | bool |
| `wready` | bool |
| `bready` | bool |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `awaddr` | register | bits<8> | 0 |
| `awlen` | register | bits<8> | 0 |
| `waddr` | register | bits<8> | 0 |
| `wcount` | register | bits<8> | 0 |
| `bvalid` | register | bool | false |
| `mem` | memory | memory(bits<32>, 16) |  |

## Behavior (rules)

- **aw** — when awvalid and awready, set `awaddr` to awaddr_in; set `awlen` to awlen_in; set `waddr` to awaddr_in; set `wcount` to 0.
- **w** — when wvalid and wready and `wcount` < `awlen`, mem_write(mem, `waddr`, wdata); set `waddr` to `waddr` + 4; set `wcount` to `wcount` + 1.
- **b** — when `wcount` equals `awlen`, set `bvalid` to true.
- **b_clear** — when `bvalid` and bready, set `bvalid` to false.

## Properties

- **waddr_increments_on_beat** (transition): after each step, `waddr` equals prev(waddr) + 4.
- **wcount_increments_on_beat** (transition): after each step, `wcount` equals prev(wcount) + 1.
- **response_after_burst** (transition): after each step, prev(wcount) equals prev(awlen).
- **wcount_bounded_by_len** (safety): always, `wcount` ≤ `awlen`.
