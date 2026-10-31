# tests/unit/test_combinational_check.py
#
# Combinational-property differential: reference eval of operand vs reference.

from pathlib import Path

from isir.lowering.ast_to_isir import convert_ast_to_isir_module
from isir.parser.parser import parse_isir
from isir.verification.combinational_check import check_combinational_properties

EXAMPLES = ["alu", "fpu", "gcd", "mul", "riscv", "riscv_ooo", "ooo_comp"]


class TestCombinationalAgree:
    def test_no_combinational_property_diverges(self):
        # `divergent` = the property is semantically FALSE (operand != reference).
        # `error` is allowed: it marks a property over a partial_spec (bodyless)
        # function, which the reference interpreter cannot evaluate.
        for ex in EXAMPLES:
            spec = convert_ast_to_isir_module(parse_isir(Path(f"examples/{ex}/{ex}.isir")).module)
            results = check_combinational_properties(spec, num_cases=50, seed=0)
            diverged = [r for r in results if r.status == "divergent"]
            assert not diverged, f"{ex}: divergent properties {[r.to_dict() for r in diverged]}"
            assert results, f"{ex}: expected at least one combinational property"

    def test_defined_function_properties_agree(self):
        # For designs whose combinational functions are all defined (no
        # partial_spec), every property must agree.
        for ex in ["alu", "mul", "riscv", "riscv_ooo", "ooo_comp"]:  # gcd/fpu are recursive/partial_spec
            spec = convert_ast_to_isir_module(parse_isir(Path(f"examples/{ex}/{ex}.isir")).module)
            results = check_combinational_properties(spec, num_cases=50, seed=0)
            not_agree = [r for r in results if r.status != "agree"]
            assert not not_agree, f"{ex}: {[r.to_dict() for r in not_agree]}"


class TestDetectsDivergence:
    def test_false_reference_is_caught(self):
        from isir.dialects.isir import SpecModule, SpecPropertyOp, Interface
        spec = SpecModule(
            name="tst", state_ops=[], rule_ops=[],
            inputs=[Interface(name="x", direction="input", data_type="bits<4>")],
            outputs=[],
            property_ops=[SpecPropertyOp(
                prop_name="bad", kind="combinational",
                expression={"kind": "combinational", "operand": "(mul x 0)", "reference": 1})],
            proof_obligations=[],
        )
        results = check_combinational_properties(spec, num_cases=20, seed=0)
        assert results[0].status == "divergent", results[0].to_dict()

    def test_assumes_are_respected(self):
        from isir.dialects.isir import SpecModule, SpecPropertyOp, Interface
        spec = SpecModule(
            name="tst", state_ops=[], rule_ops=[],
            inputs=[Interface(name="x", direction="input", data_type="bits<8>")],
            outputs=[],
            property_ops=[SpecPropertyOp(
                prop_name="le_255", kind="combinational",
                assumes=["(le x 255)"],
                expression={"kind": "combinational", "operand": "(le x 255)", "reference": True})],
            proof_obligations=[],
        )
        results = check_combinational_properties(spec, num_cases=100, seed=0)
        assert results[0].status == "agree", results[0].to_dict()

