# src/specir/dialects/acl2_ir.py
#
# ACL2 dialect – represents ACL2 functional models and proof obligations.
# Provides operations: acl2.defun, acl2.defthm, acl2.defun-sk.

from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

from specir.dialects.spec_ir import Dialect, Operation, Type


class ACL2Dialect(Dialect):
    name = "acl2"


class ACL2DefunType(Type):
    pass


class ACL2DefthmType(Type):
    pass


class ACL2DefunSkType(Type):
    pass


@dataclass
class ACL2DefunOp(Operation):
    """ACL2 function definition (defun)."""
    op_name: str = "acl2.defun"
    func_name: str = ""
    args: List[str] = field(default_factory=list)   # list of argument names
    body: str = ""                                   # ACL2 term
    guard: Optional[str] = None                      # optional guard
    mode: str = ":logic"                             # :logic or :program
    verify_guards: bool = True

    def __str__(self) -> str:
        args_str = " ".join(self.args)
        guard_str = f" :guard {self.guard}" if self.guard else ""
        mode_str = f" :mode {self.mode}" if self.mode != ":logic" else ""
        return f"acl2.defun @{self.func_name} ({args_str}){guard_str}{mode_str} -> {self.body}"


@dataclass
class ACL2DefthmOp(Operation):
    """ACL2 theorem (defthm)."""
    op_name: str = "acl2.defthm"
    thm_name: str = ""
    statement: str = ""               # ACL2 formula
    hints: List[str] = field(default_factory=list)   # :hints ((...))
    rule_classes: List[str] = field(default_factory=list)  # :rewrite, :linear, etc.
    enabled: bool = True

    def __str__(self) -> str:
        hints_str = " ".join(self.hints)
        return f"acl2.defthm @{self.thm_name} {{ {self.statement} }} hints: [{hints_str}]"


@dataclass
class ACL2DefunSkOp(Operation):
    """ACL2 existentially quantified function (defun-sk)."""
    op_name: str = "acl2.defun-sk"
    pred_name: str = ""
    exists_vars: List[str] = field(default_factory=list)  # variables bound by exists
    body: str = ""                    # formula with exists
    quantifier: str = "exists"        # exists or forall
    skolem_name: Optional[str] = None
    thm_name: Optional[str] = None

    def __str__(self) -> str:
        vars_str = " ".join(self.exists_vars)
        return f"acl2.defun-sk @{self.pred_name} (exists ({vars_str}) {self.body})"


@dataclass
class ACL2Module:
    """Container for ACL2 functions and theorems."""
    name: str
    defuns: List[ACL2DefunOp] = field(default_factory=list)
    defthms: List[ACL2DefthmOp] = field(default_factory=list)
    defun_sk_ops: List[ACL2DefunSkOp] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        lines = [f"acl2.module @{self.name} {{"]
        for d in self.defuns:
            lines.append(f"  {d}")
        for t in self.defthms:
            lines.append(f"  {t}")
        for ds in self.defun_sk_ops:
            lines.append(f"  {ds}")
        lines.append("}")
        return "\n".join(lines)


def from_spec_module(spec_module) -> ACL2Module:
    """
    Convert a SpecModule into an ACL2Module.
    This will be implemented in lowering/spec_to_acl2.py.
    """
    raise NotImplementedError("Conversion from SpecModule to ACL2Module not yet implemented")
