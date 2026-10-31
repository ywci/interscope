# tests/unit/test_coq_verify.py
#
# The "0 Admitted" gate + the Axiom-downgrade path.

from isir.lowering.coq_verify import find_admitted, downgrade_to_axiom, verify_no_admitted


def _coq(admitted=("a", "b"), proved=("c",)):
    lines = []
    for name in admitted:
        lines += [f"Theorem {name}_proved : True.", "Admitted.", ""]
    for name in proved:
        lines += [f"Theorem {name}_proved : True.", "Proof. reflexivity. Qed.", ""]
    return "\n".join(lines) + "\n"


class TestFindAdmitted:
    def test_finds_admitted_theorems(self):
        coq = _coq(admitted=("a", "b"), proved=("c",))
        assert find_admitted(coq) == ["a_proved", "b_proved"]

    def test_proved_theorems_not_reported(self):
        coq = _coq(admitted=(), proved=("c", "d"))
        assert find_admitted(coq) == []

    def test_axioms_not_reported_as_admitted(self):
        coq = "Axiom ax : True.\n" + _coq(admitted=("a",))
        assert find_admitted(coq) == ["a_proved"]  # ax is an Axiom, not Admitted


class TestDowngrade:
    def test_downgrade_removes_admitted(self):
        coq = _coq(admitted=("a",), proved=("c",))
        out = downgrade_to_axiom(coq, {"a_proved"})
        assert "Theorem a_proved" not in out
        assert "Axiom a_proved : True." in out
        assert find_admitted(out) == []
        # proved theorem untouched
        assert "Theorem c_proved" in out and "Qed." in out

    def test_verify_no_admitted_after_downgrade(self):
        coq = _coq(admitted=("a", "b"))
        assert verify_no_admitted(coq) == ["a_proved", "b_proved"]
        out = downgrade_to_axiom(coq, {"a_proved", "b_proved"})
        assert verify_no_admitted(out) == []


class TestLivenessDowngrade:
    def test_unbounded_eventually_emits_axiom_not_admitted(self):
        from isir.dialects import isir
        from isir.lowering import isir_to_koika
        property_ops = [isir.SpecPropertyOp(
            prop_name="grant_eventually", kind="safety",
            expression={"kind": "eventually", "operand": "(read grant)"})]
        proof_obligations = [{"property": "grant_eventually", "engine": "theorem_proving", "backend": "koika"}]
        state_ops = [isir.SpecStateOp(state_name="grant", kind="register", data_type="bool")]
        spec = isir.SpecModule(name="tst", state_ops=state_ops, rule_ops=[], property_ops=property_ops,
                               proof_obligations=proof_obligations, inputs=[], outputs=[], clocks=[], resets=[])
        km = isir_to_koika.convert(spec)
        code = "\n".join(km.state_definitions)
        assert "Axiom grant_eventually_proved" in code, code
        assert "Theorem grant_eventually_proved" not in code
        assert "Admitted." not in code.split("grant_eventually_proved")[-1].split("\n\n")[0]


class TestSelfIdentityAutoProof:
    def test_koika_self_identity_is_qed_not_admitted(self):
        from isir.dialects import isir
        from isir.lowering import isir_to_koika
        spec = isir.SpecModule(
            name="tst", state_ops=[isir.SpecStateOp(state_name="x", kind="register", data_type="bits<4>")],
            rule_ops=[], inputs=[], outputs=[],
            property_ops=[isir.SpecPropertyOp(prop_name="x_self", kind="safety",
                          expression={"kind": "always", "operand": "(eq (read x) (read x))"})],
            proof_obligations=[{"property": "x_self", "backend": "koika", "engine": "theorem_proving"}],
        )
        km = isir_to_koika.convert(spec)
        code = "\n".join(km.state_definitions)
        import re
        m = re.search(r"Theorem x_self_proved : .*?\n(Proof\..*?Qed\.|Admitted\.)", code, re.DOTALL)
        assert m and "Qed." in m.group(1), code[-500:]
        assert "Admitted." not in m.group(1)
