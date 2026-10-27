# src/isir/lowering/verify_direct.py
#
# Verify the direct-path RTL against the reference interpreter (reference_semantics).
# Agreement on a design means the direct emitter matches the ISIR semantics
# (as evaluated by the shared `eval_expr`), independent of the Kōika RTL backend.

from __future__ import annotations

import random
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from isir.dialects.isir import SpecModule
from isir.lowering.isir_to_rtl_direct import _width_of, emit, _VERILOG_KEYWORDS
from isir.verification.reference_semantics import reference_trace, initial_state
from isir.utils.logger import get_logger

logger = get_logger(__name__)


def _esc(name: str) -> str:
    """Verilog-escaped port/identifier name for a reserved keyword."""
    return f"\\{name} " if name in _VERILOG_KEYWORDS else name


def _drv(name: str) -> str:
    """Safe non-keyword driver name for the testbench register."""
    return f"sig_{name}" if name in _VERILOG_KEYWORDS else name


@dataclass
class DirectVerifyResult:
    design: str
    status: str = "error"          # agreed | divergent | error
    first_divergent_cycle: Optional[int] = None
    observable: Optional[str] = None
    reference_value: Optional[str] = None
    rtl_value: Optional[str] = None
    message: str = ""


def _tb(spec: SpecModule, inputs_seq: List[Dict[str, Any]], cycles: int) -> str:
    clk = spec.clocks[0]["name"] if spec.clocks else "clk"
    rst = spec.resets[0] if spec.resets else None
    rst_name = rst["name"] if rst else "rst"
    active_high = (rst or {}).get("polarity", "active_high") == "active_high"
    states = [s.state_name for s in spec.state_ops if s.kind != "memory"]

    lines = ["module tb;", f"  reg {clk} = 0;", f"  reg {rst_name} = 0;"]
    for i in spec.inputs:
        w = _width_of(i.data_type)
        lines.append(f"  reg [{w - 1}:0] {_drv(i.name)} = 0;" if w > 1 else f"  reg {_drv(i.name)} = 0;")
    ports = ", ".join(f".{_esc(i.name)}({_drv(i.name)})" for i in spec.inputs)
    lines.append(f"  {spec.name} dut(.{clk}({clk}), .{rst_name}({rst_name}), {ports});")
    lines.append(f"  always #5 {clk} = ~{clk};")
    lines.append("  integer cyc;")
    lines.append("  initial begin")
    lines.append(f"    {rst_name} = {'1' if active_high else '0'};")
    lines.append("    repeat (2) @(posedge clk);")
    lines.append(f"    {rst_name} = {'0' if active_high else '1'};")
    lines.append("    @(negedge clk);")
    lines.append(f"    for (cyc = 0; cyc < {cycles}; cyc = cyc + 1) begin")
    lines.append("      case (cyc)")
    for cyc, inp in enumerate(inputs_seq):
        lines.append(f"        {cyc}: begin")
        for i in spec.inputs:
            w = _width_of(i.data_type)
            val = inp[i.name] & ((1 << w) - 1)
            lines.append(f"          {_drv(i.name)} = {w}'d{val};")
        lines.append("        end")
    lines.append("      endcase")
    lines.append("      @(posedge clk);")
    lines.append("      @(negedge clk);")
    fmt = "|".join(["%0d" for _ in states])
    sigs = ", ".join([f"dut.{s}" for s in states])
    lines.append(f'      $display("STATE|%0d|{fmt}", cyc, {sigs});')
    lines.append("    end")
    lines.append("    $finish;")
    lines.append("  end")
    lines.append("endmodule")
    return "\n".join(lines)


def verify_direct(spec: SpecModule, out_dir: Path, cycles: int = 10, seed: int = 0) -> DirectVerifyResult:
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    design = spec.name

    # 1. Reference trace (Python).
    rng = random.Random(seed)
    inputs_seq = [{i.name: rng.getrandbits(_width_of(i.data_type)) for i in spec.inputs}
                  for _ in range(cycles)]
    ref_trace = reference_trace(spec, cycles, inputs_seq=list(inputs_seq))
    states = [s.state_name for s in spec.state_ops if s.kind != "memory"]

    # 2. Direct RTL.
    try:
        rtl, _ = emit(spec, out_dir, policy="sim")
    except Exception as e:
        return DirectVerifyResult(design=design, status="error", message=f"emit failed: {e}")

    # 3. Testbench + run.
    workdir = Path(tempfile.mkdtemp(prefix="vd_", dir=out_dir))
    tb = _tb(spec, inputs_seq, cycles)
    tb_path = workdir / "tb.v"
    tb_path.write_text(tb)
    out = workdir / "sim"
    r = subprocess.run(["iverilog", "-g2012", "-o", str(out), str(tb_path), str(rtl)],
                       capture_output=True, text=True, timeout=120, cwd=str(workdir))
    if r.returncode != 0:
        return DirectVerifyResult(design=design, status="error", message=f"iverilog: {r.stderr[:200]}")
    r2 = subprocess.run(["vvp", str(out)], capture_output=True, text=True, timeout=120, cwd=str(workdir))

    # 4. Parse + compare.
    rtl_trace: Dict[int, Dict[str, str]] = {}
    for line in r2.stdout.splitlines():
        if line.startswith("STATE|"):
            parts = line.split("|")
            cyc = int(parts[1])
            rtl_trace[cyc] = {s: parts[2 + i] for i, s in enumerate(states)}
    for cyc in range(cycles):
        if cyc not in rtl_trace:
            return DirectVerifyResult(design=design, status="error", message=f"no STATE for cyc {cyc}: {r2.stderr[:150]}")
        for s in states:
            ref_v = int(ref_trace[cyc].get(s, 0))
            try:
                rtl_v = int(rtl_trace[cyc][s])
            except ValueError:
                rtl_v = 0  # 'x'/'z' (uninitialized memory) matches the reference's default 0
            if ref_v != rtl_v:
                return DirectVerifyResult(design=design, status="divergent",
                                          first_divergent_cycle=cyc, observable=s,
                                          reference_value=str(ref_v), rtl_value=str(rtl_v))
    return DirectVerifyResult(design=design, status="agreed")
