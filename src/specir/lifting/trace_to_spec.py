# src/specir/lifting/trace_to_spec.py
#
# Lifts a TraceModule (from VCD) to an abstract SpecIR trace YAML.
# Uses annotations to map RTL signals to SpecIR state variables,
# rule conditions, inputs, and outputs. Reconstructs per-cycle
# abstract state, fired rules, and I/O values.

import re
import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union
from specir.dialects import trace_ir, spec_ir
from specir.utils.logger import get_logger

logger = get_logger(__name__)

# Regex to extract the name from a specir_ref like "module.rules[name=do_enqueue].condition"
_REF_NAME_PATTERN = re.compile(r"\[name=([^\]]+)\]")


def _extract_name_from_ref(specir_ref: str) -> Optional[str]:
    """Extract the element name from a specir_ref string, e.g. ``module.state[name=head]``."""
    match = _REF_NAME_PATTERN.search(specir_ref)
    return match.group(1) if match else None


def _extract_width(data_type: str) -> int:
    """Extract bit width from a type string like 'bits<8>'."""
    if isinstance(data_type, str) and data_type.startswith("bits<"):
        try:
            return int(data_type[5:-1])
        except ValueError:
            pass
    return 1


def _value_to_python(value: Any, width: int = 1, signed: bool = False) -> Any:
    """
    Convert a VCD bit vector representation (string like "0110" or "1'b1")
    to a Python int/bool.  Handles binary, hex, and unknown/high‑impedance
    (``x``/``z``) values – the latter return ``None``.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if not isinstance(value, str):
        return value

    # Unknown or high‑impedance
    if any(c in "xXzZ" for c in value):
        return None

    # Remove radix prefix if present
    if value.startswith('b') or value.startswith('B'):
        value = value[1:]
    elif value.startswith('h') or value.startswith('H'):
        try:
            return int(value[1:], 16)
        except ValueError:
            return None

    # Binary string
    if all(c in '01' for c in value):
        if width == 1:
            return value == '1'
        try:
            return int(value, 2)
        except ValueError:
            return None

    try:
        return int(value)
    except (ValueError, TypeError):
        return value


def _get_signal_value(cycle_data: trace_ir.TraceCycleData, signal_name: str) -> Any:
    """Return the value of a signal in a cycle, or None if missing."""
    return cycle_data.values.get(signal_name)


def _iface_name_and_type(iface: Union[spec_ir.Interface, Dict[str, Any]]) -> Tuple[str, str]:
    """
    Return the (name, data_type) tuple for an interface description.

    Accepts either a `spec_ir.Interface` dataclass or a plain dictionary
    (for backward compatibility with older test harnesses).
    """
    if isinstance(iface, dict):
        name = iface.get("name", "")
        data_type = iface.get("data_type", iface.get("type", ""))
        return name, data_type
    return iface.name, iface.data_type


def _reconstruct_state(
    state_ops: List[spec_ir.SpecStateOp],
    annotation_map: Dict[str, str],
    cycle_data: trace_ir.TraceCycleData,
    unmapped_states: Set[str]
) -> Dict[str, Any]:
    """Reconstruct abstract state values from RTL signals using annotations."""
    state_vals: Dict[str, Any] = {}
    for state_op in state_ops:
        ref = f"module.state[name={state_op.state_name}]"
        sig_name = annotation_map.get(ref)
        if sig_name:
            raw_val = _get_signal_value(cycle_data, sig_name)
            if raw_val is not None:
                width = _extract_width(state_op.data_type)
                state_vals[state_op.state_name] = _value_to_python(raw_val, width)
        else:
            unmapped_states.add(state_op.state_name)
    return state_vals


def _reconstruct_fired_rules(
    rule_ops: List[spec_ir.SpecRuleOp],
    rule_cond_signals: Dict[str, str],
    cycle_data: trace_ir.TraceCycleData,
    unmapped_rules: Set[str]
) -> List[str]:
    """
    Determine which rules fired based on rule condition signals annotated
    as ``rule_condition``.
    """
    fired: List[str] = []
    for rule_op in rule_ops:
        sig_name = rule_cond_signals.get(rule_op.rule_name)
        if sig_name:
            raw_val = _get_signal_value(cycle_data, sig_name)
            if raw_val is not None:
                if _value_to_python(raw_val, 1):
                    fired.append(rule_op.rule_name)
        else:
            unmapped_rules.add(rule_op.rule_name)
    return fired


def _reconstruct_io(
    interfaces: List[Union[spec_ir.Interface, Dict[str, Any]]],
    direction_kind: str,            # "inputs" or "outputs"
    io_signals: Dict[str, str],
    cycle_data: trace_ir.TraceCycleData
) -> Dict[str, Any]:
    """Reconstruct input/output values from RTL signals using annotations."""
    values: Dict[str, Any] = {}
    for iface in interfaces:
        name, data_type = _iface_name_and_type(iface)

        ref = f"module.{direction_kind}[name={name}]"
        sig_name = io_signals.get(ref)
        if sig_name:
            raw_val = _get_signal_value(cycle_data, sig_name)
            if raw_val is not None:
                width = _extract_width(data_type)
                values[name] = _value_to_python(raw_val, width)
    return values


def convert(
    trace_module: trace_ir.TraceModule,
    spec_module: spec_ir.SpecModule,
    strict: bool = False
) -> Dict[str, Any]:
    """
    Convert a TraceModule (with annotations) to an abstract SpecIR trace.

    Args:
        trace_module: The trace dialect module (from VCD import).
        spec_module: The original spec dialect module.
        strict: If True, raise an error when state or rule annotations are missing.

    Returns:
        A dictionary with structure:
        ``{"trace": {"cycles": [ ... ]}}``
        Each cycle contains ``cycle``, ``state``, ``fired_rules``, ``inputs``, ``outputs``.
    """
    # Build unified annotation maps
    annotation_map: Dict[str, str] = {}         # specir_ref -> signal_name
    rule_cond_signals: Dict[str, str] = {}       # rule_name -> signal_name
    io_signals: Dict[str, str] = {}              # specir_ref -> signal_name

    for ann in trace_module.annotations:
        annotation_map[ann.specir_ref] = ann.signal_name
        if ann.kind == "rule_condition":
            rule_name = _extract_name_from_ref(ann.specir_ref)
            if rule_name:
                rule_cond_signals[rule_name] = ann.signal_name
        elif ann.kind in ("input", "output"):
            io_signals[ann.specir_ref] = ann.signal_name

    # Collect missing annotations for reporting
    unmapped_states: Set[str] = set()
    unmapped_rules: Set[str] = set()

    # Build per‑cycle abstract data
    cycles = []
    for cycle_data in trace_module.cycles:
        state_vals = _reconstruct_state(
            spec_module.state_ops, annotation_map, cycle_data, unmapped_states
        )
        fired = _reconstruct_fired_rules(
            spec_module.rule_ops, rule_cond_signals, cycle_data, unmapped_rules
        )

        inputs_vals = _reconstruct_io(
            spec_module.inputs, "inputs", io_signals, cycle_data
        )
        outputs_vals = _reconstruct_io(
            spec_module.outputs, "outputs", io_signals, cycle_data
        )

        cycles.append({
            "cycle": cycle_data.cycle,
            "state": state_vals,
            "fired_rules": fired,
            "inputs": inputs_vals,
            "outputs": outputs_vals
        })

    if unmapped_states:
        logger.warning("States without RTL mapping: %s", sorted(unmapped_states))
    if unmapped_rules:
        logger.warning("Rules without RTL condition signal: %s", sorted(unmapped_rules))
    if strict and (unmapped_states or unmapped_rules):
        raise ValueError(
            f"Unmapped elements – states: {sorted(unmapped_states)}, "
            f"rules: {sorted(unmapped_rules)}"
        )

    return {"trace": {"cycles": cycles}}


def convert_to_yaml(
    trace_module: trace_ir.TraceModule,
    spec_module: spec_ir.SpecModule,
    output_path: Path,
    strict: bool = False
) -> None:
    """
    Convert and write the abstract trace to a YAML file.
    The output is wrapped with a top‑level ``trace:`` key as required by
    the SpecIR specification.
    """
    abstract_trace = convert(trace_module, spec_module, strict=strict)
    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(abstract_trace, f, default_flow_style=False, sort_keys=False)
    logger.info("Abstract trace written to %s", output_path)
