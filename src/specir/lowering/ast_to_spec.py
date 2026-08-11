# src/specir/lowering/ast_to_spec.py
#
# Canonical conversion from a parsed SpecIR AST (parser.ast.Module)
# into the spec dialect (spec_ir.SpecModule).
# All CLI modules and lowering passes should use this single entry point
# to avoid duplicated or inconsistent conversion logic.
# Revision: now converts types, components, and fairness; evidence is ignored.

from typing import List, Dict, Any, Optional
from specir.dialects.spec_ir import (
    SpecModule, SpecStateOp, SpecRuleOp, SpecPropertyOp, SpecDirectiveOp,
    SpecScheduleOp, Interface
)
from specir.utils.logger import get_logger

logger = get_logger(__name__)


def convert_ast_to_spec_module(ast_module) -> SpecModule:
    """
    Convert an AST Module (from parser.ast) into a SpecModule.

    This is the single source of truth for the AST → spec dialect lowering.
    Every CLI command (compile, verify, check, lift) should call this function
    instead of writing their own inline converters.

    Args:
        ast_module: The parser.ast.Module instance.

    Returns:
        A fully populated SpecModule.
    """
    spec_mod = SpecModule(
        name=ast_module.name,
        version=getattr(ast_module, 'version', '0.1'),
        parameters=_convert_parameters(getattr(ast_module, 'parameters', [])),
        clocks=_convert_clocks(getattr(ast_module, 'clocks', [])),
        resets=_convert_resets(getattr(ast_module, 'resets', [])),
        inputs=[_convert_interface(i) for i in getattr(ast_module, 'inputs', [])],
        outputs=[_convert_interface(o) for o in getattr(ast_module, 'outputs', [])],
        types=_convert_types(getattr(ast_module, 'types', [])),
        components=_convert_components(getattr(ast_module, 'components', [])),
        fairness=_convert_fairness(getattr(ast_module, 'fairness', []))
    )

    # State elements
    for state in getattr(ast_module, 'state', []):
        spec_mod.state_ops.append(SpecStateOp(
            state_name=state.name,
            kind=state.kind,
            data_type=_serialize_type(state.type),
            initial=state.initial,
            attributes=getattr(state, 'attributes', [])
        ))

    # Rules
    for rule in getattr(ast_module, 'rules', []):
        spec_mod.rule_ops.append(SpecRuleOp(
            rule_name=rule.name,
            condition=rule.condition,
            actions=rule.action,
            priority=getattr(rule, 'priority', None),
            rule_attributes=getattr(rule, 'attributes', [])
        ))

    # Properties
    for prop in getattr(ast_module, 'properties', []):
        expr = prop.expression   # TemporalExpr object
        spec_mod.property_ops.append(SpecPropertyOp(
            prop_name=prop.name,
            kind=prop.kind,
            expression={
                'kind': expr.kind,
                'operand': expr.operand,
                'left': getattr(expr, 'left', None),
                'right': getattr(expr, 'right', None),
                'bound': getattr(expr, 'bound', None)
            },
            assumes=prop.assumes,
            guarantees=prop.guarantees
        ))

    # Directives
    for directive in getattr(ast_module, 'directives', []):
        spec_mod.directive_ops.append(SpecDirectiveOp(
            directive_name=directive.name,
            kind=directive.type,  # AST uses "type" for assume/assert/cover
            expression=directive.expression,
            clock=getattr(directive, 'clock', None),
            severity=getattr(directive, 'severity', 'error')
        ))

    # Schedule
    schedule = getattr(ast_module, 'schedule', None)
    if schedule is not None:
        spec_mod.schedule_op = SpecScheduleOp(
            kind=schedule.kind,
            rule_order=schedule.rule_order,
            conflict_sets=schedule.conflict_sets
        )

    # Proof obligations (stored as dicts for now; may later become structured)
    for po in getattr(ast_module, 'proof_obligations', []):
        spec_mod.proof_obligations.append({
            'property': po.property,
            'status': po.status,
            'engine': po.engine,
            'backend': po.backend,
            'assumes': po.assumes,
            'guarantees': po.guarantees,
            'metadata': po.metadata,
            'confidence': po.confidence,
            'feedback': [{'iteration': fb.iteration, 'error': fb.error, 'resolution': fb.resolution}
                         for fb in getattr(po, 'feedback', [])]
        })

    # Top-level metadata
    if hasattr(ast_module, 'metadata') and ast_module.metadata:
        spec_mod.metadata = {
            'engine': ast_module.metadata.engine,
            'options': ast_module.metadata.options
        }

    logger.debug("Converted AST module '%s' to SpecModule", spec_mod.name)
    return spec_mod


def _serialize_type(type_spec) -> str:
    """Convert a type spec (string or dict) to a canonical string representation."""
    if isinstance(type_spec, str):
        return type_spec
    if isinstance(type_spec, dict):
        kind = type_spec.get('type', '')
        if kind == 'memory':
            elem = type_spec.get('elem', 'bits<32>')
            depth = type_spec.get('depth', '?')
            return f"memory({elem}, {depth})"
        if kind == 'array':
            elem = type_spec.get('elem', 'bits<8>')
            size = type_spec.get('size', '?')
            return f"array({elem}, {size})"
        if kind == 'enum':
            values = type_spec.get('values', [])
            return f"enum({', '.join(values)})"
        if kind == 'struct':
            fields = type_spec.get('fields', {})
            field_strs = [f"{k}:{v}" for k, v in fields.items()]
            return f"struct({{{', '.join(field_strs)}}})"
        return str(type_spec)
    return str(type_spec)


def _convert_parameters(params) -> Dict[str, Any]:
    """Convert list of Parameter AST objects to a dict."""
    return {p.name: {'type': p.type, 'default': p.default} for p in params}


def _convert_clocks(clocks) -> List[Dict[str, Any]]:
    """Convert list of Clock AST objects to dicts."""
    return [{'name': c.name, 'edge': c.edge, 'period': c.period} for c in clocks]


def _convert_resets(resets) -> List[Dict[str, Any]]:
    """Convert list of Reset AST objects to dicts."""
    return [{
        'name': r.name,
        'polarity': r.polarity,
        'async': getattr(r, 'async_reset', False),
        'affects': r.affects
    } for r in resets]


def _convert_interface(iface) -> Interface:
    """Convert an AST Interface to a dialect Interface object."""
    return Interface(
        name=iface.name,
        direction=iface.direction,
        data_type=_serialize_type(iface.type),
        protocol=getattr(iface, 'protocol', None)
    )


def _convert_types(types) -> List[Dict[str, Any]]:
    """Convert user-defined types (enum/struct) to dicts."""
    result = []
    for t in types:
        entry = {
            'name': t.name,
            'kind': t.kind
        }
        if t.kind == 'enum':
            entry['values'] = t.values
            entry['encoding'] = t.encoding
        elif t.kind == 'struct':
            entry['fields'] = t.fields
        result.append(entry)
    return result


def _convert_components(components) -> List[Dict[str, Any]]:
    """Convert component instances to dicts."""
    return [{
        'name': c.name,
        'module': c.module,
        'parameters': c.parameters,
        'port_map': c.port_map
    } for c in components]


def _convert_fairness(fairness) -> List[Dict[str, Any]]:
    """Convert fairness constraints to dicts."""
    return [{
        'name': f.name,
        'type': f.type,
        'condition': f.condition
    } for f in fairness]
