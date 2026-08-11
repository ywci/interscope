# src/specir/lowering/split_rules.py
#
# Automatic splitting of monolithic rules into per‑opcode rules.
#
# Many hardware designs express an “execute” rule whose action uses a
# deeply nested `ite` (if‑then‑else) to branch on an opcode or control
# signal.  Such rules produce a single `step` constructor in the Kōika
# model, making induction proofs cumbersome.
#
# This pass detects top‑level `ite` chains inside rule actions **only for
# rules that carry a specific attribute** (by default `split`).  It then
# replaces the monolithic rule with a set of mutually‑exclusive rules,
# one per branch.  The scheduler is adjusted to ``conflict_free`` so that
# at most one of the new rules fires per cycle, preserving the original
# semantics.

from __future__ import annotations

import copy
from typing import List, Optional, Tuple
from specir.dialects.spec_ir import (
    SpecModule,
    SpecRuleOp,
    SpecScheduleOp
)
from specir.utils.expr import parse_sexpr, ExprError, expr_to_string
from specir.utils.logger import get_logger

logger = get_logger(__name__)

_DEFAULT_SPLIT_ATTR = "split"


def split_rules(
    spec_module: SpecModule,
    split_attribute: str = _DEFAULT_SPLIT_ATTR,
) -> SpecModule:
    """
    Split monolithic rules that are marked with *split_attribute* and
    contain `ite` cascades.

    Returns a **new** ``SpecModule``; the original is unchanged.
    """
    new_mod = _copy_module_structure(spec_module)
    new_rules: List[SpecRuleOp] = []
    split_occurred = False

    for rule in spec_module.rule_ops:
        # Only split if the rule has the required attribute
        if split_attribute in (rule.rule_attributes or []):
            maybe_split = _try_split_rule(rule)
            if maybe_split is None:
                new_rules.append(copy.deepcopy(rule))
            else:
                split_occurred = True
                new_rules.extend(maybe_split)
        else:
            new_rules.append(copy.deepcopy(rule))

    if not split_occurred:
        return spec_module

    new_mod.rule_ops = new_rules

    # Adjust the schedule so the split rules are conflict‑free
    _make_conflict_free_for_split_rules(new_mod, spec_module.rule_ops, split_attribute)

    logger.info(
        "Split monolithic rule(s) in module '%s' into %d rules (attribute = '%s').",
        spec_module.name,
        len(new_rules),
        split_attribute
    )
    return new_mod


def _copy_module_structure(mod: SpecModule) -> SpecModule:
    """Shallow copy of the module that shares all non‑rule data."""
    return SpecModule(
        name=mod.name,
        version=mod.version,
        parameters=dict(mod.parameters),
        clocks=list(mod.clocks),
        resets=list(mod.resets),
        inputs=list(mod.inputs),
        outputs=list(mod.outputs),
        types=list(mod.types),
        components=list(mod.components),
        fairness=list(mod.fairness),
        state_ops=list(mod.state_ops),
        rule_ops=[],
        property_ops=list(mod.property_ops),
        directive_ops=list(mod.directive_ops),
        schedule_op=copy.deepcopy(mod.schedule_op) if mod.schedule_op else None,
        proof_obligations=list(mod.proof_obligations),
        metadata=dict(mod.metadata)
    )


def _make_conflict_free_for_split_rules(
    new_mod: SpecModule,
    original_rules: List[SpecRuleOp],
    split_attribute: str,
) -> None:
    """
    Ensure the schedule is ``conflict_free`` and put all rules that
    originated from the same monolithic rule into the same conflict set.
    """
    # Collect names of split rules – we use the naming convention
    # ``<original_name>_<N>``.
    split_groups: dict[str, list[str]] = {}
    for rule in new_mod.rule_ops:
        base = _original_rule_name(rule.rule_name)
        if base != rule.rule_name:
            split_groups.setdefault(base, []).append(rule.rule_name)

    if not split_groups:
        return

    existing = new_mod.schedule_op
    if existing is None:
        existing = SpecScheduleOp(kind="parallel")

    if existing.kind == "sequential":
        logger.warning(
            "Original schedule is sequential; switching to conflict_free "
            "for split rules.  Rule order within a conflict set is not "
            "specified – verify behaviour."
        )

    prev_sets: list[list[str]] = list(existing.conflict_sets) if existing.conflict_sets else []

    for rules_in_group in split_groups.values():
        prev_sets.append(rules_in_group)

    new_mod.schedule_op = SpecScheduleOp(
        kind="conflict_free",
        rule_order=[],
        conflict_sets=prev_sets
    )


def _original_rule_name(name: str) -> str:
    """Strip a trailing ``_<number>`` suffix, returning the base name."""
    parts = name.rsplit("_", 1)
    if len(parts) == 2 and parts[1].isdigit():
        return parts[0]
    return name


def _try_split_rule(rule: SpecRuleOp) -> Optional[List[SpecRuleOp]]:
    """
    Return a list of new ``SpecRuleOp`` instances if the rule can be
    split, or ``None`` if it should be kept as is.
    """
    # Parse all actions
    parsed_actions: list = []
    for action_str in rule.actions:
        try:
            parsed = parse_sexpr(action_str)
        except ExprError:
            logger.debug(
                "Rule '%s': action '%s' cannot be parsed – not splitting.",
                rule.rule_name,
                action_str
            )
            return None
        parsed_actions.append(parsed)

    # Find the first action that contains an `ite`
    split_idx = -1
    for i, act in enumerate(parsed_actions):
        if _contains_ite(act):
            split_idx = i
            break

    if split_idx == -1:
        return None  # no ite → nothing to split

    # Ensure no *other* action contains an `ite`
    for j, act in enumerate(parsed_actions):
        if j != split_idx and _contains_ite(act):
            raise ValueError(
                f"Rule '{rule.rule_name}' contains multiple independent `ite` "
                "expressions.  Automatic splitting is not supported for this "
                "case.  Please refactor the rule manually."
            )

    # Flatten the `ite` chain in the chosen action
    action_to_split = parsed_actions[split_idx]
    branches = _flatten_ite_chain(action_to_split)
    if branches is None:
        return None

    conditions, then_bodies, default_body = branches

    new_rules = []
    for idx, (branch_cond, branch_body) in enumerate(zip(conditions, then_bodies)):
        new_actions = [
            _serialise_action(act) for act in parsed_actions[:split_idx]
        ]
        new_actions.append(_serialise_action(branch_body))
        new_actions.extend(
            _serialise_action(act) for act in parsed_actions[split_idx + 1:]
        )

        combined_cond = _conjoin_conditions(rule.condition, branch_cond)

        new_rule = SpecRuleOp(
            rule_name=f"{rule.rule_name}_{idx}",
            condition=combined_cond,
            actions=new_actions,
            priority=rule.priority,
            rule_attributes=list(rule.rule_attributes)
        )
        new_rules.append(new_rule)

    if default_body is not None:
        new_actions = [
            _serialise_action(act) for act in parsed_actions[:split_idx]
        ]
        new_actions.append(_serialise_action(default_body))
        new_actions.extend(
            _serialise_action(act) for act in parsed_actions[split_idx + 1:]
        )

        neg_cond = _negate_disjunction(conditions)
        combined_cond = _conjoin_conditions(rule.condition, neg_cond)

        new_rule = SpecRuleOp(
            rule_name=f"{rule.rule_name}_{len(new_rules)}",
            condition=combined_cond,
            actions=new_actions,
            priority=rule.priority,
            rule_attributes=list(rule.rule_attributes)
        )
        new_rules.append(new_rule)

    return new_rules


def _contains_ite(expr) -> bool:
    """Return ``True`` if the expression contains an `ite` at any level."""
    if isinstance(expr, list) and len(expr) > 0:
        if expr[0] == "ite":
            return True
        for child in expr[1:]:
            if _contains_ite(child):
                return True
    return False


def _flatten_ite_chain(expr) -> Optional[Tuple[List[str], List[any], Optional[any]]]:
    """
    Flatten a nested ``(ite cond1 then1 (ite cond2 then2 … else))`` chain.

    Returns a tuple ``(conditions, bodies, default_body)`` where
    ``conditions`` and ``bodies`` are lists of equal length, and
    ``default_body`` is the final else branch (``None`` if the chain
    ends with an `ite` whose else is not a catch‑all).

    If *expr* does not start with `ite`, return ``None``.
    """
    if not (isinstance(expr, list) and len(expr) == 4 and expr[0] == "ite"):
        return None

    conditions: List[str] = []
    bodies: list = []
    current = expr
    while isinstance(current, list) and len(current) == 4 and current[0] == "ite":
        cond = current[1]
        then_body = current[2]
        else_body = current[3]

        conditions.append(_serialise_action(cond))
        bodies.append(then_body)
        current = else_body

    if isinstance(current, list) and len(current) > 0 and current[0] == "ite":
        return None   # should not happen

    return conditions, bodies, current if current != [] else None


def _conjoin_conditions(
    original_cond: Optional[str], new_cond: str
) -> Optional[str]:
    if original_cond is None:
        return new_cond
    orig_stripped = original_cond.strip()
    if orig_stripped in ("", "true", "True"):
        return new_cond
    return f"(and {orig_stripped} {new_cond})"


def _negate_disjunction(conditions: List[str]) -> str:
    if not conditions:
        return "true"
    if len(conditions) == 1:
        return f"(not {conditions[0]})"
    disj = f"(or {' '.join(conditions)})"
    return f"(not {disj})"


def _serialise_action(expr) -> str:
    return expr_to_string(expr)
