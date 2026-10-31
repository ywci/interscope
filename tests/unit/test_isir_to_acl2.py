# tests/unit/test_isir_to_acl2.py
#
# Unit tests for lowering from SpecModule to ACL2Module.

import pytest
from isir.dialects import isir, acl2
from isir.lowering import isir_to_acl2


def create_basic_spec_module():
    """Return a SpecModule with two registers, one memory, three rules, and a property."""
    state_ops = [
        isir.SpecStateOp(
            state_name="count",
            kind="register",
            data_type="bits<8>",
            initial=0
        ),
        isir.SpecStateOp(
            state_name="flag",
            kind="register",
            data_type="bool",
            initial=False
        ),
        isir.SpecStateOp(
            state_name="mem",
            kind="memory",
            data_type={"type": "memory", "elem": "bits<32>", "depth": 8}
        )
    ]

    rule_ops = [
        isir.SpecRuleOp(
            rule_name="inc",
            condition="(lt (read count) 255)",
            actions=[
                "(write count (add (read count) 1))",
                "(write flag true)",
            ],
            priority=10
        ),
        isir.SpecRuleOp(
            rule_name="reset_flag",
            condition="(read flag)",
            actions=["(write flag false)"],
            priority=5
        ),
        isir.SpecRuleOp(
            rule_name="noop",
            condition="true",
            actions=[],
            priority=0
        )
    ]

    property_ops = [
        isir.SpecPropertyOp(
            prop_name="count_bound",
            kind="safety",
            expression={"kind": "always", "operand": "(le (read count) 255)"},
            assumes=["(not (read flag))"],
            guarantees=[]
        )
    ]

    proof_obligations = [
        {
            "property": "count_bound",
            "status": "unproved",
            "engine": "theorem_proving",
            "backend": "acl2",
            "metadata": {"acl2_hints": ['("Goal" :induct t)']}
        }
    ]

    inputs = [
        isir.Interface(name="start", direction="input", data_type="bool")
    ]
    outputs = [
        isir.Interface(name="done", direction="output", data_type="bool")
    ]

    spec_mod = isir.SpecModule(
        name="counter",
        state_ops=state_ops,
        rule_ops=rule_ops,
        property_ops=property_ops,
        proof_obligations=proof_obligations,
        inputs=inputs,
        outputs=outputs,
        clocks=[],
        resets=[]
    )
    return spec_mod


class TestSpecToAcl2Basic:
    def test_convert_returns_acl2_module(self):
        spec_mod = create_basic_spec_module()
        acl2_mod = isir_to_acl2.convert(spec_mod)
        assert isinstance(acl2_mod, acl2.ACL2Module)
        assert acl2_mod.name == "counter"

    def test_contains_initial_state_defun(self):
        acl2_mod = isir_to_acl2.convert(create_basic_spec_module())
        init_def = next(d for d in acl2_mod.defuns if d.func_name.endswith("_init"))
        assert init_def.args == []
        assert "0" in init_def.body
        assert "nil" in init_def.body

    def test_transition_function_exists(self):
        acl2_mod = isir_to_acl2.convert(create_basic_spec_module())
        step_def = next(d for d in acl2_mod.defuns if d.func_name.endswith("_step"))
        assert step_def.func_name == "counter_step"
        assert "st" in step_def.args
        assert "start" in step_def.args

    def test_transition_function_uses_cond(self):
        acl2_mod = isir_to_acl2.convert(create_basic_spec_module())
        step_def = next(d for d in acl2_mod.defuns if d.func_name == "counter_step")
        # default schedule is `parallel`: all rules merge via `let*` (was `cond`)
        assert "(let*" in step_def.body

    def test_rule_priority_order_in_cond(self):
        """Highest priority rule (inc, priority 10) should appear first in cond."""
        acl2_mod = isir_to_acl2.convert(create_basic_spec_module())
        step_def = next(d for d in acl2_mod.defuns if d.func_name == "counter_step")
        inc_cond_start = step_def.body.find("(< (nth 0 st)")
        flag_cond_start = step_def.body.find("(nth 1 st)")
        assert inc_cond_start != -1, "inc condition not found in transition function"
        assert flag_cond_start != -1, "flag condition not found in transition function"
        assert inc_cond_start < flag_cond_start, "inc rule should appear before flag rule"

    def test_write_action_updates_state_correctly(self):
        """Write actions should produce (update-nth idx val st) chains."""
        acl2_mod = isir_to_acl2.convert(create_basic_spec_module())
        step_def = next(d for d in acl2_mod.defuns if d.func_name == "counter_step")
        assert "update-nth" in step_def.body
        assert "update-nth 0" in step_def.body
        assert "update-nth 1" in step_def.body

    def test_read_expression_becomes_nth(self):
        """Condition (read count) should become (nth idx st)."""
        acl2_mod = isir_to_acl2.convert(create_basic_spec_module())
        step_def = next(d for d in acl2_mod.defuns if d.func_name == "counter_step")
        assert "(nth 0 st)" in step_def.body

    def test_no_rules_creates_identity_step(self):
        """If no rules exist, transition function returns st unchanged."""
        spec_mod = isir.SpecModule(
            name="empty",
            state_ops=[isir.SpecStateOp(state_name="r", kind="register", data_type="bits<1>")],
            rule_ops=[],
            proof_obligations=[],
            inputs=[],
            outputs=[],
            clocks=[],
            resets=[]
        )
        acl2_mod = isir_to_acl2.convert(spec_mod)
        step_def = next(d for d in acl2_mod.defuns if d.func_name == "empty_step")
        # parallel merge with zero rules is still the identity (via let* st0)
        assert "(let*" in step_def.body and "st0" in step_def.body


class TestAcl2TheoremGeneration:
    def test_generates_defthm_for_proof_obligation(self):
        acl2_mod = isir_to_acl2.convert(create_basic_spec_module())
        assert len(acl2_mod.defthms) == 1
        thm = acl2_mod.defthms[0]
        assert thm.thm_name == "count_bound_correct"
        assert "implies" in thm.statement
        # sound: the bound holds at every cycle t of the trace from init
        assert "(counter_stepn t counter_init" in thm.statement
        assert "(<= (nth 0 (car (counter_stepn t counter_init" in thm.statement

    def test_hints_from_metadata(self):
        acl2_mod = isir_to_acl2.convert(create_basic_spec_module())
        thm = acl2_mod.defthms[0]
        assert thm.hints == ['("Goal" :induct t)']

    def test_no_proof_obligations_no_theorems(self):
        spec_mod = create_basic_spec_module()
        spec_mod.proof_obligations = []
        acl2_mod = isir_to_acl2.convert(spec_mod)
        assert len(acl2_mod.defthms) == 0


class TestWp0Fidelity:
    def test_width_of_type(self):
        assert isir_to_acl2._width_of_type("bool") == 1
        assert isir_to_acl2._width_of_type("bits<8>") == 8
        assert isir_to_acl2._width_of_type("bits<32>") == 32

    def test_arithmetic_wraps_at_operand_width(self):
        from isir.utils.expr import parse_sexpr
        si = {"x": 0, "y": 1}
        w = {"x": 8, "y": 8}
        assert isir_to_acl2._expr_to_acl2(parse_sexpr("(add x y)"), si, [], [], widths=w) \
            == "(mod (+ (nth 0 st) (nth 1 st)) (expt 2 8))"
        assert isir_to_acl2._expr_to_acl2(parse_sexpr("(sub x y)"), si, [], [], widths=w) \
            == "(mod (- (nth 0 st) (nth 1 st)) (expt 2 8))"
        assert isir_to_acl2._expr_to_acl2(parse_sexpr("(mul x y)"), si, [], [], widths=w) \
            == "(mod (* (nth 0 st) (nth 1 st)) (expt 2 8))"
        assert isir_to_acl2._expr_to_acl2(parse_sexpr("(shl x 2)"), si, [], [], widths=w) \
            == "(mod (ash (nth 0 st) 2) (expt 2 8))"

    def test_bitwise_ops_use_logand_logior_logxor(self):
        from isir.utils.expr import parse_sexpr
        si = {"x": 0, "y": 1}
        w = {"x": 8, "y": 8}
        assert isir_to_acl2._expr_to_acl2(parse_sexpr("(and x y)"), si, [], [], widths=w) \
            == "(logand (nth 0 st) (nth 1 st))"
        assert isir_to_acl2._expr_to_acl2(parse_sexpr("(or x y)"), si, [], [], widths=w) \
            == "(logior (nth 0 st) (nth 1 st))"
        assert isir_to_acl2._expr_to_acl2(parse_sexpr("(xor x y)"), si, [], [], widths=w) \
            == "(logxor (nth 0 st) (nth 1 st))"

    def test_saturating_adder_overflow_wraps(self):
        """overflow := ge (add x y) 256 must compare the *wrapped* 8-bit sum."""
        from pathlib import Path
        from isir.parser.parser import parse_isir
        from isir.lowering.ast_to_isir import convert_ast_to_isir_module
        spec = convert_ast_to_isir_module(
            parse_isir(Path("examples/saturating_adder/saturating_adder.isir")).module)
        km = isir_to_acl2.convert(spec)
        step = next(d for d in km.defuns if d.func_name.endswith("_step"))
        assert "(mod (+ x y) (expt 2 8))" in step.body
        # the comparison is against the wrapped sum, not the unbounded sum
        assert "(>= (mod (+ x y) (expt 2 8)) 256)" in step.body


class TestReadOnInput:
    def test_read_input_lowers_to_input_var(self):
        """(read x) on an input resolves to the input variable (matching eval_expr)."""
        from isir.lowering.isir_to_acl2 import _expr_to_acl2
        from isir.utils.expr import parse_sexpr
        si = {"count": 0}
        inputs = ["x"]
        # register read -> (nth idx st)
        assert _expr_to_acl2(parse_sexpr("(read count)"), si, [], inputs) == "(nth 0 st)"
        # input read -> the input variable name
        assert _expr_to_acl2(parse_sexpr("(read x)"), si, [], inputs) == "x"

    def test_gcd_lowers_without_unknown_state(self):
        from pathlib import Path
        from isir.parser.parser import parse_isir
        from isir.lowering.ast_to_isir import convert_ast_to_isir_module
        from isir.lowering.isir_to_acl2 import convert
        spec = convert_ast_to_isir_module(parse_isir(Path("examples/gcd/gcd.isir")).module)
        km = convert(spec)
        step = next(d for d in km.defuns if d.func_name == "gcd_step")
        # the load rule now lowers: a := x, b := y (inputs), not "Unknown state"
        assert "x" in step.body and "y" in step.body


class TestSingleCycleGaps:
    """Coverage for the single-cycle lowering gaps closed in the ACL2 backend."""

    def _expr(self, s, si=None, inputs=None, widths=None, state_types=None, input_types=None):
        from isir.utils.expr import parse_sexpr
        return isir_to_acl2._expr_to_acl2(
            parse_sexpr(s),
            si or {}, [], inputs or ["a", "b"],
            widths or {"a": 4, "b": 4},
            state_types or {}, input_types or {"a": "bits<4>", "b": "bits<4>"},
        )

    def test_lshift_rshift_aliases(self):
        assert self._expr("(lshift a b)") == "(mod (ash a b) (expt 2 4))"
        assert self._expr("(rshift a b)") == "(mod (ash a (- b)) (expt 2 4))"

    def test_defined_function_is_inlined(self):
        """A defined (non-recursive) function call is beta-reduced before lowering."""
        from isir.dialects.isir import SpecModule, SpecStateOp, SpecRuleOp, Interface
        spec = SpecModule(
            name="f", state_ops=[SpecStateOp(state_name="r", kind="register", data_type="bits<4>")],
            rule_ops=[SpecRuleOp(rule_name="tick", condition="t", actions=["(write r (add (read r) 1))"])],
            inputs=[Interface(name="i", direction="input", data_type="bool")], outputs=[],
            functions=[{"name": "inc", "params": [{"name": "v", "type": "bits<4>"}], "return": "bits<4>",
                        "body": "(add v 1)"}], property_ops=[], proof_obligations=[],
        )
        km = isir_to_acl2.convert(spec)
        step = next(d for d in km.defuns if d.func_name == "f_step")
        # inc (read r) -> (mod (+ (nth 0 st) 1) (expt 2 4)) — inlined, no `inc` call
        assert "(inc" not in step.body
        assert "(mod (+ (nth 0 st) 1) (expt 2 4))" in step.body

    def test_recursive_function_fuel_defun(self):
        from pathlib import Path
        from isir.parser.parser import parse_isir
        from isir.lowering.ast_to_isir import convert_ast_to_isir_module
        spec = convert_ast_to_isir_module(parse_isir(Path("examples/gcd/gcd.isir")).module)
        km = isir_to_acl2.convert(spec)
        gcd_sub = next(d for d in km.defuns if d.func_name == "gcd_sub")
        assert gcd_sub.args == ["fuel", "a", "b"]
        assert "(zp fuel)" in gcd_sub.body
        # recursive self-call recurses on the fuel predecessor
        assert "(gcd_sub (1- fuel)" in gcd_sub.body
        # params a/b are local variables, not state reads
        assert "(= a 0)" in gcd_sub.body

    def test_bodyless_function_encapsulate(self):
        from isir.dialects.isir import SpecModule, SpecStateOp, SpecRuleOp
        spec = SpecModule(
            name="bb", state_ops=[SpecStateOp(state_name="r", kind="register", data_type="bits<8>")],
            rule_ops=[SpecRuleOp(rule_name="tick", condition="t", actions=["(write r (sigmoid 0))"])],
            inputs=[], outputs=[],
            functions=[{"name": "sigmoid", "params": [{"name": "v", "type": "bits<8>"}], "return": "bits<8>"}],
            property_ops=[], proof_obligations=[],
        )
        km = isir_to_acl2.convert(spec)
        assert any("(encapsulate" in f and "sigmoid" in f for f in km.raw_forms)

    def test_axioms_become_defaxiom(self):
        from isir.dialects.isir import SpecModule, SpecStateOp, SpecRuleOp
        spec = SpecModule(
            name="ax", state_ops=[SpecStateOp(state_name="r", kind="register", data_type="bits<8>")],
            rule_ops=[SpecRuleOp(rule_name="tick", condition="t", actions=["(write r (read r))"])],
            inputs=[], outputs=[],
            axioms=[{"name": "r_nonneg", "statement": "(gte (read r) 0)"}],
            property_ops=[], proof_obligations=[],
        )
        km = isir_to_acl2.convert(spec)
        ax = next(t for t in km.defthms if t.thm_name == "r_nonneg")
        assert ax.axiom is True
        assert ax.to_lisp().startswith("(defaxiom r_nonneg")

    def test_combinational_property(self):
        from pathlib import Path
        from isir.parser.parser import parse_isir
        from isir.lowering.ast_to_isir import convert_ast_to_isir_module
        spec = convert_ast_to_isir_module(parse_isir(Path("examples/mul/mul.isir")).module)
        km = isir_to_acl2.convert(spec)
        comm = next(t for t in km.defthms if t.thm_name == "mul_commutative_correct")
        assert "(equal" in comm.statement
        assert "(* x y)" in comm.statement and "(* y x)" in comm.statement


class TestTemporalConstructs:
    """Coverage for the clocked trace model (next/prev/rose/fell/stable + always/after/eventually/until)."""

    def _expr(self, s, trace=True):
        from isir.utils.expr import parse_sexpr
        return isir_to_acl2._expr_to_acl2(
            parse_sexpr(s), {"x": 0}, [], ["a"],
            {"x": 4, "a": 4}, {"x": "bits<4>"}, {"a": "bits<4>"},
            trace_stepn="f_stepn" if trace else None, trace_ct="t" if trace else None,
        )

    def test_prev_next_in_trace(self):
        assert self._expr("(prev (read x))") == "(nth 0 (f_stepn (nfix (1- t)) st a))"
        assert self._expr("(next (read x))") == "(nth 0 (f_stepn (1+ t) st a))"

    def test_rose_fell_stable(self):
        assert self._expr("(rose (read x))") == "(and (nth 0 (f_stepn t st a)) (not (nth 0 (f_stepn (nfix (1- t)) st a))))"
        assert self._expr("(fell (read x))") == "(and (not (nth 0 (f_stepn t st a))) (nth 0 (f_stepn (nfix (1- t)) st a)))"
        assert self._expr("(stable (read x))") == "(equal (nth 0 (f_stepn t st a)) (nth 0 (f_stepn (nfix (1- t)) st a)))"

    def test_temporal_requires_trace(self):
        import pytest as _pytest
        from isir.utils.expr import parse_sexpr
        with _pytest.raises(Exception):
            isir_to_acl2._expr_to_acl2(parse_sexpr("(prev (read x))"), {"x": 0}, [], ["a"])

    def test_stepn_defun_generated(self):
        from isir.dialects.isir import SpecModule, SpecStateOp, SpecRuleOp
        spec = SpecModule(
            name="tr", state_ops=[SpecStateOp(state_name="r", kind="register", data_type="bits<4>")],
            rule_ops=[SpecRuleOp(rule_name="tick", condition="t", actions=["(write r (add (read r) 1))"])],
            inputs=[], outputs=[], property_ops=[], proof_obligations=[],
        )
        km = isir_to_acl2.convert(spec)
        stepn = next(d for d in km.defuns if d.func_name == "tr_stepn")
        assert stepn.args == ["n", "st"]
        assert "(if (zp n) st" in stepn.body
        assert "(tr_stepn (1- n) (tr_step st" in stepn.body

    def test_after_property_uses_stepn(self):
        from pathlib import Path
        from isir.parser.parser import parse_isir
        from isir.lowering.ast_to_isir import convert_ast_to_isir_module
        spec = convert_ast_to_isir_module(parse_isir(Path("examples/riscv/riscv.isir")).module)
        km = isir_to_acl2.convert(spec)
        thm = next(t for t in km.defthms if t.thm_name == "pc_nonneg_after_3_correct")
        assert "(riscv_mini_stepn 3 st" in thm.statement

    def test_bounded_eventually_defun(self):
        from isir.dialects.isir import SpecModule, SpecStateOp, SpecRuleOp, SpecPropertyOp
        spec = SpecModule(
            name="ev", state_ops=[SpecStateOp(state_name="r", kind="register", data_type="bits<4>")],
            rule_ops=[SpecRuleOp(rule_name="tick", condition="t", actions=["(write r (add (read r) 1))"])],
            inputs=[], outputs=[],
            property_ops=[SpecPropertyOp(prop_name="r_reaches", kind="safety",
                          expression={"kind": "eventually", "bound": 5, "operand": "(eq (read r) 3)"})],
            proof_obligations=[{"property": "r_reaches", "backend": "acl2"}],
        )
        km = isir_to_acl2.convert(spec)
        ev = next(d for d in km.defuns if d.func_name == "r_reaches_eventually")
        assert "(if (zp n)" in ev.body and "(or" in ev.body
        thm = next(t for t in km.defthms if t.thm_name == "r_reaches_correct")
        assert "(r_reaches_eventually n st" in thm.statement


class TestUnboundedLiveness:
    """defun-sk encoding for unbounded eventually/until + fairness."""

    def _spec(self):
        from isir.dialects.isir import SpecModule, SpecStateOp, SpecRuleOp, SpecPropertyOp
        return SpecModule(
            name="lv", state_ops=[SpecStateOp(state_name="r", kind="register", data_type="bits<4>")],
            rule_ops=[SpecRuleOp(rule_name="tick", condition="t", actions=["(write r (add (read r) 1))"])],
            inputs=[], outputs=[],
            property_ops=[
                SpecPropertyOp(prop_name="r_reaches_3", kind="liveness",
                               expression={"kind": "eventually", "operand": "(eq (read r) 3)"}),
                SpecPropertyOp(prop_name="r_then_5", kind="liveness",
                               expression={"kind": "until", "left": "(lt (read r) 5)", "right": "(eq (read r) 5)"}),
            ],
            proof_obligations=[{"property": "r_reaches_3", "backend": "acl2"}, {"property": "r_then_5", "backend": "acl2"}],
            fairness=[{"name": "r_fair", "type": "weak", "condition": "(lt (read r) 4)"}],
        )

    def test_unbounded_eventually_defunsk(self):
        km = isir_to_acl2.convert(self._spec())
        sk = next(d for d in km.defun_sk_ops if d.pred_name == "r_reaches_3_eventually")
        assert sk.quantifier == "exists"
        assert "(exists (i)" in sk.to_lisp()
        assert "(natp i)" in sk.body
        thm = next(t for t in km.defthms if t.thm_name == "r_reaches_3_correct")
        assert "(r_reaches_3_eventually st" in thm.statement

    def test_unbounded_until_defunsk(self):
        km = isir_to_acl2.convert(self._spec())
        before = next(d for d in km.defun_sk_ops if d.pred_name == "r_then_5_before")
        assert before.quantifier == "forall"
        assert "(implies (< j k)" in before.body
        until = next(d for d in km.defun_sk_ops if d.pred_name == "r_then_5_until")
        assert until.quantifier == "exists"

    def test_fairness_defaxiom(self):
        km = isir_to_acl2.convert(self._spec())
        ax = next(t for t in km.defthms if t.thm_name == "r_fair")
        assert ax.axiom is True
        assert "(r_fair_eventually st" in ax.statement


class TestProofAutomation:
    """skip-proofs admission + kind-aware hints + self-contained code."""

    def _gcd(self):
        from pathlib import Path
        from isir.parser.parser import parse_isir
        from isir.lowering.ast_to_isir import convert_ast_to_isir_module
        return convert_ast_to_isir_module(parse_isir(Path("examples/gcd/gcd.isir")).module)

    def test_defthms_are_admitted(self):
        km = isir_to_acl2.convert(self._gcd())
        thms = [t for t in km.defthms if not t.axiom]
        assert thms
        assert all(t.skip_proofs for t in thms)
        assert "(skip-proofs" in thms[0].to_lisp()

    def test_safety_hint_uses_stepn(self):
        from isir.dialects.isir import SpecModule, SpecStateOp, SpecRuleOp, SpecPropertyOp
        spec = SpecModule(
            name="st", state_ops=[SpecStateOp(state_name="c", kind="register", data_type="bits<8>")],
            rule_ops=[SpecRuleOp(rule_name="tick", condition="t", actions=["(write c (add (read c) 1))"])],
            inputs=[], outputs=[],
            property_ops=[SpecPropertyOp(prop_name="c_bound", kind="safety",
                          expression={"kind": "always", "operand": "(le (read c) 255)"})],
            proof_obligations=[{"property": "c_bound", "backend": "acl2"}],
        )
        km = isir_to_acl2.convert(spec)
        done = next(t for t in km.defthms if t.thm_name == "c_bound_correct")
        assert "st_stepn" in " ".join(done.hints)

    def test_code_is_self_contained(self):
        km = isir_to_acl2.convert(self._gcd())
        code = km.to_acl2_code()
        assert 'include-book "arithmetic-5/top"' in code
        assert "(defun isir-gcd" in code
        # unused-input ignorable declaration (gcd has inputs start x y)
        assert "(declare (ignorable" in code

    def test_generated_code_loads(self):
        import subprocess, shutil
        acl2 = shutil.which("acl2")
        if acl2 is None:
            import pytest
            pytest.skip("acl2 not installed")
        km = isir_to_acl2.convert(self._gcd())
        code = km.to_acl2_code()
        out = subprocess.run([acl2], input='(in-package "ACL2")\n(ld "x.lisp")\n'.replace('(ld "x.lisp")', ""),
                             capture_output=True, text=True, timeout=120)
        # load via a temp file
        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".lisp", mode="w", delete=False) as f:
            f.write(code)
            tmp = f.name
        try:
            out = subprocess.run([acl2], input=f'(in-package "ACL2")\n(ld "{tmp}")\n',
                                 capture_output=True, text=True, timeout=120)
            assert "FAILED" not in out.stdout
            assert out.returncode == 0
        finally:
            os.unlink(tmp)


class TestOperatorCoverage:
    """Exhaustive lowering of every single-cycle operator (exact term checks)."""

    def _e(self, s, state_types=None, input_types=None, trace=False, mem=None):
        from isir.utils.expr import parse_sexpr
        si = {"x": 0, "y": 1}
        st = state_types if state_types is not None else {"x": "bits<4>", "y": "bits<4>"}
        it = input_types if input_types is not None else {"a": "bits<4>", "b": "bits<4>"}
        return isir_to_acl2._expr_to_acl2(
            parse_sexpr(s), si, mem or [], ["a", "b"],
            {"x": 4, "y": 4, "a": 4, "b": 4}, st, it,
            trace_stepn="f_stepn" if trace else None, trace_ct="t" if trace else None,
        )

    def test_arithmetic_wrapped(self):
        assert self._e("(add a b)") == "(mod (+ a b) (expt 2 4))"
        assert self._e("(sub a b)") == "(mod (- a b) (expt 2 4))"
        assert self._e("(mul a b)") == "(mod (* a b) (expt 2 4))"
        assert self._e("(div a b)") == "(mod (truncate a b) (expt 2 4))"
        assert self._e("(mod a b)") == "(mod (mod a b) (expt 2 4))"
        assert self._e("(min a b)") == "(min a b)"
        assert self._e("(max a b)") == "(max a b)"
        assert self._e("(shl a b)") == "(mod (ash a b) (expt 2 4))"
        assert self._e("(shr a b)") == "(mod (ash a (- b)) (expt 2 4))"
        assert self._e("(lshift a b)") == "(mod (ash a b) (expt 2 4))"
        assert self._e("(rshift a b)") == "(mod (ash a (- b)) (expt 2 4))"
        assert self._e("(gcd a b)") == "(isir-gcd a b)"

    def test_bitwise_vs_logical(self):
        # bool operands -> logical and/or/xor
        st = {"x": "bool", "y": "bool"}; it = {"a": "bool", "b": "bool"}
        assert self._e("(and a b)", st, it) == "(and a b)"
        assert self._e("(or a b)", st, it) == "(or a b)"
        assert self._e("(xor a b)", st, it) == "(xor a b)"
        # bits operands -> bitwise logand/logior/logxor
        assert self._e("(and a b)") == "(logand a b)"
        assert self._e("(or a b)") == "(logior a b)"
        assert self._e("(xor a b)") == "(logxor a b)"
        assert self._e("(not a)") == "(not a)"

    def test_comparisons(self):
        assert self._e("(eq a b)") == "(= a b)"
        assert self._e("(neq a b)") == "(/= a b)"
        assert self._e("(gt a b)") == "(> a b)"
        assert self._e("(lt a b)") == "(< a b)"
        assert self._e("(gte a b)") == "(>= a b)"
        assert self._e("(lte a b)") == "(<= a b)"
        assert self._e("(le a b)") == "(<= a b)"
        assert self._e("(ge a b)") == "(>= a b)"
        assert self._e("(implies a b)") == "(implies a b)"

    def test_bit_vector_ops(self):
        assert self._e("(concat a b 4)") == "(+ (mod b (expt 2 4)) (* a (expt 2 4)))"
        assert self._e("(slice a 3 1)") == "(mod (floor a (expt 2 1)) (expt 2 (+ 1 (- 3 1))))"
        assert self._e("(sum a b a)") == "(+ a (+ b a))"
        assert self._e("(ite a b a)") == "(if a b a)"
        assert self._e("(read x)") == "(nth 0 st)"

    def test_mem_read(self):
        assert self._e("(mem_read m a)", mem=["m"]) == "(nth a (nth 0 mem))"

    def test_mem_write_action(self):
        from isir.utils.expr import parse_sexpr
        out = isir_to_acl2._action_to_acl2_update(
            parse_sexpr("(mem_write m a 5)"), {"x": 0}, ["m"], ["a"])
        assert "(update-nth 0 (update-nth a 5 (nth 0 mem)) mem)" in out
