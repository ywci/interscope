# tests/unit/test_result_types.py
#
# Unit tests for the result dataclasses and Status enum.
# Covers field defaults, construction, computed properties, and to_dict().

from datetime import datetime
from isir.utils.result_types import (
    BackendResult,
    CompilationReport,
    ProofObligationResult,
    SimulationReport,
    Status,
    VerificationReport,
    merge_statuses,
)


class TestStatus:
    def test_values(self):
        assert Status.PASS.value == "PASS"
        assert Status.FAIL.value == "FAIL"
        assert Status.TIMEOUT.value == "TIMEOUT"
        assert Status.ERROR.value == "ERROR"

    def test_members_and_order(self):
        assert [s for s in Status] == [
            Status.PASS,
            Status.FAIL,
            Status.TIMEOUT,
            Status.ERROR,
        ]

    def test_lookup_by_value(self):
        assert Status("PASS") is Status.PASS
        assert Status("ERROR") is Status.ERROR


class TestBackendResult:
    def test_required_fields_and_defaults(self):
        r = BackendResult(backend="koika", success=True)
        assert r.backend == "koika"
        assert r.success is True
        assert r.error_message is None
        assert r.duration is None
        assert r.output_file is None
        assert r.metadata == {}

    def test_full_construction(self):
        r = BackendResult(
            backend="acl2",
            success=False,
            error_message="boom",
            duration=1.5,
            output_file="out.lisp",
            metadata={"lemmas": 3},
        )
        assert r.error_message == "boom"
        assert r.duration == 1.5
        assert r.output_file == "out.lisp"
        assert r.metadata == {"lemmas": 3}

    def test_to_dict(self):
        r = BackendResult(
            backend="acl2",
            success=False,
            error_message="boom",
            duration=1.5,
            output_file="out.lisp",
            metadata={"lemmas": 3},
        )
        assert r.to_dict() == {
            "backend": "acl2",
            "success": False,
            "error_message": "boom",
            "duration": 1.5,
            "output_file": "out.lisp",
            "metadata": {"lemmas": 3},
        }

    def test_metadata_isolation(self):
        a = BackendResult("koika", True)
        b = BackendResult("acl2", True)
        a.metadata["extra"] = 1
        assert b.metadata == {}
        assert a.metadata == {"extra": 1}


class TestCompilationReport:
    def test_defaults(self):
        cr = CompilationReport(design_name="d", input_file="in.sv")
        assert cr.design_name == "d"
        assert cr.input_file == "in.sv"
        assert cr.results == []
        datetime.fromisoformat(cr.timestamp)

    def test_empty_results_vacuous_success(self):
        cr = CompilationReport(design_name="d", input_file="f")
        assert cr.overall_success() is True
        assert cr.success_rate() == 0.0

    def test_overall_success_and_rate(self):
        cr = CompilationReport(
            design_name="d",
            input_file="f",
            results=[
                BackendResult("koika", True),
                BackendResult("acl2", False),
            ],
        )
        assert cr.overall_success() is False
        assert cr.success_rate() == 0.5

    def test_all_success_rate_one(self):
        cr = CompilationReport(
            design_name="d",
            input_file="f",
            results=[BackendResult("koika", True)],
        )
        assert cr.overall_success() is True
        assert cr.success_rate() == 1.0

    def test_to_dict(self):
        cr = CompilationReport(
            design_name="d",
            input_file="f",
            results=[BackendResult("koika", True)],
        )
        d = cr.to_dict()
        assert d["design_name"] == "d"
        assert d["input_file"] == "f"
        assert d["overall_success"] is True
        assert d["success_rate"] == 1.0
        assert d["results"][0]["backend"] == "koika"
        assert "timestamp" in d


class TestProofObligationResult:
    def test_required_fields_and_defaults(self):
        po = ProofObligationResult(property="p", status=Status.PASS, backend="koika")
        assert po.property == "p"
        assert po.status is Status.PASS
        assert po.backend == "koika"
        assert po.iterations is None
        assert po.proof_script is None
        assert po.error_message is None
        assert po.duration is None
        assert po.details == {}

    def test_to_dict_uses_enum_value(self):
        po = ProofObligationResult(
            property="p",
            status=Status.FAIL,
            backend="koika",
            iterations=3,
            proof_script="Proof. trivial. Qed.",
            error_message="e",
            duration=0.5,
            details={"lemmas_used": ["x"]},
        )
        d = po.to_dict()
        assert d["property"] == "p"
        assert d["status"] == "FAIL"
        assert d["backend"] == "koika"
        assert d["iterations"] == 3
        assert d["proof_script"] == "Proof. trivial. Qed."
        assert d["error_message"] == "e"
        assert d["duration"] == 0.5
        assert d["details"] == {"lemmas_used": ["x"]}


class TestVerificationReport:
    def test_empty_defaults(self):
        vr = VerificationReport(design_name="d", backend="koika")
        assert vr.obligations == []
        assert vr.overall_status is Status.PASS
        assert vr.pass_rate() == 0.0

    def test_status_priority_error_dominates(self):
        obs = [
            ProofObligationResult("a", Status.PASS, "k"),
            ProofObligationResult("b", Status.TIMEOUT, "k"),
            ProofObligationResult("c", Status.ERROR, "k"),
        ]
        assert VerificationReport("d", "k", obligations=obs).overall_status is Status.ERROR

    def test_status_priority_timeout_over_fail(self):
        obs = [
            ProofObligationResult("a", Status.PASS, "k"),
            ProofObligationResult("b", Status.FAIL, "k"),
            ProofObligationResult("c", Status.TIMEOUT, "k"),
        ]
        assert VerificationReport("d", "k", obligations=obs).overall_status is Status.TIMEOUT

    def test_status_priority_fail_over_pass(self):
        obs = [
            ProofObligationResult("a", Status.PASS, "k"),
            ProofObligationResult("b", Status.FAIL, "k"),
        ]
        assert VerificationReport("d", "k", obligations=obs).overall_status is Status.FAIL

    def test_status_all_pass(self):
        obs = [ProofObligationResult("a", Status.PASS, "k")]
        assert VerificationReport("d", "k", obligations=obs).overall_status is Status.PASS

    def test_explicit_status_overridden_by_obligations(self):
        obs = [ProofObligationResult("a", Status.PASS, "k")]
        vr = VerificationReport("d", "k", obligations=obs, overall_status=Status.ERROR)
        assert vr.overall_status is Status.PASS

    def test_pass_rate(self):
        obs = [
            ProofObligationResult("a", Status.PASS, "k"),
            ProofObligationResult("b", Status.FAIL, "k"),
            ProofObligationResult("c", Status.PASS, "k"),
        ]
        vr = VerificationReport("d", "k", obligations=obs)
        assert vr.pass_rate() == 2 / 3

    def test_to_dict(self):
        obs = [
            ProofObligationResult("a", Status.PASS, "k"),
            ProofObligationResult("b", Status.FAIL, "k"),
        ]
        vr = VerificationReport("d", "k", obligations=obs)
        d = vr.to_dict()
        assert d["design_name"] == "d"
        assert d["backend"] == "k"
        assert d["overall_status"] == "FAIL"
        assert d["pass_rate"] == 0.5
        assert d["obligations"][0]["status"] == "PASS"
        assert d["obligations"][1]["status"] == "FAIL"
        assert "timestamp" in d


class TestSimulationReport:
    def test_required_fields_and_defaults(self):
        sr = SimulationReport(design_name="d", success=True)
        assert sr.design_name == "d"
        assert sr.success is True
        assert sr.cycles is None
        assert sr.coverage is None
        assert sr.vcd_path is None
        assert sr.error_message is None
        assert sr.duration is None
        assert sr.metadata == {}

    def test_full_construction(self):
        sr = SimulationReport(
            design_name="d",
            success=False,
            cycles=100,
            coverage=0.9,
            vcd_path="t.vcd",
            error_message="e",
            duration=1.0,
            metadata={"m": 1},
        )
        assert sr.cycles == 100
        assert sr.coverage == 0.9
        assert sr.vcd_path == "t.vcd"
        assert sr.error_message == "e"
        assert sr.duration == 1.0
        assert sr.metadata == {"m": 1}

    def test_to_dict(self):
        sr = SimulationReport(
            design_name="d",
            success=False,
            cycles=100,
            coverage=0.9,
            vcd_path="t.vcd",
            error_message="e",
            duration=1.0,
            metadata={"m": 1},
        )
        assert sr.to_dict() == {
            "design_name": "d",
            "success": False,
            "cycles": 100,
            "coverage": 0.9,
            "vcd_path": "t.vcd",
            "error_message": "e",
            "duration": 1.0,
            "metadata": {"m": 1},
        }


class TestMergeStatuses:
    def test_empty_returns_pass(self):
        assert merge_statuses([]) is Status.PASS

    def test_all_pass(self):
        assert merge_statuses([Status.PASS, Status.PASS]) is Status.PASS

    def test_fail_priority(self):
        assert merge_statuses([Status.PASS, Status.FAIL]) is Status.FAIL

    def test_timeout_priority(self):
        assert merge_statuses([Status.PASS, Status.FAIL, Status.TIMEOUT]) is Status.TIMEOUT

    def test_error_priority(self):
        assert merge_statuses([Status.PASS, Status.TIMEOUT, Status.ERROR]) is Status.ERROR
