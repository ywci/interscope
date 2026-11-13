# tests/unit/test_ablation.py
#
# MC-gating + co-work ablation flags.

from isir.cli.verify import _effective_backend, _setup_arg_parser


class TestAblationFlags:
    def test_flags_parsed(self):
        args = _setup_arg_parser().parse_args(["x.isir", "--mc-lemmas", "--no-cowork"])
        assert args.mc_lemmas is True
        assert args.no_cowork is True
        assert args.no_mc_lemmas is False

    def test_no_mc_lemmas_parsed(self):
        args = _setup_arg_parser().parse_args(["x.isir", "--no-mc-lemmas"])
        assert args.no_mc_lemmas is True
        assert args.mc_lemmas is False

    def test_no_cowork_downgrades_koika_acl2(self):
        assert _effective_backend("koika_acl2", no_cowork=True) == "koika"
        assert _effective_backend("koika_acl2", no_cowork=False) == "koika_acl2"
        # non-co-work backends are unaffected
        assert _effective_backend("koika", True) == "koika"
        assert _effective_backend("acl2", True) == "acl2"
        assert _effective_backend("model_checking", True) == "model_checking"

    def test_property_kind_helper(self):
        from isir.cli.verify import _property_kind
        from isir.dialects import isir
        spec = isir.SpecModule(
            name="t",
            property_ops=[
                isir.SpecPropertyOp(prop_name="p_safety", kind="safety",
                                    expression={"kind": "always", "operand": "x"}),
                isir.SpecPropertyOp(prop_name="p_comb", kind="combinational",
                                    expression={"kind": "combinational", "operand": "y"}),
            ],
        )
        assert _property_kind(spec, "p_safety") == "always"   # inductive
        assert _property_kind(spec, "p_comb") == "combinational"
        assert _property_kind(spec, "missing") is None
