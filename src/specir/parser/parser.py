# src/specir/parser/parser.py
#
# YAML to AST parser for SpecIR (.specir) files.
# Converts YAML dictionaries into the dataclasses defined in ast.py.
# Revision: made status optional in proof obligations (defaults to "unproved").

import yaml
from pathlib import Path
from typing import Any, Dict, List, Union

from specir.parser.ast import (
    Clock, ComponentInstance, Directive, Evidence, EvidenceRef, Fairness,
    Interface, Metadata, Module, Parameter, Property, ProofObligation,
    ProofObligationFeedback, Reset, Rule, Schedule, SpecIR, State,
    TemporalExpr, UserType, Candidate, OneOf,
)
from specir.utils.logger import get_logger

logger = get_logger(__name__)

SUPPORTED_VERSIONS = {"0.1"}


class SpecIRParseError(Exception):
    """Exception raised when a .specir file is malformed."""
    pass


def _require(data: Dict[str, Any], key: str, context: str = "") -> Any:
    """Get a required field or raise SpecIRParseError."""
    if key not in data:
        ctx = f" in {context}" if context else ""
        raise SpecIRParseError(f"Missing required field '{key}'{ctx}")
    return data[key]


def _parse_candidate(data: Dict[str, Any]) -> Candidate:
    """Parse a _candidate wrapper, e.g. { value: ..., confidence: 0.9 }."""
    return Candidate(
        value=data.get("value"),
        confidence=data.get("confidence", 0.0),
        source=data.get("source"),
        alternatives=data.get("alternatives", []),
    )

def _parse_one_of(data: Dict[str, Any]) -> OneOf:
    """Parse a one_of wrapper, e.g. { alternatives: [...], resolution: "user" }."""
    return OneOf(
        alternatives=data.get("alternatives", []),
        resolution=data.get("resolution"),
    )


def _parse_evidence_ref(data: Any) -> EvidenceRef:
    """Parse an evidence reference, which can be a string (local_id) or a dict."""
    if isinstance(data, str):
        return EvidenceRef(type="local_id", value=data)
    if not isinstance(data, dict):
        raise SpecIRParseError(f"Evidence ref must be a string or object, got {type(data)}")
    ref_type = data.get("type", "local_id")
    if ref_type not in ("uri", "local_id"):
        raise SpecIRParseError(f"Invalid evidence ref type '{ref_type}'. Must be 'uri' or 'local_id'.")
    return EvidenceRef(type=ref_type, value=_require(data, "value", "evidence ref"))


def _parse_evidence_list(raw: Any, default_type: str = "simulation_trace", default_engine: str = "unknown") -> List[Evidence]:
    """
    Parse an evidence field (spec) which can be:
    - a list of Evidence objects, or
    - a single string (shorthand for local_id) → single Evidence with a default type/engine,
    - a single EvidenceRef dict → single Evidence with a default type/engine.
    Returns a list of Evidence objects.
    """
    if raw is None:
        return []

    # Handle list
    if isinstance(raw, list):
        evidence_list = []
        for item in raw:
            if isinstance(item, str):
                # Shorthand: just a string reference
                ref = EvidenceRef(type="local_id", value=item)
                evidence_list.append(Evidence(type=default_type, ref=ref, engine=default_engine))
            elif isinstance(item, dict):
                # Could be an evidence ref dict or a full evidence dict
                if "type" in item and "ref" in item and "engine" in item:
                    # It's a full Evidence dict
                    evidence_list.append(Evidence(
                        type=item["type"],
                        ref=_parse_evidence_ref(item["ref"]),
                        engine=item["engine"],
                        status=item.get("status"),
                    ))
                elif "type" in item and "value" in item:
                    # It's a ref dict
                    ref = _parse_evidence_ref(item)
                    evidence_list.append(Evidence(type=default_type, ref=ref, engine=default_engine))
                else:
                    raise SpecIRParseError(f"Invalid evidence entry: {item}")
            else:
                raise SpecIRParseError(f"Invalid evidence entry type: {type(item)}")
        return evidence_list

    # Single string shorthand
    if isinstance(raw, str):
        ref = EvidenceRef(type="local_id", value=raw)
        return [Evidence(type=default_type, ref=ref, engine=default_engine)]

    # Single dict (either ref or full evidence)
    if isinstance(raw, dict):
        if "type" in raw and "ref" in raw and "engine" in raw:
            # Full evidence
            return [Evidence(
                type=raw["type"],
                ref=_parse_evidence_ref(raw["ref"]),
                engine=raw["engine"],
                status=raw.get("status"),
            )]
        else:
            # Assume it's a ref
            ref = _parse_evidence_ref(raw)
            return [Evidence(type=default_type, ref=ref, engine=default_engine)]

    raise SpecIRParseError(f"Invalid evidence value: {raw}")


def _parse_parameter(data: Dict[str, Any]) -> Parameter:
    return Parameter(
        name=_require(data, "name", "parameter"),
        type=_require(data, "type", "parameter"),
        default=data.get("default"),
    )


def _parse_clock(data: Dict[str, Any]) -> Clock:
    return Clock(
        name=_require(data, "name", "clock"),
        edge=_require(data, "edge", "clock"),
        period=data.get("period"),
    )


def _parse_reset(data: Dict[str, Any]) -> Reset:
    return Reset(
        name=_require(data, "name", "reset"),
        polarity=_require(data, "polarity", "reset"),
        async_reset=_require(data, "async", "reset"),   # YAML key is "async"
        affects=_require(data, "affects", "reset"),
    )


def _parse_interface(data: Dict[str, Any]) -> Interface:
    return Interface(
        name=_require(data, "name", "interface"),
        direction=_require(data, "direction", "interface"),
        type=_require(data, "type", "interface"),
        protocol=data.get("protocol"),
    )


def _parse_user_type(data: Dict[str, Any]) -> UserType:
    return UserType(
        name=_require(data, "name", "type"),
        kind=_require(data, "kind", "type"),
        values=data.get("values"),
        fields=data.get("fields"),
        encoding=data.get("encoding"),
    )


def _parse_component(data: Dict[str, Any]) -> ComponentInstance:
    evidence = _parse_evidence_list(data.get("evidence"), default_type="simulation_trace", default_engine="unknown")
    return ComponentInstance(
        name=_require(data, "name", "component"),
        module=_require(data, "module", "component"),
        parameters=data.get("parameters", {}),
        port_map=data.get("port_map", {}),
        evidence=evidence,
    )


def _parse_state(data: Dict[str, Any]) -> State:
    evidence = _parse_evidence_list(data.get("evidence"), default_type="simulation_trace", default_engine="unknown")
    return State(
        name=_require(data, "name", "state"),
        kind=_require(data, "kind", "state"),
        type=_require(data, "type", "state"),
        initial=data.get("initial"),
        attributes=data.get("attributes", []),
        evidence=evidence,
    )


def _parse_rule(data: Dict[str, Any]) -> Rule:
    evidence = _parse_evidence_list(data.get("evidence"), default_type="simulation_trace", default_engine="unknown")
    return Rule(
        name=_require(data, "name", "rule"),
        condition=data.get("condition"),
        action=data.get("action", []),
        priority=data.get("priority"),
        attributes=data.get("attributes", []),
        evidence=evidence,
    )


def _parse_directive(data: Dict[str, Any]) -> Directive:
    return Directive(
        type=_require(data, "type", "directive"),
        name=_require(data, "name", "directive"),
        expression=_require(data, "expression", "directive"),
        clock=data.get("clock"),
        severity=data.get("severity"),
    )


def _parse_temporal_expr(data: Dict[str, Any]) -> TemporalExpr:
    kind = _require(data, "kind", "temporal expression")
    if kind not in ("always", "eventually", "until"):
        raise SpecIRParseError(f"Invalid temporal expression kind '{kind}'. Must be always, eventually, or until.")
    return TemporalExpr(
        kind=kind,
        operand=data.get("operand"),
        left=data.get("left"),
        right=data.get("right"),
        bound=data.get("bound"),
    )


def _parse_property(data: Dict[str, Any]) -> Property:
    evidence = _parse_evidence_list(data.get("evidence"), default_type="simulation_trace", default_engine="unknown")
    return Property(
        name=_require(data, "name", "property"),
        kind=_require(data, "kind", "property"),
        expression=_parse_temporal_expr(_require(data, "expression", "property")),
        assumes=data.get("assumes", []),
        guarantees=data.get("guarantees", []),
        proof_status=data.get("proof_status", "unproved"),
        evidence=evidence,
    )


def _parse_schedule(data: Dict[str, Any]) -> Schedule:
    return Schedule(
        kind=_require(data, "kind", "schedule"),
        rule_order=data.get("rule_order", []),
        conflict_sets=data.get("conflict_sets", []),
    )


def _parse_fairness(data: Dict[str, Any]) -> Fairness:
    return Fairness(
        name=_require(data, "name", "fairness"),
        type=_require(data, "type", "fairness"),
        condition=_require(data, "condition", "fairness"),
    )


def _parse_proof_obligation_feedback(data: Dict[str, Any]) -> ProofObligationFeedback:
    return ProofObligationFeedback(
        iteration=_require(data, "iteration", "feedback"),
        error=_require(data, "error", "feedback"),
        resolution=_require(data, "resolution", "feedback"),
    )


def _parse_metadata(data: Dict[str, Any]) -> Metadata:
    return Metadata(
        engine=data.get("engine"),
        options=data.get("options", {}),
    )


def _parse_proof_obligation(data: Dict[str, Any]) -> ProofObligation:
    feedback = []
    if "feedback" in data:
        feedback = [_parse_proof_obligation_feedback(fb) for fb in data["feedback"]]
    return ProofObligation(
        property=_require(data, "property", "proof obligation"),
        status=data.get("status", "unproved"),   # optional, defaults to "unproved"
        engine=_require(data, "engine", "proof obligation"),
        backend=data.get("backend"),
        artifact=data.get("artifact"),
        assumes=data.get("assumes", []),
        guarantees=data.get("guarantees", []),
        metadata=data.get("metadata", {}),
        confidence=data.get("confidence"),
        feedback=feedback,
    )


def _parse_module(data: Dict[str, Any]) -> Module:
    return Module(
        name=_require(data, "name", "module"),
        version=data.get("version"),
        parameters=[_parse_parameter(p) for p in data.get("parameters", [])],
        clocks=[_parse_clock(c) for c in data.get("clocks", [])],
        resets=[_parse_reset(r) for r in data.get("resets", [])],
        inputs=[_parse_interface(i) for i in data.get("inputs", [])],
        outputs=[_parse_interface(o) for o in data.get("outputs", [])],
        types=[_parse_user_type(t) for t in data.get("types", [])],
        components=[_parse_component(c) for c in data.get("components", [])],
        state=[_parse_state(s) for s in data.get("state", [])],
        rules=[_parse_rule(r) for r in data.get("rules", [])],
        directives=[_parse_directive(d) for d in data.get("directives", [])],
        properties=[_parse_property(p) for p in data.get("properties", [])],
        schedule=_parse_schedule(data["schedule"]) if "schedule" in data else None,
        fairness=[_parse_fairness(f) for f in data.get("fairness", [])],
        proof_obligations=[_parse_proof_obligation(po) for po in data.get("proof_obligations", [])],
        metadata=_parse_metadata(data["metadata"]) if "metadata" in data else None,
        evidence=_parse_evidence_list(data.get("evidence"), default_type="simulation_trace", default_engine="unknown"),
    )


def parse_specir(source: Union[str, Path]) -> SpecIR:
    """
    Parse a .specir YAML file into a SpecIR AST.

    Args:
        source: Path to the .specir file.

    Returns:
        SpecIR root object.

    Raises:
        SpecIRParseError: If the YAML is malformed or required fields missing.
        FileNotFoundError: If the file does not exist.
    """
    path = Path(source)
    if not path.exists():
        raise FileNotFoundError(f"SpecIR file not found: {path}")

    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise SpecIRParseError(f"YAML parsing error in {path}: {e}")

    if not isinstance(raw, dict):
        raise SpecIRParseError(f"Root of {path} must be a mapping (dictionary)")

    # Validate version
    version = raw.get("specir_version")
    if not version:
        raise SpecIRParseError("Missing 'specir_version' field")
    if version not in SUPPORTED_VERSIONS:
        logger.warning(f"Unrecognized specir_version '{version}'. Supported versions: {SUPPORTED_VERSIONS}. Proceeding, but validation may fail.")

    module_data = raw.get("module")
    if not module_data:
        raise SpecIRParseError("Missing 'module' field")
    if not isinstance(module_data, dict):
        raise SpecIRParseError("'module' must be a mapping")

    module = _parse_module(module_data)

    # Parse top-level optional metadata and evidence
    top_metadata = None
    if "metadata" in raw:
        top_metadata = _parse_metadata(raw["metadata"])
    top_evidence = _parse_evidence_list(raw.get("evidence"), default_type="simulation_trace", default_engine="unknown")

    return SpecIR(
        specir_version=version,
        module=module,
        metadata=top_metadata,
        evidence=top_evidence,
    )
