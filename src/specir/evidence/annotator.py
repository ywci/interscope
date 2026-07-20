# src/specir/evidence/annotator.py
#
# Helper functions for attaching evidence references to SpecIR AST nodes
# or dialect operations. Supports adding evidence entries to the registry
# and linking them to specific elements (modules, states, rules, properties, etc.)
# via unique IDs or URIs.

from typing import Optional, Union, Any
from pathlib import Path

from specir.parser.ast import (
    SpecIR, Module, State, Rule, Property, ProofObligation,
    Evidence, EvidenceRef, ComponentInstance, Directive
)
from specir.evidence.registry import EvidenceRegistry


def create_evidence_ref(evidence_type: str,
                        ref_type: str,
                        ref_value: str,
                        engine: str,
                        status: Optional[str] = None,
                        property_name: Optional[str] = None) -> Evidence:
    """
    Create an Evidence object (for attaching to AST nodes).

    Args:
        evidence_type: One of 'counterexample_trace', 'inductive_invariant',
                       'coq_theorem', 'acl2_theorem', 'simulation_trace'.
        ref_type: 'uri' or 'local_id'.
        ref_value: The reference (e.g., file URI or identifier).
        engine: Verification engine (e.g., 'BMC', 'IC3', 'theorem_proving').
        status: Optional status (e.g., 'active', 'proved', 'counterexample').
        property_name: Optional property name.

    Returns:
        Evidence dataclass instance.
    """
    ref = EvidenceRef(type=ref_type, value=ref_value)
    return Evidence(
        type=evidence_type,
        ref=ref,
        engine=engine,
        status=status,
    )


def add_evidence_to_registry(evidence: Evidence,
                             property_name: Optional[str] = None,
                             db_path: Optional[Path] = None) -> int:
    """
    Add an Evidence object to the evidence registry (SQLite database).

    Args:
        evidence: Evidence dataclass instance.
        property_name: Optional property name for the evidence.
        db_path: Optional path to the evidence database (default from config).

    Returns:
        The ID of the newly inserted entry.
    """
    registry = EvidenceRegistry(db_path=db_path)
    return registry.add_evidence(
        evidence_type=evidence.type,
        ref_type=evidence.ref.type,
        ref_value=evidence.ref.value,
        engine=evidence.engine,
        status=evidence.status,
        property_name=property_name
    )


def annotate_module(module: Module,
                    evidence: Evidence,
                    property_name: Optional[str] = None,
                    db_path: Optional[Path] = None) -> Module:
    """
    Attach an evidence reference to a Module (AST) and also add to registry.

    Args:
        module: The Module AST node.
        evidence: Evidence object to attach.
        property_name: Optional property name for the registry.
        db_path: Optional database path.

    Returns:
        The same module (with evidence appended).
    """
    add_evidence_to_registry(evidence, property_name=property_name, db_path=db_path)
    if not hasattr(module, 'evidence'):
        module.evidence = []
    module.evidence.append(evidence)
    return module


def annotate_state(state: State,
                   evidence: Evidence,
                   property_name: Optional[str] = None,
                   db_path: Optional[Path] = None) -> State:
    """Attach evidence to a State AST node (single EvidenceRef)."""
    add_evidence_to_registry(evidence, property_name=property_name, db_path=db_path)
    state.evidence = EvidenceRef(type=evidence.ref.type, value=evidence.ref.value)
    return state


def annotate_rule(rule: Rule,
                  evidence: Evidence,
                  property_name: Optional[str] = None,
                  db_path: Optional[Path] = None) -> Rule:
    """Attach evidence to a Rule AST node (single EvidenceRef)."""
    add_evidence_to_registry(evidence, property_name=property_name, db_path=db_path)
    rule.evidence = EvidenceRef(type=evidence.ref.type, value=evidence.ref.value)
    return rule


def annotate_property(prop: Property,
                      evidence: Evidence,
                      property_name: Optional[str] = None,
                      db_path: Optional[Path] = None) -> Property:
    """Attach evidence to a Property AST node (list of EvidenceRef)."""
    add_evidence_to_registry(evidence, property_name=property_name or prop.name, db_path=db_path)
    if not hasattr(prop, 'evidence') or prop.evidence is None:
        prop.evidence = []
    prop.evidence.append(EvidenceRef(type=evidence.ref.type, value=evidence.ref.value))
    return prop


def annotate_component(comp: ComponentInstance,
                       evidence: Evidence,
                       property_name: Optional[str] = None,
                       db_path: Optional[Path] = None) -> ComponentInstance:
    """Attach evidence to a ComponentInstance AST node (single EvidenceRef)."""
    add_evidence_to_registry(evidence, property_name=property_name, db_path=db_path)
    comp.evidence = EvidenceRef(type=evidence.ref.type, value=evidence.ref.value)
    return comp


def annotate_proof_obligation(po: ProofObligation,
                              evidence: Evidence,
                              db_path: Optional[Path] = None) -> ProofObligation:
    """
    Attach evidence to a ProofObligation (e.g., a proven theorem artifact).

    Sets the artifact's ``type`` and ``ref`` fields.  Any existing artifact
    dictionary is preserved; only the two keys are updated.
    """
    add_evidence_to_registry(evidence, property_name=po.property, db_path=db_path)
    if po.artifact is None:
        po.artifact = {}
    po.artifact['type'] = evidence.type
    po.artifact['ref'] = evidence.ref.value
    return po
