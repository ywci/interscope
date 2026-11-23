# tests/sat_gate/test_ctg_generalization.py

from isir.verification.sat_gate.lemma_hint import (
    _cube_to_predicate, bulk_drop_core, generalize_cube,
)
from isir.verification.sat_gate.smt_encode import (
    solve_smt_bad_cube_step, solve_smt_bad_cube_step_model,
)


def test_original_cti_cube_is_not_inductive():
    widths = {"count": 4, "flag": 1}
    transitions = {"count": "(add (read count) 1)", "flag": "(read flag)"}
    pred = _cube_to_predicate(frozenset({("count", 7), ("flag", 1)}))
    assert solve_smt_bad_cube_step([], transitions, widths, pred) == "sat"


def test_identity_cube_is_inductive():
    widths = {"count": 4, "flag": 1}
    transitions = {"count": "(add (read count) 0)", "flag": "(read flag)"}
    pred = _cube_to_predicate(frozenset({("count", 5), ("flag", 1)}))
    assert solve_smt_bad_cube_step([], transitions, widths, pred) == "unsat"


def test_generalize_returns_inductive_subset():
    widths = {"count": 4, "flag": 1}
    transitions = {"count": "(add (read count) 1)", "flag": "(read flag)"}
    cube = frozenset({("count", 7), ("flag", 1)})
    generalized = generalize_cube(transitions, widths, cube)
    assert generalized <= cube
    pred = _cube_to_predicate(generalized)
    assert solve_smt_bad_cube_step([], transitions, widths, pred) == "unsat"


def test_generalize_is_noop_for_single_literal():
    widths = {"count": 4}
    transitions = {"count": "(add (read count) 1)"}
    cube = frozenset({("count", 7)})
    assert generalize_cube(transitions, widths, cube) == cube


def test_bad_cube_step_model_returns_predecessor():
    widths = {"count": 4}
    transitions = {"count": "(add (read count) 1)"}
    pred = _cube_to_predicate(frozenset({("count", 7)}))
    status, state = solve_smt_bad_cube_step_model([], transitions, widths, pred)
    assert status == "sat"
    assert state == {"count": 6}


def test_ctg_depth_runs_and_returns_subset():
    widths = {"count": 4, "flag": 1}
    transitions = {"count": "(add (read count) 1)", "flag": "(read flag)"}
    cube = frozenset({("count", 7), ("flag", 1)})
    init = {"count": 0, "flag": 0}
    generalized = generalize_cube(transitions, widths, cube,
                                  generalization_depth=2,
                                  init_values=init, cti_probe_k=3)
    assert generalized <= cube


def test_bulk_drop_core_returns_inductive_subset():
    widths = {"count": 4, "flag": 1}
    transitions = {"count": "(add (read count) 0)", "flag": "(read flag)"}
    cube = frozenset({("count", 5), ("flag", 1)})
    core = bulk_drop_core([], transitions, widths, cube)
    assert core <= cube
    pred = _cube_to_predicate(core)
    assert solve_smt_bad_cube_step([], transitions, widths, pred) == "unsat"


def test_bulk_drop_core_no_drop_when_not_inductive():
    widths = {"count": 4, "flag": 1}
    transitions = {"count": "(add (read count) 1)", "flag": "(read flag)"}
    cube = frozenset({("count", 7), ("flag", 1)})
    assert bulk_drop_core([], transitions, widths, cube) == cube
