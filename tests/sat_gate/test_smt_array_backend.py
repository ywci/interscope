# tests/sat_gate/test_smt_array_backend.py
"""SMT array backend capability matrix + memory helpers (§17)."""

from isir.verification.sat_gate.smt_array_backend import (
    SmtArrayCapability, probe_capability, smt_mem_decl, smt_mem_read, smt_mem_write,
)
from isir.verification.sat_gate.obligation import QueryKind
from isir.verification.sat_gate.policy import CertTier


def test_ind_step_memory_is_supported():
    cap = probe_capability(QueryKind.IND_STEP, has_memory=True)
    assert cap is not None
    assert cap.memory == "smt_array"
    assert cap.cert_tier is CertTier.T1


def test_base_entail_is_unsupported_in_phase2():
    assert probe_capability(QueryKind.BASE_ENTAIL, has_memory=False) is None


def test_falsify_init_is_unsupported_in_phase2():
    assert probe_capability(QueryKind.FALSIFY_INIT, has_memory=False) is None


def test_memory_smt_helpers_emit_abv():
    assert smt_mem_decl("mem", 3, 32) == \
        "(declare-const mem (Array (_ BitVec 3) (_ BitVec 32)))"
    assert smt_mem_read("mem", "idx") == "(select mem idx)"
    assert smt_mem_write("mem", "idx", "val") == "(store mem idx val)"


def test_capability_defaults():
    cap = SmtArrayCapability()
    assert QueryKind.IND_STEP in cap.query_kinds
    assert cap.cert_tier is CertTier.T1
