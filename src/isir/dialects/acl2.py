# src/isir/dialects/acl2.py
#
# ACL2 dialect – represents ACL2 functional models and proof obligations.
# Provides operations: acl2.defun, acl2.defthm, acl2.defun-sk.

from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from isir.dialects.isir import Dialect, Operation, Type


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

    def to_lisp(self) -> str:
        """Loadable ACL2 `(defun ...)` form."""
        args_str = " ".join(self.args)
        xargs = []
        if self.guard:
            g = f":guard {self.guard}"
            if not self.verify_guards:
                g += " :verify-guards nil"
            xargs.append(g)
        if self.mode and self.mode != ":logic":
            xargs.append(f":mode {self.mode}")
        if xargs:
            declare = f"(declare (xargs {' '.join(xargs)}))"
            return f"(defun {self.func_name} ({args_str})\n  {declare}\n  {self.body})"
        return f"(defun {self.func_name} ({args_str})\n  {self.body})"


@dataclass
class ACL2DefthmOp(Operation):
    """ACL2 theorem (defthm) or axiom (defaxiom)."""
    op_name: str = "acl2.defthm"
    thm_name: str = ""
    statement: str = ""               # ACL2 formula
    hints: List[str] = field(default_factory=list)   # :hints ((...))
    rule_classes: List[str] = field(default_factory=list)  # :rewrite, :linear, etc.
    enabled: bool = True
    axiom: bool = False               # True => defaxiom (unproved)
    skip_proofs: bool = False         # True => wrap in (skip-proofs ...)

    def __str__(self) -> str:
        hints_str = " ".join(self.hints)
        return f"acl2.defthm @{self.thm_name} {{ {self.statement} }} hints: [{hints_str}]"

    def to_lisp(self) -> str:
        """Loadable ACL2 `(defthm ...)` / `(defaxiom ...)` / `(skip-proofs ...)`."""
        head = "defaxiom" if self.axiom else "defthm"
        if self.hints:
            form = f"({head} {self.thm_name}\n  {self.statement}\n  :hints ({' '.join(self.hints)}))"
        else:
            form = f"({head} {self.thm_name}\n  {self.statement})"
        if self.skip_proofs and not self.axiom:
            return f"(skip-proofs\n  {form})"
        return form


@dataclass
class ACL2DefunSkOp(Operation):
    """ACL2 quantified function (defun-sk): exists/forall over bound vars."""
    op_name: str = "acl2.defun-sk"
    pred_name: str = ""
    free_args: List[str] = field(default_factory=list)   # free variables (st, inputs)
    exists_vars: List[str] = field(default_factory=list)  # variables bound by exists/forall
    body: str = ""                    # formula with the bound vars
    quantifier: str = "exists"        # exists or forall
    skolem_name: Optional[str] = None
    thm_name: Optional[str] = None

    def __str__(self) -> str:
        vars_str = " ".join(self.exists_vars)
        return f"acl2.defun-sk @{self.pred_name} ({self.quantifier} ({vars_str}) {self.body})"

    def to_lisp(self) -> str:
        """Loadable ACL2 `(defun-sk ...)` form."""
        free = " ".join(self.free_args)
        vars_str = " ".join(self.exists_vars)
        form = f"(defun-sk {self.pred_name} ({free})\n  ({self.quantifier} ({vars_str}) {self.body})"
        if self.skolem_name:
            form += f"\n  :skolem-name {self.skolem_name}"
        form += ")"
        return form


@dataclass
class ACL2Module:
    """Container for ACL2 functions and theorems."""
    name: str
    defuns: List[ACL2DefunOp] = field(default_factory=list)
    defthms: List[ACL2DefthmOp] = field(default_factory=list)
    defun_sk_ops: List[ACL2DefunSkOp] = field(default_factory=list)
    raw_forms: List[str] = field(default_factory=list)   # e.g. (encapsulate ...)
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

    def to_acl2_code(self) -> str:
        """Loadable ACL2 Lisp: defun/defthm/defaxiom forms plus raw forms."""
        parts = [f";; Generated from ISIR design {self.name}",
                 '(in-package "ACL2")',
                 '(include-book "arithmetic-5/top" :dir :system)']
        for f in self.raw_forms:
            parts.append(f)
        for d in self.defuns:
            parts.append(d.to_lisp())
        for ds in self.defun_sk_ops:
            parts.append(ds.to_lisp())
        for t in self.defthms:
            parts.append(t.to_lisp())
        return "\n\n".join(parts) + "\n"


def from_spec_module(spec_module) -> ACL2Module:
    """
    Convert a SpecModule into an ACL2Module.
    This will be implemented in lowering/isir_to_acl2.py.
    """
    raise NotImplementedError("Conversion from SpecModule to ACL2Module not yet implemented")
