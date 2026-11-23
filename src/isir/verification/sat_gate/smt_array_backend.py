# src/isir/verification/sat_gate/smt_array_backend.py
#
# SMT array backend: the QF_ABV encoding route with array memories. This
# is the memory-capable route that avoids Path A's array instantiation; the
# narrow memory slice supports IND_STEP only at T1 certification
# (completeness-critical).

from dataclasses import dataclass
from typing import Optional
from isir.verification.sat_gate.obligation import QueryKind
from isir.verification.sat_gate.policy import CertTier


@dataclass(frozen=True)
class SmtArrayCapability:
    memory: str = "smt_array"
    query_kinds: frozenset = frozenset({QueryKind.IND_STEP})
    cert_tier: CertTier = CertTier.T1


def probe_capability(kind: QueryKind, has_memory: bool) -> Optional[SmtArrayCapability]:
    """Return the capability if the SMT array backend supports the obligation.

    The narrow slice: IND_STEP only; memory via SMT arrays; T1 certification.
    """
    cap = SmtArrayCapability()
    if kind not in cap.query_kinds:
        return None
    if has_memory and cap.memory != "smt_array":
        return None
    return cap


def smt_mem_decl(name: str, addr_w: int, elem_w: int) -> str:
    return f"(declare-const {name} (Array (_ BitVec {addr_w}) (_ BitVec {elem_w})))"


def smt_mem_read(mem: str, index: str) -> str:
    return f"(select {mem} {index})"


def smt_mem_write(mem: str, index: str, value: str) -> str:
    return f"(store {mem} {index} {value})"
