# InterScope – SpecIR: Specification Intermediate Representation for Hardware Verification

InterScope is the reference implementation of **SpecIR** (Specification Intermediate Representation), a framework for multi‑engine hardware verification.  It bridges natural‑language design specifications with simulation, model checking, and theorem proving (Kōika/Coq and ACL2).

The project provides:

- A **YAML‑based specification language** (`.specir` files) – supports version `0.1`.  
- **Unified assertion dialect** lowering to SVA, VHDL PSL, or Verilog OVL.  
- **Dual proof backends** (Kōika/Coq + ACL2) with LLM‑assisted proof generation and iterative repair.  
- **Model checking** of generated assertions using SymbiYosys (sby).  
- **Trace lifting** from Verilator VCD simulations back to abstract SpecIR traces.  
- **Evidence registry** for tracking proven theorems, counterexamples, and coverage.  
- A **user‑customisable proof library** (`src/lib/koika/assist.py`) that can be extended with new theorems.  
- **PERF (Proof tree Exploration with Reflective Feedback)** – an advanced test‑time proof search that uses tree exploration, Pareto pruning, and LLM reflection to tackle hard proof obligations, with explicit integration of model‑checking counterexamples.

---

## Quick Installation

```bash
git clone https://github.com/ywci/interscope.git
cd interscope
./install.sh
```

---

## Configuration

Edit `conf/config.yaml` to set:

- LLM provider (OpenAI, Anthropic, Ollama) and API keys.
- Paths to external tools (auto‑detected by default).
- Prover‑specific settings (tactic hints, proof timeout, repair attempts).
- Model‑checking parameters (`bmc_max_depth`, `ic3_max_steps`, `formal_timeout`).
- Simulation settings (cycles, Verilator path).
- **PERF settings**: beam size, branching factor, depth limit, Pareto dimensions, etc. (see below).

All paths are optional; the tool works with sensible defaults.

---

## Usage

The main entry point is the `run.sh` wrapper. All commands are forwarded to the `specir` CLI running inside the uv environment.

### Basic Commands

| Command | Description |
|---------|-------------|
| `./run.sh --compile <file.specir>` | Compile a SpecIR design to Kōika/ACL2/assert dialects and optionally generate RTL. |
| `./run.sh --verify <file.specir>` | Run proof obligations (theorem proving **or** model checking) on the design. |
| `./run.sh --sim <file.specir>` | Compile to RTL and run Verilator simulation (produces a VCD trace). |
| `./run.sh --lift <vcd_file>` | Lift a VCD trace to an abstract SpecIR trace (YAML). |
| `./run.sh --check <trace.yaml>` | Check properties against an abstract trace. |
| `./run.sh --query ...` | Query the evidence registry (SQLite). |

**Additional flags**  

- `--show-proof` : When verifying, print the complete proof script for each successful obligation.  
- `--no-llm` : Disable LLM assistance (use built‑in provers only) – useful for fast integration tests.  
- `--assert-lang sva|vhdl|verilog_ovl` (for `--compile` with `--backend assert`): choose the target assertion language.  
- `--cycles N` : Override the simulation cycle count.

### Choosing a Verification Backend

| Backend           | Best for                                                                 | Limitations |
|-------------------|--------------------------------------------------------------------------|-------------|
| `model_checking`  | Boolean safety properties, complex control logic, multi‑rule designs     | No bit‑selects (`slice`) |
| `koika`           | Single‑rule designs with simple arithmetic, alignment invariants         | Deeply nested `ite`, multiple rules |
| `acl2`            | First‑order functional models, simple invariants                        | Same as Kōika; currently experimental |

---

## PERF: Proof tree Exploration with Reflective Feedback

**PERF** is a **test‑time proof search** engine that extends the linear repair loop with a **tree‑based beam search**.  When a proof attempt fails, PERF:

1. Generates **multiple divergent repair attempts** from the failing script (using the LLM).  
2. **Verifies each attempt** in parallel (with optional tool‑grounding).  
3. **Scores candidates** using a **Pareto‑optimal front** across multiple dimensions (e.g., subgoal reduction, trace alignment, syntactic purity).  
4. **Selects a beam** of the best candidates and repeats the process.  

PERF is particularly effective when:

- The proof is hard and requires exploring several alternative strategies.
- A **counterexample trace** from model checking is available – PERF uses it to guide the search (`trace_alignment` dimension).
- You want to reduce the number of manual repair iterations.

Before launching the full beam search, PERF attempts a fast **interactive skeleton proof** (structural induction + inversion) when `try_skeleton_first` is enabled (the default). This often succeeds immediately on simple safety properties. During the beam search, PERF also injects the actual Coq/ACL2 definitions into the LLM prompts, enabling more accurate proof generation.

### Enabling PERF

PERF can be enabled globally in `conf/config.yaml` under the `proof.perf` block, or per‑invocation with `--perf`:

```bash
./run.sh --verify examples/fifo/fifo.specir --perf
```

To disable PERF even if the config says otherwise, use `--no-perf`.

**Important**: PERF **disables the proof library cache** (`use_proof_library: false`).  If both are enabled, the system raises a `ConfigurationError` to prevent silent bypass.  You can either set `use_proof_library: false` in `config.yaml` or let the CLI override it.

### PERF Configuration Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `enabled` | Master switch | `false` |
| `beam_size` | Number of proof strategies to keep per depth (B) | `3` |
| `branches_per_node` | Divergent repairs per failed proof (N) | `4` |
| `depth_limit` | Maximum refinement iterations (L) | `3` |
| `dimensions` | Pareto dimensions for scoring | `["subgoal_reduction", "trace_alignment", "syntactic_purity"]` |
| `primary_dimension` | Tie‑breaker for beam selection | `"subgoal_reduction"` |
| `scoring_tournament_size` | Compare each candidate to K others | `2` |
| `generation_temperature` | LLM temperature for child generation | `0.4` |
| `always_verify_children` | Verify every child with the tool | `true` |
| `max_workers` | Parallel threads for node evaluation | `4` |
| `timeout_per_node` | Seconds per node verification | `300` |
| `trace_alignment_weight` | Weight for the MC trace dimension | `0.6` |

You can override any of these via **environment variables** (e.g., `PERF_BEAM_SIZE=5`) or **per‑obligation metadata** in the `.specir` file.

### PERF Statistics

To see detailed traversal statistics (nodes explored, depths reached, pruning, token usage), pass `--perf-stats`:

```bash
./run.sh --verify examples/fifo/fifo.specir --perf --perf-stats
```

The output will include a summary table with all key metrics.

### Integration with Model Checking

When PERF is used on an obligation that also has a model‑checking counterpart (or when a counterexample trace is available), the `trace_alignment` dimension is automatically activated.  PERF uses the trace to:

- **Score** proof scripts that explicitly address the failing scenario (higher score).  
- **Guide** the LLM to generate repairs that target the root cause of the violation.

This closes the loop between bounded model checking (fast but incomplete) and theorem proving (complete but slow).

### Example: PERF on the FIFO Design

```bash
cd examples/fifo
../../run.sh --verify fifo.specir --backend koika --perf --perf-stats
```

PERF will try to prove the `fifo_no_overflow` property even though the proof library is disabled.  It may find a proof after a few depths, or report exhaustion.

---

### Examples

#### FIFO Design (Kōika + ACL2 + Simulation)

```bash
cd examples/fifo
../../run.sh --compile fifo.specir
../../run.sh --verify fifo.specir --backend koika
../../run.sh --verify fifo.specir --backend acl2
../../run.sh --sim fifo.specir --cycles 100
../../run.sh --lift build/traces/fifo.vcd --spec fifo.specir
../../run.sh --check build/traces/lifted.yaml --spec fifo.specir
```

#### ALU (Kōika + ACL2)

```bash
cd examples/simple_alu
../../run.sh --compile alu.specir
../../run.sh --verify alu.specir --backend koika
../../run.sh --verify alu.specir --backend acl2
../../run.sh --sim alu.specir --cycles 100
```

#### RISC‑V Mini

```bash
cd examples/riscv_mini
../../run.sh --verify riscv_mini.specir --backend koika
# The pc_aligned property is automatically proved.
```

#### UART

```bash
cd examples/uart
../../run.sh --verify uart.specir --backend koika
```

#### FIR Filter

```bash
cd examples/fir
../../run.sh --compile fir.specir
../../run.sh --verify fir.specir --backend koika
../../run.sh --verify fir.specir --backend acl2
```

The FIR filter demonstrates a **sequential schedule**, global input assumptions, and proof obligations that are automatically discharged by the proof library.

#### Model Checking

To verify properties using model checking, ensure that the proof obligation in the `.specir` file specifies `engine: model_checking` (and optionally `metadata.mc_engine: bmc` or `induction`).  Then run:

```bash
./run.sh --verify examples/fifo/fifo.specir --backend model_checking
```

The CLI will:

1. Synthesise RTL via Kōika.  
2. Generate SVA assertions.  
3. Run SymbiYosys (`sby`).  
4. Report the results.  If a counterexample is found, its VCD trace is saved and can be lifted for inspection.

**Current limitations**  
Model checking currently supports **Boolean safety properties only**.  Properties that use bit‑selects (e.g., `(slice … 7 7)`) are not yet compatible with Yosys and will be skipped.  Use the theorem‑proving backends (Kōika/ACL2) for such properties.

**Theorem‑proving limitations**  
The Kōika backend currently works best on designs with a **single rule** and simple arithmetic.  
Designs with deeply nested `ite` expressions (e.g., a single `execute` rule that branches on an opcode) or multiple rules may generate Coq models that are too complex for the automated proof pipeline.  
For such designs, **model checking** is the recommended verification method.  
**PERF** can also be used to explore multiple repair strategies for such complex designs, often yielding a proof where the standard repair loop fails.

#### Assertion Generation (standalone)

```bash
./run.sh --compile examples/fifo/fifo.specir --backend assert --assert-lang sva
./run.sh --compile examples/fifo/fifo.specir --backend assert --assert-lang vhdl
./run.sh --compile examples/fifo/fifo.specir --backend assert --assert-lang verilog_ovl
```

The generated assertion files are placed in `build/<design>/assertions/`.

All example designs (FIFO, ALU, Counter, FIR, RISC‑V mini, UART) now include pre‑configured `proof_obligations` with `engine: model_checking`.  You can therefore run `./run.sh --verify <design>.specir --backend model_checking` for any of them.

---

## Customising the Proof Library

You can add your own lemma proofs without modifying the core package.  Simply edit **`src/lib/koika/assist.py`** and add a new entry to the `PROOF_LIBRARY` dictionary:

```python
PROOF_LIBRARY = {
    # ... existing entries ...
    "my_theorem_proved": """Proof.
  (* your Coq proof here *)
Qed.""",
}
```

The existing entries are **complete Coq proofs** (not skeletons) and are applied automatically when a theorem name matches.  The prover will automatically pick up new entries the next time it runs.  This makes it easy to maintain a personal library of proven properties for your own designs.

---

## License

This project is licensed under the **MIT License** – see the [LICENSE](LICENSE) file for details.
