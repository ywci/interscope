# tests/unit/test_acl2_combinational.py
#
# Safeguards for the ACL2 combinational lowering (the bugs found during the
# "can ACL2 prove the Koika properties" investigation):
#   1. a falsy `reference` (0 / false) must NOT lower to `t`;
#   2. combinational defthms must carry the input bit-width hypotheses;
#   3. combinational defthms must use :rule-classes nil (tautologies are legal);
#   4. the arithmetic combinational defthms of `mul` actually PROVE (un-skipped).

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from isir.dialects import isir
from isir.lowering import isir_to_acl2
from isir.lowering.ast_to_isir import convert_ast_to_isir_module
from isir.parser.parser import parse_isir

ACL2 = shutil.which("acl2")
pytestmark = pytest.mark.skipif(ACL2 is None, reason="acl2 not installed")


def _combinational_spec(reference, operand="(mul x 0)"):
    property_ops = [isir.SpecPropertyOp(
        prop_name="p", kind="combinational",
        expression={"kind": "combinational", "operand": operand, "reference": reference})]
    proof_obligations = [{"property": "p", "engine": "theorem_proving", "backend": "acl2"}]
    inputs = [isir.Interface(name="x", direction="input", data_type="bits<4>")]
    return isir.SpecModule(name="tst", state_ops=[], rule_ops=[], property_ops=property_ops,
                           proof_obligations=proof_obligations, inputs=inputs, outputs=[],
                           clocks=[], resets=[])


class TestFalsyReference:
    def test_reference_zero_is_not_t(self):
        km = isir_to_acl2.convert(_combinational_spec(reference=0))
        thm = km.defthms[0]
        assert thm.statement.rstrip().endswith("0))"), thm.statement
        assert " t))" not in thm.statement, thm.statement

    def test_reference_false_is_not_t(self):
        km = isir_to_acl2.convert(_combinational_spec(reference=False))
        thm = km.defthms[0]
        assert " nil))" in thm.statement, thm.statement
        assert ") t))" not in thm.statement, thm.statement


class TestInputBoundsAndRuleClasses:
    def test_input_bit_width_hypotheses_present(self):
        km = isir_to_acl2.convert(_combinational_spec(reference=0))
        thm = km.defthms[0]
        assert "(natp x)" in thm.statement
        assert "(< x (expt 2 4))" in thm.statement

    def test_rule_classes_nil(self):
        km = isir_to_acl2.convert(_combinational_spec(reference=0))
        thm = km.defthms[0]
        assert thm.rule_classes_nil is True
        assert ":rule-classes nil" in km.to_acl2_code()


class TestCombinationalProve:
    def test_mul_combinational_defthms_prove(self):
        spec = convert_ast_to_isir_module(parse_isir(Path("examples/mul/mul.isir")).module)
        km = isir_to_acl2.convert(spec)
        provable = {"mul_commutative_correct", "mul_distributive_correct", "mul_zero_correct",
                    "mul_one_correct", "truncation_definitional_correct", "overflow_definitional_correct"}
        for t in km.defthms:
            if t.thm_name in provable:
                t.skip_proofs = False  # actually attempt the proof
        with tempfile.NamedTemporaryFile("w", suffix=".lisp", delete=False) as f:
            f.write(km.to_acl2_code())
            tmp = f.name
        out = subprocess.run([ACL2], input=f'(in-package "ACL2")\n(ld "{tmp}")\n',
                             capture_output=True, text=True, timeout=180)
        text = out.stdout + out.stderr
        assert "ACL2 Error" not in text, f"combinational proof failed:\n{text[-2000:]}"
        assert "FAILED" not in text, f"combinational proof failed:\n{text[-2000:]}"
        for name in sorted(provable):
            assert re.search(rf"\( DEFTHM {name.upper()} ", text), f"{name} not attempted"
