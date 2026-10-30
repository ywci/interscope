# tests/unit/test_attribution.py
#
# Attribution of lowering-refinement failures.

import pytest
from pathlib import Path
from isir.parser.parser import parse_isir
from isir.lowering.ast_to_isir import convert_ast_to_isir_module
from isir.verification.lowering_refinement import (
    LoweringRefinementStatus,
    RefinementItemResult,
    run_lowering_refinement,
)
from isir.verification.attribution import (
    AttributionCategory,
    attribute_item,
    attribute_report,
    has_spec_ambiguity,
)
from isir.utils.expr import parse_sexpr


def _spec(name: str):
    return convert_ast_to_isir_module(parse_isir(Path(f"examples/{name}/{name}.isir")).module)


class TestSpecAmbiguityHeuristic:
    def test_literal_wider_than_operand(self):
        e = parse_sexpr("(ge (add x y) 256)")
        assert has_spec_ambiguity(e, 8, {"x": 8, "y": 8})

    def test_literal_fits(self):
        e = parse_sexpr("(ge (add x y) 200)")
        assert not has_spec_ambiguity(e, 8, {"x": 8, "y": 8})


class TestAttributeItem:
    def test_lowering_bug(self):
        item = RefinementItemResult("i", LoweringRefinementStatus.BOUNDED_FAIL, "m")
        attr = attribute_item(item, parse_sexpr("(add a b)"), 8, {"a": 8, "b": 8})
        assert attr.category == AttributionCategory.LOWERING_BUG

    def test_spec_ambiguity(self):
        item = RefinementItemResult("i", LoweringRefinementStatus.BOUNDED_FAIL, "m")
        rhs = parse_sexpr("(ge (add x y) 256)")
        attr = attribute_item(item, rhs, 8, {"x": 8, "y": 8})
        assert attr.category == AttributionCategory.SPEC_AMBIGUITY

    def test_modeling_gap(self):
        item = RefinementItemResult("i", LoweringRefinementStatus.PROOF_OUT_OF_SCOPE, "m",
                                    category="koika_modeling_gap")
        attr = attribute_item(item, None, 1, {})
        assert attr.category == AttributionCategory.KOIKA_MODELING_GAP

    def test_bound_exhausted(self):
        item = RefinementItemResult("i", LoweringRefinementStatus.PROOF_OUT_OF_SCOPE, "m",
                                    category="bound_exhausted")
        attr = attribute_item(item, None, 1, {})
        assert attr.category == AttributionCategory.BOUND_EXHAUSTED


class TestAttributeReport:
    def test_injected_bug_is_lowering_bug(self, monkeypatch, tmp_path):
        import isir.lowering.koika_to_rtl as k
        orig = k._coq_bits_expr

        def buggy(expr, reg_widths, current_width):
            return orig(expr, reg_widths, current_width).replace("+", "-")

        monkeypatch.setattr(k, "_coq_bits_expr", buggy)

        spec = _spec("counter")
        rr = run_lowering_refinement(spec, cache_dir=tmp_path)
        ar = attribute_report(rr, spec)
        cats = {a.category for a in ar.attributions}
        assert AttributionCategory.LOWERING_BUG in cats

    def test_excluded_operator_is_modeling_gap(self, tmp_path):
        spec = _spec("alu")
        rr = run_lowering_refinement(spec, cache_dir=tmp_path)
        ar = attribute_report(rr, spec)
        cats = {a.category for a in ar.attributions}
        assert AttributionCategory.KOIKA_MODELING_GAP in cats
