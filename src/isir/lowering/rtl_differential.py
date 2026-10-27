# src/isir/lowering/rtl_differential.py
#
# D5 — lockstep differential harness (short-path direct RTL vs long-path Kōika RTL).
#
# This harness drives both emitted RTL models with identical stimulus and compares
# the *observable projection* (the non-memory state registers) every cycle.  It is
# a divergence *detector*, not a correctness decider: a mismatch is recorded and
# classified, and attribution is left to the refinement evidence / replay tool.

from __future__ import annotations

import random
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from isir.dialects.isir import SpecModule
from isir.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class DiffResult:
    design: str
    status: str = "error"                       # agreed_long_short | divergent_long_short | error
    first_divergent_cycle: Optional[int] = None
    divergence_kind: str = ""                   # state_mismatch (currently the only compared projection)
    observable: Optional[str] = None            # spec_item_id (state name)
    short_value: Optional[str] = None
    long_value: Optional[str] = None
    message: str = ""


def _capitalize(name: str) -> str:
    return name[0].upper() + name[1:] if name else name


# Operators the LONG path (koika_to_rtl._has_unsupported_ops) silently drops.
_LONG_PATH_UNSUPPORTED = ("mem_read", "mem_write", "slice", "mul", "div", "mod")


def _long_path_skips(spec: SpecModule) -> List[str]:
    """Return the operators present in any rule/condition that the long path drops."""
    from isir.utils.expr import parse_sexpr, unfold_user_functions

    functions = getattr(spec, "functions", None) or []
    found: set = set()

    def walk(e):
        if isinstance(e, list):
            if e and e[0] in _LONG_PATH_UNSUPPORTED:
                found.add(e[0])
            for a in e[1:]:
                walk(a)

    for r in spec.rule_ops:
        for s in [r.condition or "true"] + list(r.actions):
            try:
                # Unfold user functions so an unsupported op in a function body
                # (e.g. slice inside `vpn`) also marks the design as skipped.
                walk(parse_sexpr(unfold_user_functions(s, functions)))
            except Exception:
                pass
    return sorted(found)


def _width_of(data_type: str) -> int:
    from isir.lowering.isir_to_rtl_direct import _width_of as _w
    return _w(data_type)


def _esc(name: str) -> str:
    """Verilog-escaped port name for a reserved keyword."""
    from isir.lowering.isir_to_rtl_direct import _VERILOG_KEYWORDS
    return f"\\{name} " if name in _VERILOG_KEYWORDS else name


def _drv(name: str) -> str:
    """Safe non-keyword driver name for the testbench register."""
    from isir.lowering.isir_to_rtl_direct import _VERILOG_KEYWORDS
    return f"sig_{name}" if name in _VERILOG_KEYWORDS else name


def _compare_states(spec: SpecModule) -> List[Tuple[str, str]]:
    """Return [(short_state, long_state)] for the observable projection.

    The short path uses the declared (lowercase) state names; the long path
    (Kōika product) exposes the same registers capitalized and `/* public */`.
    Memories are excluded (not currently sampled by the harness).
    """
    pairs = []
    for s in spec.state_ops:
        if s.kind == "memory":
            continue
        pairs.append((s.state_name, _capitalize(s.state_name)))
    return pairs


def _generate_testbench(spec: SpecModule, short_module: str, long_module: str,
                        cycles: int, seed: int, latency: int = 1) -> str:
    """Emit a lockstep testbench: identical stimulus, per-cycle state compare.

    Reset correspondence: the short path uses the ISIR reset name/polarity; the
    long path (Kōika product) always exposes ``rst_n`` (active-low, normalized
    from ``RST_N``).  The harness drives both from one ``reset_active`` signal.

    Latency: ``koika_to_rtl._internalize_inputs`` latches each input in a
    register, so the long path's states are ``latency`` cycles behind the short
    path.  We compare ``short.state[N - latency]`` against ``long.State[N]`` by
    sampling the short path into ``prev_*`` registers one cycle early.
    """
    rng = random.Random(seed)
    clk = spec.clocks[0]["name"] if spec.clocks else "clk"
    rst = spec.resets[0] if spec.resets else None
    short_rst = rst["name"] if rst else "rst"
    short_active_high = (rst or {}).get("polarity", "active_high") == "active_high"
    long_rst = "rst_n"  # Kōika always normalizes RST_N → rst_n (active-low)

    inputs = spec.inputs
    states = _compare_states(spec)
    state_widths = {s.state_name: _width_of(s.data_type) for s in spec.state_ops if s.kind != "memory"}

    short_ports = ", ".join(f".{_esc(i.name)}({_drv(i.name)})" for i in inputs)
    long_ports = ", ".join(f".Inp_{i.name}({_drv(i.name)})" for i in inputs)

    lines = []
    lines.append("module tb;")
    lines.append(f"  reg {clk} = 0;")
    lines.append("  reg reset_active = 1;")
    lines.append(f"  wire short_rst = {'reset_active' if short_active_high else '~reset_active'};")
    lines.append("  wire long_rst = ~reset_active;")
    for i in inputs:
        w = _width_of(i.data_type)
        lines.append(f"  reg [{w - 1}:0] {_drv(i.name)} = 0;" if w > 1 else f"  reg {_drv(i.name)} = 0;")
    # `prev_*` registers hold the short path's state `latency` cycles earlier.
    for short, _ in states:
        w = state_widths.get(short, 1)
        lines.append(f"  reg [{w - 1}:0] prev_{short} = 0;" if w > 1 else f"  reg prev_{short} = 0;")

    lines.append(f"  {short_module} short_path(.{clk}({clk}), .{short_rst}(short_rst), {short_ports});")
    lines.append(f"  {long_module} long_path(.{clk}({clk}), .{long_rst}(long_rst), {long_ports});")
    lines.append(f"  always #5 {clk} = ~{clk};")

    lines.append("  integer cyc;")
    lines.append("  initial begin")
    lines.append("    reset_active = 1;")
    lines.append("    repeat (2) @(posedge clk);")
    lines.append("    reset_active = 0;")
    lines.append("    @(negedge clk);")  # settle at negedge (NBA settled, no posedge race)
    lines.append("    for (cyc = 0; cyc < CYCLES; cyc = cyc + 1) begin")
    for i in inputs:
        w = _width_of(i.data_type)
        val = rng.getrandbits(w)
        lines.append(f"      {_drv(i.name)} = {w}'d{val};")
    lines.append("      @(posedge clk);")
    lines.append("      @(negedge clk);")  # let non-blocking updates settle
    for short, long in states:
        lines.append(f"      if (short_path.{short} !== long_path.{long}) begin")
        lines.append(f"        $display(\"DIVERGE|%0d|{short}|%0d|%0d\", cyc, short_path.{short}, long_path.{long});")
        lines.append("        $fatal(1, \"DIVERGENCE\");")
        lines.append("      end")
    lines.append("    end")
    lines.append('    $display("AGREED");')
    lines.append("    $finish;")
    lines.append("  end")
    lines.append("endmodule")
    return "\n".join(lines)


def _run_sim(workdir: Path, tb_path: Path, verilog_files: List[Path]) -> Tuple[str, str]:
    """Compile + run the testbench; return (stdout, stderr)."""
    out = workdir / "tb_sim"
    cmd = ["iverilog", "-g2012", "-DCYCLES=20", "-o", str(out), str(tb_path)] + [str(f) for f in verilog_files]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120, cwd=str(workdir))
    if r.returncode != 0:
        return "", f"iverilog failed: {r.stderr[:400]}"
    r2 = subprocess.run(["vvp", str(out)], capture_output=True, text=True, timeout=120, cwd=str(workdir))
    return r2.stdout, r2.stderr


def diff_design(spec: SpecModule, short_dir: Path, long_dir: Path,
                cycles: int = 20, seed: int = 0) -> DiffResult:
    """Generate both RTL models, run lockstep, and classify the first divergence."""
    from isir.lowering.isir_to_rtl_direct import emit as direct_emit
    from isir.lowering.koika_to_rtl import convert as koika_rtl_convert

    design = spec.name
    short_dir = Path(short_dir).resolve()
    long_dir = Path(long_dir).resolve()
    short_dir.mkdir(parents=True, exist_ok=True)
    long_dir.mkdir(parents=True, exist_ok=True)

    skipped = _long_path_skips(spec)
    if skipped:
        return DiffResult(design=design, status="long_path_unsupported",
                          message=f"long path drops: {', '.join(skipped)}")

    # Short path (direct).
    try:
        short_rtl, _ = direct_emit(spec, short_dir, policy="sim")
    except Exception as e:
        return DiffResult(design=design, status="error", message=f"short-path emit failed: {e}")

    # Long path (Kōika → RTL).
    try:
        koika_rtl_convert(spec, long_dir)
    except Exception as e:
        return DiffResult(design=design, status="error", message=f"long-path emit failed: {e}")

    long_rtl = long_dir / f"{design}.v"
    if not long_rtl.exists():
        # cuttlec may nest the output.
        for cand in sorted(long_dir.rglob("*.v")):
            long_rtl = cand
            break
    if not long_rtl.exists():
        return DiffResult(design=design, status="error", message="long-path RTL not found")

    # Rename the long module to avoid a name clash with the short module.
    workdir = Path(tempfile.mkdtemp(prefix="diff_", dir=long_dir))
    long_renamed = workdir / f"{design}_long.v"
    text = long_rtl.read_text()
    text = text.replace(f"module {design}(", f"module {design}_long(", 1)
    long_renamed.write_text(text)

    tb = _generate_testbench(spec, design, f"{design}_long", cycles, seed)
    tb_path = workdir / "tb.v"
    tb_path.write_text(tb)
    # CYCLES is a define used by the testbench; pass it directly instead.
    tb_path.write_text(tb.replace("CYCLES", str(cycles)))

    stdout, stderr = _run_sim(workdir, tb_path, [short_rtl, long_renamed])
    if "AGREED" in stdout:
        return DiffResult(design=design, status="agreed_long_short")
    for line in stdout.splitlines():
        if line.startswith("DIVERGE|"):
            # DIVERGE|<cyc>|<state>|<short>|<long>
            parts = line.split("|")
            return DiffResult(design=design, status="divergent_long_short",
                              first_divergent_cycle=int(parts[1]), divergence_kind="state_mismatch",
                              observable=parts[2], short_value=parts[3], long_value=parts[4])
    return DiffResult(design=design, status="error", message=stderr[:400] or "no result")
