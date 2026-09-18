# tests/unit/test_trace_lifting.py
#
# Unit tests for trace lifting.

import re
import json
import tempfile
import pytest
from pathlib import Path
import yaml
from isir.dialects import trace, isir
from isir.lifting import vcd_to_trace, trace_to_isir


@pytest.fixture
def mock_trace_module():
    """Return a TraceModule with simple data."""
    mod_op = trace.TraceModuleOp(trace_name="test")
    clock = trace.TraceClockOp(clock_name="clk", edge="posedge")
    sig1 = trace.TraceSignalOp(signal_name="head_sig", width=3)
    sig2 = trace.TraceSignalOp(signal_name="full_sig", width=1)
    ann1 = trace.TraceAnnotationOp(signal_name="head_sig", isir_ref="module.state[name=head]", kind="register")
    ann2 = trace.TraceAnnotationOp(signal_name="full_sig", isir_ref="module.state[name=full]", kind="register")
    ann3 = trace.TraceAnnotationOp(signal_name="enq_cond", isir_ref="module.rules[name=enqueue].condition", kind="rule_condition")
    trace_mod = trace.TraceModule(module_op=mod_op, clock=clock, signals=[sig1, sig2], annotations=[ann1, ann2, ann3])
    trace_mod.add_cycle(0, {"head_sig": 0b001, "full_sig": 0, "enq_cond": 1})
    trace_mod.add_cycle(1, {"head_sig": 0b010, "full_sig": 0, "enq_cond": 0})
    return trace_mod


@pytest.fixture
def mock_spec_module():
    """Return a SpecModule with matching state and rules."""
    state_ops = [
        isir.SpecStateOp(state_name="head", kind="register", data_type="bits<3>", initial=0),
        isir.SpecStateOp(state_name="full", kind="register", data_type="bool", initial=False)
    ]
    rule_ops = [
        isir.SpecRuleOp(rule_name="enqueue", condition="(not (read full))", actions=[]),
        isir.SpecRuleOp(rule_name="dequeue", condition="(not empty)", actions=[])
    ]
    inputs = [isir.Interface(name="enqueue", direction="input", data_type="bool")]
    outputs = [isir.Interface(name="data_out", direction="output", data_type="bits<32>")]
    spec_mod = isir.SpecModule(
        name="fifo",
        state_ops=state_ops,
        rule_ops=rule_ops,
        inputs=inputs,
        outputs=outputs
    )
    return spec_mod


def test_vcd_to_trace_missing_file():
    with pytest.raises(FileNotFoundError):
        vcd_to_trace.convert(Path("/nonexistent.vcd"))


def test_vcd_to_trace_with_mapping(mock_trace_module, monkeypatch, tmp_path):
    def mock_parse(*args, **kwargs):
        return mock_trace_module

    monkeypatch.setattr(vcd_to_trace, "_parse_vcd", mock_parse)

    dummy_vcd = tmp_path / "dummy.vcd"
    dummy_vcd.write_text("")

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json") as f:
        mapping = {
            "mapping": [
                {"rtl_signal": "head_sig", "isir_ref": "module.state[name=head]", "kind": "register"}
            ]
        }
        json.dump(mapping, f)
        f.flush()
        trace_mod = vcd_to_trace.convert(dummy_vcd, mapping_file=Path(f.name))

    assert len(trace_mod.annotations) == 4
    assert trace_mod.annotations[-1].signal_name == "head_sig"
    assert trace_mod.annotations[-1].isir_ref == "module.state[name=head]"


def test_reconstruct_state(mock_trace_module, mock_spec_module):
    annotation_map = {
        ann.isir_ref: ann.signal_name
        for ann in mock_trace_module.annotations
    }
    unmapped = set()
    cycle_data = mock_trace_module.cycles[0]
    state_vals = trace_to_isir._reconstruct_state(
        mock_spec_module.state_ops,
        annotation_map,
        cycle_data,
        unmapped
    )
    assert state_vals.get("head") == 1
    assert state_vals.get("full") == 0


def test_reconstruct_fired_rules(mock_trace_module, mock_spec_module):
    rule_cond_signals = {}
    for ann in mock_trace_module.annotations:
        if ann.kind == "rule_condition":
            match = re.search(r"\[name=([^\]]+)\]", ann.isir_ref)
            if match:
                rule_cond_signals[match.group(1)] = ann.signal_name

    unmapped = set()
    cycle_data = mock_trace_module.cycles[0]
    fired = trace_to_isir._reconstruct_fired_rules(
        mock_spec_module.rule_ops,
        rule_cond_signals,
        cycle_data,
        unmapped
    )
    assert "enqueue" in fired
    assert "dequeue" not in fired

    cycle_data2 = mock_trace_module.cycles[1]
    fired2 = trace_to_isir._reconstruct_fired_rules(
        mock_spec_module.rule_ops,
        rule_cond_signals,
        cycle_data2,
        unmapped
    )
    assert "enqueue" not in fired2


def test_convert_to_abstract_trace(mock_trace_module, mock_spec_module):
    abstract = trace_to_isir.convert(mock_trace_module, mock_spec_module)
    assert "trace" in abstract
    assert "cycles" in abstract["trace"]
    assert len(abstract["trace"]["cycles"]) == 2
    c0 = abstract["trace"]["cycles"][0]
    assert c0["cycle"] == 0
    assert c0["state"]["head"] == 1
    assert c0["fired_rules"] == ["enqueue"]
    c1 = abstract["trace"]["cycles"][1]
    assert c1["state"]["head"] == 2
    assert c1["fired_rules"] == []


def test_convert_to_yaml(mock_trace_module, mock_spec_module, tmp_path):
    output = tmp_path / "abstract.yaml"
    trace_to_isir.convert_to_yaml(mock_trace_module, mock_spec_module, output)
    assert output.exists()
    with open(output, "r") as f:
        data = yaml.safe_load(f)
    assert "trace" in data
    assert "cycles" in data["trace"]
    assert len(data["trace"]["cycles"]) == 2


def test_reconstruct_io(mock_trace_module, mock_spec_module):
    ann = trace.TraceAnnotationOp(
        signal_name="enq_in",
        isir_ref="module.inputs[name=enqueue]",
        kind="input"
    )
    mock_trace_module.annotations.append(ann)

    io_signals = {}
    for a in mock_trace_module.annotations:
        if a.kind in ("input", "output"):
            io_signals[a.isir_ref] = a.signal_name

    mock_spec_module.inputs = [
        isir.Interface(name="enqueue", direction="input", data_type="bool")
    ]
    mock_trace_module.cycles[0].values["enq_in"] = 1

    io_vals = trace_to_isir._reconstruct_io(
        mock_spec_module.inputs,
        "inputs",
        io_signals,
        mock_trace_module.cycles[0]
    )
    assert io_vals.get("enqueue") == 1
