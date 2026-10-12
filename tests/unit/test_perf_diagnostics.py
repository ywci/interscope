# tests/unit/test_perf_diagnostics.py
#
# Unit tests for the PERF diagnostic-report generator.

import pytest
from isir.verification.perf.perf_diagnostics import (
    generate_diagnostics,
    print_diagnostics,
)
from isir.verification.perf.perf_stats import PERFStats


class TestGenerateDiagnosticsBasics:
    def test_none_stats(self):
        assert generate_diagnostics(None) == "No PERF statistics available."

    def test_header_and_empty_sections(self):
        stats = PERFStats()
        report = generate_diagnostics(stats)
        assert "PERF Failure Diagnostics" in report
        assert "Top errors: none recorded." in report
        assert "Beam collapse events: 0" in report
        assert "Backtracking summary:" in report
        assert "Recommendations:" in report
        assert "No specific recommendations." in report


class TestTopErrors:
    def test_top_errors_are_listed_with_counts(self):
        stats = PERFStats()
        stats.record_error_signature("focused, but cannot be unfocused")
        stats.record_error_signature("focused, but cannot be unfocused")
        stats.record_error_signature("focused, but cannot be unfocused")
        stats.record_error_signature("unable to unify foo with bar")

        report = generate_diagnostics(stats)
        assert "Top errors:" in report
        assert "1. focused, but cannot be unfocused (3 occurrences)" in report
        assert "2. unable to unify foo with bar (1 occurrences)" in report

    def test_long_signature_is_truncated(self):
        stats = PERFStats()
        long_sig = "x" * 150
        stats.record_error_signature(long_sig)

        report = generate_diagnostics(stats)
        assert long_sig[:120] + "..." in report
        assert long_sig not in report


class TestBeamCollapse:
    def test_beam_collapse_reported(self):
        stats = PERFStats()
        stats.record_beam_collapse()
        stats.record_beam_collapse()
        report = generate_diagnostics(stats)
        assert "Beam collapse events: 2" in report

    def test_no_beam_collapse_reported(self):
        stats = PERFStats()
        report = generate_diagnostics(stats)
        assert "Beam collapse events: 0" in report


class TestBacktracking:
    def test_backtracking_summary_counts_and_reasons(self):
        stats = PERFStats()
        stats.record_backtrack(1)
        stats.record_backtrack(2)
        stats.record_on_demand_backtrack("depth_interval")
        stats.record_backtrack_details(
            diversity_used=True,
            alternate_primary_used=True,
            noise_used=True,
            force_regeneration_used=True,
        )

        report = generate_diagnostics(stats)
        assert "Total backtracks:            2" in report
        assert "On\u2011demand backtracks:        1" in report
        assert "depth_interval" in report
        assert "Diversity scoring used:      1 times" in report
        assert "Alternate primary dim used:  1 times" in report
        assert "Scoring noise used:          1 times" in report
        assert "Forced regeneration used:    1 times" in report

    def test_reflection_quality_history(self):
        stats = PERFStats()
        stats.record_backtrack(1)
        stats.reflection_quality_history.append({
            "backtrack_num": 1,
            "quality": 0.25,
            "delta": 0.1,
            "pre_best_primary": 0.5,
            "post_best_primary": 0.6,
        })

        report = generate_diagnostics(stats)
        assert "Reflection quality history:" in report
        assert "quality=0.25" in report
        assert "pre_best=0.500" in report
        assert "post_best=0.600" in report


class TestRecommendations:
    def test_focus_bullet_recommendation(self):
        stats = PERFStats()
        stats.record_error_signature("focused, but cannot be unfocused")
        report = generate_diagnostics(stats)
        assert "Focus/bullet errors are prevalent" in report

    def test_unification_recommendation(self):
        stats = PERFStats()
        stats.record_error_signature("unable to unify something")
        report = generate_diagnostics(stats)
        assert "Unification errors suggest applying the induction hypothesis" in report

    def test_beam_collapse_recommendation(self):
        stats = PERFStats()
        stats.record_beam_collapse()
        report = generate_diagnostics(stats)
        assert "Beam collapse occurred." in report

    def test_backtracking_without_reflection_recommendation(self):
        stats = PERFStats()
        stats.record_backtrack(1)
        report = generate_diagnostics(stats)
        assert "Backtracking was used but no reflection quality was recorded." in report

    def test_low_reflection_quality_recommendation(self):
        stats = PERFStats()
        stats.record_backtrack(1)
        stats.reflection_quality_history.append({
            "backtrack_num": 1,
            "quality": 0.1,
            "delta": 0.0,
            "pre_best_primary": 0.5,
            "post_best_primary": 0.5,
        })
        report = generate_diagnostics(stats)
        assert "Several backtracks produced low reflection quality." in report


class TestPrintDiagnostics:
    def test_print_diagnostics(self, capsys):
        stats = PERFStats()
        print_diagnostics(stats)
        captured = capsys.readouterr()
        assert "PERF Failure Diagnostics" in captured.out
