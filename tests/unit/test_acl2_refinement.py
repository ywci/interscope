# tests/unit/test_acl2_refinement.py
#
# Bounded evaluation differential (ACL2 step vs eval_expr).

import shutil
import pytest
from pathlib import Path
from isir.parser.parser import parse_isir
from isir.lowering.ast_to_isir import convert_ast_to_isir_module
from isir.verification.acl2_refinement import run_acl2_differential


ACL2 = shutil.which("acl2")
pytestmark = pytest.mark.skipif(ACL2 is None, reason="acl2 not installed")


def _spec(name: str):
    return convert_ast_to_isir_module(parse_isir(Path(f"examples/{name}/{name}.isir")).module)


class TestAcl2Differential:
    def test_counter_bounded_pass(self):
        r = run_acl2_differential(_spec("counter"), num_cases=20, seed=3)
        assert r.status == "bounded_pass", (r.status, r.message, r.counterexample)

    def test_saturating_adder_bounded_pass(self):
        r = run_acl2_differential(_spec("saturating_adder"), num_cases=20, seed=3)
        assert r.status == "bounded_pass", (r.status, r.message, r.counterexample)

    def test_arbiter_bounded_pass(self):
        r = run_acl2_differential(_spec("arbiter"), num_cases=20, seed=3)
        assert r.status == "bounded_pass", (r.status, r.message, r.counterexample)

    def test_gcd_parallel_bounded_pass(self):
        """The multi-rule parallel GCD now matches the reference (all enabled
        rules fire with original-state reads)."""
        r = run_acl2_differential(_spec("gcd"), num_cases=20, seed=3)
        assert r.status == "bounded_pass", (r.status, r.message, r.counterexample)


class TestAcl2DifferentialInjectedBug:
    def test_add_to_sub_is_caught(self, monkeypatch):
        import isir.lowering.isir_to_acl2 as k
        orig = k._expr_to_acl2

        def buggy(expr, *args, **kwargs):
            return orig(expr, *args, **kwargs).replace("+", "-")

        monkeypatch.setattr(k, "_expr_to_acl2", buggy)
        r = run_acl2_differential(_spec("counter"), num_cases=20, seed=3)
        assert r.status == "bounded_fail", "the +/ - lowering bug must be caught"


class TestAcl2LoweringRefinement:
    def test_counter_is_proof_pass(self):
        from isir.verification.acl2_refinement import run_acl2_lowering_refinement
        from isir.verification.lowering_refinement import LoweringRefinementStatus
        r = run_acl2_lowering_refinement(_spec("counter"), num_cases=10, seed=0)
        assert r.items
        assert all(i.status == LoweringRefinementStatus.PROOF_PASS for i in r.items)

    def test_injected_bug_blocks(self, monkeypatch):
        import isir.lowering.isir_to_acl2 as k
        from isir.verification.acl2_refinement import run_acl2_lowering_refinement
        orig = k._expr_to_acl2
        monkeypatch.setattr(k, "_expr_to_acl2",
                            lambda e, *a, **kw: orig(e, *a, **kw).replace("+", "-"))
        r = run_acl2_lowering_refinement(_spec("counter"), num_cases=10, seed=0)
        assert r.has_bounded_fail

    def test_evidence_records(self, tmp_path):
        from isir.evidence.registry import EvidenceRegistry
        from isir.verification.acl2_refinement import run_acl2_lowering_refinement
        registry = EvidenceRegistry(db_path=tmp_path / "evidence.db")
        run_acl2_lowering_refinement(_spec("counter"), num_cases=10, seed=0, registry=registry)
        rows = registry.list_evidence(engine="lowering_refinement", limit=100)
        assert rows, "expected lowering_refinement evidence rows"
