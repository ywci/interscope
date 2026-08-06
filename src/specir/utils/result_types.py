# src/specir/utils/result_types.py
#
# Standard dataclasses for compilation, verification, and simulation results.
# These provide a uniform output format for batch processing and evaluation.

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
from datetime import datetime


class Status(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    TIMEOUT = "TIMEOUT"
    ERROR = "ERROR"


@dataclass
class BackendResult:
    """Result of compiling a single design to one backend."""
    backend: str                          # e.g. "koika", "acl2", "sva", "vhdl", "verilog_ovl", "rtl"
    success: bool
    error_message: Optional[str] = None
    duration: Optional[float] = None       # seconds
    output_file: Optional[str] = None      # path to generated file
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "backend": self.backend,
            "success": self.success,
            "error_message": self.error_message,
            "duration": self.duration,
            "output_file": self.output_file,
            "metadata": self.metadata,
        }


@dataclass
class CompilationReport:
    """Full compilation report for one design."""
    design_name: str
    input_file: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    results: List[BackendResult] = field(default_factory=list)

    def overall_success(self) -> bool:
        return all(r.success for r in self.results)

    def success_rate(self) -> float:
        if not self.results:
            return 0.0
        return sum(1 for r in self.results if r.success) / len(self.results)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "design_name": self.design_name,
            "input_file": self.input_file,
            "timestamp": self.timestamp,
            "results": [r.to_dict() for r in self.results],
            "overall_success": self.overall_success(),
            "success_rate": self.success_rate(),
        }


@dataclass
class ProofObligationResult:
    """Result of verifying a single proof obligation."""
    property: str                         # property name
    status: Status                        # PASS, FAIL, TIMEOUT, ERROR
    backend: str                          # "koika", "acl2", "model_checking"
    iterations: Optional[int] = None      # for PERF (number of beam iterations)
    proof_script: Optional[str] = None    # successful proof script (if any)
    error_message: Optional[str] = None
    duration: Optional[float] = None
    details: Dict[str, Any] = field(default_factory=dict)
    # examples: {"automation": "skeleton", "lemmas_used": ["head_const"], "perf_stats": {...}}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "property": self.property,
            "status": self.status.value,
            "backend": self.backend,
            "iterations": self.iterations,
            "proof_script": self.proof_script,
            "error_message": self.error_message,
            "duration": self.duration,
            "details": self.details,
        }


@dataclass
class VerificationReport:
    """Verification report for one design (may contain multiple obligations)."""
    design_name: str
    backend: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    obligations: List[ProofObligationResult] = field(default_factory=list)
    overall_status: Status = Status.PASS

    def __post_init__(self):
        if self.obligations:
            if any(o.status == Status.ERROR for o in self.obligations):
                self.overall_status = Status.ERROR
            elif any(o.status == Status.TIMEOUT for o in self.obligations):
                self.overall_status = Status.TIMEOUT
            elif any(o.status == Status.FAIL for o in self.obligations):
                self.overall_status = Status.FAIL
            else:
                self.overall_status = Status.PASS

    def pass_rate(self) -> float:
        if not self.obligations:
            return 0.0
        return sum(1 for o in self.obligations if o.status == Status.PASS) / len(self.obligations)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "design_name": self.design_name,
            "backend": self.backend,
            "timestamp": self.timestamp,
            "obligations": [o.to_dict() for o in self.obligations],
            "overall_status": self.overall_status.value,
            "pass_rate": self.pass_rate(),
        }


@dataclass
class SimulationReport:
    """Report for a simulation run."""
    design_name: str
    success: bool
    cycles: Optional[int] = None
    coverage: Optional[float] = None
    vcd_path: Optional[str] = None
    error_message: Optional[str] = None
    duration: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "design_name": self.design_name,
            "success": self.success,
            "cycles": self.cycles,
            "coverage": self.coverage,
            "vcd_path": self.vcd_path,
            "error_message": self.error_message,
            "duration": self.duration,
            "metadata": self.metadata,
        }


def merge_statuses(statuses: List[Status]) -> Status:
    """Given a list of Status values, return the most severe."""
    if not statuses:
        return Status.PASS
    if Status.ERROR in statuses:
        return Status.ERROR
    if Status.TIMEOUT in statuses:
        return Status.TIMEOUT
    if Status.FAIL in statuses:
        return Status.FAIL
    return Status.PASS
