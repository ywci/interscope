# src/specir/dialects/koika_ir.py
#
# Kōika dialect – represents Kōika designs embedded in Coq.
# Provides operations: koika.rule, koika.design, koika.theorem.
# KoikaModule now optionally carries input/output interface information
# for RTL generation.

from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

from specir.dialects.spec_ir import Dialect, Operation, Type


class KoikaDialect(Dialect):
    name = "koika"


class KoikaRuleType(Type):
    pass


class KoikaDesignType(Type):
    pass


class KoikaTheoremType(Type):
    pass


@dataclass
class KoikaRuleOp(Operation):
    """A Kōika rule definition."""
    name: str = "koika.rule"
    rule_name: str = ""
    condition: str = ""               # Coq/Kōika boolean expression
    actions: List[str] = field(default_factory=list)  # list of Kōika action strings
    attributes: List[str] = field(default_factory=list)

    def __str__(self) -> str:
        cond_str = f"cond = {self.condition}" if self.condition else "cond = true"
        actions_str = "; ".join(self.actions)
        return f"koika.rule @{self.rule_name} {{ {cond_str} -> {actions_str} }}"


@dataclass
class KoikaDesignOp(Operation):
    """A Kōika design composed of rules."""
    name: str = "koika.design"
    design_name: str = ""
    rules: List[str] = field(default_factory=list)   # rule names
    schedule: str = "parallel"        # parallel, conflict_free, sequential

    def __str__(self) -> str:
        rules_str = ", ".join(self.rules)
        return f"koika.design @{self.design_name} {{ rules: [{rules_str}], schedule: {self.schedule} }}"


@dataclass
class KoikaTheoremOp(Operation):
    """A Coq theorem (proof obligation) for a Kōika design."""
    name: str = "koika.theorem"
    theorem_name: str = ""
    statement: str = ""               # Coq theorem statement (e.g., "forall st, reachable st -> ...")
    proof_script: Optional[str] = None   # Coq proof script (or "Admitted.")
    tactic_hints: List[str] = field(default_factory=list)  # suggested tactics for LLM

    def __str__(self) -> str:
        return f"koika.theorem @{self.theorem_name} {{ {self.statement} }}"


@dataclass
class KoikaModule:
    """Container for a Kōika design and its proofs.

    The optional *inputs* and *outputs* fields carry the design's interface
    information.  They are derived from the SpecIR specification and can be
    used by the RTL backend to generate proper Verilog ports.
    """
    name: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    state_definitions: List[str] = field(default_factory=list)   # Coq inductive for regfile, etc.
    rule_ops: List[KoikaRuleOp] = field(default_factory=list)
    design_op: Optional[KoikaDesignOp] = None
    theorem_ops: List[KoikaTheoremOp] = field(default_factory=list)
    inputs: List[Any] = field(default_factory=list)    # Interface objects (spec_ir.Interface or dicts)
    outputs: List[Any] = field(default_factory=list)   # Interface objects
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        lines = [f"koika.module @{self.name} {{"]
        for state in self.state_definitions:
            lines.append(f"  {state}")
        for rule in self.rule_ops:
            lines.append(f"  {rule}")
        if self.design_op:
            lines.append(f"  {self.design_op}")
        for thm in self.theorem_ops:
            lines.append(f"  {thm}")
        lines.append("}")
        return "\n".join(lines)


def from_spec_module(spec_module) -> KoikaModule:
    """
    Convert a SpecModule (from spec dialect) into a KoikaModule.

    This function delegates to the canonical lowering pass
    ``specir.lowering.spec_to_koika.convert``.
    """
    from specir.lowering.spec_to_koika import convert as spec_to_koika_convert
    return spec_to_koika_convert(spec_module)
