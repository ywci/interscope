# src/specir/dialects/rtl_ir.py
#
# RTL dialect – represents Verilog RTL generated from Kōika.
# Provides operations: rtl.module, rtl.reg, rtl.wire, rtl.assign, rtl.always,
# rtl.instance, and others. Also includes mapping annotations from RTL signals
# to SpecIR elements (used for trace lifting).

from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

from specir.dialects.spec_ir import Dialect, Operation, Type


class RTLDialect(Dialect):
    name = "rtl"


class RTLRegType(Type):
    pass


class RTLWireType(Type):
    pass


class RTLModuleType(Type):
    pass


@dataclass
class RTLModuleOp(Operation):
    """Top‑level RTL module."""
    name: str = "rtl.module"
    module_name: str = ""
    ports: List[Dict[str, Any]] = field(default_factory=list)  # name, direction, width
    parameters: Dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"rtl.module @{self.module_name}"


@dataclass
class RTLRegOp(Operation):
    """Register declaration."""
    name: str = "rtl.reg"
    reg_name: str = ""
    width: int = 1
    initial: Optional[str] = None   # e.g., "0"

    def __str__(self) -> str:
        init_str = f" init={self.initial}" if self.initial else ""
        return f"rtl.reg @{self.reg_name} <{self.width}>{init_str}"


@dataclass
class RTLWireOp(Operation):
    """Wire declaration."""
    name: str = "rtl.wire"
    wire_name: str = ""
    width: int = 1

    def __str__(self) -> str:
        return f"rtl.wire @{self.wire_name} <{self.width}>"


@dataclass
class RTLAssignOp(Operation):
    """Continuous assignment."""
    name: str = "rtl.assign"
    lhs: str = ""
    rhs: str = ""

    def __str__(self) -> str:
        return f"rtl.assign {self.lhs} = {self.rhs}"


@dataclass
class RTLAlwaysOp(Operation):
    """Always block (combinational or clocked)."""
    name: str = "rtl.always"
    sensitivity: str = ""            # e.g., "@(posedge clk)" or "@(*)"
    body: List[str] = field(default_factory=list)  # list of statements (strings)
    clock: Optional[str] = None
    reset: Optional[str] = None

    def __str__(self) -> str:
        return f"rtl.always {self.sensitivity} {{ ... }}"


@dataclass
class RTLInstanceOp(Operation):
    """Module instantiation."""
    name: str = "rtl.instance"
    instance_name: str = ""
    module_name: str = ""
    port_map: Dict[str, str] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"rtl.instance @{self.instance_name} of {self.module_name}"


@dataclass
class RTLModule:
    """
    A single Verilog module.
    Supports dual representation: structured (parsed operations) and raw Verilog.
    """
    name: str
    ports: List[Dict[str, Any]] = field(default_factory=list)
    parameters: Dict[str, Any] = field(default_factory=dict)
    regs: List[RTLRegOp] = field(default_factory=list)
    wires: List[RTLWireOp] = field(default_factory=list)
    assigns: List[RTLAssignOp] = field(default_factory=list)
    always_blocks: List[RTLAlwaysOp] = field(default_factory=list)
    instances: List[RTLInstanceOp] = field(default_factory=list)
    raw_verilog: Optional[str] = None
    file_path: Optional[Path] = None


@dataclass
class MappingEntry:
    """Maps an RTL signal to a SpecIR element."""
    rtl_signal: str          # hierarchical path, e.g., "top.fifo.head"
    specir_ref: str          # e.g., "module.state[name=head]"
    kind: str                # register, rule_condition, memory, etc.
    width: Optional[int] = None


@dataclass
class RTLMapping:
    """Container for mapping entries for a design."""
    design_name: str
    entries: List[MappingEntry] = field(default_factory=list)

    def to_json(self) -> Dict[str, Any]:
        """Export to JSON‑serializable dict (used for mapping.json)."""
        return {
            "design": self.design_name,
            "mapping": [
                {
                    "rtl_signal": e.rtl_signal,
                    "specir_ref": e.specir_ref,
                    "kind": e.kind,
                    "width": e.width
                }
                for e in self.entries
            ]
        }


@dataclass
class RTLModuleContainer:
    """Container for a set of RTL modules and their mapping."""
    modules: Dict[str, RTLModule] = field(default_factory=dict)
    mapping: Optional[RTLMapping] = None
    design_name: str = ""

    @property
    def top_module(self) -> Optional[RTLModule]:
        """Return the top-level module (typically named after the design)."""
        if self.design_name in self.modules:
            return self.modules[self.design_name]
        if self.modules:
            return next(iter(self.modules.values()))
        return None


def from_koika_module(koika_module) -> RTLModuleContainer:
    """
    Convert a KoikaModule (from koika dialect) into an RTLModuleContainer.
    This will be implemented in lowering/koika_to_rtl.py.
    """
    raise NotImplementedError("Conversion from KoikaModule to RTLModuleContainer not yet implemented")
