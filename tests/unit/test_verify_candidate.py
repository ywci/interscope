# tests/unit/test_verify_candidate.py
#
# RTL Conformance (Mode B): simulate an externally-provided Candidate RTL and
# check it against the spec's properties.

import pytest
import shutil
import tempfile
from pathlib import Path
from isir.lowering.ast_to_isir import convert_ast_to_isir_module
from isir.lowering.isir_to_rtl_direct import emit
from isir.lowering.verify_candidate import verify_candidate_rtl
from isir.parser.parser import parse_isir


pytestmark = pytest.mark.skipif(shutil.which("iverilog") is None or shutil.which("vvp") is None,
                                reason="iverilog/vvp not installed")


def _counter_spec():
    return convert_ast_to_isir_module(parse_isir(Path("examples/counter/counter.isir")).module)


class TestVerifyCandidateRtl:
    def test_direct_rtl_conforms(self, tmp_path):
        spec = _counter_spec()
        rtl, _ = emit(spec, tmp_path, policy="sim")
        r = verify_candidate_rtl(spec, str(rtl), cycles=6, seed=0)
        assert r.status == "conforms", (r.status, r.message, r.to_dict())

    def test_broken_rtl_diverges(self, tmp_path):
        spec = _counter_spec()
        broken = tmp_path / "counter.v"
        broken.write_text(
            "module counter(clk, rst, inc, count, overflow_flag);\n"
            "  input clk, rst, inc;\n"
            "  output reg [3:0] count;\n"
            "  output reg overflow_flag;\n"
            "  always @(posedge clk) begin count <= 4'd0; overflow_flag <= 1'b1; end\n"
            "endmodule\n")
        r = verify_candidate_rtl(spec, str(broken), cycles=6, seed=0)
        assert r.status == "diverges", (r.status, r.message)
        assert any(rec.primary_spec_item_id == "no_overflow_when_not_full" for rec in r.records)

    def test_missing_rtl_is_error(self, tmp_path):
        spec = _counter_spec()
        r = verify_candidate_rtl(spec, str(tmp_path / "nope.v"), cycles=6, seed=0)
        assert r.status == "error"
