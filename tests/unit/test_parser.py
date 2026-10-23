# tests/unit/test_parser.py
#
# Unit tests for the ISIR YAML parser.
# Updated for Reset.async_reset and version 0.1 compatibility.

import pytest
import yaml
from pathlib import Path
from tempfile import NamedTemporaryFile
from isir.parser.parser import parse_isir, load_expanded_raw, ISIRParseError
from isir.parser.ast import (
    ISIR, Module, Clock, Reset, State, Rule, Property, TemporalExpr,
    Interface, Parameter, ComponentInstance, Directive, Fairness,
    ProofObligation, Metadata, Evidence, EvidenceRef
)


def write_temp_isir(data: dict) -> Path:
    """Write a YAML dictionary to a temporary .isir file and return its path."""
    with NamedTemporaryFile(mode="w", suffix=".isir", delete=False) as f:
        yaml.dump(data, f, default_flow_style=False)
        return Path(f.name)


def test_minimal_isir():
    data = {
        "isir_version": "0.1",
        "module": {
            "name": "minimal",
            "clocks": [{"name": "clk", "edge": "posedge"}],
            "resets": [{"name": "rst", "polarity": "active_high", "async": False, "affects": "all"}],
            "state": [{"name": "reg1", "kind": "register", "type": "bits<8>"}],
            "rules": [{"name": "rule1", "action": ["(write reg1 0)"]}],
        }
    }
    path = write_temp_isir(data)
    spec = parse_isir(path)
    assert spec.isir_version == "0.1"
    assert spec.module.name == "minimal"
    assert len(spec.module.clocks) == 1
    assert spec.module.clocks[0].name == "clk"
    assert len(spec.module.resets) == 1
    assert spec.module.resets[0].name == "rst"
    assert len(spec.module.state) == 1
    assert spec.module.state[0].name == "reg1"
    assert len(spec.module.rules) == 1
    assert spec.module.rules[0].name == "rule1"
    path.unlink()


def test_full_fifo_example():
    data = {
        "isir_version": "0.1",
        "module": {
            "name": "fifo",
            "clocks": [{"name": "clk", "edge": "posedge"}],
            "resets": [{"name": "rst", "polarity": "active_high", "async": False, "affects": "all"}],
            "inputs": [
                {"name": "data_in", "direction": "input", "type": "bits<32>"},
                {"name": "write_en", "direction": "input", "type": "bool"},
                {"name": "read_en", "direction": "input", "type": "bool"},
            ],
            "outputs": [
                {"name": "data_out", "direction": "output", "type": "bits<32>"},
                {"name": "full", "direction": "output", "type": "bool"},
                {"name": "empty", "direction": "output", "type": "bool"},
            ],
            "state": [
                {"name": "mem", "kind": "memory", "type": {"type": "memory", "elem": "bits<32>", "depth": 8}},
                {"name": "write_ptr", "kind": "register", "type": "bits<3>", "initial": 0},
                {"name": "read_ptr", "kind": "register", "type": "bits<3>", "initial": 0},
                {"name": "count", "kind": "register", "type": "bits<4>", "initial": 0},
            ],
            "rules": [
                {
                    "name": "write",
                    "condition": "(and write_en (not (read full)))",
                    "action": [
                        "(mem_write mem (read write_ptr) data_in)",
                        "(write write_ptr (add (read write_ptr) 1))",
                        "(write count (add (read count) 1))"
                    ]
                },
                {
                    "name": "read",
                    "condition": "(and read_en (not (read empty)))",
                    "action": [
                        "(write data_out (mem_read mem (read read_ptr)))",
                        "(write read_ptr (add (read read_ptr) 1))",
                        "(write count (sub (read count) 1))"
                    ]
                },
                {
                    "name": "update_flags",
                    "condition": "true",
                    "action": [
                        "(write full (eq (read count) 8))",
                        "(write empty (eq (read count) 0))"
                    ]
                }
            ],
            "properties": [
                {
                    "name": "no_overflow",
                    "kind": "safety",
                    "expression": {"kind": "always", "operand": "(implies (and write_en (read full)) false)"}
                }
            ]
        }
    }
    path = write_temp_isir(data)
    spec = parse_isir(path)
    assert spec.module.name == "fifo"
    assert len(spec.module.state) == 4
    assert len(spec.module.rules) == 3
    assert len(spec.module.properties) == 1
    prop = spec.module.properties[0]
    assert prop.name == "no_overflow"
    assert prop.expression.kind == "always"
    path.unlink()


def test_with_proof_obligation():
    data = {
        "isir_version": "0.1",
        "module": {
            "name": "with_proof",
            "clocks": [{"name": "clk", "edge": "posedge"}],
            "resets": [{"name": "rst", "polarity": "active_high", "async": False, "affects": "all"}],
            "state": [{"name": "reg", "kind": "register", "type": "bits<8>"}],
            "rules": [{"name": "inc", "condition": "true", "action": ["(write reg (add (read reg) 1))"]}],
            "properties": [
                {
                    "name": "reg_never_overflow",
                    "kind": "safety",
                    "expression": {"kind": "always", "operand": "(lt (read reg) 256)"}
                }
            ],
            "proof_obligations": [
                {
                    "property": "reg_never_overflow",
                    "status": "unproved",
                    "engine": "theorem_proving",
                    "backend": "koika",
                    "metadata": {"coq_tactic": "induction reg"},
                    "confidence": 0.8
                }
            ]
        }
    }
    path = write_temp_isir(data)
    spec = parse_isir(path)
    po = spec.module.proof_obligations[0]
    assert po.property == "reg_never_overflow"
    assert po.backend == "koika"
    assert po.metadata == {"coq_tactic": "induction reg"}
    assert po.confidence == 0.8
    path.unlink()


def test_combinational_property_parsing():
    data = {
        "isir_version": "0.1",
        "module": {
            "name": "comb",
            "clocks": [{"name": "clk", "edge": "posedge"}],
            "resets": [{"name": "rst", "polarity": "active_high", "async": False, "affects": "all"}],
            "state": [{"name": "acc", "kind": "register", "type": "bits<8>"}],
            "rules": [{"name": "upd", "condition": "true", "action": ["(write acc (add (read a) (read b))"]}],
            "inputs": [{"name": "a", "direction": "input", "type": "bits<8>"},
                       {"name": "b", "direction": "input", "type": "bits<8>"}],
            "properties": [
                {
                    "name": "add_commutative",
                    "kind": "combinational",
                    "expression": {
                        "kind": "combinational",
                        "operand": "(add a b)",
                        "reference": "(add b a)"
                    }
                }
            ]
        }
    }
    path = write_temp_isir(data)
    spec = parse_isir(path)
    prop = spec.module.properties[0]
    assert prop.kind == "combinational"
    assert prop.expression.kind == "combinational"
    assert prop.expression.operand == "(add a b)"
    assert prop.expression.reference == "(add b a)"
    path.unlink()


def test_transition_property_parsing():
    data = {
        "isir_version": "0.1",
        "module": {
            "name": "trans",
            "clocks": [{"name": "clk", "edge": "posedge"}],
            "resets": [{"name": "rst", "polarity": "active_high", "async": False, "affects": "all"}],
            "state": [{"name": "acc", "kind": "register", "type": "bits<8>"}],
            "rules": [{"name": "upd", "condition": "true", "action": ["(write acc (add (read a) (read b))"]}],
            "inputs": [{"name": "a", "direction": "input", "type": "bits<8>"},
                       {"name": "b", "direction": "input", "type": "bits<8>"}],
            "properties": [
                {
                    "name": "acc_updates_to_sum",
                    "kind": "transition",
                    "expression": {
                        "kind": "transition",
                        "operand": "(eq (read acc) (add a b))"
                    }
                }
            ]
        }
    }
    path = write_temp_isir(data)
    spec = parse_isir(path)
    prop = spec.module.properties[0]
    assert prop.kind == "transition"
    assert prop.expression.kind == "transition"
    assert prop.expression.operand == "(eq (read acc) (add a b))"
    path.unlink()


def test_transition_property_requires_operand():
    data = {
        "isir_version": "0.1",
        "module": {
            "name": "trans",
            "clocks": [{"name": "clk", "edge": "posedge"}],
            "resets": [{"name": "rst", "polarity": "active_high", "async": False, "affects": "all"}],
            "state": [{"name": "acc", "kind": "register", "type": "bits<8>"}],
            "rules": [{"name": "upd", "condition": "true", "action": ["(write acc (add (read a) (read b))"]}],
            "inputs": [{"name": "a", "direction": "input", "type": "bits<8>"}],
            "properties": [
                {"name": "bad_trans", "kind": "transition", "expression": {"kind": "transition"}}
            ]
        }
    }
    path = write_temp_isir(data)
    with pytest.raises(ISIRParseError):
        parse_isir(path)
    path.unlink()


def test_independence_property_parsing():
    data = {
        "isir_version": "0.1",
        "module": {
            "name": "indep",
            "clocks": [{"name": "clk", "edge": "posedge"}],
            "resets": [{"name": "rst", "polarity": "active_high", "async": False, "affects": "all"}],
            "state": [{"name": "acc", "kind": "register", "type": "bits<8>"}],
            "rules": [{"name": "upd", "condition": "true", "action": ["(write acc (slice a 7 0)"]}],
            "inputs": [{"name": "a", "direction": "input", "type": "bits<32>"},
                       {"name": "mask", "direction": "input", "type": "bits<4>"}],
            "properties": [
                {
                    "name": "reduction_independent_of_mask",
                    "kind": "independence",
                    "expression": {
                        "kind": "independence",
                        "operand": "(slice a 7 0)",
                        "independent_of": ["mask"]
                    }
                }
            ]
        }
    }
    path = write_temp_isir(data)
    spec = parse_isir(path)
    prop = spec.module.properties[0]
    assert prop.kind == "independence"
    assert prop.expression.kind == "independence"
    assert prop.expression.operand == "(slice a 7 0)"
    assert prop.expression.independent_of == ["mask"]
    path.unlink()


def test_independence_property_requires_independent_of():
    data = {
        "isir_version": "0.1",
        "module": {
            "name": "indep",
            "clocks": [{"name": "clk", "edge": "posedge"}],
            "resets": [{"name": "rst", "polarity": "active_high", "async": False, "affects": "all"}],
            "state": [{"name": "acc", "kind": "register", "type": "bits<8>"}],
            "rules": [{"name": "upd", "condition": "true", "action": ["(write acc (slice a 7 0)"]}],
            "inputs": [{"name": "a", "direction": "input", "type": "bits<32>"}],
            "properties": [
                {"name": "bad_indep", "kind": "independence",
                 "expression": {"kind": "independence", "operand": "(slice a 7 0)"}}
            ]
        }
    }
    path = write_temp_isir(data)
    with pytest.raises(ISIRParseError):
        parse_isir(path)
    path.unlink()


def test_combinational_property_requires_reference():
    data = {
        "isir_version": "0.1",
        "module": {
            "name": "comb",
            "clocks": [{"name": "clk", "edge": "posedge"}],
            "resets": [{"name": "rst", "polarity": "active_high", "async": False, "affects": "all"}],
            "state": [{"name": "acc", "kind": "register", "type": "bits<8>"}],
            "rules": [{"name": "upd", "condition": "true", "action": ["(write acc (add (read a) (read b))"]}],
            "inputs": [{"name": "a", "direction": "input", "type": "bits<8>"}],
            "properties": [
                {
                    "name": "bad_comb",
                    "kind": "combinational",
                    "expression": {"kind": "combinational", "operand": "(add a a)"}
                }
            ]
        }
    }
    path = write_temp_isir(data)
    with pytest.raises(ISIRParseError):
        parse_isir(path)
    path.unlink()


def test_functions_and_axioms_parsing():
    data = {
        "isir_version": "0.1",
        "module": {
            "name": "fpu",
            "clocks": [{"name": "clk", "edge": "posedge"}],
            "resets": [{"name": "rst", "polarity": "active_high", "async": False, "affects": "all"}],
            "state": [{"name": "acc", "kind": "register", "type": "bits<16>"}],
            "rules": [{"name": "upd", "condition": "true", "action": ["(write acc (abstract_finite_add a b)"]}],
            "inputs": [{"name": "a", "direction": "input", "type": "bits<16>"},
                       {"name": "b", "direction": "input", "type": "bits<16>"}],
            "functions": [
                {"name": "abstract_finite_add",
                 "params": [{"name": "x", "type": "bits<16>"}, {"name": "y", "type": "bits<16>"}],
                 "return": "bits<16>"}
            ],
            "axioms": [
                {"name": "finite_add_commutative",
                 "forall": [{"name": "x", "type": "bits<16>"}, {"name": "y", "type": "bits<16>"}],
                 "statement": "(eq (abstract_finite_add x y) (abstract_finite_add y x))"}
            ]
        }
    }
    path = write_temp_isir(data)
    spec = parse_isir(path)
    fn = spec.module.functions[0]
    assert fn.name == "abstract_finite_add"
    assert fn.params[0].name == "x"
    assert fn.params[0].type == "bits<16>"
    assert fn.return_type == "bits<16>"
    ax = spec.module.axioms[0]
    assert ax.name == "finite_add_commutative"
    assert ax.forall_vars[0].name == "x"
    assert ax.statement == "(eq (abstract_finite_add x y) (abstract_finite_add y x))"
    path.unlink()


def test_missing_isir_version():
    data = {
        "module": {"name": "test", "clocks": [], "resets": [], "state": [], "rules": []}
    }
    path = write_temp_isir(data)
    with pytest.raises(ISIRParseError, match="Missing 'isir_version' field"):
        parse_isir(path)
    path.unlink()


def test_missing_module():
    data = {"isir_version": "0.1"}
    path = write_temp_isir(data)
    with pytest.raises(ISIRParseError, match="Missing 'module' field"):
        parse_isir(path)
    path.unlink()


def test_module_not_dict():
    data = {"isir_version": "0.1", "module": "not a dict"}
    path = write_temp_isir(data)
    with pytest.raises(ISIRParseError, match="'module' must be a mapping"):
        parse_isir(path)
    path.unlink()


def test_invalid_yaml_syntax():
    path = Path("/tmp/invalid.isir")
    path.write_text("isir_version: 0.1\nmodule: [unclosed list\n")
    with pytest.raises(ISIRParseError, match="YAML parsing error"):
        parse_isir(path)
    path.unlink()


def test_missing_required_field_in_module():
    data = {
        "isir_version": "0.1",
        "module": {
            "name": "missing_clocks",
            "resets": [{"name": "rst", "polarity": "active_high", "async": False, "affects": "all"}],
            "state": [],
            "rules": []
        }
    }
    path = write_temp_isir(data)
    spec = parse_isir(path)
    assert spec.module.clocks == []
    path.unlink()


def test_optional_fields():
    data = {
        "isir_version": "0.1",
        "module": {
            "name": "optional_test",
            "clocks": [{"name": "clk", "edge": "posedge"}],
            "resets": [{"name": "rst", "polarity": "active_high", "async": False, "affects": "all"}],
            "state": [],
            "rules": [],
            "parameters": [{"name": "WIDTH", "type": "int", "default": 32}],
            "inputs": [{"name": "in1", "direction": "input", "type": "bool"}],
            "outputs": [],
            "types": [{"name": "state_t", "kind": "enum", "values": ["A", "B"]}],
            "directives": [{"type": "assume", "name": "assume1", "expression": "true"}],
            "fairness": [{"name": "fair1", "type": "weak", "condition": "(eventually req)"}],
            "metadata": {"engine": "ic3"},
            "evidence": [{"type": "coq_theorem", "ref": "#lemma1", "engine": "theorem_proving"}],
        }
    }
    path = write_temp_isir(data)
    spec = parse_isir(path)
    assert len(spec.module.parameters) == 1
    assert spec.module.parameters[0].name == "WIDTH"
    assert len(spec.module.inputs) == 1
    assert len(spec.module.types) == 1
    assert spec.module.types[0].name == "state_t"
    assert len(spec.module.directives) == 1
    assert spec.module.directives[0].type == "assume"
    assert len(spec.module.fairness) == 1
    assert spec.module.fairness[0].name == "fair1"
    assert spec.module.metadata.engine == "ic3"
    assert len(spec.module.evidence) == 1
    path.unlink()


def test_file_not_found():
    with pytest.raises(FileNotFoundError):
        parse_isir("/non/existent/file.isir")


def test_parameter_substitution():
    """Module parameters substitute `$name` references, with optional overrides."""
    import tempfile
    text = '''
isir_version: "0.1"
module:
  name: pc
  parameters:
    - {name: width, type: int, default: 4}
    - {name: modulus, type: int, default: 16}
  clocks: [{name: clk, edge: posedge}]
  resets: [{name: rst, polarity: active_high, async: false, affects: all}]
  inputs: [{name: en, direction: input, type: "bool"}]
  state: [{name: count, kind: register, type: "bits<$width>", initial: 0}]
  rules:
    - name: tick
      condition: en
      action: [(write count (mod (add (read count) 1) $modulus))]
'''
    p = Path(tempfile.mkdtemp()) / "pc.isir"
    p.write_text(text)
    # defaults
    spec = parse_isir(p)
    assert spec.module.state[0].type == "bits<4>"
    assert "16" in spec.module.rules[0].action[0]
    # overrides
    spec2 = parse_isir(p, parameter_overrides={"width": 8, "modulus": 256})
    assert spec2.module.state[0].type == "bits<8>"
    assert "256" in spec2.module.rules[0].action[0]


def test_repeat_expansion():
    """`repeat` blocks expand to N instantiated copies with `{var}` substitution."""
    import tempfile
    text = '''
isir_version: "0.1"
module:
  name: rp
  parameters:
    - {name: num, type: int, default: 3}
  clocks: [{name: clk, edge: posedge}]
  resets: [{name: rst, polarity: active_high, async: false, affects: all}]
  inputs: [{name: en, direction: input, type: "bool"}]
  state:
    - repeat:
        var: i
        range: $num
        items:
          - {name: "c{i}_state", kind: register, type: "bits<2>", initial: 0}
'''
    p = Path(tempfile.mkdtemp()) / "rp.isir"
    p.write_text(text)
    spec = parse_isir(p)
    names = [s.name for s in spec.module.state]
    assert names == ["c0_state", "c1_state", "c2_state"]
    # override to 2 cores
    spec2 = parse_isir(p, parameter_overrides={"num": 2})
    names2 = [s.name for s in spec2.module.state]
    assert names2 == ["c0_state", "c1_state"]


def test_reduce_expansion():
    """`reduce` folds build nested expressions and `@name` references resolve."""
    import tempfile
    text = '''
isir_version: "0.1"
module:
  name: rd
  parameters:
    - {name: n, type: int, default: 3}
  reductions:
    - name: any_ok
      var: j
      range: $n
      init: "false"
      step: "(or {acc} (eq a {j}))"
  clocks: [{name: clk, edge: posedge}]
  resets: [{name: rst, polarity: active_high, async: false, affects: all}]
  inputs: [{name: a, direction: input, type: "bits<2>"}]
  state:
    - {name: x, kind: register, type: "bits<2>", initial: 0}
  rules:
    - name: r
      action:
        - (write x (ite @any_ok 1 0))
'''
    p = Path(tempfile.mkdtemp()) / "rd.isir"
    p.write_text(text)
    raw = load_expanded_raw(p)
    action = raw["module"]["rules"][0]["action"][0]
    # folded: (or (or (or false (eq a 0)) (eq a 1)) (eq a 2))
    assert "(or (or (or false (eq a 0)) (eq a 1)) (eq a 2))" in action
    assert "reductions" not in raw["module"]


def test_component_flattening(tmp_path):
    """`components` load a child module by path, prefix it, and bind ports."""
    (tmp_path / "child.isir").write_text('''
isir_version: "0.1"
module:
  name: child
  clocks: [{name: clk, edge: posedge}]
  resets: [{name: rst, polarity: active_high, async: false, affects: all}]
  inputs: [{name: en, direction: input, type: "bool"}]
  state:
    - {name: cnt, kind: register, type: "bits<4>", initial: 0}
  rules:
    - name: tick
      condition: en
      action:
        - (write cnt (add (read cnt) 1))
  properties:
    - name: bound
      kind: safety
      expression:
        kind: always
        operand: (le (read cnt) 15)
  proof_obligations:
    - property: bound
      status: unproved
      engine: theorem_proving
      backend: koika
''', encoding="utf-8")
    (tmp_path / "top.isir").write_text('''
isir_version: "0.1"
module:
  name: top
  clocks: [{name: clk, edge: posedge}]
  resets: [{name: rst, polarity: active_high, async: false, affects: all}]
  inputs: [{name: go, direction: input, type: "bool"}]
  components:
    - name: u0
      module: "child.isir"
      port_map: {en: go}
''', encoding="utf-8")
    raw = load_expanded_raw(tmp_path / "top.isir")
    mod = raw["module"]
    assert [s["name"] for s in mod["state"]] == ["u0_cnt"]
    assert [i["name"] for i in mod["inputs"]] == ["go"]
    assert [r["name"] for r in mod["rules"]] == ["u0_tick"]
    assert mod["rules"][0]["condition"] == "go"
    assert mod["rules"][0]["action"] == ["(write u0_cnt (add (read u0_cnt) 1))"]
    assert [p["name"] for p in mod["properties"]] == ["u0_bound"]
    assert mod["proof_obligations"][0]["property"] == "u0_bound"
    assert "components" not in mod


def test_reduce_positional_args():
    """`@name(a)` passes a positional argument into the folded expression."""
    import tempfile
    text = '''
isir_version: "0.1"
module:
  name: pa
  parameters:
    - {name: n, type: int, default: 2}
  reductions:
    - name: any_eq
      var: j
      range: $n
      init: "false"
      step: "(or {acc} (eq (read x{j}) $1))"
  clocks: [{name: clk, edge: posedge}]
  resets: [{name: rst, polarity: active_high, async: false, affects: all}]
  inputs: [{name: a, direction: input, type: "bits<2>"}]
  state:
    - {name: x0, kind: register, type: "bits<2>", initial: 0}
    - {name: x1, kind: register, type: "bits<2>", initial: 0}
  rules:
    - name: r
      action:
        - (write x0 (ite @any_eq(a) 1 0))
'''
    p = Path(tempfile.mkdtemp()) / "pa.isir"
    p.write_text(text)
    raw = load_expanded_raw(p)
    action = raw["module"]["rules"][0]["action"][0]
    assert "(or (or false (eq (read x0) a)) (eq (read x1) a))" in action


def test_component_cross_instance_wiring(tmp_path):
    """`port_map` can bind a child *state* to a parent signal (cross-instance wire)."""
    (tmp_path / "buf.isir").write_text('''
isir_version: "0.1"
module:
  name: buf
  clocks: [{name: clk, edge: posedge}]
  resets: [{name: rst, polarity: active_high, async: false, affects: all}]
  inputs: [{name: d, direction: input, type: "bits<4>"}]
  state:
    - {name: q, kind: register, type: "bits<4>", initial: 0}
  rules:
    - name: update
      condition: "true"
      action: [(write q d)]
''', encoding="utf-8")
    (tmp_path / "top.isir").write_text('''
isir_version: "0.1"
module:
  name: top
  clocks: [{name: clk, edge: posedge}]
  resets: [{name: rst, polarity: active_high, async: false, affects: all}]
  inputs: [{name: d0, direction: input, type: "bits<4>"}]
  state:
    - {name: mid, kind: register, type: "bits<4>", initial: 0}
  components:
    - name: a
      module: "buf.isir"
      port_map: {d: d0, q: mid}
    - name: b
      module: "buf.isir"
      port_map: {d: mid}
''', encoding="utf-8")
    raw = load_expanded_raw(tmp_path / "top.isir")
    mod = raw["module"]
    rules = {r["name"]: r for r in mod["rules"]}
    # a writes the shared 'mid' wire; b reads it.
    assert rules["a_update"]["action"] == ["(write mid d0)"]
    assert rules["b_update"]["action"] == ["(write b_q mid)"]
    # 'mid' is declared once in the parent, not duplicated.
    assert [s["name"] for s in mod["state"]].count("mid") == 1


def test_component_lift_properties_false(tmp_path):
    """`lift_properties: false` drops a child's proof obligations (reuse, not re-prove)."""
    (tmp_path / "child.isir").write_text('''
isir_version: "0.1"
module:
  name: child
  clocks: [{name: clk, edge: posedge}]
  resets: [{name: rst, polarity: active_high, async: false, affects: all}]
  inputs: [{name: d, direction: input, type: "bits<4>"}]
  state:
    - {name: q, kind: register, type: "bits<4>", initial: 0}
  rules:
    - name: update
      condition: "true"
      action: [(write q d)]
  properties:
    - name: q_nonneg
      kind: safety
      expression: {kind: always, operand: "(ge (read q) 0)"}
  proof_obligations:
    - {property: q_nonneg, status: unproved, engine: theorem_proving, backend: koika}
''', encoding="utf-8")
    (tmp_path / "top.isir").write_text('''
isir_version: "0.1"
module:
  name: top
  clocks: [{name: clk, edge: posedge}]
  resets: [{name: rst, polarity: active_high, async: false, affects: all}]
  inputs: [{name: d0, direction: input, type: "bits<4>"}]
  components:
    - name: a
      module: "child.isir"
      lift_properties: false
      port_map: {d: d0}
''', encoding="utf-8")
    raw = load_expanded_raw(tmp_path / "top.isir")
    mod = raw["module"]
    assert mod.get("properties", []) == []
    assert mod.get("proof_obligations", []) == []
    assert [r["name"] for r in mod["rules"]] == ["a_update"]


def test_lift_properties_invariant_mode(tmp_path):
    """`lift_properties: invariant` lifts a child's safety/always property as an
    assumed reachable invariant with its user functions unfolded."""
    (tmp_path / "child.isir").write_text('''
isir_version: "0.1"
module:
  name: child
  clocks: [{name: clk, edge: posedge}]
  resets: [{name: rst, polarity: active_high, async: false, affects: all}]
  inputs: [{name: d, direction: input, type: "bits<4>"}]
  state:
    - {name: q, kind: register, type: "bits<4>", initial: 0}
  functions:
    - name: is_three
      params: [{name: s, type: "bits<4>"}]
      return: "bool"
      body: (eq s 3)
  rules:
    - name: update
      condition: "true"
      action: [(write q d)]
  properties:
    - name: q_is_three
      kind: safety
      expression: {kind: always, operand: "(is_three (read q))"}
  proof_obligations:
    - {property: q_is_three, status: unproved, engine: theorem_proving, backend: koika}
''', encoding="utf-8")
    (tmp_path / "top.isir").write_text('''
isir_version: "0.1"
module:
  name: top
  clocks: [{name: clk, edge: posedge}]
  resets: [{name: rst, polarity: active_high, async: false, affects: all}]
  inputs: [{name: d0, direction: input, type: "bits<4>"}]
  components:
    - name: a
      module: "child.isir"
      lift_properties: invariant
      port_map: {d: d0}
''', encoding="utf-8")
    raw = load_expanded_raw(tmp_path / "top.isir")
    mod = raw["module"]
    invs = mod.get("invariants", [])
    assert len(invs) == 1, f"expected 1 lifted invariant, got {invs}"
    assert invs[0]["name"] == "a_q_is_three"
    assert invs[0]["assumed"] is True
    # function is_three was unfolded to (eq ... 3)
    assert "is_three" not in invs[0]["operand"]
    assert "(eq (read a_q) 3)" in invs[0]["operand"]
    assert mod.get("properties", []) == []
    assert mod.get("proof_obligations", []) == []
