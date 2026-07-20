# InterScope File Structure

```
interscope/
├── conf/                              # Configuration directory
│   ├── config.yaml                    # Main configuration (LLM keys, prover settings, simulation cycles, model‑checking parameters, etc.)
│   └── schemas/
│       └── specir_schema.yaml         # JSON Schema for `.specir` files (accepts version 0.1)
│
├── examples/                          # Runnable SpecIR designs (also used by integration tests)
│
├── src/                               # All Python source code
│   ├── lib/                           # User‑customisable libraries (on PYTHONPATH=src)
│   │   └── koika/
│   │       └── assist.py              # Proof library for Kōika/Coq theorems (users can add entries)
│   │
│   └── specir/                        # Main package
│       │
│       ├── cli/                       # Command‑line interface subcommands (entry points)
│       │   ├── compile.py             # `specir compile`: spec → Kōika/ACL2/assert; optional RTL generation & simulation
│       │   ├── verify.py              # `specir verify`: run proof obligations (theorem proving and model checking) on a design
│       │   ├── sim.py                 # `specir sim`: compile to RTL and run Verilator simulation (produces VCD)
│       │   ├── lift.py                # `specir lift`: VCD → abstract trace YAML
│       │   ├── check.py               # `specir check`: check properties against an abstract trace
│       │   └── query.py               # `specir query`: query evidence registry (SQLite)
│       │
│       ├── parser/                    # YAML → Abstract Syntax Tree (AST)
│       │   ├── ast.py                 # Dataclasses for all SpecIR constructs
│       │   ├── parser.py              # Loads YAML, builds AST, reports syntax errors
│       │   └── validator.py           # Validates a .specir dict against the JSON Schema (cached)
│       │
│       ├── dialects/                  # Intermediate representation dialects (MLIR‑inspired)
│       │   ├── spec_ir.py             # Spec dialect operations and SpecModule container
│       │   ├── assert_ir.py           # Unified assert dialect
│       │   ├── koika_ir.py            # Kōika dialect (rule, design, theorem)
│       │   ├── acl2_ir.py             # ACL2 dialect (defun, defthm, defun‑sk)
│       │   ├── rtl_ir.py              # RTL dialect – Verilog module, registers, wires, mapping
│       │   └── trace_ir.py            # Trace dialect – cycles, signals, annotations
│       │
│       ├── lowering/                  # Lowering passes (source → target dialects or code)
│       │   ├── ast_to_spec.py         # Canonical AST → SpecModule conversion
│       │   ├── spec_to_koika.py       # SpecModule → KoikaModule (reachability‑based Coq for verification)
│       │   ├── spec_to_acl2.py        # SpecModule → ACL2Module
│       │   ├── spec_to_assert.py      # SpecModule → unified assert dialect
│       │   ├── assert_to_sva.py       # assert IR → SystemVerilog SVA
│       │   ├── assert_to_vhdl.py      # assert IR → VHDL PSL
│       │   ├── assert_to_verilog_ovl.py # assert IR → Verilog OVL
│       │   └── koika_to_rtl.py        # SpecIR → Verilog synthesis via Kōika’s Coq DSL (handles parameterised types, skips unsupported ops, patches Verilog for inputs)
│       │
│       ├── lifting/                   # Lifting passes (simulation → abstract spec)
│       │   ├── vcd_to_trace.py        # VCD file → trace dialect
│       │   ├── trace_to_spec.py       # trace dialect + mapping → abstract trace YAML
│       │   └── llm_lifter.py          # Optional: LLM‑assisted lifting (placeholder)
│       │
│       ├── verification/              # Verification engines and proof orchestration
│       │   ├── property_checker.py    # Evaluates temporal properties on abstract traces
│       │   ├── model_checker.py       # Wrapper for external model checkers (SymbiYosys / sby) – generates .sby scripts, parses results, returns counterexample traces
│       │   ├── simulation.py          # High‑level simulation orchestrator; optionally generates assertion files alongside RTL
│       │   └── proof/                 # Theorem proving support
│       │       ├── proof.py           # Abstract base classes: ProofSkill, ProofResult
│       │       ├── proof_skill.py     # LLM‑driven proof orchestrator (now supports model‑checking engine via ModelCheckProver)
│       │       ├── koika/             # Kōika/Coq proof backend
│       │       │   ├── prover.py      # Interactive prover (rocq‑mcp + LLM)
│       │       │   ├── proof_gen.py   # One‑shot Coq proof generation (LLM)
│       │       │   └── repair.py      # Iterative repair of Coq proofs (LLM + rocq‑mcp)
│       │       └── acl2/              # ACL2 proof backend
│       │           ├── prover.py      # High‑level ACL2 prover
│       │           ├── proof_gen.py   # ACL2 proof generation (LLM)
│       │           └── repair.py      # Iterative repair of ACL2 proofs (LLM)
│       │
│       ├── backends/                  # Low‑level wrappers for external tools
│       │   ├── koika_compiler.py      # Kōika → Verilog: invokes external Kōika compiler (cuttlec) on an existing .ml file
│       │   ├── acl2_client.py         # ACL2 MCP client (background event loop)
│       │   ├── verilator_sim.py       # Verilator build & run: testbench generation, simulation, VCD collection
│       │   ├── llm_client.py          # LLM API client (OpenAI, Anthropic, Ollama)
│       │   └── rocq_client.py         # rocq‑mcp MCP client (JSON‑RPC, Coq sessions)
│       │
│       ├── evidence/                  # Evidence registry (proven theorems, counterexamples, traces, invariants)
│       │   ├── registry.py            # SQLite‑backed registry (CRUD, filtering, statistics); now includes convenience method add_counterexample for model checking
│       │   └── annotator.py           # Attaches evidence references to AST nodes
│       │
│       └── utils/                     # Utility modules
│           ├── expr.py                # S‑expression engine (parse, evaluate, type check)
│           ├── logger.py              # Structured logging (console + file)
│           └── config_loader.py       # Configuration loader with defaults, environment variable substitution
│
├── tests/                             # Unit and integration tests (pytest)
│   ├── unit/                          # Unit tests (fast, isolated)
│   │   ├── test_ast.py                # AST dataclass tests
│   │   ├── test_parser.py             # YAML parser tests
│   │   ├── test_dialects.py           # Dialect creation tests
│   │   ├── test_expr.py               # S‑expression engine tests
│   │   ├── test_ast_to_spec.py        # AST → SpecModule conversion tests
│   │   ├── test_lowering.py           # Lowering pass tests (spec→assert, assert→SVA/VHDL/OVL)
│   │   ├── test_spec_to_koika.py      # Spec→Kōika (verification model) lowering tests
│   │   ├── test_spec_to_acl2.py       # Spec→ACL2 lowering tests
│   │   ├── test_koika_compiler.py     # Kōika compiler backend tests (path resolution, compilation mocks)
│   │   ├── test_koika_to_rtl.py       # Kōika synthesis tests (Coq file generation, parameter resolution, mocked compilation)
│   │   ├── test_verilator_sim.py      # Verilator backend tests (testbench generation, error handling)
│   │   ├── test_simulation.py         # High‑level simulation orchestrator tests (now includes assertion generation)
│   │   ├── test_trace_lifting.py      # VCD → trace → abstract spec lifting tests
│   │   ├── test_property_checker.py   # Property checker tests
│   │   ├── test_evidence.py           # Evidence registry and annotator tests
│   │   ├── test_proof_koika.py        # Kōika prover and proof generation tests (mocked)
│   │   ├── test_proof.py              # ProofResult and ProofSkill base class tests
│   │   ├── test_model_checker.py      # Model‑checking wrapper tests (script generation, output parsing, end‑to‑end)
│   │   ├── test_verify.py             # Verify CLI tests (theorem proving, model checking, mixed obligations, reporting)
│   │   ├── test_acl2_client.py        # ACL2 MCP client tests
│   │   ├── test_acl2_prover.py        # ACL2 prover tests
│   │   ├── test_cli_sim.py            # CLI simulation subcommand tests
│   │   ├── test_proof_skill.py        # ProofSkill orchestrator tests (LLM-driven proof)
│   │   └── test_rocq_client.py        # rocq‑mcp client tests
│   └── integration/                   # End‑to‑end tests (require installed backends)
│       ├── fifo/
│       │   ├── fifo.specir            # FIFO specification
│       │   └── test_fifo.py           # FIFO integration test
│       ├── alu/
│       │   ├── alu.specir             # ALU specification
│       │   └── test_alu.py            # ALU integration test
│       └── counter/
│           ├── counter.specir         # Counter specification
│           └── test_counter.py        # Counter integration test
│
└── scripts/                           # Development utilities
```
