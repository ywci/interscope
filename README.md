# InterScope – SpecIR: Specification Intermediate Representation for Hardware Verification

InterScope is the reference implementation of **SpecIR** (Specification Intermediate Representation), a framework for multi‑engine hardware verification. It bridges natural‑language design specifications with simulation, model checking, and theorem proving (Kōika/Coq and ACL2).

The project provides:

- A **YAML‑based specification language** (`.specir` files) – supports version `0.1`.  
- **Unified assertion dialect** lowering to SVA, VHDL PSL, or Verilog OVL.  
- **Dual proof backends** (Kōika/Coq + ACL2) with LLM‑assisted proof generation and iterative repair.  
- **Model checking** of generated assertions using SymbiYosys (sby).  
- **Trace lifting** from Verilator VCD simulations back to abstract SpecIR traces.  
- **Evidence registry** for tracking proven theorems, counterexamples, and coverage.  
- A **user‑customisable proof library** (`src/lib/koika/assist.py`) that can be extended with new theorems.  
- **PERF (Proof tree Exploration with Reflective Feedback)** – an advanced test‑time proof search that uses tree exploration, Pareto pruning, and LLM reflection to tackle hard proof obligations, with explicit integration of model‑checking counterexamples.  
- **Batch processing** of multiple `.specir` files with structured reporting for integration into evaluation pipelines.

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

- LLM provider (OpenAI, Anthropic, Ollama, DeepSeek) and API keys.
- Paths to external tools (auto‑detected by default).
- Prover‑specific settings (tactic hints, proof timeout, repair attempts).
- Model‑checking parameters (`bmc_max_depth`, `ic3_max_steps`, `formal_timeout`).
- Simulation settings (cycles, Verilator path).
- **PERF settings**: beam size, branching factor, depth limit, Pareto dimensions, backtracking (including on‑demand triggers), reflection quality, repair persistence, and minimum beam size (see below).
- **Synthesis settings** (optional) for RTL quality experiments.

All paths are optional; the tool works with sensible defaults.

---

## Usage

The main entry point is the `run.sh` wrapper. All commands are forwarded to the `specir` CLI running inside the uv environment.

### Global Options

| Option | Description |
|--------|-------------|
| `--batch [DIR]` | Process all `.specir` files found recursively in DIR (default: current directory). |
| `--output-format json\|text` | Output results in structured JSON or human‑readable text (default: text). |
| `--report-file <path>` | Save aggregated results to the specified file (JSON/CSV). |
| `--config <file>` | Load additional configuration from an external YAML file (deep‑merged with defaults). |
| `--debug` | Enable debug logging. |

These global options apply to all commands (`compile`, `verify`, `sim`, etc.).

### Basic Commands

| Command | Description |
|---------|-------------|
| `./run.sh --compile <file.specir>` | Compile a SpecIR design to Kōika/ACL2/assert dialects and optionally generate RTL. |
| `./run.sh --verify <file.specir>` | Run proof obligations (theorem proving **or** model checking) on the design. |
| `./run.sh --sim <file.specir>` | Compile to RTL and run Verilator simulation (produces a VCD trace). |
| `./run.sh --lift <vcd_file>` | Lift a VCD trace to an abstract SpecIR trace (YAML). |
| `./run.sh --check <trace.yaml>` | Check properties against an abstract trace. |
| `./run.sh --query ...` | Query the evidence registry (SQLite) – now with `export`, `stats`, and `filter` sub‑commands. |

For compatibility, the old `--command` style is still accepted. The newer unified CLI also accepts commands without leading dashes, e.g.:

```bash
./run.sh compile examples/fifo/fifo.specir
./run.sh verify examples/fifo/fifo.specir --perf
```

**Additional flags**  

- `--show-proof` : When verifying, print the complete proof script for each successful obligation.  
- `--no-llm` : Disable LLM assistance (use built‑in provers only) – useful for fast integration tests.  
- `--assert-lang sva|vhdl|verilog_ovl` (for `--compile` with `--backend assert`): choose the target assertion language.  
- `--cycles N` : Override the simulation cycle count.  
- `--coverage` (sim) : Enable Verilator coverage collection and report coverage percentage.  
- `--synthesize` (compile/sim) : After RTL generation, run Yosys synthesis and report area/delay/power (optional, requires Yosys).  
- `--perf` : Enable PERF for this verification run.  
- `--no-perf` : Disable PERF even if configured globally.  
- `--perf-stats` : Print detailed PERF traversal statistics (nodes, depths, pruning, token usage, reflection quality).  
- `--no-pareto` : Disable Pareto pruning (ablation).  
- `--no-trace-alignment` : Disable the trace‑alignment dimension (ablation).  
- `--no-reflection` : Disable reflection feedback (ablation).  
- `--dry-run` : Parse and validate only; do not execute provers.

Flags `--perf`, `--no-perf`, `--perf-stats`, `--no-pareto`, `--no-trace-alignment`, `--no-reflection`, and `--dry-run` are only meaningful with `--verify`.

### Choosing a Verification Backend

| Backend           | Best for                                                                 | Limitations |
|-------------------|--------------------------------------------------------------------------|-------------|
| `model_checking`  | Boolean safety properties, complex control logic, multi‑rule designs     | No bit‑selects (`slice`) |
| `koika`           | Single‑rule designs with simple arithmetic, alignment invariants         | Deeply nested `ite`, multiple rules |
| `acl2`            | First‑order functional models, simple invariants                        | Same as Kōika; currently experimental |

---

## PERF: Proof tree Exploration with Reflective Feedback

**PERF** is a **test‑time proof search** engine that extends the linear repair loop with a **tree‑based beam search**. When a proof attempt fails, PERF:

1. Generates **multiple divergent repair attempts** from the failing script (using the LLM).  
2. **Verifies each attempt** in parallel (with optional tool‑grounding).  
3. **Scores candidates** using a **Pareto‑optimal front** across multiple dimensions (e.g., subgoal reduction, trace alignment, syntactic purity).  
4. **Selects a beam** of the best candidates and repeats the process.  

PERF is particularly effective when:

- The proof is hard and requires exploring several alternative strategies.
- A **counterexample trace** from model checking is available – PERF uses it to guide the search (`trace_alignment` dimension).
- You want to reduce the number of manual repair iterations.

**Recent improvements:**

- PERF can build a **destruct‑chain skeleton** as the root node when the obligation has a deeply nested `ite` (e.g., opcode dispatch chains). This gives the search a strong, structurally informed starting point.
- After PERF exhausts, the most promising candidate from the search is **automatically handed to the linear prover** for a final focused repair pass, instead of being discarded.
- A `min_beam_size` parameter prevents the beam from collapsing to a single node, preserving diversity.
- Light repair attempts per unique error signature are now configurable (`perf_light_repair_attempts`), making PERF’s repair more persistent and closer to the linear prover’s behaviour.
- Backtracking and reflection quality are now explicitly configurable (see below).

Before launching the full beam search, PERF attempts a fast **interactive skeleton proof** (structural induction + inversion) when `try_skeleton_first` is enabled (the default). This often succeeds immediately on simple safety properties. During the beam search, PERF also injects the actual Coq/ACL2 definitions into the LLM prompts, enabling more accurate proof generation.

### Enabling PERF

PERF can be enabled globally in `conf/config.yaml` under the `proof.perf` block, or per‑invocation with `--perf`:

```bash
./run.sh --verify examples/fifo/fifo.specir --perf
```

To disable PERF even if the config says otherwise, use `--no-perf`.

**Important**: PERF **disables the proof library cache** (`use_proof_library: false`). If both are enabled, the system raises a `ConfigurationError` to prevent silent bypass. You can either set `use_proof_library: false` in `config.yaml` or let the CLI override it.

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
| `min_beam_size` | Minimum nodes to keep in the beam to prevent collapse | `2` |
| `perf_light_repair_attempts` | Light repair attempts per unique error signature | `2` |

**Backtracking settings**

| Parameter | Description | Default |
|-----------|-------------|---------|
| `backtracking.enabled` | Enable stagnation‑based backtracking | `false` |
| `backtracking.stagnation_depth` | Consecutive non‑improving depths before backtrack | `2` |
| `backtracking.max_restarts` | Maximum number of backtrack operations | `3` |
| `backtracking.max_backtrack_depth` | How many depths to go back | `2` |
| `backtracking.restore_beam_size` | Beam size after backtracking | `3` |
| `backtracking.avoid_repeated_branches` | Exclude previously selected nodes when restoring | `true` |

**On‑demand backtracking triggers**

| Parameter | Description | Default |
|-----------|-------------|---------|
| `backtracking.on_demand.enabled` | Master switch for on‑demand backtracking | `false` |
| `backtracking.on_demand.force_every` | Trigger a backtrack every N depths (0 = off) | `0` |
| `backtracking.on_demand.time_limit` | Trigger a backtrack after N seconds (0 = off) | `0.0` |
| `backtracking.on_demand.max_same_error` | Trigger a backtrack after repeated identical errors | `5` |
| `backtracking.on_demand.skip_forced_regeneration` | Avoid forced regeneration for on‑demand backtracks | `true` |

> Note: `backtracking.on_demand.enabled` is the master switch. The individual `force_every`, `time_limit`, and `max_same_error` triggers are ignored unless `enabled` is `true`.  
> For designs where the same error repeats often, increasing `max_same_error` (e.g., to `15`) in `config.yaml` reduces trigger frequency.

**Reflection quality assessment**

| Parameter | Description | Default |
|-----------|-------------|---------|
| `reflection_quality_window` | Depths to wait before evaluating reflection quality | `2` |
| `min_reflection_quality` | Minimum reflection quality to accept a backtrack | `0.2` |
| `max_reflection_retries` | Retry limit for alternative backtrack depths | `2` |

You can override any of these via **environment variables** (see below) or **per‑obligation metadata** in the `.specir` file.

### Environment Variables

The following environment variables can be used to override PERF settings without editing the configuration file:

```bash
PERF_ENABLED=true|false
PERF_BEAM_SIZE=5
PERF_BRANCHES=6
PERF_DEPTH=4
PERF_DIMENSIONS="a,b,c"
PERF_PRIMARY_DIMENSION="a"
PERF_TEMPERATURE=0.5
PERF_MAX_WORKERS=8
PERF_TIMEOUT_NODE=600
PERF_TOURNAMENT_SIZE=3
PERF_ALWAYS_VERIFY=false
PERF_ON_DEMAND_BACKTRACK=true|false
PERF_REFLECTION_QUALITY_WINDOW=3
PERF_MIN_REFLECTION_QUALITY=0.15
PERF_MAX_REFLECTION_RETRIES=2
```

Example:

```bash
PERF_BEAM_SIZE=5 PERF_DEPTH=3 ./run.sh --verify examples/fifo/fifo.specir --perf
```

### PERF Statistics

To see detailed traversal statistics (nodes explored, depths reached, pruning, token usage, reflection quality), pass `--perf-stats`:

```bash
./run.sh --verify examples/fifo/fifo.specir --perf --perf-stats
```

The output will include a summary table with all key metrics, including backtrack counts, diversity usage, reflection quality history, and per‑depth breakdown.

### Integration with Model Checking

When PERF is used on an obligation that also has a model‑checking counterpart (or when a counterexample trace is available), the `trace_alignment` dimension is automatically activated. PERF uses the trace to:

- **Score** proof scripts that explicitly address the failing scenario (higher score).  
- **Guide** the LLM to generate repairs that target the root cause of the violation.

This closes the loop between bounded model checking (fast but incomplete) and theorem proving (complete but slow).

---

## Batch Processing and Structured Output

For running experiments over multiple designs, InterScope supports batch mode and structured JSON output.

```bash
# Batch compile all designs in a directory, output JSON
./run.sh --batch benchmarks/level1/ --compile --output-format json --report-file compile_results.json
```

Individual commands can also produce JSON output without batch mode:

```bash
./run.sh --compile examples/fifo/fifo.specir --output-format json
./run.sh --verify examples/fifo/fifo.specir --backend koika --output-format json
./run.sh --sim examples/fifo/fifo.specir --cycles 100 --output-format json
```

The JSON output for each command follows a standardised schema defined in `src/specir/utils/result_types.py`. Aggregated batch reports include summary statistics and can be exported to CSV as well.

---

## Evidence Registry Enhancements

The evidence registry (`specir query`) now supports additional sub‑commands for exporting and analyzing verification results:

```bash
# Export all evidence to JSON
./run.sh --query export results.json

# Show summary statistics
./run.sh --query stats

# Filter evidence by design and status
./run.sh --query filter --design fifo --status proved
```

The registry schema has been extended to record `design_name`, `iterations`, and `llm_used` for better provenance tracking.

---

## RTL Synthesis (Optional)

For RTL quality experiments, InterScope integrates Yosys synthesis:

```bash
# Generate RTL and run Yosys synthesis to obtain area/delay metrics
./run.sh --compile examples/fifo/fifo.specir --synthesize
./run.sh --sim examples/fifo/fifo.specir --synthesize
```

The synthesis results (area, cell count, delay) are included in the structured output and can be saved with `--report-file`.

---

## Examples

### FIFO Design (Kōika + ACL2 + Simulation)

```bash
cd examples/fifo
../../run.sh --compile fifo.specir
../../run.sh --verify fifo.specir --backend koika
../../run.sh --verify fifo.specir --backend acl2
../../run.sh --sim fifo.specir --cycles 100
../../run.sh --lift build/traces/fifo.vcd --spec fifo.specir
../../run.sh --check build/traces/lifted.yaml --spec fifo.specir
```

### Batch Compilation and Verification for a Directory

```bash
# Compile all designs in a directory
../../run.sh --batch benchmarks/level1/ --compile --output-format json

# Verify with PERF, disable Pareto pruning (ablation study)
../../run.sh --batch benchmarks/level1/ --verify --backend koika --perf --no-pareto --output-format json --report-file ablation_no_pareto.json
```

### Model Checking

```bash
./run.sh --verify examples/fifo/fifo.specir --backend model_checking
```

### Assertion Generation (standalone)

```bash
./run.sh --compile examples/fifo/fifo.specir --backend assert --assert-lang sva
./run.sh --compile examples/fifo/fifo.specir --backend assert --assert-lang vhdl
./run.sh --compile examples/fifo/fifo.specir --backend assert --assert-lang verilog_ovl
```

The generated assertion files are placed in `build/<design>/assertions/`.

The SVA backend emits **Yosys‑compatible procedural assertions** and uses **non‑ANSI style port declarations** to avoid syntax errors in SymbiYosys.

---

## Customising the Proof Library

You can add your own lemma proofs without modifying the core package. Simply edit **`src/lib/koika/assist.py`** and add a new entry to the `PROOF_LIBRARY` dictionary:

```python
PROOF_LIBRARY = {
    # ... existing entries ...
    "my_theorem_proved": """Proof.
  (* your Coq proof here *)
Qed.""",
}
```

The existing entries are **complete Coq proofs** (not skeletons) and are applied automatically when a theorem name matches. The prover will automatically pick up new entries the next time it runs. This makes it easy to maintain a personal library of proven properties for your own designs.

---

## License

This project is licensed under the **MIT License** – see the [LICENSE](LICENSE) file for details.
