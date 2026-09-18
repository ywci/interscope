# Project Structure

```
interscope/
├── conf/                              # Configuration directory
│   ├── config.yaml                    # Main configuration (LLM keys, prover settings, PERF, etc.)
│   └── schemas/
│       ├── isir_schema.yaml           # JSON Schema for `.isir` input files (version 0.1)
│       └── trace_schema.yaml          # JSON Schema for abstract trace YAML (from `isir lift`)
├── docs/                              # Design and user documentation
│   ├── ARCH.md                        # Architecture overview
│   └── ISIR.md                        # ISIR language reference
├── examples/                          # Runnable ISIR designs (also used by integration tests)
├── scripts/                           # Development utilities
│   ├── extract_mapping.py             # Extract ISIR mapping from Verilog annotations; PERF‑specific fields
│   └── vcd_to_trace.py                # VCD → trace dialect debug script; PERF extensions for trace filtering
├── src/                               # All Python source code
│   ├── lib/                           # User‑customisable libraries (on PYTHONPATH=src)
│   │   └── koika/
│   │       └── assist.py              # Proof library for Kōika/Coq theorems (users can add entries)
│   └── isir/                          # Main package
│       ├── cli/                       # Command‑line interface subcommands (entry points)
│       │   ├── main.py                # Central CLI entry point with batch mode, global options, config merging
│       │   ├── compile.py             # Compile a .isir to backends, returns CompilationReport, JSON output
│       │   ├── verify.py              # Run proof obligations, returns VerificationReport, PERF ablation flags
│       │   ├── sim.py                 # Simulate a design, returns SimulationReport, optional coverage
│       │   ├── lift.py                # `isir lift`: VCD → abstract trace YAML
│       │   ├── check.py               # `isir check`: check properties against an abstract trace (schema‑validated)
│       │   ├── query.py               # Query evidence registry; export, stats, filter sub‑commands
│       │   └── validate_config.py     # Validate config.yaml for conflicts (PERF vs. use_proof_library)
│       ├── parser/                    # YAML → Abstract Syntax Tree (AST)
│       │   ├── ast.py                 # Dataclasses for all ISIR constructs; PERF fields on ProofObligation
│       │   ├── parser.py              # Loads YAML, builds AST, reports syntax errors; parses PERF overrides
│       │   └── validator.py           # Validates a .isir dict against conf/schemas/isir_schema.yaml (cached)
│       ├── dialects/                  # Intermediate representation dialects (MLIR‑inspired)
│       │   ├── isir.py                # ISIR dialect operations and ISIRModule container
│       │   ├── asserts.py             # Unified assert dialect
│       │   ├── koika.py               # Kōika dialect (rule, design, theorem)
│       │   ├── acl2.py                # ACL2 dialect (defun, defthm, defun‑sk)
│       │   ├── rtl.py                 # RTL dialect – Verilog module, registers, wires, mapping; PERF signal grouping
│       │   └── trace.py               # Trace dialect – cycles, signals, annotations; PERF failing‑window extraction
│       ├── lowering/                  # Lowering passes (source → target dialects or code)
│       │   ├── ast_to_isir.py         # Canonical AST → ISIRModule conversion
│       │   ├── split_rules.py         # Attribute‑driven monolithic rule splitting (opt‑in, pre‑lowering pass)
│       │   ├── isir_to_koika.py       # ISIRModule → KoikaModule (reachability‑based Coq for verification)
│       │   ├── isir_to_acl2.py        # ISIRModule → ACL2Module (functional model + theorems)
│       │   ├── isir_to_assert.py      # ISIRModule → unified AssertModule
│       │   ├── assert_to_sva.py       # AssertModule → SystemVerilog SVA (Yosys‑compatible)
│       │   ├── assert_to_vhdl.py      # AssertModule → VHDL PSL
│       │   ├── assert_to_verilog_ovl.py # AssertModule → Verilog OVL
│       │   └── koika_to_rtl.py        # ISIR → Verilog synthesis via Kōika's Coq DSL
│       ├── lifting/                   # Lifting passes (simulation → abstract spec)
│       │   ├── vcd_to_trace.py        # VCD file → trace dialect
│       │   └── trace_to_isir.py       # trace dialect + mapping → abstract trace YAML
│       ├── verification/              # Verification engines and proof orchestration
│       │   ├── property_checker.py    # Evaluates temporal properties on abstract traces
│       │   ├── model_checker.py       # Wrapper for SymbiYosys (sby), returns duration/details
│       │   ├── simulation.py          # High‑level simulation orchestrator; optional coverage, SimulationReport
│       │   ├── proof/                 # Theorem proving support
│       │   │   ├── proof.py           # Abstract ProofResult with iterations, duration, backend, metadata
│       │   │   ├── proof_skill.py     # LLM‑driven proof orchestrator; dispatches to Koika/ACL2/MC, PERF integration
│       │   │   ├── prelude_templates.py  # Standard prelude templates for each proof backend
│       │   │   ├── structural_validator.py # Structural validation of Coq proof scripts
│       │   │   ├── tactic_modernizer.py   # Tactic modernisation for Coq proof scripts
│       │   │   ├── domain_tactics.py      # Domain‑specific proof patterns and lemma hints
│       │   │   ├── proof_pattern_cache.py # Persistent cache for successful proofs and reusable tactic patterns
│       │   │   ├── koika/             # Kōika/Coq proof backend
│       │   │   │   ├── prover.py      # Interactive prover (rocq‑mcp + LLM); returns ProofResult
│       │   │   │   ├── proof_gen.py   # LLM prompts for Coq proofs, tactic extraction, PERF multi‑variant generation
│       │   │   │   ├── repair.py      # One‑shot repair of failed Coq proofs using LLM
│       │   │   │   ├── auto_patcher.py    # Deterministic patching of common Coq errors
│       │   │   │   └── template_gen.py    # Template‑based Coq proof variant generator
│       │   │   └── acl2/              # ACL2 proof backend
│       │   │       ├── prover.py      # High‑level ACL2 prover with checkpoint/repair; accepts initial_script for PERF
│       │   │       ├── proof_gen.py   # ACL2 proof generation prompts, PERF variant generation
│       │   │       ├── repair.py      # Iterative repair of ACL2 hints/defuns
│       │   │       └── template_gen.py    # Template‑based ACL2 proof variant generator
│       │   └── perf/                  # PERF: Proof tree Exploration with Reflective Feedback
│       │       ├── perf_config.py     # Configuration dataclass, validation, loading from global/obligation metadata
│       │       ├── perf_evidence.py   # PERF‑specific evidence management (proofs, counterexamples, statistics)
│       │       ├── perf_parallel.py   # Thread‑pool evaluator for parallel candidate verification
│       │       ├── perf_scorer.py     # Multi‑dimensional scoring via tournament‑style LLM comparisons and Pareto optimality
│       │       ├── perf_stats.py      # Statistics collection and reporting (nodes, depths, tokens)
│       │       ├── perf_analyzer.py   # Structural analysis of a Coq proof obligation for PERF
│       │       ├── perf_traversal.py  # Core beam‑search engine with Pareto pruning and reflective feedback
│       │       ├── error_history.py   # Dedicated PERF error‑history tracker for failure deduplication
│       │       └── perf_diagnostics.py # Human‑readable PERF failure diagnostics generation
│       ├── backends/                  # Low‑level wrappers for external tools
│       │   ├── koika_compiler.py      # Kōika compiler wrapper (cuttlec) for existing .ml files
│       │   ├── acl2_client.py         # ACL2 MCP client (background event loop, synchronous API); provides load_file()
│       │   ├── verilator_sim.py       # Verilator build & run; optional coverage collection flag
│       │   ├── llm_client.py          # Multi‑provider LLM client (OpenAI, Anthropic, Ollama, DeepSeek)
│       │   └── rocq_client.py         # rocq‑mcp MCP client (JSON‑RPC, Coq sessions, workspace resolution, coqc fallback)
│       ├── evidence/                  # Evidence registry (proven theorems, counterexamples, traces, invariants)
│       │   ├── registry.py            # SQLite‑backed registry; design_name, iterations, llm_used; export/stats/query
│       │   └── annotator.py           # Attaches evidence references to AST nodes
│       └── utils/                     # Utility modules
│           ├── expr.py                # S‑expression engine (parse, evaluate, type check)
│           ├── logger.py              # Structured logging (console + file, rotation)
│           ├── config_loader.py       # Configuration loading, deep merge, external config file, PERF env overrides
│           ├── result_types.py        # Standard dataclasses: CompilationReport, VerificationReport, SimulationReport,
│           │                          # BackendResult, ProofObligationResult, Status
│           ├── batch.py               # Batch processing: find_isir_files, run_batch with timeout and progress
│           ├── reporting.py           # Aggregation and export: JSON/CSV report generation
│           └── yosys_synth.py         # Yosys synthesis wrapper for area, delay, cell count extraction
└── tests/                             # Unit and integration tests (pytest)
    ├── integration/                   # End‑to‑end tests (require installed backends)
    └── unit/                          # Unit tests (fast, isolated)
```
