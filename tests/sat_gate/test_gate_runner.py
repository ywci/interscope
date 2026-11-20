# tests/sat_gate/test_gate_runner.py
"""End-to-end gate runner on the slice."""

from isir.parser.parser import parse_isir
from isir.lowering.ast_to_isir import convert_ast_to_isir_module

from isir.verification.sat_gate.gate_runner import run_gate
from isir.verification.sat_gate.policy import EvidenceAction


def _load(name):
    return convert_ast_to_isir_module(
        parse_isir(f"examples/{name}/{name}.isir").module
    )


def test_saturating_counter_inductive_pair():
    results, metrics = run_gate(_load("saturating_counter"))
    cr = [r for r in results if r.property == "count_in_range"]
    assert len(cr) == 1
    assert cr[0].base_status == "unsat"
    assert cr[0].step_status == "unsat"
    assert cr[0].evidence_action is EvidenceAction.PROVE_STEP
    assert metrics.coverage() == 1.0
    assert metrics.firing_rate() == 1.0


def test_counter_inductive_pair():
    results, _ = run_gate(_load("counter"))
    cb = [r for r in results if r.property == "counter_bound"]
    assert len(cb) == 1
    assert cb[0].evidence_action is EvidenceAction.PROVE_STEP


def test_fifo_memory_inductive_pair():
    # memory-bearing design routes through the SMT array backend (IND_STEP only).
    results, _ = run_gate(_load("fifo"))
    cb = [r for r in results if r.property == "count_bound"]
    assert len(cb) == 1
    assert cb[0].step_status == "unsat"
    assert cb[0].evidence_action is EvidenceAction.PROVE_STEP
