# src/isir/parser/parser.py
#
# YAML to AST parser for ISIR (.isir) files.
# Converts YAML dictionaries into the dataclasses defined in ast.py.

import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from isir.parser.ast import (
    Clock, ComponentInstance, Directive, Evidence, EvidenceRef, Fairness,
    Function, FunctionParam, Axiom, Invariant, Interface, Metadata, Module,
    Parameter, Property, ProofObligation, ProofObligationFeedback, Reset, Rule,
    Schedule, ISIR, State, TemporalExpr, UserType, Candidate, OneOf,
)
from isir.utils.logger import get_logger
from isir.utils.expr import parse_sexpr, expr_to_string

logger = get_logger(__name__)

SUPPORTED_VERSIONS = {"0.1"}


class ISIRParseError(Exception):
    """Exception raised when a .isir file is malformed."""
    pass


def _require(data: Dict[str, Any], key: str, context: str = "") -> Any:
    """Get a required field or raise ISIRParseError."""
    if key not in data:
        ctx = f" in {context}" if context else ""
        raise ISIRParseError(f"Missing required field '{key}'{ctx}")
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
        raise ISIRParseError(f"Evidence ref must be a string or object, got {type(data)}")
    ref_type = data.get("type", "local_id")
    if ref_type not in ("uri", "local_id"):
        raise ISIRParseError(f"Invalid evidence ref type '{ref_type}'. Must be 'uri' or 'local_id'.")
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

    if isinstance(raw, list):
        evidence_list = []
        for item in raw:
            if isinstance(item, str):
                ref = EvidenceRef(type="local_id", value=item)
                evidence_list.append(Evidence(type=default_type, ref=ref, engine=default_engine))
            elif isinstance(item, dict):
                if "type" in item and "ref" in item and "engine" in item:
                    evidence_list.append(Evidence(
                        type=item["type"],
                        ref=_parse_evidence_ref(item["ref"]),
                        engine=item["engine"],
                        status=item.get("status"),
                    ))
                elif "type" in item and "value" in item:
                    ref = _parse_evidence_ref(item)
                    evidence_list.append(Evidence(type=default_type, ref=ref, engine=default_engine))
                else:
                    raise ISIRParseError(f"Invalid evidence entry: {item}")
            else:
                raise ISIRParseError(f"Invalid evidence entry type: {type(item)}")
        return evidence_list

    if isinstance(raw, str):
        ref = EvidenceRef(type="local_id", value=raw)
        return [Evidence(type=default_type, ref=ref, engine=default_engine)]

    if isinstance(raw, dict):
        if "type" in raw and "ref" in raw and "engine" in raw:
            return [Evidence(
                type=raw["type"],
                ref=_parse_evidence_ref(raw["ref"]),
                engine=raw["engine"],
                status=raw.get("status")
            )]
        else:
            ref = _parse_evidence_ref(raw)
            return [Evidence(type=default_type, ref=ref, engine=default_engine)]

    raise ISIRParseError(f"Invalid evidence value: {raw}")


def _parse_parameter(data: Dict[str, Any]) -> Parameter:
    return Parameter(
        name=_require(data, "name", "parameter"),
        type=_require(data, "type", "parameter"),
        default=data.get("default")
    )


def _parse_clock(data: Dict[str, Any]) -> Clock:
    return Clock(
        name=_require(data, "name", "clock"),
        edge=_require(data, "edge", "clock"),
        period=data.get("period")
    )


def _parse_reset(data: Dict[str, Any]) -> Reset:
    return Reset(
        name=_require(data, "name", "reset"),
        polarity=_require(data, "polarity", "reset"),
        async_reset=_require(data, "async", "reset"),
        affects=_require(data, "affects", "reset")
    )


def _parse_interface(data: Dict[str, Any]) -> Interface:
    return Interface(
        name=_require(data, "name", "interface"),
        direction=_require(data, "direction", "interface"),
        type=_require(data, "type", "interface"),
        protocol=data.get("protocol")
    )


def _parse_user_type(data: Dict[str, Any]) -> UserType:
    return UserType(
        name=_require(data, "name", "type"),
        kind=_require(data, "kind", "type"),
        values=data.get("values"),
        fields=data.get("fields"),
        encoding=data.get("encoding")
    )


def _parse_component(data: Dict[str, Any]) -> ComponentInstance:
    evidence = _parse_evidence_list(data.get("evidence"), default_type="simulation_trace", default_engine="unknown")
    return ComponentInstance(
        name=_require(data, "name", "component"),
        module=_require(data, "module", "component"),
        parameters=data.get("parameters", {}),
        port_map=data.get("port_map", {}),
        evidence=evidence
    )


def _parse_state(data: Dict[str, Any]) -> State:
    evidence = _parse_evidence_list(data.get("evidence"), default_type="simulation_trace", default_engine="unknown")
    return State(
        name=_require(data, "name", "state"),
        kind=_require(data, "kind", "state"),
        type=_require(data, "type", "state"),
        initial=data.get("initial"),
        attributes=data.get("attributes", []),
        evidence=evidence
    )


def _parse_rule(data: Dict[str, Any]) -> Rule:
    evidence = _parse_evidence_list(data.get("evidence"), default_type="simulation_trace", default_engine="unknown")
    return Rule(
        name=_require(data, "name", "rule"),
        condition=data.get("condition"),
        action=data.get("action", []),
        priority=data.get("priority"),
        attributes=data.get("attributes", []),
        evidence=evidence
    )


def _parse_directive(data: Dict[str, Any]) -> Directive:
    return Directive(
        type=_require(data, "type", "directive"),
        name=_require(data, "name", "directive"),
        expression=_require(data, "expression", "directive"),
        clock=data.get("clock"),
        severity=data.get("severity")
    )


def _parse_temporal_expr(data: Dict[str, Any]) -> TemporalExpr:
    kind = _require(data, "kind", "temporal expression")
    if kind not in ("always", "eventually", "until", "combinational", "transition", "independence", "after"):
        raise ISIRParseError(
            f"Invalid temporal expression kind '{kind}'. Must be always, eventually, until, combinational, transition, independence, or after."
        )
    if kind == "combinational" and data.get("reference") is None:
        raise ISIRParseError("Combinational property requires a 'reference' golden expression.")
    if kind == "transition" and data.get("operand") is None:
        raise ISIRParseError("Transition property requires an 'operand' over the next state.")
    if kind == "after" and data.get("bound") is None:
        raise ISIRParseError("Bounded (after) property requires a numeric 'bound'.")
    if kind == "independence":
        if data.get("operand") is None:
            raise ISIRParseError("Independence property requires an 'operand' expression.")
        independent_of = data.get("independent_of")
        if not isinstance(independent_of, list) or not independent_of:
            raise ISIRParseError("Independence property requires a non-empty 'independent_of' list of input names.")
    return TemporalExpr(
        kind=kind,
        operand=data.get("operand"),
        left=data.get("left"),
        right=data.get("right"),
        bound=data.get("bound"),
        reference=data.get("reference"),
        independent_of=data.get("independent_of"),
        rule=data.get("rule")
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
        evidence=evidence
    )


def _parse_schedule(data: Dict[str, Any]) -> Schedule:
    return Schedule(
        kind=_require(data, "kind", "schedule"),
        rule_order=data.get("rule_order", []),
        conflict_sets=data.get("conflict_sets", [])
    )


def _parse_fairness(data: Dict[str, Any]) -> Fairness:
    return Fairness(
        name=_require(data, "name", "fairness"),
        type=_require(data, "type", "fairness"),
        condition=_require(data, "condition", "fairness")
    )


def _parse_function(data: Dict[str, Any]) -> Function:
    params = []
    for p in data.get("params", []):
        if not isinstance(p, dict) or "name" not in p or "type" not in p:
            raise ISIRParseError("Function params must be mappings with 'name' and 'type'.")
        params.append(FunctionParam(name=p["name"], type=p["type"]))
    return Function(
        name=_require(data, "name", "function"),
        params=params,
        return_type=data.get("return", "bits<1>"),
        body=data.get("body"),
        recursive=bool(data.get("recursive", False)),
        measure=data.get("measure")
    )


def _parse_axiom(data: Dict[str, Any]) -> Axiom:
    forall_vars = []
    for p in data.get("forall", []):
        if not isinstance(p, dict) or "name" not in p or "type" not in p:
            raise ISIRParseError("Axiom 'forall' binders must be mappings with 'name' and 'type'.")
        forall_vars.append(FunctionParam(name=p["name"], type=p["type"]))
    return Axiom(
        name=_require(data, "name", "axiom"),
        forall_vars=forall_vars,
        statement=_require(data, "statement", "axiom")
    )


def _parse_invariant(data: Dict[str, Any]) -> Invariant:
    return Invariant(
        name=_require(data, "name", "invariant"),
        operand=_require(data, "operand", "invariant"),
        assumed=bool(data.get("assumed", False))
    )


def _parse_proof_obligation_feedback(data: Dict[str, Any]) -> ProofObligationFeedback:
    return ProofObligationFeedback(
        iteration=_require(data, "iteration", "feedback"),
        error=_require(data, "error", "feedback"),
        resolution=_require(data, "resolution", "feedback")
    )


def _parse_metadata(data: Dict[str, Any]) -> Metadata:
    return Metadata(
        engine=data.get("engine"),
        options=data.get("options", {})
    )


def _parse_proof_obligation(data: Dict[str, Any]) -> ProofObligation:
    """
    Parse a proof obligation from YAML data.

    PERF-specific fields are extracted from metadata.perf and mapped to
    the corresponding fields on the ProofObligation dataclass.
    """
    feedback = []
    if "feedback" in data:
        feedback = [_parse_proof_obligation_feedback(fb) for fb in data["feedback"]]

    metadata = data.get("metadata", {})
    perf_data = metadata.get("perf", {})

    perf_beam_size = perf_data.get("beam_size")
    if perf_beam_size is not None:
        if not isinstance(perf_beam_size, int) or perf_beam_size < 1:
            raise ISIRParseError(
                f"perf.beam_size must be a positive integer, got {perf_beam_size}"
            )

    perf_branches = perf_data.get("branches_per_node")
    if perf_branches is not None:
        if not isinstance(perf_branches, int) or perf_branches < 1:
            raise ISIRParseError(
                f"perf.branches_per_node must be a positive integer, got {perf_branches}"
            )

    perf_depth_limit = perf_data.get("depth_limit")
    if perf_depth_limit is not None:
        if not isinstance(perf_depth_limit, int) or perf_depth_limit < 1:
            raise ISIRParseError(
                f"perf.depth_limit must be a positive integer, got {perf_depth_limit}"
            )

    perf_primary_dimension = perf_data.get("primary_dimension")
    if perf_primary_dimension is not None and not isinstance(perf_primary_dimension, str):
        raise ISIRParseError(
            f"perf.primary_dimension must be a string, got {type(perf_primary_dimension)}"
        )

    perf_dimensions = perf_data.get("dimensions")
    if perf_dimensions is not None:
        if not isinstance(perf_dimensions, list):
            raise ISIRParseError(
                f"perf.dimensions must be a list of strings, got {type(perf_dimensions)}"
            )
        if not perf_dimensions:
            raise ISIRParseError("perf.dimensions list cannot be empty")
        for dim in perf_dimensions:
            if not isinstance(dim, str):
                raise ISIRParseError(
                    f"perf.dimensions must contain strings, got {type(dim)}"
                )

    perf_generation_temperature = perf_data.get("generation_temperature")
    if perf_generation_temperature is not None:
        if not isinstance(perf_generation_temperature, (int, float)):
            raise ISIRParseError(
                f"perf.generation_temperature must be a number, got {type(perf_generation_temperature)}"
            )
        if not 0.0 <= perf_generation_temperature <= 1.0:
            raise ISIRParseError(
                f"perf.generation_temperature must be between 0.0 and 1.0, "
                f"got {perf_generation_temperature}"
            )

    perf_trace_alignment_weight = perf_data.get("trace_alignment_weight")
    if perf_trace_alignment_weight is not None:
        if not isinstance(perf_trace_alignment_weight, (int, float)):
            raise ISIRParseError(
                f"perf.trace_alignment_weight must be a number, got {type(perf_trace_alignment_weight)}"
            )
        if not 0.0 <= perf_trace_alignment_weight <= 1.0:
            raise ISIRParseError(
                f"perf.trace_alignment_weight must be between 0.0 and 1.0, "
                f"got {perf_trace_alignment_weight}"
            )

    # Validate that primary_dimension is in dimensions if both are set
    if perf_primary_dimension is not None and perf_dimensions is not None:
        if perf_primary_dimension not in perf_dimensions:
            raise ISIRParseError(
                f"perf.primary_dimension '{perf_primary_dimension}' must be one of "
                f"perf.dimensions: {perf_dimensions}"
            )

    # Determine engine - support "perf" as a valid engine value
    engine = data.get("engine", "theorem_proving")
    if engine not in ("theorem_proving", "model_checking", "simulation", "perf"):
        logger.warning(
            f"Unknown engine '{engine}' in proof obligation, "
            f"defaulting to 'theorem_proving'"
        )
        engine = "theorem_proving"

    return ProofObligation(
        property=_require(data, "property", "proof obligation"),
        status=data.get("status", "unproved"),
        engine=engine,
        backend=data.get("backend"),
        artifact=data.get("artifact"),
        assumes=data.get("assumes", []),
        guarantees=data.get("guarantees", []),
        metadata=metadata,
        confidence=data.get("confidence"),
        feedback=feedback,
        perf_beam_size=perf_beam_size,
        perf_branches=perf_branches,
        perf_depth_limit=perf_depth_limit,
        perf_primary_dimension=perf_primary_dimension,
        perf_dimensions=perf_dimensions,
        perf_generation_temperature=perf_generation_temperature,
        perf_trace_alignment_weight=perf_trace_alignment_weight
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
        functions=[_parse_function(f) for f in data.get("functions", [])],
        axioms=[_parse_axiom(a) for a in data.get("axioms", [])],
        invariants=[_parse_invariant(i) for i in data.get("invariants", [])],
        schedule=_parse_schedule(data["schedule"]) if "schedule" in data else None,
        fairness=[_parse_fairness(f) for f in data.get("fairness", [])],
        proof_obligations=[_parse_proof_obligation(po) for po in data.get("proof_obligations", [])],
        metadata=_parse_metadata(data["metadata"]) if "metadata" in data else None,
        evidence=_parse_evidence_list(data.get("evidence"), default_type="simulation_trace", default_engine="unknown")
    )


def _substitute_params(obj: Any, params: Dict[str, Any]) -> Any:
    """Recursively replace ``$name`` references in string fields with parameter values."""
    if isinstance(obj, str):
        for name, value in params.items():
            obj = obj.replace(f"${name}", str(value))
        return obj
    if isinstance(obj, list):
        return [_substitute_params(x, params) for x in obj]
    if isinstance(obj, dict):
        return {k: _substitute_params(v, params) for k, v in obj.items()}
    return obj


def _instantiate(obj: Any, var: str, value: int) -> Any:
    """Replace ``{var}`` references with an integer value, recursing."""
    if isinstance(obj, str):
        return obj.replace("{" + var + "}", str(value))
    if isinstance(obj, list):
        return [_instantiate(x, var, value) for x in obj]
    if isinstance(obj, dict):
        return {k: _instantiate(v, var, value) for k, v in obj.items()}
    return obj


def _expand_repeats(obj: Any) -> Any:
    """Expand ``repeat: {var, range, items}`` blocks into N instantiated copies.

    A ``repeat`` dict inside a list expands to ``range`` copies of ``items``,
    with ``{var}`` replaced by the index.  Nested repeats are supported.
    """
    if isinstance(obj, list):
        result = []
        for x in obj:
            if isinstance(x, dict) and "repeat" in x:
                rep = x["repeat"]
                var = rep.get("var", "i")
                rng = int(rep.get("range", 0))
                items = rep.get("items", [])
                for i in range(rng):
                    result.extend(_expand_repeats(_instantiate(items, var, i)))
            else:
                result.append(_expand_repeats(x))
        return result
    if isinstance(obj, dict):
        return {k: _expand_repeats(v) for k, v in obj.items()}
    return obj


def _expand_reductions(raw: Any) -> Any:
    """Expand named ``reduce`` folds and replace ``@name`` references.

    A ``reduce`` entry ``{name, var, range, init, step}`` builds a nested
    expression by left-folding ``step`` over ``range`` indices, substituting
    ``{acc}`` (the accumulated expression) and ``{var}`` (the index).  The
    resulting string then replaces every ``@name`` reference anywhere in the
    design.  ``@name(a1, a2, ...)`` passes positional arguments, substituted
    for ``$1``, ``$2``, ... inside the folded expression.  This gives general-N
    reductions (N-way ``or``, "find first" ``ite``) without design-specific
    helpers.
    """
    import re

    module = raw.get("module", {})
    if not isinstance(module, dict):
        return raw
    reductions = module.get("reductions", [])
    if not reductions:
        return raw

    folded: Dict[str, str] = {}
    for r in reductions:
        name = r.get("name")
        if not name:
            continue
        var = r.get("var", "j")
        rng = int(r.get("range", 0))
        init = str(r.get("init", ""))
        step = str(r.get("step", ""))
        acc = init
        for idx in range(rng):
            acc = step.replace("{acc}", acc).replace("{" + var + "}", str(idx))
        folded[name] = acc

    def _substitute(obj: Any) -> Any:
        if isinstance(obj, str):
            for name, val in folded.items():
                pattern = re.compile(r"@" + re.escape(name) + r"(?:\(([^)]*)\))?")
                def _repl(match: Any) -> str:
                    args = match.group(1)
                    if args is None:
                        return val
                    result = val
                    for k, arg in enumerate(a.strip() for a in args.split(",")):
                        result = result.replace(f"${k + 1}", arg)
                    return result
                obj = pattern.sub(_repl, obj)
            return obj
        if isinstance(obj, list):
            return [_substitute(x) for x in obj]
        if isinstance(obj, dict):
            return {k: _substitute(v) for k, v in obj.items()}
        return obj

    result = _substitute(raw)
    # The reduce templates are consumed; drop them before schema validation.
    if isinstance(result.get("module"), dict):
        result["module"].pop("reductions", None)
    return result


def _resolve_component_path(base_path: Path, module_ref: str) -> Path:
    """Resolve a component's ``module`` reference to an ``.isir`` file path.

    Tries the parent file's directory first (like ``#include``), then the
    current working directory, then the reference as given.
    """
    ref = Path(module_ref)
    if ref.is_absolute():
        return ref
    for candidate in (base_path.parent / ref, Path.cwd() / ref, ref):
        if candidate.exists():
            return candidate
    return base_path.parent / ref


def _build_name_map(child_module: Dict[str, Any], prefix: str, port_map: Dict[str, Any]) -> Dict[str, str]:
    """Map every child identifier to its flattened (prefixed/bound) parent name."""
    name_map: Dict[str, str] = {}
    for key in ("inputs", "outputs", "state"):
        for item in child_module.get(key, []) or []:
            n = item.get("name") if isinstance(item, dict) else None
            if n:
                name_map[n] = str(port_map.get(n, f"{prefix}_{n}"))
    for key in ("functions", "rules", "properties"):
        for item in child_module.get(key, []) or []:
            n = item.get("name") if isinstance(item, dict) else None
            if n:
                name_map[n] = f"{prefix}_{n}"
    return name_map


def _substitute_sexpr_names(expr: Any, name_map: Dict[str, str]) -> Any:
    """Recursively replace identifier atoms in a parsed sexpr."""
    if isinstance(expr, str):
        return name_map.get(expr, expr)
    if isinstance(expr, list):
        return [_substitute_sexpr_names(e, name_map) for e in expr]
    return expr


def _substitute_sexpr_string(s: Any, name_map: Dict[str, str]) -> Any:
    """Parse a sexpr string, substitute names, and re-serialize it."""
    if not isinstance(s, str):
        return s
    try:
        return expr_to_string(_substitute_sexpr_names(parse_sexpr(s), name_map))
    except Exception:
        return s


def _merge_modules(parent: Dict[str, Any], child: Dict[str, Any]) -> None:
    """Merge the child's flattened state/ports/functions/rules/properties into the parent."""
    for key in ("state", "inputs", "outputs", "functions", "rules", "properties", "axioms", "invariants", "proof_obligations"):
        items = child.get(key, [])
        if items:
            parent.setdefault(key, [])
            parent[key].extend(items)


def _unfold_function_bodies(sexpr_str: Any, functions: List[Dict[str, Any]]) -> Any:
    """Beta-reduce user function calls in a sexpr using their declared bodies.

    E.g. with ``is_modified(s) = (eq s 3)``, the call ``(is_modified (read c0_state))``
    becomes ``(eq (read c0_state) 3)``.  Nested calls are reduced recursively.
    """
    if not sexpr_str or not functions:
        return sexpr_str
    fn_map = {}
    for fn in functions:
        name = fn.get("name")
        body = fn.get("body")
        params = [p.get("name") for p in (fn.get("params") or [])]
        if name and body is not None:
            fn_map[name] = (params, parse_sexpr(body) if isinstance(body, str) else body)
    if not fn_map:
        return sexpr_str
    try:
        node = parse_sexpr(sexpr_str) if isinstance(sexpr_str, str) else sexpr_str
    except Exception:
        return sexpr_str

    def _subst(n, sub):
        if isinstance(n, str):
            return sub.get(n, n)
        if isinstance(n, list):
            return [_subst(x, sub) for x in n]
        return n

    def _unfold(n, depth=0):
        if depth > 32:
            return n
        if isinstance(n, list) and n and isinstance(n[0], str) and n[0] in fn_map:
            params, body = fn_map[n[0]]
            args = n[1:]
            sub = {params[i]: args[i] for i in range(min(len(params), len(args)))}
            return _unfold(_subst(body, sub), depth + 1)
        if isinstance(n, list):
            return [_unfold(x, depth) for x in n]
        return n

    return expr_to_string(_unfold(node))


def _flatten_components(raw: Dict[str, Any], base_path: Path) -> Dict[str, Any]:
    """Expand hierarchical ``components`` into flattened, prefixed declarations.

    Each component names an ``.isir`` module (by path).  Its state, ports,
    functions, rules and properties are loaded, prefixed with the instance
    name, and merged into the parent; ``port_map`` rebinds child ports to
    parent signals instead of the prefix.
    """
    module = raw.get("module", {})
    if not isinstance(module, dict):
        return raw
    components = module.get("components", [])
    if not components:
        return raw

    for comp in components:
        if not isinstance(comp, dict):
            continue
        name = comp.get("name")
        module_ref = comp.get("module")
        if not name or not module_ref:
            continue
        overrides = comp.get("parameters", {}) or {}
        port_map = comp.get("port_map", {}) or {}
        lift_props = comp.get("lift_properties", True)
        # lift_properties modes:
        #   true/"obligations" (default) : lift and re-prove the child's obligations
        #   false/"drop"                : drop the child's properties/invariants
        #   "invariant"                 : lift safety/always properties as *assumed*
        #                                 reachable invariants (reuse, don't re-prove)
        if lift_props is False or lift_props == "drop":
            lift_mode = "drop"
        elif lift_props == "invariant":
            lift_mode = "invariant"
        else:
            lift_mode = "obligations"

        path = _resolve_component_path(base_path, str(module_ref))
        child = load_expanded_raw(path, parameter_overrides=overrides)
        child_module = child.get("module", {})
        if lift_mode == "drop":
            child_module["properties"] = []
            child_module["proof_obligations"] = []
            child_module["invariants"] = []
        name_map = _build_name_map(child_module, str(name), port_map)

        # Drop child ports *and wires* bound via `port_map`: they are wired to
        # parent signals, not promoted/merged into the parent.
        bound_names = {str(k) for k in port_map}
        for key in ("inputs", "outputs", "state"):
            child_module[key] = [
                item for item in (child_module.get(key, []) or [])
                if not (isinstance(item, dict) and item.get("name") in bound_names)
            ]

        # Prefix declaration names.
        for key in ("state", "inputs", "outputs", "functions", "rules", "properties", "axioms", "invariants"):
            for item in child_module.get(key, []) or []:
                if isinstance(item, dict) and item.get("name"):
                    item["name"] = name_map.get(item["name"], f"{name}_{item['name']}")

        # Substitute references inside expressions.
        for fn in child_module.get("functions", []) or []:
            fn["body"] = _substitute_sexpr_string(fn.get("body"), name_map)
        for rule in child_module.get("rules", []) or []:
            rule["condition"] = _substitute_sexpr_string(rule.get("condition"), name_map)
            rule["action"] = [_substitute_sexpr_string(a, name_map) for a in (rule.get("action") or [])]
        for prop in child_module.get("properties", []) or []:
            expr = prop.get("expression", {}) if isinstance(prop.get("expression"), dict) else {}
            if "operand" in expr:
                expr["operand"] = _substitute_sexpr_string(expr["operand"], name_map)
            if "rule" in expr and expr["rule"] in name_map:
                expr["rule"] = name_map[expr["rule"]]
        for ax in child_module.get("axioms", []) or []:
            ax["statement"] = _substitute_sexpr_string(ax.get("statement"), name_map)
        for inv in child_module.get("invariants", []) or []:
            inv["operand"] = _substitute_sexpr_string(inv.get("operand"), name_map)
        for po in child_module.get("proof_obligations", []) or []:
            if isinstance(po, dict) and po.get("property") in name_map:
                po["property"] = name_map[po["property"]]

        # lift_properties: invariant — convert the child's safety/always
        # properties into assumed reachable invariants (reuse, don't re-prove).
        if lift_mode == "invariant":
            lifted_invariants = []
            for prop in child_module.get("properties", []) or []:
                if prop.get("kind") != "safety":
                    continue
                expr = prop.get("expression", {})
                if not isinstance(expr, dict) or expr.get("kind") != "always":
                    continue
                operand = expr.get("operand")
                if operand is None:
                    continue
                # Unfold the child's user functions so the lifted invariant is in
                # primitive operators, matching the parent's own (unfolded) form.
                operand = _unfold_function_bodies(
                    operand, child_module.get("functions", []) or []
                )
                lifted_invariants.append({
                    "name": prop.get("name"),
                    "operand": operand,
                    "assumed": True,
                })
            child_module.setdefault("invariants", []).extend(lifted_invariants)
            child_module["properties"] = []
            child_module["proof_obligations"] = []

        _merge_modules(module, child_module)

    module.pop("components", None)
    return raw


def load_expanded_raw(source: Union[str, Path], parameter_overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Load a .isir file, substitute parameters, and expand repeats.

    Returns the fully expanded raw YAML dictionary (before AST parsing), so
    callers can validate or inspect the resolved design.
    """
    path = Path(source)
    if not path.exists():
        raise FileNotFoundError(f"ISIR file not found: {path}")

    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ISIRParseError(f"YAML parsing error in {path}: {e}")

    if not isinstance(raw, dict):
        raise ISIRParseError(f"Root of {path} must be a dictionary")

    module_raw = raw.get("module", {})
    params: Dict[str, Any] = {}
    if isinstance(module_raw, dict):
        for p in module_raw.get("parameters", []) or []:
            if isinstance(p, dict) and "name" in p:
                params[p["name"]] = p.get("default")
    if parameter_overrides:
        params.update(parameter_overrides)
    raw = _substitute_params(raw, params)
    raw = _expand_reductions(raw)
    raw = _expand_repeats(raw)
    raw = _flatten_components(raw, path)
    return raw


def parse_isir(source: Union[str, Path], parameter_overrides: Optional[Dict[str, Any]] = None) -> ISIR:
    """
    Parse a .isir YAML file into a ISIR AST.

    Args:
        source: Path to the .isir file.
        parameter_overrides: Optional mapping overriding module parameter defaults.
            ``$name`` references anywhere in the design are substituted with the
            resolved parameter values before parsing, and ``repeat`` blocks are
            expanded.

    Returns:
        ISIR root object.

    Raises:
        ISIRParseError: If the YAML is malformed or required fields missing.
        FileNotFoundError: If the file does not exist.
    """
    raw = load_expanded_raw(source, parameter_overrides)

    version = raw.get("isir_version")
    if not version:
        raise ISIRParseError("Missing 'isir_version' field")
    if version not in SUPPORTED_VERSIONS:
        logger.warning(
            f"Unrecognized isir_version '{version}'. "
            f"Supported versions: {SUPPORTED_VERSIONS}. Proceeding, but validation may fail."
        )

    module_data = raw.get("module")
    if not module_data:
        raise ISIRParseError("Missing 'module' field")
    if not isinstance(module_data, dict):
        raise ISIRParseError("'module' must be a mapping")

    module = _parse_module(module_data)

    top_metadata = None
    if "metadata" in raw:
        top_metadata = _parse_metadata(raw["metadata"])
    top_evidence = _parse_evidence_list(raw.get("evidence"), default_type="simulation_trace", default_engine="unknown")

    return ISIR(
        isir_version=version,
        module=module,
        metadata=top_metadata,
        evidence=top_evidence
    )
