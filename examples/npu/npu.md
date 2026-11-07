# npu specification

## Inputs

| Name | Type |
|------|------|
| `ucode_valid` | bool |
| `ucode_opcode` | bits<3> |
| `gemm_done` | bool |
| `softmax_done` | bool |
| `layernorm_done` | bool |
| `gelu_done` | bool |
| `vec_done` | bool |
| `dma_done` | bool |
| `a0` | bits<8> |
| `a1` | bits<8> |
| `x` | bits<8> |
| `b` | bits<8> |
| `load_valid` | bool |
| `w_in00` | bits<8> |
| `w_in01` | bits<8> |
| `w_in10` | bits<8> |
| `w_in11` | bits<8> |
| `scale` | bits<8> |
| `shift` | bits<4> |
| `mean` | bits<8> |
| `inv_std` | bits<8> |
| `beta` | bits<8> |
| `start` | bool |
| `direction` | bool |
| `base_addr` | bits<8> |
| `burst_len` | bits<4> |

## State

| Name | Kind | Type | Initial |
|------|------|------|---------|
| `gemm_busy` | register | bool | false |
| `softmax_busy` | register | bool | false |
| `layernorm_busy` | register | bool | false |
| `gelu_busy` | register | bool | false |
| `vec_busy` | register | bool | false |
| `dma_busy` | register | bool | false |
| `all_idle` | register | bool | true |
| `ucode_opcode_out` | register | bits<3> | 0 |
| `ucode_running` | register | bool | false |
| `sram_addr` | register | bits<3> | 0 |
| `sram_data_in` | register | bits<8> | 0 |
| `sram_write_en` | register | bool | false |
| `sram_read_en` | register | bool | false |
| `sram_data_out` | register | bits<8> | 0 |
| `softmax_valid` | register | bool | false |
| `layernorm_valid` | register | bool | false |
| `gelu_valid` | register | bool | false |
| `vec_valid` | register | bool | false |
| `gemm_acc0` | register | bits<32> | 0 |
| `gemm_acc1` | register | bits<32> | 0 |
| `gemm_out0` | register | bits<8> | 0 |
| `gemm_out1` | register | bits<8> | 0 |
| `softmax_out` | register | bits<8> | 0 |
| `layernorm_out` | register | bits<8> | 0 |
| `gelu_out` | register | bits<8> | 0 |
| `vec_out` | register | bits<8> | 0 |
| `gemm_w00` | register | bits<8> | 0 |
| `gemm_w01` | register | bits<8> | 0 |
| `gemm_w10` | register | bits<8> | 0 |
| `gemm_w11` | register | bits<8> | 0 |
| `softmax_row_max` | register | bits<8> | 0 |
| `softmax_max_finder_min_val` | register | bits<8> | 0 |
| `softmax_max_finder_first` | register | bool | true |
| `softmax_max_finder_count` | register | bits<8> | 0 |
| `vec_mac_acc` | register | bits<32> | 0 |
| `vec_mac_acc_out` | register | bits<32> | 0 |
| `dma_addr` | register | bits<8> | 0 |
| `dma_remaining` | register | bits<4> | 0 |
| `dma_is_store` | register | bool | false |
| `ucode_pc` | register | bits<4> | 0 |
| `sram_mem` | memory | memory(bits<8>, 8) |  |

## Behavior (rules)

- **update_all_idle** — when true, set `all_idle` to not (`gemm_busy` or `softmax_busy` or `layernorm_busy` or `gelu_busy` or `vec_busy` or `dma_busy`).
- **dispatch_gemm** — when ucode_running and `ucode_opcode_out` equals 0 and not (`gemm_busy`), set `gemm_busy` to true.
- **dispatch_softmax** — when ucode_running and `ucode_opcode_out` equals 1 and not (`softmax_busy`), set `softmax_busy` to true; set `softmax_valid` to true.
- **dispatch_layernorm** — when ucode_running and `ucode_opcode_out` equals 2 and not (`layernorm_busy`), set `layernorm_busy` to true; set `layernorm_valid` to true.
- **dispatch_gelu** — when ucode_running and `ucode_opcode_out` equals 3 and not (`gelu_busy`), set `gelu_busy` to true; set `gelu_valid` to true.
- **dispatch_vec** — when ucode_running and `ucode_opcode_out` equals 4 and not (`vec_busy`), set `vec_busy` to true; set `vec_valid` to true.
- **dispatch_dma** — when ucode_running and `ucode_opcode_out` equals 5 and not (`dma_busy`), set `dma_busy` to true.
- **complete_gemm** — when `gemm_busy` and gemm_done, set `gemm_busy` to false.
- **complete_softmax** — when `softmax_busy` and softmax_done, set `softmax_busy` to false; set `softmax_valid` to false.
- **complete_layernorm** — when `layernorm_busy` and layernorm_done, set `layernorm_busy` to false; set `layernorm_valid` to false.
- **complete_gelu** — when `gelu_busy` and gelu_done, set `gelu_busy` to false; set `gelu_valid` to false.
- **complete_vec** — when `vec_busy` and vec_done, set `vec_busy` to false; set `vec_valid` to false.
- **complete_dma** — when `dma_busy` and dma_done, set `dma_busy` to false.
- **gemm_load_weights** — when load_valid, set `gemm_w00` to w_in00; set `gemm_w01` to w_in01; set `gemm_w10` to w_in10; set `gemm_w11` to w_in11.
- **gemm_mac_step** — when not (load_valid) and gemm_busy, set `gemm_acc0` to `gemm_acc0` + a0 × `gemm_w00` + a1 × `gemm_w10`; set `gemm_acc1` to `gemm_acc1` + a0 × `gemm_w01` + a1 × `gemm_w11`.
- **gemm_requantize** — when gemm_busy, set `gemm_out0` to min(`gemm_acc0` × scale shifted right by shift, 255); set `gemm_out1` to min(`gemm_acc1` × scale shifted right by shift, 255).
- **softmax_shift** — when softmax_valid, set `softmax_out` to min(gemm_out0 − `softmax_row_max`, 255).
- **softmax_max_finder_update** — when softmax_valid, set `softmax_max_finder_min_val` to if `softmax_max_finder_first`, then gemm_out0, otherwise if gemm_out0 < `softmax_max_finder_min_val`, then gemm_out0, otherwise `softmax_max_finder_min_val`; set `softmax_row_max` to if `softmax_max_finder_first`, then gemm_out0, otherwise if gemm_out0 > `softmax_row_max`, then gemm_out0, otherwise `softmax_row_max`; set `softmax_max_finder_count` to `softmax_max_finder_count` + 1; set `softmax_max_finder_first` to false.
- **layernorm_normalize** — when layernorm_valid, set `layernorm_out` to min(gemm_out1 − mean × inv_std + beta, 255).
- **gelu_compute** — when gelu_valid, set `gelu_out` to gelu_gelu(x).
- **vec_compute** — when vec_valid, set `vec_out` to vec_clamp8(if 0 equals 0, then a0 + b, otherwise `vec_mac_acc_out`).
- **vec_mac_unit_accumulate** — when vec_valid, set `vec_mac_acc` to `vec_mac_acc` + `a0` × `b`; set `vec_mac_acc_out` to `vec_mac_acc` + `a0` × `b`.
- **dma_start_burst** — when start and not (`dma_busy`), set `dma_addr` to min(base_addr, 255); set `dma_remaining` to min(burst_len, 15); set `dma_is_store` to direction; set `dma_busy` to true.
- **dma_burst_step** — when `dma_busy` and `dma_remaining` does not equal 0, set `dma_addr` to min(`dma_addr` + 1, 255); set `dma_remaining` to `dma_remaining` − 1.
- **dma_complete_burst** — when `dma_busy` and `dma_remaining` equals 0, set `dma_busy` to false.
- **ucode_start_fetch** — when ucode_valid and not (`ucode_running`), set `ucode_running` to true; set `ucode_pc` to 0.
- **ucode_decode** — when `ucode_running`, set `ucode_opcode_out` to ucode_opcode.
- **ucode_advance** — when `ucode_running` and all_idle, set `ucode_pc` to min(`ucode_pc` + 1, 15).
- **ucode_finish** — when `ucode_running` and `ucode_pc` equals 15, set `ucode_running` to false.
- **sram_write** — when sram_write_en, mem_write(sram_mem, sram_addr, min(sram_data_in, 255)).
- **sram_read** — when sram_read_en, sram_write(sram_data_out, mem_read(sram_mem, sram_addr)).

## Properties

- **gemm_dispatched_only_when_free** (transition): after each step, `gemm_busy` equals true.
- **softmax_dispatched_only_when_free** (transition): after each step, `softmax_busy` equals true.
- **vec_dispatched_only_when_free** (transition): after each step, `vec_busy` equals true.
- **dma_dispatched_only_when_free** (transition): after each step, `dma_busy` equals true.
