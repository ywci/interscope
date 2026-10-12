# tests/unit/test_reporting.py
#
# Unit tests for reporting aggregation and export helpers
# (isir.utils.reporting). Covers JSON/CSV export and summary statistics.

import csv
import json
import pytest
from pathlib import Path
from isir.utils.reporting import (
    aggregate_compilation_reports,
    aggregate_verification_reports,
    aggregate_simulation_reports,
    write_json_report,
    write_compilation_csv,
    write_verification_csv,
    write_simulation_csv,
    _flatten_compilation,
    _flatten_verification,
    _flatten_simulation,
)
from isir.utils.result_types import (
    BackendResult,
    CompilationReport,
    ProofObligationResult,
    SimulationReport,
    Status,
    VerificationReport,
)


def _compilation_reports():
    return [
        CompilationReport(
            design_name="d1",
            input_file="a.isir",
            results=[
                BackendResult(backend="koika", success=True, duration=2.0),
                BackendResult(backend="acl2", success=False, duration=4.0),
            ],
        ),
        CompilationReport(
            design_name="d2",
            input_file="b.isir",
            results=[
                BackendResult(backend="koika", success=True, duration=6.0),
                BackendResult(
                    backend="verilog_ovl", success=True, duration=None
                ),
            ],
        ),
    ]


class TestAggregateCompilation:
    def test_empty(self):
        result = aggregate_compilation_reports([])
        assert result == {
            "total_designs": 0,
            "overall_success_rate": 0.0,
            "by_backend": {},
        }

    def test_aggregate(self):
        result = aggregate_compilation_reports(_compilation_reports())

        assert result["total_designs"] == 2
        assert result["overall_success_count"] == 1
        assert result["overall_success_rate"] == 0.5

        koika = result["by_backend"]["koika"]
        assert koika == {
            "success_count": 2,
            "total": 2,
            "success_rate": 1.0,
            "avg_duration_s": 4.0,
        }

        acl2 = result["by_backend"]["acl2"]
        assert acl2["success_count"] == 0
        assert acl2["total"] == 1
        assert acl2["success_rate"] == 0.0
        assert acl2["avg_duration_s"] == 4.0

        ovl = result["by_backend"]["verilog_ovl"]
        assert ovl["success_count"] == 1
        assert ovl["avg_duration_s"] is None


class TestAggregateVerification:
    def test_empty(self):
        result = aggregate_verification_reports([])
        assert result == {
            "total_designs": 0,
            "overall_pass_rate": 0.0,
            "by_backend": {},
        }

    def test_aggregate(self):
        reports = [
            VerificationReport(
                design_name="d1",
                backend="koika",
                obligations=[
                    ProofObligationResult(
                        property="p1", status=Status.PASS, backend="koika",
                        iterations=10, duration=1.0,
                    ),
                    ProofObligationResult(
                        property="p2", status=Status.FAIL, backend="koika",
                        iterations=20, duration=2.0,
                    ),
                ],
            ),
            VerificationReport(
                design_name="d2",
                backend="acl2",
                obligations=[
                    ProofObligationResult(
                        property="p3", status=Status.PASS, backend="acl2",
                        iterations=None, duration=None,
                    ),
                ],
            ),
        ]

        result = aggregate_verification_reports(reports)

        assert result["total_designs"] == 2
        assert result["overall_pass_count"] == 1
        assert result["overall_pass_rate"] == 0.5

        koika = result["by_backend"]["koika"]
        assert koika["total_obligations"] == 2
        assert koika["pass_count"] == 1
        assert koika["pass_rate"] == 0.5
        assert koika["avg_duration_s"] == 1.5
        assert koika["avg_iterations"] == 15.0

        acl2 = result["by_backend"]["acl2"]
        assert acl2["total_obligations"] == 1
        assert acl2["pass_count"] == 1
        assert acl2["pass_rate"] == 1.0
        assert acl2["avg_duration_s"] is None
        assert acl2["avg_iterations"] is None


class TestAggregateSimulation:
    def test_empty(self):
        result = aggregate_simulation_reports([])
        assert result == {"total": 0, "pass_rate": 0.0}

    def test_aggregate(self):
        reports = [
            SimulationReport(
                design_name="d1", success=True, cycles=100,
                coverage=85.0, duration=1.5,
            ),
            SimulationReport(
                design_name="d2", success=False, cycles=None,
                coverage=None, duration=2.5,
            ),
        ]

        result = aggregate_simulation_reports(reports)

        assert result["total"] == 2
        assert result["pass_count"] == 1
        assert result["pass_rate"] == 0.5
        assert result["avg_duration_s"] == 2.0
        assert result["avg_coverage_pct"] == 85.0


class TestWriteJson:
    def test_writes_indented_json(self, tmp_path):
        out = tmp_path / "report.json"
        data = {"a": 1, "nested": {"b": [1, 2, 3]}, "path": Path("/tmp/x")}

        write_json_report(data, out)

        assert out.exists()
        text = out.read_text()
        assert "\n  " in text
        parsed = json.loads(text)
        assert parsed["a"] == 1
        assert parsed["nested"]["b"] == [1, 2, 3]
        assert parsed["path"] == "/tmp/x"

    def test_creates_parent_directories(self, tmp_path):
        out = tmp_path / "deep" / "nested" / "report.json"
        write_json_report({"x": [1]}, out)
        assert out.exists()


class TestCompilationCsv:
    def test_write_and_read(self, tmp_path):
        out = tmp_path / "compilation.csv"
        write_compilation_csv(_compilation_reports(), out)

        assert out.exists()
        with open(out, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

        assert len(rows) == 4
        assert rows[0] == {
            "design": "d1",
            "backend": "koika",
            "success": "True",
            "error_message": "",
            "duration_s": "2.0",
            "output_file": "",
        }
        acl2_row = [r for r in rows if r["backend"] == "acl2"][0]
        assert acl2_row["success"] == "False"

    def test_empty_reports_writes_nothing(self, tmp_path):
        out = tmp_path / "compilation.csv"
        write_compilation_csv([], out)
        assert not out.exists()

    def test_flatten_none_fields(self):
        report = CompilationReport(
            design_name="d",
            input_file="x.isir",
            results=[BackendResult(backend="koika", success=True)],
        )
        rows = _flatten_compilation([report])
        assert rows[0]["error_message"] == ""
        assert rows[0]["duration_s"] == ""
        assert rows[0]["output_file"] == ""


class TestVerificationCsv:
    def test_write_and_read(self, tmp_path):
        report = VerificationReport(
            design_name="d1",
            backend="koika",
            obligations=[
                ProofObligationResult(
                    property="p1", status=Status.PASS, backend="koika",
                    iterations=5, duration=0.5,
                    details={"automation": "skeleton", "lemmas_used": ["l1", "l2"]},
                ),
                ProofObligationResult(
                    property="p2", status=Status.TIMEOUT, backend="koika",
                    error_message="timed out",
                ),
            ],
        )
        out = tmp_path / "verification.csv"
        write_verification_csv([report], out)

        with open(out, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

        assert len(rows) == 2
        assert rows[0]["design"] == "d1"
        assert rows[0]["backend"] == "koika"
        assert rows[0]["property"] == "p1"
        assert rows[0]["status"] == "PASS"
        assert rows[0]["iterations"] == "5"
        assert rows[0]["automation"] == "skeleton"
        assert rows[0]["lemmas_used"] == "l1,l2"
        # Second obligation: status value, empty iterations/duration.
        assert rows[1]["status"] == "TIMEOUT"
        assert rows[1]["iterations"] == ""
        assert rows[1]["error_message"] == "timed out"

    def test_empty_obligations_writes_nothing(self, tmp_path):
        out = tmp_path / "verification.csv"
        write_verification_csv([VerificationReport("d", "koika")], out)
        assert not out.exists()

    def test_flatten_missing_details_defaults(self):
        report = VerificationReport(
            design_name="d",
            backend="koika",
            obligations=[
                ProofObligationResult(
                    property="p", status=Status.PASS, backend="koika"
                )
            ],
        )
        rows = _flatten_verification([report])
        assert rows[0]["automation"] == ""
        assert rows[0]["lemmas_used"] == ""


class TestSimulationCsv:
    def test_write_and_read(self, tmp_path):
        reports = [
            SimulationReport(
                design_name="d1", success=True, cycles=42,
                coverage=99.5, vcd_path="/tmp/t.vcd", duration=1.1,
            ),
            SimulationReport(
                design_name="d2", success=False,
                error_message="mismatch",
            ),
        ]
        out = tmp_path / "simulation.csv"
        write_simulation_csv(reports, out)

        with open(out, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

        assert len(rows) == 2
        assert rows[0]["design"] == "d1"
        assert rows[0]["success"] == "True"
        assert rows[0]["cycles"] == "42"
        assert rows[0]["coverage_pct"] == "99.5"
        assert rows[0]["vcd_path"] == "/tmp/t.vcd"
        # Failure row has blank optional fields.
        assert rows[1]["design"] == "d2"
        assert rows[1]["success"] == "False"
        assert rows[1]["cycles"] == ""
        assert rows[1]["error_message"] == "mismatch"

    def test_empty_reports_writes_nothing(self, tmp_path):
        out = tmp_path / "simulation.csv"
        write_simulation_csv([], out)
        assert not out.exists()

    def test_flatten_none_fields(self):
        report = SimulationReport(design_name="d", success=True)
        rows = _flatten_simulation([report])
        assert rows[0]["cycles"] == ""
        assert rows[0]["coverage_pct"] == ""
        assert rows[0]["vcd_path"] == ""
        assert rows[0]["error_message"] == ""
