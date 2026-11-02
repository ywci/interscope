# tests/unit/test_cowork.py
#
# koika_acl2 co-work backend: merge + concurrent dispatch.

from isir.verification.cowork import CoWorkResult, merge_cowork, run_cowork
from isir.verification.proof.proof import ProofResult


def _koika(success, lemmas=None, meta=None, err=None):
    return ProofResult(success=success, proof_script="koika proof" if success else None,
                       auxiliary_lemmas=lemmas or [], metadata=meta or {}, error_message=err)


def _acl2(success, lemmas=None, meta=None, err=None):
    return ProofResult(success=success, proof_script="acl2 proof" if success else None,
                       auxiliary_lemmas=lemmas or [], metadata=meta or {}, error_message=err)


class TestMergeCowork:
    def test_koika_wins_and_shares_acl2_lemmas(self):
        r = merge_cowork(_koika(True, lemmas=["L1"]), _acl2(False, lemmas=["L2"], meta={"tactic": "induct"}))
        assert r.success and r.winner == "koika"
        assert "L1" in r.auxiliary_lemmas and "L2" in r.auxiliary_lemmas

    def test_acl2_wins(self):
        r = merge_cowork(_koika(False), _acl2(True, lemmas=["Lx"]))
        assert r.success and r.winner == "acl2"
        assert r.proof_script == "acl2 proof"

    def test_both_fail_merges_progress(self):
        r = merge_cowork(_koika(False, err="koika stuck", meta={"subgoal": "S1"}),
                         _acl2(False, err="acl2 stuck", meta={"checkpoint": "C1"}))
        assert not r.success and r.winner is None
        assert r.metadata["koika"] == {"subgoal": "S1"}
        assert r.metadata["acl2"] == {"checkpoint": "C1"}
        assert "koika stuck" in r.error_message and "acl2 stuck" in r.error_message


class TestRunCowork:
    def test_concurrent_first_wins(self):
        r = run_cowork(lambda: _koika(True, lemmas=["K"]),
                       lambda: _acl2(False))
        assert r.success and r.winner == "koika"
        assert "K" in r.auxiliary_lemmas


class TestKoikaAcl2Integration:
    def test_acl2_lowers_invariants(self):
        from isir.dialects import isir
        from isir.lowering import isir_to_acl2
        spec = isir.SpecModule(
            name="tst",
            state_ops=[isir.SpecStateOp(state_name="c", kind="register", data_type="bits<8>", initial=0)],
            rule_ops=[isir.SpecRuleOp(rule_name="tick", condition="t", actions=["(write c (add (read c) 1))"])],
            inputs=[], outputs=[],
            property_ops=[],
            invariants=[{"name": "c_le_255", "operand": "(le (read c) 255)"}],
            proof_obligations=[],
        )
        km = isir_to_acl2.convert(spec)
        thm = next((t for t in km.defthms if t.thm_name == "c_le_255"), None)
        assert thm is not None, "invariant not lowered to ACL2"
        assert "(nth 0 (car (tst_stepn t tst_init" in thm.statement or \
               "(nth 0 (tst_stepn t tst_init" in thm.statement
        assert thm.skip_proofs  # admitted lemma, usable as rewrite rule

    def test_koika_acl2_backend_accepted_by_both(self):
        from isir.cli.verify import _canonical_backend
        from isir.dialects import isir
        from isir.lowering import isir_to_acl2, isir_to_koika
        assert _canonical_backend("koika_acl2") == "koika_acl2"
        spec = isir.SpecModule(
            name="tst",
            state_ops=[isir.SpecStateOp(state_name="c", kind="register", data_type="bits<8>")],
            rule_ops=[], inputs=[], outputs=[],
            property_ops=[isir.SpecPropertyOp(prop_name="c_self", kind="safety",
                          expression={"kind": "always", "operand": "(eq (read c) (read c))"})],
            proof_obligations=[{"property": "c_self", "backend": "koika_acl2", "engine": "theorem_proving"}],
        )
        acl2_mod = isir_to_acl2.convert(spec)
        assert any(t.thm_name == "c_self_correct" for t in acl2_mod.defthms)
        koika_mod = isir_to_koika.convert(spec)
        assert "c_self_proved" in "\n".join(koika_mod.state_definitions)

    def test_examples_with_koika_acl2_lower_to_both(self):
        from pathlib import Path
        from isir.parser.parser import parse_isir
        from isir.lowering.ast_to_isir import convert_ast_to_isir_module
        from isir.lowering import isir_to_acl2, isir_to_koika
        for ex in ("counter", "fifo", "riscv_ooo_cache", "multicore_comp",
                    "chi_noc_multicore", "core_comp", "chi_multicore", "axi4_lite"):
            spec = convert_ast_to_isir_module(parse_isir(Path(f"examples/{ex}/{ex}.isir")).module)
            cw = [po for po in spec.proof_obligations if po.get("backend") == "koika_acl2"]
            assert cw, f"{ex}: no koika_acl2 properties"
            acl2_names = {t.thm_name for t in isir_to_acl2.convert(spec).defthms}
            koika_text = "\n".join(isir_to_koika.convert(spec).state_definitions)
            for po in cw:
                n = po.get("property")
                assert f"{n}_correct" in acl2_names, f"{n} not lowered to ACL2"
                assert f"{n}_proved" in koika_text, f"{n} not lowered to Koika"
