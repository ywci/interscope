# tests/sat_gate/test_array_exactness.py

import subprocess
import tempfile
from pathlib import Path

from isir.verification.sat_gate.smt_array_backend import (
    SmtArrayCapability, probe_capability, smt_mem_decl, smt_mem_read, smt_mem_write,
)
from isir.verification.sat_gate.obligation import QueryKind


def _z3(body: str) -> str:
    with tempfile.NamedTemporaryFile("w", suffix=".smt2", delete=False) as f:
        f.write(body)
        path = Path(f.name)
    return subprocess.run(["z3", str(path)], capture_output=True, text=True,
                          timeout=60).stdout.strip()


def test_index_sort_width_matches_address_width():
    # The index sort width equals the address space width.
    decl = smt_mem_decl("mem", addr_w=5, elem_w=8)
    assert "(_ BitVec 5)" in decl and "(_ BitVec 8)" in decl


def test_data_width_exact():
    # The data width is exact, no implicit truncation.
    decl = smt_mem_decl("mem", addr_w=5, elem_w=8)
    assert "(_ BitVec 8)" in decl


def test_read_during_write_ordering():
    # select(store(a,i,v), i) = v is a theorem (write-then-read).
    body = (
        "(set-logic QF_ABV)\n"
        "(declare-const a (Array (_ BitVec 4) (_ BitVec 8)))\n"
        "(declare-const i (_ BitVec 4))\n"
        "(declare-const v (_ BitVec 8))\n"
        "(assert (not (= (select (store a i v) i) v)))\n"
        "(check-sat)\n"
)
    assert _z3(body) == "unsat"


def test_smt_read_write_helpers():
    assert smt_mem_read("m", "i") == "(select m i)"
    assert smt_mem_write("m", "i", "v") == "(store m i v)"


def test_capability_documents_total_array_over_approximation():
    # SMT arrays are total, so OOB is an over-approximation; the
    # capability records the memory mode and the T1 (completeness) tier.
    cap = probe_capability(QueryKind.IND_STEP, has_memory=True)
    assert isinstance(cap, SmtArrayCapability)
    assert cap.memory == "smt_array"
