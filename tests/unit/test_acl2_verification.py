# tests/unit/test_acl2_verification.py
#
# End-to-end ACL2 verification: every example lowers to loadable ACL2 without exception.

import glob
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from isir.parser.parser import parse_isir
from isir.lowering.ast_to_isir import convert_ast_to_isir_module
from isir.lowering import isir_to_acl2

ACL2 = shutil.which("acl2")
pytestmark = pytest.mark.skipif(ACL2 is None, reason="acl2 not installed")

EXAMPLES = sorted(Path(p).stem for p in glob.glob("examples/*/*.isir"))

# Core fragments that must both load and pass the differential.
CORE_FRAGMENTS = ["counter", "gcd", "arbiter", "saturating_adder", "alu"]

# Additional designs that exercise the wider feature surface (recursive
# functions, combinational equivalence, temporal `prev`, blackbox axioms).
FEATURE_DESIGNS = ["mul", "blackbox", "axi4_lite", "riscv", "fifo", "fibonacci"]


def _convert(name):
    path = f"examples/{name}/{name}.isir"
    spec = convert_ast_to_isir_module(parse_isir(Path(path)).module)
    return isir_to_acl2.convert(spec)


def _load(km, timeout=120):
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".lisp", mode="w", delete=False) as f:
        f.write(km.to_acl2_code())
        tmp = f.name
    try:
        out = subprocess.run([ACL2], input=f'(in-package "ACL2")\n(ld "{tmp}")\n',
                             capture_output=True, text=True, timeout=timeout)
        return out.stdout + out.stderr, out.returncode
    finally:
        os.unlink(tmp)


class TestAllExamplesLower:
    @pytest.mark.parametrize("name", EXAMPLES)
    def test_lowers_without_exception(self, name):
        # every example must produce a loadable ACL2 module (no lowering error)
        km = _convert(name)
        assert km is not None
        assert km.to_acl2_code().strip()


class TestRepresentativeLoads:
    @pytest.mark.parametrize("name", CORE_FRAGMENTS + FEATURE_DESIGNS)
    def test_generated_code_loads(self, name):
        km = _convert(name)
        out, rc = _load(km)
        assert rc == 0, f"{name} ACL2 load failed (exit {rc})"
        assert "FAILED" not in out, f"{name} generated code FAILED:\n{out[-2000:]}"


class TestDifferentialAgrees:
    @pytest.mark.parametrize("name", CORE_FRAGMENTS)
    def test_bounded_pass(self, name):
        from isir.verification.acl2_refinement import run_acl2_differential
        spec = convert_ast_to_isir_module(parse_isir(Path(f"examples/{name}/{name}.isir")).module)
        r = run_acl2_differential(spec, num_cases=20, seed=0)
        assert r.status == "bounded_pass", (name, r.status, r.counterexample)


class TestAcl2Books:
    def test_semantics_correspondence_refinement_load(self):
        driver = '(in-package "ACL2")\n' + "".join(
            f'(ld "{p}")\n' for p in
            ["src/semantics/acl2/acl2_semantics.lisp",
             "src/semantics/acl2/acl2_correspondence.lisp",
             "src/semantics/acl2/refinement.lisp"])
        out = subprocess.run([ACL2], input=driver, capture_output=True, text=True, timeout=300)
        assert "FAILED" not in out.stdout + out.stderr
