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

---

## Quick Installation

```bash
git clone https://github.com/ywci/interscope.git
cd interscope
./install.sh
```

Activate the environment:

```bash
source .venv/bin/activate
```

If you need the Kōika toolchain and your OCaml/Coq versions don’t match, run:

```bash
./install.sh --install-koika-switch
```

To skip external tools (for a minimal Python‑only setup):

```bash
INSTALL_EXTERNAL=false ./install.sh
```

The installer prints clear warnings if any tool could not be installed automatically; you can then follow the manual steps it provides.

---

## Configuration

Edit `conf/config.yaml` to set:

- LLM provider (OpenAI, Anthropic, Ollama) and API keys.
- Paths to external tools (auto‑detected by default).
- Prover‑specific settings (tactic hints, proof timeout, repair attempts).
- Model‑checking parameters (`bmc_max_depth`, `ic3_max_steps`, `formal_timeout`).
- Simulation settings (cycles, Verilator path).

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
