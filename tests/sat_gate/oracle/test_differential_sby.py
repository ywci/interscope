# tests/sat_gate/oracle/test_differential_sby.py

import pytest
import shutil
import tempfile
from pathlib import Path
from isir.utils.config_loader import get_project_root
from isir.parser.parser import parse_isir
from isir.lowering.ast_to_isir import convert_ast_to_isir_module
from isir.verification.sat_gate.isir_bridge import (
    always_operand, initial_values, transitions_of, widths_of,
)
from isir.verification.sat_gate.compile_dyn import compile_ind_step
from isir.verification.sat_gate.solver_oneshot import solve_cnf


_KOIKA_COQ = get_project_root() / "tools" / "koika" / "_build" / "default" / "coq"
pytestmark = pytest.mark.skipif(
    shutil.which("sby") is None or not _KOIKA_COQ.exists(),
    reason="sby or the Kōika Coq library is not available",
)


def test_counter_ind_step_matches_sby():
    spec = convert_ast_to_isir_module(
        parse_isir("examples/counter/counter.isir").module
)
    widths = widths_of(spec)
    transitions = transitions_of(spec)
    inv = always_operand(spec, "counter_bound")

    gate_status = solve_cnf(compile_ind_step(inv, transitions, widths).cnf).status

    # sby: whole-design bounded/induction audit of the same property.
    from isir.verification.model_checker import run_mc_audit
    with tempfile.TemporaryDirectory() as td:
        result = run_mc_audit(spec, Path(td), engine="induction")
    sby_holds = result.get("success", False)

    # counter_bound is a 4-bit tautology: the gate says UNSAT and sby proves it.
    assert gate_status == "unsat"
    assert sby_holds
