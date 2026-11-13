# tests/unit/test_gen_spec.py
#
# Natural-language spec generation (no S-expressions) + round-trip verification.

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from gen_spec import (  # noqa: E402
    _facts,
    _reconstruct,
    gen_markdown,
    verify_roundtrip,
)

from isir.lowering.ast_to_isir import convert_ast_to_isir_module  # noqa: E402
from isir.parser.parser import parse_isir  # noqa: E402


def _spec(ex):
    return convert_ast_to_isir_module(
        parse_isir(Path(f"examples/{ex}/{ex}.isir")).module
    )


class TestGenSpec:
    def test_markdown_has_no_sexpressions(self):
        md = gen_markdown(_spec("alu"))
        # No raw S-expression syntax in the natural-language prose.
        assert "(read " not in md
        assert "(write " not in md
        assert "(eq " not in md
        # Natural-language markers present.
        assert "equals" in md
        assert "set " in md

    def test_markdown_has_no_isir_yaml(self):
        md = gen_markdown(_spec("alu"))
        assert "spec.module" not in md
        assert "state_ops" not in md
        assert "rule_ops" not in md

    def test_roundtrip_lossless(self):
        for ex in ("alu", "counter", "fifo", "mul", "saturating_adder"):
            assert verify_roundtrip(_spec(ex), cycles=10, seed=0), ex

    def test_facts_sidecar_reconstructs_equivalent(self):
        from isir.verification.reference_semantics import reference_trace
        spec = _spec("gcd")
        recon = _reconstruct(_facts(spec))
        assert reference_trace(spec, 8, 0) == reference_trace(recon, 8, 0)

    def test_markdown_has_no_overview(self):
        md = gen_markdown(_spec("alu"))
        assert "## Overview" not in md

    def test_llm_roundtrip_does_not_overwrite_original(self, monkeypatch):
        import gen_spec
        from isir.verification.reference_semantics import reference_trace

        spec = _spec("alu")
        md = gen_markdown(spec)
        # The regenerated .isir must go to a temp file, never the original.
        import tempfile
        captured = {}

        class FakeLLM:
            def generate(self, prompt):
                # Return a minimal ISIR (valid YAML) for the round-trip parse.
                return (
                    "spec.module @alu {\n"
                    "  inputs:\n"
                    "    - {name: op, type: \"bits<3>\"}\n"
                    "    - {name: a, type: \"bits<8>\"}\n"
                    "    - {name: b, type: \"bits<8>\"}\n"
                    "  state:\n"
                    "    - {name: result_reg, type: \"bits<8>\", initial: 0}\n"
                    "}\n"
                )

        def fake_load_config():
            return {"llm": {"provider": "deepseek", "model": "deepseek-chat"}}

        def fake_get_client(config):
            return FakeLLM()

        monkeypatch.setattr("isir.utils.config_loader.load_config", fake_load_config)
        monkeypatch.setattr("isir.backends.llm_client.get_llm_client_from_config", fake_get_client)

        # The original .isir file must remain byte-for-byte unchanged.
        orig = Path("examples/alu/alu.isir").read_text()
        result = gen_spec.llm_roundtrip(spec, md)
        assert Path("examples/alu/alu.isir").read_text() == orig
        assert result in (True, False)  # not None => LLM path ran

    def test_every_example_has_spec_md(self):
        """Every examples/*/*.isir must have a sibling natural-language .md."""
        missing = [
            str(p) for p in sorted(Path("examples").glob("*/*.isir"))
            if not p.with_suffix(".md").exists()
        ]
        assert not missing, f"examples missing a natural-language spec: {missing}"

    def test_new_operator_mul_full_is_naturalized(self):
        from gen_spec import _nl
        out = _nl(["mul_full", "a", "b"])
        assert "non-wrapping" in out
        assert "(mul_full" not in out
