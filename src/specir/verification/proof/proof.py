# src/specir/verification/proof/proof.py
#
# Abstract base classes for proof skills and proof results.
# Defines the interface for pluggable proof backends (Kōika/Coq, ACL2, etc.).

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class ProofResult:
    """Result of a proof attempt."""
    success: bool
    proof_script: Optional[str] = None          # The generated proof script (Coq/ACL2)
    error_message: Optional[str] = None         # Error message if failed
    auxiliary_lemmas: List[str] = field(default_factory=list)  # Additional lemmas generated
    metadata: Dict[str, Any] = field(default_factory=dict)    # e.g., proof steps, repair attempts

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
