# src/specir/utils/reporting.py
#
# Aggregation and export of compilation, verification, and simulation
# results produced by InterScope.

import csv
import json
import statistics
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from specir.utils.result_types import (
    CompilationReport,
    VerificationReport,
    SimulationReport,
    BackendResult,
    ProofObligationResult,
    Status,
)


def aggregate_compilation_reports(
    reports: List[CompilationReport],
) -> Dict[str, Any]:
    """Return summary statistics for a set of compilation reports."""
    if not reports:
        return {"total_designs": 0, "overall_success_rate": 0.0, "by_backend": {}}

    total_designs = len(reports)
    overall_success_count = sum(1 for r in reports if r.overall_success())

    # Per‑backend statistics
    backend_map: Dict[str, List[BackendResult]] = {}
    for report in reports:
        for res in report.results:
            backend_map.setdefault(res.backend, []).append(res)

    by_backend = {}
    for backend, results in backend_map.items():
        success_count = sum(1 for r in results if r.success)
        durations = [r.duration for r in results if r.duration is not None]
        by_backend[backend] = {
            "success_count": success_count,
            "total": len(results),
            "success_rate": success_count / len(results) if results else 0.0,
            "avg_duration_s": statistics.mean(durations) if durations else None,
        }

    return {
        "total_designs": total_designs,
        "overall_success_count": overall_success_count,
        "overall_success_rate": overall_success_count / total_designs,
        "by_backend": by_backend,
    }


def aggregate_verification_reports(
    reports: List[VerificationReport],
) -> Dict[str, Any]:
    """Return summary statistics for a set of verification reports."""
    if not reports:
        return {"total_designs": 0, "overall_pass_rate": 0.0, "by_backend": {}}

    total_designs = len(reports)
    # Group obligations by backend
    backend_map: Dict[str, List[ProofObligationResult]] = {}
    for report in reports:
        backend = report.backend
        backend_map.setdefault(backend, []).extend(report.obligations)

    by_backend = {}
    for backend, obligations in backend_map.items():
        pass_count = sum(1 for o in obligations if o.status == Status.PASS)
        durations = [o.duration for o in obligations if o.duration is not None]
        iterations = [o.iterations for o in obligations if o.iterations is not None]
        by_backend[backend] = {
            "total_obligations": len(obligations),
            "pass_count": pass_count,
            "pass_rate": pass_count / len(obligations) if obligations else 0.0,
            "avg_duration_s": statistics.mean(durations) if durations else None,
            "avg_iterations": statistics.mean(iterations) if iterations else None,
        }

    overall_pass = sum(
        1 for r in reports if r.overall_status == Status.PASS
    )

    return {
        "total_designs": total_designs,
        "overall_pass_count": overall_pass,
        "overall_pass_rate": overall_pass / total_designs if total_designs else 0.0,
        "by_backend": by_backend,
    }


def aggregate_simulation_reports(
    reports: List[SimulationReport],
) -> Dict[str, Any]:
    """Return summary statistics for a set of simulation reports."""
    if not reports:
        return {"total": 0, "pass_rate": 0.0}

    pass_count = sum(1 for r in reports if r.success)
    durations = [r.duration for r in reports if r.duration is not None]
    coverages = [r.coverage for r in reports if r.coverage is not None]

    return {
        "total": len(reports),
        "pass_count": pass_count,
        "pass_rate": pass_count / len(reports),
        "avg_duration_s": statistics.mean(durations) if durations else None,
        "avg_coverage_pct": statistics.mean(coverages) if coverages else None,
    }


def write_json_report(data: Any, filepath: Union[str, Path]) -> None:
    """Write *data* to *filepath* as indented JSON."""
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)


def _flatten_compilation(reports: List[CompilationReport]) -> List[Dict[str, Any]]:
    """Flatten compilation reports into a list of rows (one per backend per design)."""
    rows = []
    for report in reports:
        for res in report.results:
            rows.append({
                "design": report.design_name,
                "backend": res.backend,
                "success": res.success,
                "error_message": res.error_message or "",
                "duration_s": res.duration if res.duration is not None else "",
                "output_file": res.output_file or "",
            })
    return rows


def write_compilation_csv(
    reports: List[CompilationReport],
    filepath: Union[str, Path],
) -> None:
    """Write compilation results to a CSV file."""
    rows = _flatten_compilation(reports)
    if not rows:
        return
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


def _flatten_verification(reports: List[VerificationReport]) -> List[Dict[str, Any]]:
    """Flatten verification reports into rows (one per obligation)."""
    rows = []
    for report in reports:
        for obl in report.obligations:
            rows.append({
                "design": report.design_name,
                "backend": report.backend,
                "property": obl.property,
                "status": obl.status.value,
                "iterations": obl.iterations if obl.iterations is not None else "",
                "duration_s": obl.duration if obl.duration is not None else "",
                "error_message": obl.error_message or "",
                "automation": obl.details.get("automation", ""),
                "lemmas_used": ",".join(obl.details.get("lemmas_used", [])),
            })
    return rows


def write_verification_csv(
    reports: List[VerificationReport],
    filepath: Union[str, Path],
) -> None:
    """Write verification results to a CSV file."""
    rows = _flatten_verification(reports)
    if not rows:
        return
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


def _flatten_simulation(reports: List[SimulationReport]) -> List[Dict[str, Any]]:
    """Flatten simulation reports into rows (one per design)."""
    rows = []
    for r in reports:
        rows.append({
            "design": r.design_name,
            "success": r.success,
            "cycles": r.cycles if r.cycles is not None else "",
            "coverage_pct": r.coverage if r.coverage is not None else "",
            "duration_s": r.duration if r.duration is not None else "",
            "vcd_path": r.vcd_path or "",
            "error_message": r.error_message or "",
        })
    return rows


def write_simulation_csv(
    reports: List[SimulationReport],
    filepath: Union[str, Path],
) -> None:
    """Write simulation results to a CSV file."""
    rows = _flatten_simulation(reports)
    if not rows:
        return
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
