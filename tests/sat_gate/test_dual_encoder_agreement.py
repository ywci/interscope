# tests/sat_gate/test_dual_encoder_agreement.py

import shutil
import pytest
from isir.parser.parser import parse_isir
from isir.lowering.ast_to_isir import convert_ast_to_isir_module
from isir.lowering.isir_to_rtl_direct import emit as direct_emit
from isir.verification.sat_gate.isir_bridge import widths_of
from isir.verification.sat_gate.rtlil import (
    parse_rtlil, run_yosys_pass, signal_map,
)


pytestmark = pytest.mark.skipif(
    shutil.which("yosys") is None, reason="yosys not installed"
)


def test_static_signals_agree_with_dynamic():
    spec = convert_ast_to_isir_module(
        parse_isir("examples/counter/counter.isir").module
)
    widths = widths_of(spec)
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as td:
        rtl_path, _ = direct_emit(spec, Path(td), policy="sim")
        rtlil = run_yosys_pass(rtl_path, spec.name, Path(td))
        static = signal_map(rtlil)

    # the state register widths agree across the two encoders (count_out -> count).
    assert static.get("count_out") == widths.get("count"), (static, widths)


def test_parse_rtlil_extracts_wires_and_cells():
    spec = convert_ast_to_isir_module(
        parse_isir("examples/counter/counter.isir").module
)
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as td:
        rtl_path, _ = direct_emit(spec, Path(td), policy="sim")
        rtlil = run_yosys_pass(rtl_path, spec.name, Path(td))
        parsed = parse_rtlil(rtlil)
    assert parsed["wires"]
    assert parsed["cells"]  # the $add/$and/$eq cells
