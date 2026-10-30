# src/isir/lowering/verify_candidate.py
#
# RTL Conformance (Section 3, Mode B) end-to-end: simulate an externally
# provided Candidate RTL (`.v`) against the Confirmed specification's interface
# and check its safety/invariant properties, yielding RawEvidenceRecords.

from __future__ import annotations

import random
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List

from isir.dialects.isir import SpecModule
from isir.lowering.spec_consistency import check_rtl_conformance
from isir.lowering.verify_direct import _tb, _width_of


@dataclass
class CandidateConformanceResult:
    design: str
    status: str = "error"          # conforms | diverges | error
    records: List[Any] = field(default_factory=list)
    message: str = ""

    def to_dict(self) -> dict:
        return {
            "design": self.design,
            "status": self.status,
            "divergent_properties": [r.primary_spec_item_id for r in self.records],
            "message": self.message,
        }


def verify_candidate_rtl(spec: SpecModule, rtl_path: str,
                         cycles: int = 10, seed: int = 0) -> CandidateConformanceResult:
    """Simulate `rtl_path` (module name == spec.name, ports == spec's inputs +
    clock/reset) and check the spec's safety/invariant properties on the trace.

    Returns a `diverges` result with one RawEvidenceRecord per failing property
    (attributed to `rtl_implementation_error` by `annotation.record_to_finding`).
    """
    rtl_path = Path(rtl_path).resolve()
    if not rtl_path.exists():
        return CandidateConformanceResult(spec.name, "error", [], f"candidate RTL not found: {rtl_path}")

    rng = random.Random(seed)
    inputs_seq = [{i.name: rng.getrandbits(_width_of(i.data_type)) for i in spec.inputs}
                  for _ in range(cycles)]
    states = [s.state_name for s in spec.state_ops if s.kind != "memory"]

    workdir = Path(tempfile.mkdtemp(prefix="cand_"))
    tb_path = workdir / "tb.v"
    tb_path.write_text(_tb(spec, inputs_seq, cycles))
    out = workdir / "sim"
    r = subprocess.run(["iverilog", "-g2012", "-o", str(out), str(tb_path), str(rtl_path)],
                       capture_output=True, text=True, timeout=120, cwd=str(workdir))
    if r.returncode != 0:
        return CandidateConformanceResult(spec.name, "error", [], f"iverilog: {r.stderr[:200]}")
    r2 = subprocess.run(["vvp", str(out)], capture_output=True, text=True, timeout=120, cwd=str(workdir))

    rtl_trace: dict = {}
    for line in r2.stdout.splitlines():
        if line.startswith("STATE|"):
            parts = line.split("|")
            cyc = int(parts[1])
            rtl_trace[cyc] = {s: parts[2 + i] for i, s in enumerate(states)}

    trace: List[dict] = []
    for cyc in range(cycles):
        if cyc not in rtl_trace:
            return CandidateConformanceResult(spec.name, "error", [], f"no STATE for cyc {cyc}: {r2.stderr[:150]}")
        state: dict = {}
        for s in states:
            v = rtl_trace[cyc][s]
            try:
                state[s] = int(v)
            except ValueError:
                state[s] = 0  # 'x'/'z' -> default 0
        trace.append({"state": state, "inputs": inputs_seq[cyc], "memories": {}})

    records = check_rtl_conformance(spec, trace)
    status = "diverges" if records else "conforms"
    return CandidateConformanceResult(spec.name, status, records)
