# SpecIR: Specification Intermediate Representation for Hardware Verification

## Version 0.1

---

## 1. Overview

SpecIR is a **structured intermediate representation** bridging natural‑language hardware design specifications and multiple verification engines (simulation, model checking, interactive theorem proving). It provides:

- A **human‑readable and machine‑processable** syntax (YAML 1.2).
- **Multi‑dialect layering** inspired by MLIR, implemented through internal dialects.
- Formal semantics for core constructs (states, rules, properties, directives).
- A **unified `assert` dialect** that lowers to SVA, VHDL PSL, or Verilog OVL.
- **Dual proof backends**: Kōika (Coq‑based, rule‑level reasoning) and ACL2 (first‑order, rewrite‑based reasoning).
- A **`trace` dialect** to capture simulation results (e.g., from Verilator) and **lift** them back to abstract SpecIR events.
- Built‑in support for **proof obligations, evidence binding, hierarchical design, and LLM‑driven iterative refinement**.
- **PERF (Proof tree Exploration with Reflective Feedback)** – a test‑time proof search engine that uses beam‑search, Pareto‑optimal pruning, and LLM reflection to tackle hard proof obligations, with explicit integration of model‑checking counterexamples.

---

## 2. Core Design Principles

1. **Semantic precision** – each SpecIR construct has a well‑defined meaning (operational or denotational).
2. **Traceability** – every element can be linked to verification artifacts (counterexamples, invariants, lemmas, simulation traces).
3. **Dialect layering** – lowering is explicit and verifiable; lifting (trace → spec) closes the verification loop.
4. **Unified assertion model** – a single `assert` dialect captures verification intent independent of target RTL language.
5. **Multi‑backend proofs** – support both Kōika/Coq (higher‑order, interactive) and ACL2 (first‑order, highly automated).
6. **LLM friendliness** – supports partial specifications, confidence annotations, and iterative repair feedback.
7. **Practicality** – includes clock/reset, hierarchy, and directives for real hardware; integrates with Verilator simulation.

---

## 3. Concrete Syntax

SpecIR uses **YAML 1.2** with a strictly defined subset (no implicit booleans, no flow style except for short sequences). A JSON schema is provided for validation.

### 3.1 Top‑Level Structure

```yaml
specir_version: "0.1"
module:
  name: <identifier>
  version: <string>
  parameters:                        # optional parametric design
    - name: <identifier>
      type: int | bit | string
      default: <value>
  clocks:                            # clock definitions
    - name: <identifier>
      period: <string>               # e.g., "10ns" (optional)
      edge: posedge | negedge
  resets:                            # reset definitions
    - name: <identifier>
      polarity: active_high | active_low
      async: true | false
      affects: [<state_name>, ...] | "all"
  inputs: [...]                      # list of Interface
  outputs: [...]                     # list of Interface
  types: [...]                       # user-defined types (enum, struct)
  components: [...]                  # hierarchical instantiation
  state: [...]                       # list of State
  rules: [...]                       # list of Rule
  directives: [...]                  # assume/assert/cover directives
  properties: [...]                  # temporal properties
  fairness: [...]                    # fairness constraints (optional)
  proof_obligations: [...]           # list of ProofObligation
  metadata: {...}                    # engine-specific hints (optional)
```

### 3.2 Core Data Types

| Type            | Syntax in YAML                          | Description                         |
|-----------------|-----------------------------------------|-------------------------------------|
| `bits(n)`       | `"bits<8>"`                             | bit vector of width n               |
| `int`           | `"int"`                                 | mathematical integer (unbounded)    |
| `bool`          | `"bool"`                                | boolean                             |
| `enum`          | `{ type: "enum", values: [A, B], encoding: "bits<1>" }` | enumerated type |
| `struct`        | `{ type: "struct", fields: { f1: "bits<8>", f2: "bool" } }` | record |
| `array(T,n)`    | `{ type: "array", elem: T, size: n }`   | fixed‑size array                    |
| `memory(T, depth)` | `{ type: "memory", elem: T, depth: d }` | random‑access memory            |

### 3.3 State Declaration

```yaml
- name: <identifier>
  kind: register | memory | wire
  type: <Type>                           # basic or user-defined
  initial: <value>                       # optional
  attributes: [stable, volatile, shadow]
  evidence: <EvidenceRef>                # optional link
```

### 3.4 Interface Declaration

```yaml
- name: <identifier>
  direction: input | output | inout
  type: <Type>
  protocol: ready_valid | handshake | fixed_cycle | none
```

### 3.5 Expressions

Expressions are represented as **nested S‑expressions** for unambiguity.

#### Expression Grammar

```
Expr ::= <literal>
       | <identifier>
       | (op op_name <Expr>*)               # unary/binary operator
       | (ite <Expr> <Expr> <Expr>)         # if‑then‑else
       | (read <state_name>)                # read register/memory
       | (write <state_name> <Expr>)        # write action
       | (mem_read <memory_name> <address>)
       | (mem_write <memory_name> <address> <data>)
```

**Operators**: `and`, `or`, `not`, `eq`, `neq`, `gt`, `lt`, `gte`, `lte`, `add`, `sub`, `mul`, `div`, `mod`, `concat`, `(slice high low)`.

> **Note**: Temporal operators (`next`, `prev`, `rose`, `fell`, `stable`) are **only allowed within property expressions** (see Section 3.7) and not inside rule conditions/actions.

Example:
```yaml
condition: (and (eq (read head) (read tail)) (not (read empty)))
```

Implementations may choose to normalise large hexadecimal literals (e.g., `0xFFFF`) to their decimal equivalents during lowering.

### 3.6 Rule Definition

```yaml
- name: <identifier>
  condition: <Expr>                         # optional (default true)
  action:                                   # list of actions
    - (write <state> <Expr>)
    - (mem_write <memory> <addr> <data>)
  priority: <int>                           # optional, higher = earlier
  attributes: [atomic, speculative, commutative, split]
  evidence: <EvidenceRef>
```

**Semantics**: A rule fires in a cycle iff its `condition` evaluates to true under the current state. Its `action` updates state variables atomically; concurrent rule firing follows the `schedule` (default: all enabled rules fire in parallel if no conflicts).

The **`split` attribute** indicates that the rule should be automatically decomposed into one rule per branch of its top‑level `ite` chain (via the `split_rules` pre‑lowering pass). This simplifies induction proofs for opcode‑style designs where a single rule uses a deeply nested `ite` to select among many operations.

### 3.7 Property Definition (Temporal)

```yaml
- name: <identifier>
  kind: safety | liveness | invariant
  expression:                              # temporal logic expression
    kind: always | eventually | until
    operand: <Expr>                        # for always/eventually
    left: <Expr>                           # for until
    right: <Expr>
    bound: <int>                           # optional, for bounded eventually/until
  assumes: [<Expr>]                        # environment assumptions (optional)
  guarantees: [<Expr>]                     # what the design guarantees
  proof_status: unproved | proved | counterexample
  evidence: <EvidenceRef>
```

**Temporal operators allowed in `operand` or `left`/`right`**:
- `(next <Expr>)` – value in the next cycle.
- `(prev <Expr>)` – value in the previous cycle.
- `(rose <Expr>)` – rising edge (current true, previous false).
- `(fell <Expr>)` – falling edge.
- `(stable <Expr>)` – value unchanged from previous cycle.

**Semantics**: Properties are interpreted over traces of states (one per cycle). The subset of LTL is:
- `always φ` : φ holds in every cycle.
- `eventually φ` : φ holds in some future cycle; if `bound` given, within that many cycles.
- `φ until ψ` : φ holds until ψ holds (ψ must eventually hold); optional bound.

### 3.8 Verification Directives (Assume/Assert/Cover)

For simulation, model checking, and proof.

```yaml
- type: assume
  name: <identifier>
  expression: <Expr>                       # constraint on inputs or state
  clock: <clock_name>                      # optional
- type: assert
  name: <identifier>
  expression: <Expr>                       # check that holds in all cycles
  severity: error | warning
- type: cover
  name: <identifier>
  expression: <Expr>                       # reachability target
```

In theorem‑prover backends, top‑level `assume` directives are translated into global `Axiom` declarations that constrain the environment for all subsequent proofs.  Per‑property assumptions are embedded directly into the respective theorem statements.

### 3.9 Schedule (Concurrency Control)

```yaml
kind: parallel | sequential | conflict_free
rule_order: [<rule_name>, ...]               # for sequential/priority
conflict_sets:                               # mutual exclusion groups
  - [<rule_name>, <rule_name>]
```

**Semantics**:
- `parallel` : all enabled rules fire simultaneously (default, assumes no conflicting writes).
- `sequential` : rules execute in the given order within one cycle (writes from earlier visible to later).
- `conflict_free` : at most one rule from each conflict set may fire per cycle; choice is non‑deterministic.

### 3.10 Fairness Constraints (Optional)

```yaml
- name: <identifier>
  type: weak | strong
  condition: <Expr>                         # e.g., (eventually granted)
```

### 3.11 Hierarchical Instantiation

```yaml
- name: <instance_name>
  module: <module_name>                     # reference to another SpecIR module
  parameters: { <param_name>: <value> }
  port_map:
    <formal_port>: <actual_signal_or_state>
  evidence: <EvidenceRef>                   # optional
```

### 3.12 Proof Obligation

A **first‑class** link between a property and its verification artifacts, supporting **multiple theorem proving backends** (Kōika/Coq and ACL2).

```yaml
- property: <property_name>
  status: unproved | proved | disproved | inconclusive
  engine: theorem_proving | model_checking | simulation
  backend: kōika | acl2            # selects the proof system
  artifact:                                # optional
    type: coq_theorem | acl2_theorem | invariant | counterexample_trace
    ref: <string>                          # path / identifier (see EvidenceRef)
  assumes: [<Expr>]                        # additional assumptions for this proof
  guarantees: [<Expr>]                     # additional guarantees
  metadata:                                # proof guidance
    # For Kōika (Coq)
    coq_tactic: "induction head; simpl; auto."
    coq_lemma: "fifo_invariants.v"
    # For ACL2
    acl2_hints: ((:rewrite defun-sk) (:induct tail))
    acl2_rule_classes: (:rewrite :linear)
    # Interactive prover tuning (Kōika backend)
    max_consecutive_failures: 10   # how many failed tactics before giving up
    max_steps: 80                  # maximum tactic steps attempted
    pre_simplify: true             # apply `simpl` before calling the LLM
    invariant_mining: true         # try auto‑generated lemmas first
  confidence: 0.0 .. 1.0                   # if LLM‑generated
  feedback:                                # iterative repair info
    - iteration: <int>
      error: <string>
      resolution: <string>
```

When `backend: kōika`, the lowering pass (`spec → kōika`) generates a Coq theorem and a proof skeleton. When `backend: acl2`, it generates an ACL2 `defthm` and supporting `defun-sk` or `defchoose` forms.

**PERF (Proof tree Exploration with Reflective Feedback)** can be enabled globally or per‑obligation.  
When PERF is active, the proof search is guided by a tree‑based beam search with multi‑dimensional scoring.  
Per‑obligation overrides are placed in `metadata.perf`:

```yaml
- property: <property_name>
  …
  metadata:
    # … (existing fields) …
    perf:
      beam_size: 5               # number of proof strategies to keep per depth (B)
      branches_per_node: 4       # divergent repair attempts per failed proof (N)
      depth_limit: 3             # maximum refinement iterations (L)
      dimensions:                # Pareto dimensions for scoring
        - subgoal_reduction
        - trace_alignment
        - syntactic_purity
      primary_dimension: "subgoal_reduction"
      generation_temperature: 0.4
      trace_alignment_weight: 0.6
```

All PERF settings are optional; missing values fall back to the global configuration.

### 3.13 Evidence Reference Format

```yaml
evidence_ref:
  type: uri | local_id
  value: "file:///path/to/artifact" | "#local_id"
```

### 3.14 Metadata (Engine‑Specific Hints)

```yaml
metadata:
  engine: ic3 | bmc | kōika | acl2
  options:
    max_depth: 100
    invariant_template: "full -> head != tail"
  # Optional fields for design classification
  design_category: "fifo"          # free‑form string (e.g., "alu", "fifo", "riscv")
  design_level: 2                  # integer 1–4 indicating complexity
  expected_properties:             # list of property names expected to be provable
    - "fifo_no_overflow"
    - "fifo_no_underflow"
```

**Description**:
- `engine` and `options` are the existing fields for engine‑specific parameters.
- `design_category` is an optional free‑form string that classifies the design (e.g., `"fifo"`, `"alu"`). It may be used to group results during batch evaluation.
- `design_level` is an optional integer (1–4) that indicates the design’s complexity level. It has no impact on verification semantics.
- `expected_properties` is an optional list of property names that are expected to be provable for the design. This can be used to compute verification success rates in automated benchmarks.

All these fields are optional; when absent, the design is treated as uncategorised. The schema (`conf/schemas/specir_schema.yaml`) has been updated to accept them.

---

## 4. Dialect‑Based Layering

SpecIR lowering uses **six internal dialects**, each modelled on the MLIR concept of operations and lowering passes. The `proof` dialect has been **removed** – all proof obligations are lowered directly to the Kōika or ACL2 backends.

| Dialect | Purpose | Example Ops |
|---------|---------|--------------|
| `spec`  | Original specification | `spec.state`, `spec.rule`, `spec.property` |
| `assert`| **Unified** assertions (SVA, VHDL PSL, Verilog OVL) | `assert.always`, `assert.sequence`, `assert.cover` |
| `kōika` | Kōika design + Coq proofs | `kōika.rule`, `kōika.design`, `kōika.theorem` |
| `acl2`  | ACL2 functional model + theorems | `acl2.defun`, `acl2.defthm`, `acl2.defun-sk` |
| `rtl`   | Trusted RTL (Kōika compiled) | `rtl.module`, `rtl.reg` |
| `trace` | Simulation/counterexample traces (VCD, etc.) | `trace.cycle`, `trace.signal`, `trace.annotation` |

The `spec` dialect module container additionally holds `types`, `components`, and `fairness` lists that mirror the top‑level YAML structure.

### 4.1 Lowering and Lifting Passes (Definitive)

**Lowering (design → implementation)**:
1. **`spec → kōika`** : Translate state, rules, schedule, and directives into Kōika definitions and Coq lemmas/theorems.
2. **`spec → acl2`** : Generate ACL2 functional model (if needed) and proof obligations as `defthm` forms.
3. **`spec → assert`** : Convert properties and directives into the unified `assert` dialect (language‑agnostic).
4. **`assert → sva`** : Lower unified assertions to SystemVerilog SVA.
5. **`assert → vhdl_psl`** : Lower unified assertions to VHDL‑2008 PSL.
6. **`assert → verilog_ovl`** : Lower boolean `assert.always` to Verilog OVL macro calls; reject unsupported temporal constructs.
7. **`kōika → rtl`** : Kōika’s verified compiler generates RTL. This pass also emits **source mapping** (RTL signal → SpecIR element) as a separate annotation file.

**Lifting (simulation back to specification)**:
8. **`vcd → trace`** : Convert a Value Change Dump (VCD) file from Verilator (or any simulator) into the `trace` dialect.
9. **`trace → spec`** : Using source mapping, reconstruct abstract state updates, rule firings, and property evaluations from the low‑level `trace` dialect. Output a SpecIR‑compatible trace (YAML) that can be checked against original properties.

Each lowering pass must preserve the semantics defined in Section 5. Lifting is heuristic but aims to be semantics‑preserving up to mapping completeness.

---

## 5. Formal Semantics

A full denotational semantics is out of scope here, but we define the core interpretation:

- **State** : A mapping from state names to values (bit vectors, integers, enums).
- **Rule** : A relation `(state, input) → (state', output)`.
- **Design** : A set of rules with a scheduler defining the next‑state function.
- **Property** : A temporal logic formula evaluated on the infinite trace produced by the design under all possible inputs (assumptions constrain inputs).
- **Directive**: `assume` restricts input space; `assert` must hold for all traces satisfying assumptions; `cover` checks reachability.

**Semantic Preservation**: Lowering from `spec` to `kōika` or `acl2` or `assert` is correct if for every design satisfying the `spec` semantics, the lowered artifact satisfies the corresponding target semantics (e.g., Kōika simulation matches, ACL2 model satisfies the theorem, SVA assertions hold).

**Lifting Correctness**: The `trace → spec` pass is correct if the lifted abstract trace, when simulated under the original SpecIR semantics, produces the same sequence of abstract state updates as the concrete RTL simulation, modulo the mapping provided.

---

## 6. Evidence Binding and Traceability

Every SpecIR element may contain an `evidence` field with a list of references:

```yaml
evidence:
  - type: counterexample_trace
    ref: { type: uri, value: "trace_123.vcd" }
    engine: BMC
    status: active
  - type: inductive_invariant
    ref: { type: local_id, value: "lemma_fifo_no_overflow" }
    engine: IC3
  - type: coq_theorem
    ref: { type: uri, value: "file://proofs/fifo_proofs.v#no_overflow" }
  - type: acl2_theorem
    ref: { type: uri, value: "file://proofs/fifo.lisp#no-overflow" }
  - type: simulation_trace
    ref: { type: uri, value: "file://sim/fifo.vcd" }
```

A global evidence registry maps each `ref` to the actual artifact.

---

## 7. LLM Integration Features

SpecIR includes explicit constructs to support LLM‑based translation and iterative repair.

### 7.1 Candidate and Confidence Annotations

Any field can be wrapped as:

```yaml
_candidate:
  value: <original_value>
  confidence: 0.85
  source: "LLM:gpt-4"
  alternatives:
    - value: <alternative1>
      confidence: 0.10
    - value: <alternative2>
      confidence: 0.05
```

### 7.2 Feedback Recording

The `feedback` field (under `ProofObligation` or top‑level) stores past verification attempts:

```yaml
feedback:
  - timestamp: "2026-06-05T10:00:00Z"
    engine: "kōika_coq"
    error: "Type mismatch: expected bits<8>, got bits<32>"
    resolution: "Changed state width to 32"
    iteration: 3
```

### 7.3 Ambiguity Representation

For underspecified properties, use `one_of`:

```yaml
property:
  name: "cache_coherence"
  one_of:
    - expression: (always (eq (read cache_line) (read memory)))
    - expression: (eventually (eq (read cache_line) (read memory)))
  resolution: "user" | "verification"
```

### 7.4 PERF: Proof tree Exploration with Reflective Feedback

PERF is a **test‑time proof search** engine that extends the linear repair loop with a **tree‑based beam search**.  
When a proof attempt fails, PERF:

1. Generates **multiple divergent repair attempts** from the failing script (using the LLM).  
2. **Verifies each attempt** in parallel (with optional tool‑grounding).  
3. **Scores candidates** using a **Pareto‑optimal front** across multiple dimensions (e.g., subgoal reduction, trace alignment, syntactic purity).  
4. **Selects a beam** of the best candidates and repeats the process.

PERF is particularly effective when:

- The proof is hard and requires exploring several alternative strategies.
- A **counterexample trace** from model checking is available – PERF uses it to guide the search (`trace_alignment` dimension).
- You want to reduce the number of manual repair iterations.

PERF is controlled through the configuration file, environment variables, and per‑obligation metadata (Section 3.12).  It is fully integrated with the Kōika/Coq backend and can be invoked via the CLI.

---

## 8. Mapping from SpecIR to Kōika Dialect

The following table defines the **canonical lowering** from SpecIR constructs to Kōika (Coq‑embedded DSL). This mapping is used in the `spec → kōika` lowering pass. Proof obligations are lowered to Coq lemmas/theorems within the same dialect.

| SpecIR Construct | Kōika Target | Notes |
|----------------|--------------|-------|
| `state` (register) | entry in indexed register file (e.g., `Inductive reg_idx := ...`) | Each register becomes a separate index; Kōika’s `read`/`write` use the index. |
| `state` (memory) | separate array variable (e.g., `Definition mem := array (bits 32) 8`) | Memories are not part of the register file; array reads/writes use `readₐ`/`writeₐ`. |
| `rule` with `condition` + `action` | `Definition rule_name : rule := {{ ... }}` | Condition mapped to Kōika `bool` expression; actions become sequential `;;` compositions. |
| `schedule` (`sequential`) | A single composed `step` constructor that threads rules in order using `let` bindings | The state after the first rule is fed into the second, etc., modelling sequential execution in one cycle. |
| `schedule` (`conflict_free`) | `choose` combinator or manual sequentialisation | `choose` selects one rule from a conflict set; if unavailable, encode as a priority‑based scheduler. |
| `property` (safety, liveness, invariant) | Coq lemma/theorem with `reachable` predicate and appropriate temporal encoding | Safety: `forall st, reachable st -> (property st)`. Liveness: encoded via ghost counters or co‑induction. |
| `directive` (`assume`) (top‑level) | Coq `Axiom` declaration | Becomes a global hypothesis usable in all proofs. |
| `directive` (`assume`) (per‑property) | Precondition in lemmas | Used as an additional hypothesis in the theorem statement. |
| `directive` (`assert`) | Coq lemma (same as safety property) | Treated as a proof obligation. |
| `directive` (`cover`) | Not directly supported; encode as existence lemma | Prove `exists st, reachable st /\ cover_condition st`. |
| `proof_obligation` (backend=kōika) | Coq theorem with optional proof script | Lowered to `Theorem ... Proof. ... Qed.` or `Admitted.` |
| `evidence` ref | Metadata comment + global registry | Stored as Coq `(*# evidence ... *)` attribute or external mapping file. |
| `clock`/`reset` | Implicit in Kōika’s cycle semantics; resets become initial register values | Kōika assumes a single clock; resets are modelled by initial state. |
| `enum` type | Coq `Inductive` type | Example: `Inductive StateType := IDLE | SEND | WAIT`. |
| `struct` type | Coq `Record` or tuple | Flattened into register file entries as needed. |
| `component` instantiation | Not natively supported; inline or use Coq module system | May require flattening or separate compilation. |
| `fairness` constraint | Encoded as a separate Coq assumption in liveness proofs | `WeakFairness (eventually granted)`. |

---

## 9. Mapping from SpecIR to ACL2 Dialect

The `acl2` dialect represents ACL2 functional models and theorems. Lowering from SpecIR to ACL2 is used for backends that prefer first‑order, rewrite‑based reasoning.

| SpecIR Construct | ACL2 Target | Notes |
|----------------|-------------|-------|
| `state` (register) | ACL2 variable or `st` field in a structure | Typically represented as a field in a `defstobj` or a record. |
| `state` (memory) | ACL2 array (`defstobj` field with `:type (array ...)`) | Efficient reasoning requires `defstobj`. |
| `rule` (condition + action) | ACL2 transition function (e.g., `(defun next-state (st inputs) ...)`) | The rule becomes a conditional update. |
| `schedule` | Encoded in transition function using `cond` or `case` | Conflict‑free scheduling becomes a `cond` with priority. |
| `property` (safety) | `defthm` with implication | Example: `(defthm no-overflow (implies (full st) (not (enqueue st))))`. |
| `property` (liveness) | Encoded as `defun-sk` (exists) or `defchoose` | Typically requires well‑foundedness measure. |
| `directive` (`assume`) | `defthm` with hypothesis or `encapsulate` | Can be captured as a constraint. |
| `directive` (`assert`) | Same as safety property. | |
| `directive` (`cover`) | `defthm` asserting existence of a state satisfying condition | `(exists st (cover-condition st))`. |
| `proof_obligation` (backend=acl2) | `defthm` with optional hints (`:hints (("Goal" :induct t)))` | Generated with ACL2 syntax. |
| `evidence` ref | ACL2 comments + external registry | `; Evidence: file://...` |
| `enum` type | ACL2 `defenum` or explicit constants | `(defenum state-type (IDLE SEND WAIT))`. |
| `clock`/`reset` | Included in transition function and initial state predicate | Reset is an initial state condition. |

### Example ACL2 Output (FIFO no_overflow)

```lisp
(defthm no-overflow
  (implies (full st)
           (not (enqueue st)))
  :hints (("Goal" :induct (run st n))))
```

---

## 10. Unified Assert Dialect and Lowering to RTL Languages

The `assert` dialect is **language‑agnostic**. It captures verification intent without committing to SystemVerilog, VHDL, or Verilog. Lowering passes translate this unified IR to concrete assertion languages.

### 10.1 Unified Assert Dialect Operations

| Operation | Description | Example (in MLIR‑like syntax) |
|-----------|-------------|-------------------------------|
| `assert.always` | Boolean invariant checked every cycle | `assert.always (not (full and empty))` |
| `assert.sequence` | Temporal sequence of events | `assert.sequence { req; (##2 grant) }` |
| `assert.property` | Temporal property (always, eventually, until) with optional bound | `assert.property { always (req -> eventually grant) }` |
| `assert.assume` | Environment constraint | `assert.assume { always (not (enq and deq)) }` |
| `assert.cover` | Reachability target | `assert.cover { full }` |
| `assert.clock` | Declare clock for following assertions | `assert.clock @posedge clk` |
| `assert.reset` | Declare reset condition | `assert.reset (not rst_n)` |

### 10.2 Lowering from Unified Assert to Target Languages

| Unified Assert | SVA (SystemVerilog) | VHDL PSL | Verilog (via OVL) | Notes |
|----------------|----------------------|----------|-------------------|-------|
| `assert.always (bool)` | `assert property (@(posedge clk) bool);` | `assert always bool;` | `ovl_assert_always #(…)` macro | SVA requires clock; VHDL uses default clock; OVL only for boolean |
| `assert.sequence {…}` | `sequence … endsequence` | `sequence … endsequence;` | Not supported | OVL lacks sequences |
| `assert.property { always φ }` | `assert property (@(posedge clk) φ);` | `assert always φ;` | Not supported (use SVA instead) | |
| `assert.property { eventually φ }` | `assert property (##[0:$] φ);` | `assert always (req -> eventually! grant);` | Not supported | |
| `assert.assume` | `assume property (…);` | `assume always …;` | Not supported | |
| `assert.cover` | `cover property (…);` | `cover property (…);` | `ovl_cover (clk, reset, cond);` | OVL cover only for boolean |
| `assert.clock` | `@(posedge clk)` | `default clock is …;` | Ignored (implicit clock) | |
| `assert.reset` | `disable iff (reset)` | Inline in property (e.g., `reset -> …`) | Passed to OVL module | |

### 10.3 Example: FIFO Assertions in Unified Assert Dialect

**Unified `assert` IR**:

```mlir
assert.clock @posedge clk
assert.reset (!rst_n)

assert.assume { always (not (enqueue and dequeue)) }

assert.property { always (full -> not enqueue) }
assert.property { always ((head == tail) -> not dequeue) }

assert.cover { full }
```

**Lowered outputs**:

- **SVA**:
  ```systemverilog
  assume property (@(posedge clk) disable iff (!rst_n) not (enqueue && dequeue));
  assert property (@(posedge clk) disable iff (!rst_n) full |-> !enqueue);
  assert property (@(posedge clk) disable iff (!rst_n) (head == tail) |-> !dequeue);
  cover property (@(posedge clk) full);
  ```

- **VHDL PSL**:
  ```vhdl
  -- default clock is clk’event and clk = ‘1’;
  assume always (not (enqueue and dequeue));
  assert always full -> not enqueue;
  assert always (head = tail) -> not dequeue;
  cover property (full);
  ```

- **Verilog OVL** (only boolean assertions are supported; temporal ones would be rejected or require manual SVA wrapper):
  ```verilog
  ovl_assert_always #(1,0,"no_over") u0 (clk, rst_n, !(full && enqueue));
  ovl_assert_always #(1,0,"no_under") u1 (clk, rst_n, !((head==tail) && dequeue));
  ovl_cover u2 (clk, rst_n, full);
  ```

---

## 11. Trace Dialect and Lifting from Simulation

The `trace` dialect captures cycle‑by‑cycle signal values from simulation (e.g., Verilator VCD) and supports **lifting** back to abstract SpecIR events.

### 11.1 Trace Dialect Operations

| Operation | Description | Example |
|-----------|-------------|---------|
| `trace.module` | Container for a simulation trace | `trace.module @fifo_sim` |
| `trace.clock` | Defines the clock period and edge | `trace.clock @clk period=10ns` |
| `trace.signal` | Declares a signal (RTL wire/reg) | `trace.signal @full` |
| `trace.cycle` | A time step (typically one clock cycle) | `trace.cycle 1` |
| `trace.value` | Value of a signal in a cycle | `trace.value @full = 0b0` |
| `trace.annotation` | Mapping from an RTL signal to a SpecIR element | `trace.annotation @full spec_ref = "module.state[name=full]"` |

The `trace` dialect can be serialized in a compact binary format (e.g., Protobuf) for large traces, or in YAML for small tests.

### 11.2 Source Mapping from Kōika → RTL → Trace

When the `kōika → rtl` lowering pass generates Verilog, it also emits a **mapping file** (JSON) that records for each RTL signal:

- The original SpecIR state, rule, or internal signal name.
- The kind of SpecIR element (register, rule condition, rule action, etc.).
- The expression that produced the signal (if combinational).

Example mapping entry:
```json
{
  "rtl_signal": "fifo_top.do_enqueue_cond",
  "specir_ref": "module.rules[name=do_enqueue].condition",
  "kind": "rule_condition"
}
```

This mapping is embedded in the Verilog as `//@specir` comments or stored separately.

### 11.3 Lifting Pass: `trace → spec`

The lifting pass reconstructs an abstract execution trace from the concrete `trace` dialect and the mapping.

**Algorithm**:
1. Read the `trace` module and the mapping database.
2. For each cycle:
   - For each registered `state` signal, translate its bit value to the SpecIR type (e.g., `bits<3>` → integer).
   - For each rule condition signal, determine if the rule fired (`condition == true` and no conflict prevented it).
   - For each rule action, infer that the rule’s effect produced the observed state changes (optional verification).
3. Produce a **SpecIR trace** in YAML format:

```yaml
trace:
  cycles:
    - cycle: 0
      state: { head: 0, tail: 0, full: false }
      fired_rules: [do_enqueue]
      inputs: { enqueue: true, data_in: 0x1234 }
    - cycle: 1
      state: { head: 1, tail: 0, full: false }
      fired_rules: []
      inputs: { enqueue: false, dequeue: false }
```

4. Optionally, the lifted trace can be **checked against the original properties** using the same property evaluation engine as used for simulation.

### 11.4 Integration with Verilator

Verilator is a popular Verilog simulator that can produce VCD traces. The typical workflow:

```bash
# 1. Generate RTL from SpecIR via Kōika
specir compile fifo.specir --backend kōika --out rtl/fifo.v --mapping fifo.mapping.json

# 2. Build Verilator simulation with tracing enabled
verilator --cc --trace rtl/fifo.v --top-module fifo
make -C obj_dir -f Vfifo.mk

# 3. Run simulation, produce VCD
./obj_dir/Vfifo +trace +vcd=fifo.vcd

# 4. Convert VCD to trace dialect
specir import vcd --input fifo.vcd --mapping fifo.mapping.json --output fifo.trace.mlir

# 5. Lift to SpecIR abstract trace
specir lift --trace fifo.trace.mlir --mapping fifo.mapping.json --output fifo_trace.yaml

# 6. Check properties against the lifted trace
specir check --trace fifo_trace.yaml --spec fifo.specir
```

If a property is violated, the lifted trace shows the exact abstract cycle and state that caused the violation, making debugging far easier than inspecting raw VCD.

### 11.5 Using LLM for Heuristic Lifting

When mapping information is incomplete (e.g., combinational logic not annotated), the lifting pass can invoke an LLM to **infer** higher‑level events from signal patterns. The LLM is given:

- A description of the SpecIR design (states, rules).
- A snippet of the `trace` dialect (several cycles of relevant signals).
- The expected output format (SpecIR trace).

The LLM’s output is marked as `_candidate` with a confidence score, and the user can accept or reject it.

PERF’s `trace_alignment` dimension uses lifted counterexample traces to score proof scripts that explicitly address the failing scenario, closing the loop between bounded model checking and theorem proving.

---

## 12. References

- MLIR documentation on dialects and lowering.
- Kōika: A Rule‑Based Hardware Design Language in Coq.
- ACL2: A Computational Logic for Applicative Common Lisp.
- Property Specification Language (PSL) IEEE 1850.
- SystemVerilog 1800-2017, Annex F (Assertions).
- VHDL‑2008, Part 4 (PSL Integration).
- Open Verification Library (OVL) 2.0.
- Verilator: Cycle‑accurate Verilog simulator.
- Value Change Dump (VCD) format specification.
- Previous discussions on SpecIR design, lowering, lifting, and LLM integration.
