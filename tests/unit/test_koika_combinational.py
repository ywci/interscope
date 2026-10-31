# tests/unit/test_koika_combinational.py
#
# Koika-equivalent safeguards (mirroring test_acl2_combinational.py):
#   1. the generated Coq for examples must actually TYPE-CHECK under coqc;
#   2. a falsy `reference` (0 / false) must NOT lower to `true`;
#   3. combinational theorems must carry the input bit-width hypotheses.

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from isir.dialects import isir
from isir.lowering import isir_to_koika
from isir.lowering.ast_to_isir import convert_ast_to_isir_module
from isir.parser.parser import parse_isir


def _resolve_coqc():
    c = shutil.which("coqc")
    if c:
        return c
    r = subprocess.run(["bash", "-c", 'eval "$(opam env 2>/dev/null)" && command -v coqc'],
                       capture_output=True, text=True)
    return r.stdout.strip() or None


COQC = _resolve_coqc()
pytestmark = pytest.mark.skipif(COQC is None, reason="coqc not installed")

EXAMPLES = ["counter", "gcd", "arbiter", "saturating_adder", "alu", "mul", "fifo", "blackbox", "axi4_lite"]


def _coq_text(spec):
    km = isir_to_koika.convert(spec)
    return "\n".join(km.state_definitions) + "\n"


def _typecheck(name, tmp_path):
    spec = convert_ast_to_isir_module(parse_isir(Path(f"examples/{name}/{name}.isir")).module)
    code = _coq_text(spec)
    vfile = tmp_path / f"{name}.v"
    vfile.write_text(code)
    r = subprocess.run([COQC, str(vfile)], capture_output=True, text=True, timeout=180, cwd=str(tmp_path))
    return r.returncode, r.stderr


def _combinational_spec(reference, operand="(mul x 0)"):
    property_ops = [isir.SpecPropertyOp(
        prop_name="p", kind="combinational",
        expression={"kind": "combinational", "operand": operand, "reference": reference})]
    proof_obligations = [{"property": "p", "engine": "theorem_proving", "backend": "koika"}]
    inputs = [isir.Interface(name="x", direction="input", data_type="bits<4>")]
    return isir.SpecModule(name="tst", state_ops=[], rule_ops=[], property_ops=property_ops,
                           proof_obligations=proof_obligations, inputs=inputs, outputs=[],
                           clocks=[], resets=[])


class TestCoqcTypecheck:
    @pytest.mark.parametrize("name", EXAMPLES)
    def test_generated_coq_typechecks(self, name, tmp_path):
        rc, stderr = _typecheck(name, tmp_path)
        assert rc == 0, f"{name} generated Coq failed to type-check:\n{stderr[-1500:]}"


class TestFalsyReference:
    def test_reference_zero_is_not_true(self):
        code = _coq_text(_combinational_spec(reference=0))
        assert "Theorem p_proved" in code
        assert "= (true)" not in code and "= (t)" not in code, code
        assert "= (0)" in code, code

    def test_reference_false_is_not_true(self):
        code = _coq_text(_combinational_spec(reference=False, operand="(eq x 0)"))
        assert "= (true)" not in code, code
        assert "= (false)" in code, code


class TestInputBounds:
    def test_mul_one_has_input_width_hypotheses(self):
        spec = convert_ast_to_isir_module(parse_isir(Path("examples/mul/mul.isir")).module)
        code = _coq_text(spec)
        m = re.search(r"Theorem mul_one_proved : (.*?)\.", code, re.DOTALL)
        assert m, "mul_one_proved not found"
        stmt = m.group(1)
        assert "(x inputs < 2^16)" in stmt, stmt
        assert "(y inputs < 2^16)" in stmt, stmt
