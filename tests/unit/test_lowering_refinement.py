# tests/unit/test_lowering_refinement.py
#
# Integration of lowering-refinement evidence into the pipeline.

import json
import pytest
from pathlib import Path
from isir.parser.parser import parse_isir
from isir.lowering.ast_to_isir import convert_ast_to_isir_module
from isir.verification.lowering_refinement import (
    LoweringRefinementStatus,
    run_lowering_refinement,
)


def _spec(name: str):
    return convert_ast_to_isir_module(parse_isir(Path(f"examples/{name}/{name}.isir")).module)


class TestStatus:
    def test_counter_pass(self, tmp_path):
        r = run_lowering_refinement(_spec("counter"), cache_dir=tmp_path)
        assert not r.has_bounded_fail
        # supported write actions are upgraded to proof_pass
        assert all(i.status == LoweringRefinementStatus.PROOF_PASS for i in r.items)

    def test_unsupported_out_of_scope(self, tmp_path):
        r = run_lowering_refinement(_spec("alu"), cache_dir=tmp_path)
        # The execute rule uses slice/shift and is out of the Kōika subset.
        scoped = [i for i in r.items if i.status == LoweringRefinementStatus.PROOF_OUT_OF_SCOPE]
        assert scoped, "expected some out-of-scope items for the ALU"

    def test_cache_hit(self, tmp_path):
        run_lowering_refinement(_spec("counter"), cache_dir=tmp_path)
        r2 = run_lowering_refinement(_spec("counter"), cache_dir=tmp_path)
        assert r2.cache_hits == len(r2.items)


class TestInjectedBug:
    def test_bug_is_bounded_fail_and_blocks(self, tmp_path, monkeypatch):
        import isir.lowering.koika_to_rtl as k

        orig = k._coq_bits_expr

        def buggy(expr, reg_widths, current_width):
            # Swap + -> - so `add` lowers to `sub`: a real lowering bug.
            return orig(expr, reg_widths, current_width).replace("+", "-")

        monkeypatch.setattr(k, "_coq_bits_expr", buggy)

        r = run_lowering_refinement(_spec("counter"), cache_dir=tmp_path)
        assert r.has_bounded_fail, "the injected +/ - bug must be caught"
        failing = [i for i in r.items if i.status == LoweringRefinementStatus.BOUNDED_FAIL]
        assert failing
        # every bounded_fail item carries a counterexample
        assert all(i.counterexample and i.counterexample.get("model") for i in failing)


class TestProofPass:
    def test_toy_counter_is_proof_pass(self, tmp_path):
        import isir.dialects.isir as isir
        spec = isir.SpecModule(name="toy_counter")
        spec.state_ops.append(isir.SpecStateOp(state_name="count", kind="register",
                                               data_type="bits<4>", initial=0))
        spec.rule_ops.append(isir.SpecRuleOp(rule_name="inc", condition="true",
                                             actions=["(write count (add (read count) 1))"]))
        r = run_lowering_refinement(spec, cache_dir=tmp_path)
        assert len(r.items) == 1
        it = r.items[0]
        assert it.status == LoweringRefinementStatus.PROOF_PASS
        assert it.mode == "lowering_refinement_proof"

    def test_real_core_fragment_designs_are_proof_pass(self, tmp_path):
        for name in ["counter", "gcd", "arbiter"]:
            r = run_lowering_refinement(_spec(name), cache_dir=tmp_path / name)
            assert r.items, name
            assert all(i.status == LoweringRefinementStatus.PROOF_PASS for i in r.items), \
                f"{name}: expected all proof_pass, got {[(i.item_id, i.status.value) for i in r.items]}"

    def test_alu_slice_items_remain_out_of_scope(self, tmp_path):
        """The ALU uses slice/shift, so its arithmetic items stay out of scope."""
        r = run_lowering_refinement(_spec("alu"), cache_dir=tmp_path)
        scoped = [i for i in r.items if i.status == LoweringRefinementStatus.PROOF_OUT_OF_SCOPE]
        assert scoped, "ALU slice/shift items must remain proof_out_of_scope"


class TestCoreFragmentExpr:
    def test_supported_and_excluded(self):
        from isir.verification.lowering_refinement import _is_core_fragment_expr
        assert _is_core_fragment_expr(["add", ["read", "count"], 1])
        assert _is_core_fragment_expr(["sub", ["read", "a"], ["read", "b"]])
        assert _is_core_fragment_expr(["ite", ["read", "done"], 0, 1])
        assert _is_core_fragment_expr(["and", ["read", "x"], ["read", "y"]])
        assert _is_core_fragment_expr(["eq", ["read", "a"], ["read", "b"]])
        assert _is_core_fragment_expr(["lt", ["read", "a"], 15])
        # excluded operators
        assert not _is_core_fragment_expr(["slice", ["read", "x"], 7, 0])
        assert not _is_core_fragment_expr(["mul", ["read", "x"], ["read", "y"]])
        assert not _is_core_fragment_expr(["mem_read", "m", ["read", "addr"]])
        assert not _is_core_fragment_expr(["shl", ["read", "x"], 1])


class TestDifferentialConsistency:
    def test_bounded_pass_agrees(self, tmp_path, monkeypatch):
        from isir.lowering import rtl_differential as rd
        monkeypatch.setattr(rd, "diff_design",
                            lambda spec, s, l, cycles=8, seed=0:
                            rd.DiffResult(design=spec.name, status="agreed_long_short"))
        r = run_lowering_refinement(_spec("counter"), cache_dir=tmp_path, run_differential=True)
        assert r.differential_status == "agreed_long_short"
        assert r.differential_consistent is True

    def test_bounded_pass_diverges_is_inconsistent(self, tmp_path, monkeypatch):
        from isir.lowering import rtl_differential as rd
        monkeypatch.setattr(rd, "diff_design",
                            lambda spec, s, l, cycles=8, seed=0:
                            rd.DiffResult(design=spec.name, status="divergent_long_short"))
        r = run_lowering_refinement(_spec("counter"), cache_dir=tmp_path, run_differential=True)
        assert r.differential_status == "divergent_long_short"
        # bounded_pass (no sat) but behavioral divergence -> harness/encoding defect
        assert r.differential_consistent is False


class TestEvidence:
    def test_evidence_records(self, tmp_path):
        from isir.evidence.registry import EvidenceRegistry
        db = tmp_path / "evidence.db"
        registry = EvidenceRegistry(db_path=db)
        run_lowering_refinement(_spec("saturating_adder"), cache_dir=tmp_path, registry=registry)
        rows = registry.list_evidence(engine="lowering_refinement", limit=100)
        assert rows, "expected lowering_refinement evidence rows"
        assert all(r["status"] in ("bounded_pass", "proof_pass") for r in rows)
