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


class TestFirstWins:
    def test_fast_winner_not_blocked_by_slow_loser(self):
        import time
        from isir.verification.cowork import run_cowork

        def fast():
            return ProofResult(success=True, proof_script="fast", backend="koika")

        def slow():
            time.sleep(2.0)
            return ProofResult(success=False, backend="acl2")

        t0 = time.time()
        r = run_cowork(fast, slow)
        dt = time.time() - t0
        assert r.success and r.winner == "koika"
        assert dt < 1.5, f"first-wins still blocked on the slow loser ({dt:.2f}s)"


class TestCrossBackendReflection:
    def _double_failure(self):
        from isir.verification.cowork import CoWorkResult
        return CoWorkResult(
            success=False, winner=None,
            metadata={"koika_error": "lia cannot prove x*y <= 65025",
                      "acl2_error": "checkpoint: (<= (mod (* x y) 65536) 65025)"},
            error_message="koika: ...; acl2: ...",
        )

    def test_build_prompt_contains_both_errors(self):
        from isir.verification.cowork import build_reflection_prompt
        p = build_reflection_prompt(self._double_failure())
        assert "lia cannot prove x*y <= 65025" in p
        assert "checkpoint: (<= (mod (* x y) 65536) 65025)" in p

    def test_reflect_returns_none_on_success(self):
        from isir.verification.cowork import CoWorkResult, reflect_on_failure
        cw = CoWorkResult(success=True, winner="koika")
        assert reflect_on_failure(cw, object()) is None

    def test_reflect_returns_llm_suggestion(self):
        from isir.verification.cowork import reflect_on_failure
        class FakeLLM:
            def generate(self, prompt):
                assert "lia cannot prove" in prompt and "checkpoint" in prompt
                return "add lemma: x<=255 -> y<=255 -> x*y<=65025"
        sug = reflect_on_failure(self._double_failure(), FakeLLM())
        assert "x*y<=65025" in sug

    def test_cowork_retry_proves_when_reflection_succeeds(self):
        from isir.verification.cowork import cowork_retry
        class FakeLLM:
            def generate(self, prompt):
                return "Lemma helper : ... Proof. lia. Qed. Proof. nia. Qed."
        def retry(script):
            assert "helper" in script
            return ProofResult(success=True, proof_script=script)
        r = cowork_retry(self._double_failure(), FakeLLM(), retry)
        assert r is not None and r.success
        assert r.metadata.get("cowork_reflection_proved") is True

    def test_cowork_retry_returns_none_when_retry_fails(self):
        from isir.verification.cowork import cowork_retry
        class FakeLLM:
            def generate(self, prompt):
                return "Proof. nia. Qed."
        def retry(script):
            return ProofResult(success=False, error_message="still fails")
        assert cowork_retry(self._double_failure(), FakeLLM(), retry) is None


class TestRealWorldCoworkUsefulnessExamples:
    """The 4 re-tagged real-world properties must be cowork (koika_acl2) and
    lower to both backends, so the cross-backend reflection path is exercised."""
    TARGETS = {
        "fpu": ["flip_sign_involutive"],
        "gcd": ["gcd_commutes", "gcd_diag"],
        "riscv": ["pc_nonneg_after_3"],
    }

    def test_properties_are_koika_acl2(self):
        from pathlib import Path
        from isir.parser.parser import parse_isir
        from isir.lowering.ast_to_isir import convert_ast_to_isir_module
        for ex, props in self.TARGETS.items():
            spec = convert_ast_to_isir_module(parse_isir(Path(f"examples/{ex}/{ex}.isir")).module)
            tagged = {po.get("property") for po in spec.proof_obligations if po.get("backend") == "koika_acl2"}
            for p in props:
                assert p in tagged, f"{ex}:{p} not koika_acl2-tagged"

    def test_properties_lower_to_both_backends(self):
        from pathlib import Path
        from isir.parser.parser import parse_isir
        from isir.lowering.ast_to_isir import convert_ast_to_isir_module
        from isir.lowering import isir_to_acl2, isir_to_koika
        for ex, props in self.TARGETS.items():
            spec = convert_ast_to_isir_module(parse_isir(Path(f"examples/{ex}/{ex}.isir")).module)
            a = {t.thm_name for t in isir_to_acl2.convert(spec).defthms}
            k = "\n".join(isir_to_koika.convert(spec).state_definitions)
            for p in props:
                assert f"{p}_correct" in a, f"{ex}:{p} missing from ACL2"
                assert f"{p}_proved" in k, f"{ex}:{p} missing from Koika"

    def test_energy_meter_lowers_to_both(self):
        from pathlib import Path
        from isir.parser.parser import parse_isir
        from isir.lowering.ast_to_isir import convert_ast_to_isir_module
        from isir.lowering import isir_to_acl2, isir_to_koika
        spec = convert_ast_to_isir_module(parse_isir(Path("examples/energy_meter/energy_meter.isir")).module)
        a = {t.thm_name for t in isir_to_acl2.convert(spec).defthms}
        k = "\n".join(isir_to_koika.convert(spec).state_definitions)
        assert "energy_bounded_correct" in a
        assert "energy_bounded_proved" in k

    def test_rec_comm_lowers_to_both(self):
        from pathlib import Path
        from isir.parser.parser import parse_isir
        from isir.lowering.ast_to_isir import convert_ast_to_isir_module
        from isir.lowering import isir_to_acl2, isir_to_koika
        spec = convert_ast_to_isir_module(parse_isir(Path("examples/rec_comm/rec_comm.isir")).module)
        a = {t.thm_name for t in isir_to_acl2.convert(spec).defthms}
        k = "\n".join(isir_to_koika.convert(spec).state_definitions)
        assert "rec_commutes_correct" in a
        assert "rec_commutes_proved" in k


class TestLemmaShareArm:
    def _prover(self):
        from isir.verification.proof.koika.prover import KoikaProver
        return KoikaProver(config={"provers": {"koika": {"use_proof_library": False}}})

    def test_inject_shared_lemmas_adds_hint_for_declared(self, tmp_path):
        f = tmp_path / "t.v"
        f.write_text("Theorem count_increments_proved : True.\nAdmitted.\n")
        p = self._prover()
        p._inject_shared_lemmas(f, ["count_increments_proved", "not_declared_proved"])
        c = f.read_text()
        assert "Hint Resolve count_increments_proved : core." in c
        assert "not_declared_proved" not in c

    def test_inject_shared_lemmas_skips_duplicate(self, tmp_path):
        f = tmp_path / "t.v"
        f.write_text("Hint Resolve a_proved : core.\nTheorem a_proved : True.\nAdmitted.\n")
        p = self._prover()
        p._inject_shared_lemmas(f, ["a_proved"])
        assert f.read_text().count("Hint Resolve a_proved") == 1

    def test_inject_shared_lemmas_noop_when_empty(self, tmp_path):
        f = tmp_path / "t.v"
        f.write_text("Theorem x : True.\nAdmitted.\n")
        p = self._prover()
        p._inject_shared_lemmas(f, [])
        assert f.read_text() == "Theorem x : True.\nAdmitted.\n"

    def test_shared_hint_is_load_bearing(self, tmp_path):
        """A `Hint Resolve` of a shared step-identity is actually load-bearing:
        the goal is unprovable by eauto without it, and provable with it."""
        import shutil, subprocess
        coqc = shutil.which("coqc")
        if coqc is None:
            import pytest
            pytest.skip("coqc not installed")
        base = (
            "Axiom f : nat -> nat.\n"
            "Theorem step_identity : forall x, f x = x + 1.\n"
            "Proof. Admitted.\n"
            "Theorem always_prop : f 5 = 6.\n"
            "Proof. eauto. Qed.\n"
        )
        # Without the hint, eauto cannot close always_prop (f is opaque).
        no_hint = tmp_path / "no_hint.v"
        no_hint.write_text(base)
        r = subprocess.run([coqc, str(no_hint)], capture_output=True, text=True, cwd=str(tmp_path))
        assert r.returncode != 0, "expected failure without the shared hint"

        # With the hint injected after step_identity, eauto closes it.
        with_hint = tmp_path / "with_hint.v"
        with_hint.write_text(base)
        p = self._prover()
        p._inject_shared_lemmas(with_hint, ["step_identity"])
        assert "Hint Resolve step_identity : core." in with_hint.read_text()
        r2 = subprocess.run([coqc, str(with_hint)], capture_output=True, text=True, cwd=str(tmp_path))
        assert r2.returncode == 0, f"expected success with the shared hint: {r2.stderr}"

    def test_energy_accum_lowers_to_both(self):
        from pathlib import Path
        from isir.parser.parser import parse_isir
        from isir.lowering.ast_to_isir import convert_ast_to_isir_module
        from isir.lowering import isir_to_acl2, isir_to_koika
        spec = convert_ast_to_isir_module(parse_isir(Path("examples/energy_accum/energy_accum.isir")).module)
        a = {t.thm_name for t in isir_to_acl2.convert(spec).defthms}
        k = "\n".join(isir_to_koika.convert(spec).state_definitions)
        assert "energy_step_correct" in a and "energy_bounded_correct" in a
        assert "energy_step_proved" in k and "energy_bounded_proved" in k
