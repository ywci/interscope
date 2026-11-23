# src/isir/verification/sat_gate/solver_oneshot.py
#
# One-shot solver: solve a compiled CNF via an external one-shot solver over
# DIMACS. No incrementality, no learned-clause reuse.

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional
from isir.verification.sat_gate.bitblast import CNF


@dataclass
class SolverResult:
    status: str                       # "sat" | "unsat" | "unknown"
    model: Optional[Dict[int, bool]]  # var -> bool, for SAT


def _write_dimacs(cnf: CNF, path: Path) -> int:
    nvars = 0
    for c in cnf.clauses:
        for lit in c:
            nvars = max(nvars, abs(lit))
    lines = [f"p cnf {nvars} {len(cnf.clauses)}"]
    for c in cnf.clauses:
        lines.append(" ".join(str(l) for l in c) + " 0")
    path.write_text("\n".join(lines) + "\n")
    return nvars


def solve_cnf(cnf: CNF, solver: str = "z3",
              timeout_s: Optional[float] = None) -> SolverResult:
    """Solve ``cnf`` with a one-shot external solver.

    ``solver`` is the binary name (default ``z3``; CaDiCaL/Kissat also speak
    DIMACS).  Returns SAT with the model, UNSAT, or UNKNOWN.
    """
    with tempfile.TemporaryDirectory() as td:
        cnf_path = Path(td) / "formula.cnf"
        _write_dimacs(cnf, cnf_path)
        cmd = [solver, str(cnf_path)]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=timeout_s)
        except FileNotFoundError:
            return SolverResult(status="unknown", model=None)
        except subprocess.TimeoutExpired:
            return SolverResult(status="unknown", model=None)

    out = proc.stdout + "\n" + proc.stderr
    if "s SATISFIABLE" in out:
        model: Dict[int, bool] = {}
        for line in out.splitlines():
            if line.startswith("v "):
                for tok in line[2:].split():
                    v = int(tok)
                    if v != 0:
                        model[abs(v)] = v > 0
        return SolverResult(status="sat", model=model)
    if "s UNSATISFIABLE" in out:
        return SolverResult(status="unsat", model=None)
    return SolverResult(status="unknown", model=None)


def solve_cnf_with_proof(cnf: CNF) -> "tuple[SolverResult, Optional[list]]":
    """Solve ``cnf`` with the in-process CaDiCaL and return (result, DRAT proof).

    The proof is a list of DIMACS-style DRAT lines (strings).  Only meaningful
    for UNSAT; for SAT it is None.  Uses pysat's bundled CaDiCaL with proof
    tracing so no external drat-trim is required for the T3 check.
    """
    from pysat.solvers import Cadical103

    c = Cadical103(bootstrap_with=cnf.clauses, with_proof=True)
    try:
        if c.solve():
            model = {abs(l): (l > 0) for l in c.get_model()}
            return SolverResult(status="sat", model=model), None
        proof = c.get_proof()
        return SolverResult(status="unsat", model=None), proof
    finally:
        c.delete()
