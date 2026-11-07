# axi4_stream specification

## Inputs

| Name | Type |
|------|------|
| `tdata_in` | bits<32> |
| `tvalid_in` | bool |
| `tlast_in` | bool |
| `tready_out` | bool |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `full` | register | bool | false |
| `data` | register | bits<32> | 0 |
| `last` | register | bool | false |

## Behavior (rules)

- **step** — when true, set `full` to if `full`, then not (tready_out), otherwise tvalid_in; set `data` to if `full`, then `data`, otherwise tdata_in; set `last` to if `full`, then `last`, otherwise tlast_in.

## Properties

- **full_bool** (safety): always, `full` equals true or `full` equals false.
- **source_holds_valid_until_ready** (transition): after each step, if prev(full) and tready_out equals false, then `full` equals true.
- **source_holds_data_until_ready** (transition): after each step, if prev(full) and tready_out equals false, then `data` equals prev(data).
- **sink_accepts_when_empty** (transition): after each step, if not (prev(full)) and tvalid_in, then `full` equals true.
- **data_latches_on_accept** (transition): after each step, if not (prev(full)) and tvalid_in, then `data` equals tdata_in.
- **tlast_latches_on_accept** (transition): after each step, if not (prev(full)) and tvalid_in, then `last` equals tlast_in.
- **handshake_transfers_beat** (transition): after each step, if handshake(prev(full), tready_out), then `full` equals false.
