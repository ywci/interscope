# src/specir/dialects/rtl_ir.py
#
# RTL dialect – represents Verilog RTL generated from Kōika.
# Provides operations: rtl.module, rtl.reg, rtl.wire, rtl.assign, rtl.always,
# rtl.instance, and others. Also includes mapping annotations from RTL signals
# to SpecIR elements (used for trace lifting).

from pathlib import Path
from typing import List, Dict, Any, Optional, Set, Union
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
    """
    Maps an RTL signal to a SpecIR element.

    PERF-specific fields enable fine-grained trace alignment:
      - signal_group: Categorises signals (control, data, state, input, output).
      - is_relevant_for_proof: Whether this signal matters for the current proof.
      - source_rule: Which rule generated this signal (if known).
      - expression: The original SpecIR expression (for combinational signals).
      - relevant_properties: List of property names this signal is relevant to.
    """
    rtl_signal: str          # hierarchical path, e.g., "top.fifo.head"
    specir_ref: str          # e.g., "module.state[name=head]"
    kind: str                # register, rule_condition, memory, input, output, etc.
    width: Optional[int] = None

    # PERF-specific fields for trace alignment
    signal_group: str = "state"        # "control", "data", "state", "input", "output"
    is_relevant_for_proof: bool = True
    source_rule: Optional[str] = None
    expression: Optional[str] = None
    relevant_properties: List[str] = field(default_factory=list)

    def to_json(self) -> Dict[str, Any]:
        """Export to JSON‑serializable dict (used for mapping.json)."""
        result = {
            "rtl_signal": self.rtl_signal,
            "specir_ref": self.specir_ref,
            "kind": self.kind,
            "width": self.width,
            # PERF fields
            "signal_group": self.signal_group,
            "is_relevant_for_proof": self.is_relevant_for_proof,
        }
        if self.source_rule is not None:
            result["source_rule"] = self.source_rule
        if self.expression is not None:
            result["expression"] = self.expression
        if self.relevant_properties:
            result["relevant_properties"] = self.relevant_properties
        return result

    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> "MappingEntry":
        """Create a MappingEntry from a JSON dict."""
        return cls(
            rtl_signal=data["rtl_signal"],
            specir_ref=data["specir_ref"],
            kind=data["kind"],
            width=data.get("width"),
            signal_group=data.get("signal_group", "state"),
            is_relevant_for_proof=data.get("is_relevant_for_proof", True),
            source_rule=data.get("source_rule"),
            expression=data.get("expression"),
            relevant_properties=data.get("relevant_properties", []),
        )


@dataclass
class RTLMapping:
    """Container for mapping entries for a design."""
    design_name: str
    entries: List[MappingEntry] = field(default_factory=list)

    def to_json(self) -> Dict[str, Any]:
        """Export to JSON‑serializable dict (used for mapping.json)."""
        return {
            "design": self.design_name,
            "mapping": [e.to_json() for e in self.entries]
        }

    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> "RTLMapping":
        """Create an RTLMapping from a JSON dict."""
        return cls(
            design_name=data["design"],
            entries=[MappingEntry.from_json(e) for e in data.get("mapping", [])]
        )

    def filter_for_obligation(self, obligation: Union[Dict[str, Any], str]) -> List[MappingEntry]:
        """
        Filter mapping entries relevant to a specific proof obligation.

        Args:
            obligation: Either a proof obligation dict (with 'property' key)
                       or a property name string.

        Returns:
            List of mapping entries that are relevant to this obligation.
        """
        # Extract property name
        if isinstance(obligation, dict):
            prop_name = obligation.get("property")
        else:
            prop_name = obligation

        if not prop_name:
            return self.entries.copy()

        filtered = []
        for entry in self.entries:
            # Include if:
            # 1. The entry is explicitly marked as relevant
            # 2. The entry's relevant_properties list contains the property
            # 3. The specir_ref points to something related to the property
            #    (e.g., the property's name appears in the ref)
            if not entry.is_relevant_for_proof:
                continue

            if prop_name in entry.relevant_properties:
                filtered.append(entry)
                continue

            # Heuristic: if specir_ref contains the property name (e.g., rule condition)
            if prop_name in entry.specir_ref:
                filtered.append(entry)
                continue

            # If no specific relevance, include by default (conservative)
            # But we want to be selective, so we only include if it's a state or input
            # that might be used in the property.
            # For PERF trace_alignment, we want to include state and input signals.
            if entry.kind in ("register", "memory", "input", "output"):
                filtered.append(entry)

        return filtered

    def build_property_signal_index(self) -> Dict[str, List[str]]:
        """
        Build a reverse index mapping property names to relevant signal names.

        Returns:
            Dictionary: property_name -> list of RTL signal names.
        """
        index: Dict[str, List[str]] = {}
        for entry in self.entries:
            for prop in entry.relevant_properties:
                if prop not in index:
                    index[prop] = []
                index[prop].append(entry.rtl_signal)

            # Also add entries based on specir_ref heuristic
            # (e.g., if specir_ref contains "property[name=...]")
            import re
            match = re.search(r"property\[name=([^\]]+)\]", entry.specir_ref)
            if match:
                prop_name = match.group(1)
                if prop_name not in index:
                    index[prop_name] = []
                index[prop_name].append(entry.rtl_signal)

        return index

    def filter_by_group(self, group: str) -> List[MappingEntry]:
        """Return only mapping entries belonging to a specific signal group."""
        return [e for e in self.entries if e.signal_group == group]

    def get_signals_for_property(self, property_name: str) -> List[str]:
        """
        Get all RTL signal names relevant to a given property.

        Uses the property-signal index built by build_property_signal_index.
        """
        index = self.build_property_signal_index()
        return index.get(property_name, [])


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

    def get_verilog_path(self) -> Optional[Path]:
        """Return the path to the top-level Verilog file, if available."""
        top = self.top_module
        if top and top.file_path:
            return top.file_path
        return None

    def get_mapping_for_obligation(self, obligation: Dict[str, Any]) -> List[MappingEntry]:
        """
        Get mapping entries relevant to a proof obligation.

        Returns the filtered list if mapping is available; otherwise an empty list.
        """
        if not self.mapping:
            return []
        return self.mapping.filter_for_obligation(obligation)

    def get_signal_groups(self) -> Dict[str, List[str]]:
        """
        Return a dictionary mapping signal groups to list of RTL signal names.

        Used by PERF for efficient trace filtering.
        """
        if not self.mapping:
            return {}
        groups: Dict[str, List[str]] = {}
        for entry in self.mapping.entries:
            group = entry.signal_group
            if group not in groups:
                groups[group] = []
            groups[group].append(entry.rtl_signal)
        return groups

    def get_relevant_signals(self, property_name: str) -> List[str]:
        """
        Get RTL signal names relevant to a specific property.

        Uses the mapping's property-signal index.
        """
        if not self.mapping:
            return []
        return self.mapping.get_signals_for_property(property_name)


def from_koika_module(koika_module) -> RTLModuleContainer:
    """
    Convert a KoikaModule (from koika dialect) into an RTLModuleContainer.
    This will be implemented in lowering/koika_to_rtl.py.
    """
    raise NotImplementedError("Conversion from KoikaModule to RTLModuleContainer not yet implemented")
