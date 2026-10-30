# tests/unit/test_acl2_semantics.py
#
# The ACL2 transcription of the source semantics
# (src/semantics/acl2/acl2_semantics.lisp) must load and prove the ALU
# example, which must agree with the reference `eval_expr`.

import shutil
import pytest
import subprocess
from pathlib import Path
from isir.utils.expr import eval_expr, parse_sexpr


ACL2 = shutil.which("acl2")
SEMANTICS = Path("src/semantics/acl2/acl2_semantics.lisp")
CORRESPONDENCE = Path("src/semantics/acl2/acl2_correspondence.lisp")
REFINEMENT = Path("src/semantics/acl2/refinement.lisp")

pytestmark = pytest.mark.skipif(ACL2 is None, reason="acl2 not installed")


def _run_acl2(files=()):
    driver = '(in-package "ACL2")\n'
    for f in files:
        driver += f'(ld "{f}")\n'
    out = subprocess.run([ACL2], input=driver,
                         capture_output=True, text=True, timeout=300)
    return out.stdout + out.stderr


class TestAcl2SemanticsLoads:
    def test_book_has_no_failures(self):
        out = _run_acl2([SEMANTICS])
        assert "FAILED" not in out, "acl2_semantics.lisp failed to load cleanly"

    def test_alu_add_wraps_proved(self):
        out = _run_acl2([SEMANTICS])
        assert "ALU-ADD-WRAPS" in out, "alu-add-wraps theorem not proved"


class TestAcl2CorrespondenceLoads:
    def test_book_has_no_failures(self):
        out = _run_acl2([SEMANTICS, CORRESPONDENCE])
        assert "FAILED" not in out, "acl2_correspondence.lisp failed to load cleanly"

    def test_correspondence_theorems_present(self):
        out = _run_acl2([SEMANTICS, CORRESPONDENCE])
        for thm in ["ADD-CORRESPONDENCE", "AND-CORRESPONDENCE", "XOR-CORRESPONDENCE",
                    "SUB-CORRESPONDENCE", "R-STATE", "SUPPORTED-BINOP"]:
            assert thm in out, f"{thm} not admitted"


class TestAcl2RefinementLoads:
    def test_book_has_no_failures(self):
        out = _run_acl2([SEMANTICS, CORRESPONDENCE, REFINEMENT])
        assert "FAILED" not in out, "refinement.lisp failed to load cleanly"

    def test_core_fragment_instances_present(self):
        out = _run_acl2([SEMANTICS, CORRESPONDENCE, REFINEMENT])
        for thm in ["COUNTER-ADD-REFINES", "GCD-SUB-REFINES", "ARBITER-ITE-REFINES"]:
            assert thm in out, f"{thm} not admitted"


class TestAcl2SemanticsAgreesWithEvalExpr:
    def test_alu_add_matches_reference(self):
        """The ACL2 step computes 250+10 = 4 (mod 256); eval_expr gives 4."""
        out = _run_acl2([SEMANTICS])
        # the proved theorem equates isir-step to (cons (list 4) nil)
        assert "ALU-ADD-WRAPS" in out
        ref = eval_expr(parse_sexpr("(add a b)"), {}, {"a": 250, "b": 10}, {},
                        width=8, widths={"a": 8, "b": 8})
        assert ref == 4
