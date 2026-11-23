# crc32 specification

## Inputs

| Name | Type |
|------|------|
| `data_in` | bits<8> |
| `data_valid` | bool |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `crc` | register | bits<32> | 0 |
| `count` | register | bits<2> | 0 |
| `done` | register | bool | false |
| `crc_table` | memory | memory(bits<32>, 256) |  |

## Behavior (rules)

- **process_byte** — when data_valid and not (`done`), set `crc` to rshift(`crc`, 8) xor mem_read(crc_table, `crc` xor `data_in` and 255); set `count` to `count` + 1; set `done` to `count` equals 3.

## Properties

- **done_after_4_bytes** (safety): always, if done, then `count` equals 3.
- **crc_reset_value** (safety): always, if not (rst_n), then `crc` equals 0.
- **done_initial_false** (safety): always, if not (rst_n), then not (done).
- **done_iff_count_eq_4** (safety): always, done equals `count` equals 4.
- **crc_32_bit** (safety): always, `crc` ≥ 0 and `crc` ≤ 4294967295.
- **crc_accumulates_byte** (transition): after each step, `count` equals prev(count) + 1 and done equals prev(count) equals 3.
