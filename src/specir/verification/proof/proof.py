# src/specir/verification/proof/proof.py
#
# Abstract base classes for proof skills and proof results.
# Defines the interface for pluggable proof backends (Kōika/Coq, ACL2, etc.).

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class ProofResult:
    """Result of a proof attempt.

    Attributes:
        success: Whether the proof succeeded.
        proof_script: The generated proof script (Coq/ACL2), if any.
        error_message: Error message if failed.
        auxiliary_lemmas: Additional lemmas generated.
        metadata: Extra data (proof steps, repair attempts, automation level, etc.).
        iterations: Number of PERF iterations (if applicable).
        duration: Wall-clock time in seconds.
        backend: The backend used (e.g. "koika", "acl2").
    """
    success: bool
    proof_script: Optional[str] = None
    error_message: Optional[str] = None
    auxiliary_lemmas: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    iterations: Optional[int] = None
    duration: Optional[float] = None
    backend: Optional[str] = None

    @property
    def status(self) -> str:
        """Derive a string status code from the success flag and error message."""
        if self.success:
            return "PASS"
        if self.error_message and "timeout" in self.error_message.lower():
            return "TIMEOUT"
        return "FAIL"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to a dictionary suitable for JSON serialisation."""
        return {
            "success": self.success,
            "status": self.status,
            "proof_script": self.proof_script,
            "error_message": self.error_message,
            "auxiliary_lemmas": self.auxiliary_lemmas,
            "metadata": self.metadata,
            "iterations": self.iterations,
            "duration": self.duration,
            "backend": self.backend,
        }

    @classmethod
    def combine(cls, results: List['ProofResult']) -> 'ProofResult':
        """Combine multiple proof results into a summary."""
        all_success = all(r.success for r in results)
        return cls(
            success=all_success,
            metadata={
                "total": len(results),
                "passed": sum(1 for r in results if r.success),
                "failed": sum(1 for r in results if not r.success),
            }
        )


class ProofSkill(ABC):
    """
    Abstract base class for proof generation skills.
    Subclasses implement proof generation for specific backends (Kōika/Coq, ACL2).
    """

    @abstractmethod
    def prove(self, proof_obligation: Dict[str, Any], context: Dict[str, Any]) -> ProofResult:
        """
        Attempt to prove a proof obligation.

        Args:
            proof_obligation: Dictionary containing the proof obligation (property name,
                              status, engine, backend, assumes, guarantees, metadata).
            context: Additional context (e.g., design AST, configuration, previous attempts).

        Returns:
            ProofResult with success flag, proof script, and optional error.
        """
        pass

    @abstractmethod
    def can_handle(self, proof_obligation: Dict[str, Any]) -> bool:
        """
        Check if this skill can handle the given proof obligation.
        Usually checks the 'backend' field (e.g., 'koika', 'acl2').
        """
        pass
