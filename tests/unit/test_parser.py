# tests/unit/test_parser.py
#
# Unit tests for the SpecIR YAML parser.
# Updated for Reset.async_reset and version 0.1 compatibility.

import pytest
import yaml
from pathlib import Path
from tempfile import NamedTemporaryFile

from specir.parser.parser import parse_specir, SpecIRParseError
from specir.parser.ast import (
    SpecIR, Module, Clock, Reset, State, Rule, Property, TemporalExpr,
    Interface, Parameter, ComponentInstance, Directive, Fairness,
    ProofObligation, Metadata, Evidence, EvidenceRef
)


def write_temp_specir(data: dict) -> Path:
    """Write a YAML dictionary to a temporary .specir file and return its path."""
    with NamedTemporaryFile(mode="w", suffix=".specir", delete=False) as f:
        yaml.dump(data, f, default_flow_style=False)
        return Path(f.name)


def test_minimal_specir():
    data = {
        "specir_version": "0.1",
        "module": {
            "name": "minimal",
            "clocks": [{"name": "clk", "edge": "posedge"}],
            "resets": [{"name": "rst", "polarity": "active_high", "async": False, "affects": "all"}],
            "state": [{"name": "reg1", "kind": "register", "type": "bits<8>"}],
            "rules": [{"name": "rule1", "action": ["(write reg1 0)"]}],
        }
    }
    path = write_temp_specir(data)
    spec = parse_specir(path)
    assert spec.specir_version == "0.1"
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
        "specir_version": "0.1",
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
    path = write_temp_specir(data)
    spec = parse_specir(path)
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
        "specir_version": "0.1",
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
    path = write_temp_specir(data)
    spec = parse_specir(path)
    po = spec.module.proof_obligations[0]
    assert po.property == "reg_never_overflow"
    assert po.backend == "koika"
    assert po.metadata == {"coq_tactic": "induction reg"}
    assert po.confidence == 0.8
    path.unlink()


def test_missing_specir_version():
    data = {
        "module": {"name": "test", "clocks": [], "resets": [], "state": [], "rules": []}
    }
    path = write_temp_specir(data)
    with pytest.raises(SpecIRParseError, match="Missing 'specir_version' field"):
        parse_specir(path)
    path.unlink()


def test_missing_module():
    data = {"specir_version": "0.1"}
    path = write_temp_specir(data)
    with pytest.raises(SpecIRParseError, match="Missing 'module' field"):
        parse_specir(path)
    path.unlink()


def test_module_not_dict():
    data = {"specir_version": "0.1", "module": "not a dict"}
    path = write_temp_specir(data)
    with pytest.raises(SpecIRParseError, match="'module' must be a mapping"):
        parse_specir(path)
    path.unlink()


def test_invalid_yaml_syntax():
    # Write a file with invalid YAML
    path = Path("/tmp/invalid.specir")
    path.write_text("specir_version: 0.1\nmodule: [unclosed list\n")
    with pytest.raises(SpecIRParseError, match="YAML parsing error"):
        parse_specir(path)
    path.unlink()


def test_missing_required_field_in_module():
    # Missing 'clocks' (parser does not enforce, only validator does)
    data = {
        "specir_version": "0.1",
        "module": {
            "name": "missing_clocks",
            "resets": [{"name": "rst", "polarity": "active_high", "async": False, "affects": "all"}],
            "state": [],
            "rules": []
        }
    }
    path = write_temp_specir(data)
    # Parser does not validate schema, so it should not crash
    spec = parse_specir(path)
    assert spec.module.clocks == []   # default empty list
    path.unlink()


def test_optional_fields():
    data = {
        "specir_version": "0.1",
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
            "components": [{"name": "sub", "module": "submod"}],
            "directives": [{"type": "assume", "name": "assume1", "expression": "true"}],
            "fairness": [{"name": "fair1", "type": "weak", "condition": "(eventually req)"}],
            "metadata": {"engine": "ic3"},
            "evidence": [{"type": "coq_theorem", "ref": "#lemma1", "engine": "theorem_proving"}],
        }
    }
    path = write_temp_specir(data)
    spec = parse_specir(path)
    assert len(spec.module.parameters) == 1
    assert spec.module.parameters[0].name == "WIDTH"
    assert len(spec.module.inputs) == 1
    assert len(spec.module.types) == 1
    assert spec.module.types[0].name == "state_t"
    assert len(spec.module.components) == 1
    assert spec.module.components[0].name == "sub"
    assert len(spec.module.directives) == 1
    assert spec.module.directives[0].type == "assume"
    assert len(spec.module.fairness) == 1
    assert spec.module.fairness[0].name == "fair1"
    assert spec.module.metadata.engine == "ic3"
    assert len(spec.module.evidence) == 1
    path.unlink()


def test_file_not_found():
    with pytest.raises(FileNotFoundError):
        parse_specir("/non/existent/file.specir")
