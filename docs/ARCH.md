```text
interscope/
├── conf/                              # Configuration directory
│   ├── config.yaml                    # Main configuration (LLM keys, prover settings, PERF, etc.)
│   └── schemas/
│       └── specir_schema.yaml         # JSON Schema for `.specir` files (version 0.1)
├── examples/                          # Runnable SpecIR designs (also used by integration tests)
├── src/                               # All Python source code
│   ├── lib/                           # User‑customisable libraries (on PYTHONPATH=src)
│   │   └── koika/
│   │       └── assist.py              # Proof library for Kōika/Coq theorems (users can add entries)
│   └── specir/                        # Main package
│       ├── cli/                       # Command‑line interface subcommands (entry points)
│       │   ├── main.py                # Central CLI entry point with batch mode, global options, config merging
│       │   ├── compile.py             # Compile a .specir to backends, returns CompilationReport, JSON output
│       │   ├── verify.py              # Run proof obligations, returns VerificationReport, PERF ablation flags
│       │   ├── sim.py                 # Simulate a design, returns SimulationReport, optional coverage
│       │   ├── lift.py                # `specir lift`: VCD → abstract trace YAML
│       │   ├── check.py               # `specir check`: check properties against an abstract trace
│       │   └── query.py               # Query evidence registry; added export, stats, filter sub‑commands
│       ├── parser/                    # YAML → Abstract Syntax Tree (AST)
│       │   ├── ast.py                 # Dataclasses for all SpecIR constructs; PERF fields on ProofObligation
│       │   ├── parser.py              # Loads YAML, builds AST, reports syntax errors; parses PERF overrides
│       │   └── validator.py           # Validates a .specir dict against the JSON Schema (cached)
│       ├── dialects/                  # Intermediate representation dialects (MLIR‑inspired)
│       │   ├── spec_ir.py             # Spec dialect operations and SpecModule container
│       │   ├── assert_ir.py           # Unified assert dialect
│       │   ├── koika_ir.py            # Kōika dialect (rule, design, theorem)
│       │   ├── acl2_ir.py             # ACL2 dialect (defun, defthm, defun‑sk)
│       │   ├── rtl_ir.py              # RTL dialect – Verilog module, registers, wires, mapping; PERF signal grouping
│       │   └── trace_ir.py            # Trace dialect – cycles, signals, annotations; PERF failing‑window extraction
│       ├── lowering/                  # Lowering passes (source → target dialects or code)
│       │   ├── ast_to_spec.py         # Canonical AST → SpecModule conversion
│       │   ├── split_rules.py         # Attribute‑driven monolithic rule splitting (opt‑in, pre‑lowering pass)
│       │   ├── spec_to_koika.py       # SpecModule → KoikaModule (reachability‑based Coq for verification)
│       │   ├── spec_to_acl2.py        # SpecModule → ACL2Module (functional model + theorems)
│       │   ├── spec_to_assert.py      # SpecModule → unified AssertModule
│       │   ├── assert_to_sva.py       # AssertModule → SystemVerilog SVA (Yosys‑compatible)
│       │   ├── assert_to_vhdl.py      # AssertModule → VHDL PSL
│       │   ├── assert_to_verilog_ovl.py # AssertModule → Verilog OVL
│       │   └── koika_to_rtl.py        # SpecIR → Verilog synthesis via Kōika's Coq DSL (parameterised types, input injection)
│       ├── lifting/                   # Lifting passes (simulation → abstract spec)
│       │   ├── vcd_to_trace.py        # VCD file → trace dialect
│       │   ├── trace_to_spec.py       # trace dialect + mapping → abstract trace YAML
│       │   └── llm_lifter.py          # Optional: LLM‑assisted lifting (placeholder)
│       ├── verification/              # Verification engines and proof orchestration
│       │   ├── property_checker.py    # Evaluates temporal properties on abstract traces
│       │   ├── model_checker.py       # Wrapper for SymbiYosys (sby), returns duration/details
│       │   ├── simulation.py          # High‑level simulation orchestrator; optional coverage, SimulationReport
│       │   ├── proof/                 # Theorem proving support
│       │   │   ├── proof.py           # Abstract ProofResult with iterations, duration, backend, metadata
│       │   │   ├── proof_skill.py     # LLM‑driven proof orchestrator; dispatches to Koika/ACL2/MC, PERF integration
│       │   │   ├── koika/             # Kōika/Coq proof backend
│       │   │   │   ├── prover.py      # Interactive prover (rocq‑mcp + LLM); returns ProofResult
│       │   │   │   ├── proof_gen.py   # LLM prompts for Coq proofs, tactic extraction, PERF multi‑variant generation
│       │   │   │   └── repair.py      # One‑shot repair of failed Coq proofs using LLM
│       │   │   └── acl2/              # ACL2 proof backend
│       │   │       ├── prover.py      # High‑level ACL2 prover with checkpoint/repair; returns ProofResult
│       │   │       ├── proof_gen.py   # ACL2 proof generation prompts, PERF variant generation
│       │   │       └── repair.py      # Iterative repair of ACL2 hints/defuns
│       │   └── perf/                  # PERF: Proof tree Exploration with Reflective Feedback
│       │       ├── perf_config.py     # Configuration dataclass, validation, loading from global/obligation metadata
│       │       ├── perf_evidence.py   # PERF‑specific evidence management (proofs, counterexamples, statistics)
│       │       ├── perf_parallel.py   # Thread‑pool evaluator for parallel candidate verification
│       │       ├── perf_scorer.py     # Multi‑dimensional scoring via tournament‑style LLM comparisons and Pareto optimality
│       │       ├── perf_stats.py      # Statistics collection and reporting (nodes, depths, tokens)
│       │       └── perf_traversal.py  # Core beam‑search engine with Pareto pruning and reflective feedback
│       ├── backends/                  # Low‑level wrappers for external tools
│       │   ├── koika_compiler.py      # Kōika compiler wrapper (cuttlec) for existing .ml files
│       │   ├── acl2_client.py         # ACL2 MCP client (background event loop, synchronous API)
│       │   ├── verilator_sim.py       # Verilator build & run; optional coverage collection flag
│       │   ├── llm_client.py          # Multi‑provider LLM client (OpenAI, Anthropic, Ollama, DeepSeek) with batch/structured
│       │   └── rocq_client.py         # rocq‑mcp MCP client (JSON‑RPC, Coq sessions, workspace resolution)
│       ├── evidence/                  # Evidence registry (proven theorems, counterexamples, traces, invariants)
│       │   ├── registry.py            # SQLite‑backed registry; new fields (design_name, iterations, llm_used),
│       │   │                          # export/stats/query methods
│       │   └── annotator.py           # Attaches evidence references to AST nodes
│       └── utils/                     # Utility modules
│           ├── expr.py                # S‑expression engine (parse, evaluate, type check)
│           ├── logger.py              # Structured logging (console + file, rotation)
│           ├── config_loader.py       # Configuration loading, deep merge, external config file, PERF env overrides
│           ├── result_types.py        # Standard dataclasses: CompilationReport, VerificationReport, SimulationReport,
│           │                          # BackendResult, ProofObligationResult, Status
│           ├── batch.py               # Batch processing: find_specir_files, run_batch with timeout and progress
│           ├── reporting.py           # Aggregation and export: JSON/CSV report generation for compilation,
│           │                          # verification, simulation
│           └── yosys_synth.py         # Yosys synthesis wrapper for area, delay, cell count extraction (RQ5)
├── tests/                             # Unit and integration tests (pytest)
│   ├── unit/                          # Unit tests (fast, isolated)
│   │   └── ... (existing test files)  # e.g., test_ast.py, test_parser.py, test_dialects.py, etc.
│   └── integration/                   # End‑to‑end tests (require installed backends)
│       └── ... (existing test dirs)   # e.g., fifo/, alu/, counter/
└── scripts/                           # Development utilities
    ├── vcd_to_trace.py                # VCD → trace dialect debug script; PERF extensions for trace filtering
    └── extract_mapping.py             # Extract SpecIR mapping from Verilog annotations; PERF‑specific fields
```