# tests/unit/test_cli_query.py
#
# Unit tests for the `isir query` CLI subcommand, using an in-memory
# SQLite EvidenceRegistry (via tmp_path) rather than the real project DB.

import argparse
import json
import pytest
from pathlib import Path
from unittest.mock import patch
from isir.cli.query import (
    _setup_arg_parser,
    query_evidence,
    _get_evidence_by_id,
    _format_evidence,
)
from isir.evidence.registry import EvidenceRegistry


@pytest.fixture
def registry(tmp_path):
    """A real EvidenceRegistry backed by a temp SQLite file."""
    reg = EvidenceRegistry(db_path=tmp_path / "evidence.db")
    reg.add_evidence(
        evidence_type="coq_theorem",
        ref_type="local_id",
        ref_value="local:p1",
        engine="koika",
        status="proved",
        property_name="p1",
        design_name="fifo",
        iterations=10,
        llm_used=True
    )
    reg.add_evidence(
        evidence_type="counterexample_trace",
        ref_type="local_id",
        ref_value="local:p2",
        engine="BMC",
        status="counterexample",
        property_name="p2",
        design_name="fifo",
        llm_used=False
    )
    return reg


class TestArgumentParser:
    def test_list_default(self):
        args = _setup_arg_parser().parse_args(["list"])
        assert args.command == "list"
        assert args.output_format == "text"

    def test_list_filters(self):
        args = _setup_arg_parser().parse_args([
            "list", "--type", "coq_theorem", "-p", "p1",
            "-e", "koika", "-d", "fifo", "--output-format", "json"
        ])
        assert args.type == "coq_theorem"
        assert args.property == "p1"
        assert args.engine == "koika"
        assert args.design == "fifo"
        assert args.output_format == "json"

    def test_id_subcommand(self):
        args = _setup_arg_parser().parse_args(["id", "42", "--output-format", "json"])
        assert args.command == "id"
        assert args.id == "42"
        assert args.output_format == "json"

    def test_stats_subcommand(self):
        args = _setup_arg_parser().parse_args(["stats", "--output-format", "json"])
        assert args.command == "stats"
        assert args.output_format == "json"

    def test_export_subcommand(self):
        args = _setup_arg_parser().parse_args([
            "export", "out.json", "--design", "fifo",
            "--backend", "koika", "--status", "proved"
        ])
        assert args.output_file == "out.json"
        assert args.design == "fifo"
        assert args.backend == "koika"
        assert args.status == "proved"

    def test_filter_subcommand(self):
        args = _setup_arg_parser().parse_args([
            "filter", "--property", "p1", "--type", "coq_theorem",
            "--limit", "10", "--output-format", "json"
        ])
        assert args.property == "p1"
        assert args.type == "coq_theorem"
        assert args.limit == 10
        assert args.output_format == "json"

    def test_list_type_choices(self):
        with pytest.raises(SystemExit):
            _setup_arg_parser().parse_args(["list", "--type", "bogus"])


class TestHelpers:
    def test_format_evidence(self):
        ev = {
            "id": 1,
            "type": "coq_theorem",
            "ref_type": "local_id",
            "ref_value": "local:p1",
            "engine": "koika",
            "status": "proved",
            "property_name": "p1",
            "design_name": "fifo",
            "iterations": 10,
            "llm_used": True,
            "created_at": "2024-01-01"
        }
        out = _format_evidence(ev)
        assert "ID: 1" in out
        assert "Type: coq_theorem" in out
        assert "LLM Used: True" in out

    def test_get_evidence_by_numeric_id(self, registry):
        new_id = registry.add_evidence(
            evidence_type="coq_theorem", ref_type="local_id",
            ref_value="local:x", engine="koika", status="proved",
        )
        ev = _get_evidence_by_id(registry, str(new_id))
        assert ev is not None
        assert ev["id"] == new_id

    def test_get_evidence_by_ref(self, registry):
        ev = _get_evidence_by_id(registry, "local:p1")
        assert ev is not None
        assert ev["property_name"] == "p1"

    def test_get_evidence_missing(self, registry):
        assert _get_evidence_by_id(registry, "local:missing") is None
        assert _get_evidence_by_id(registry, "999999") is None


def _args(command, **overrides):
    ns = argparse.Namespace(
        command=command,
        debug=False,
        output_format="text",
        type=None,
        property=None,
        engine=None,
        design=None,
        id=None,
        output_file=None,
        backend=None,
        status=None,
        limit=1000
    )
    ns.__dict__.update(overrides)
    return ns


class TestQueryEvidence:
    def test_list_text(self, registry, capsys):
        args = _args("list")
        with patch("isir.cli.query.EvidenceRegistry", return_value=registry):
            ret = query_evidence(args)
        out = capsys.readouterr().out
        assert ret == 0
        assert "coq_theorem" in out
        assert "Total: 2 entries" in out

    def test_list_json(self, registry, capsys):
        args = _args("list", type="coq_theorem", output_format="json")
        with patch("isir.cli.query.EvidenceRegistry", return_value=registry):
            ret = query_evidence(args)
        data = json.loads(capsys.readouterr().out)
        assert ret == 0
        assert len(data) == 1
        assert data[0]["type"] == "coq_theorem"

    def test_list_empty(self, registry, capsys):
        args = _args("list", type="simulation_trace")
        with patch("isir.cli.query.EvidenceRegistry", return_value=registry):
            ret = query_evidence(args)
        out = capsys.readouterr().out
        assert ret == 0
        assert "No evidence found" in out

    def test_id_found_json(self, registry, capsys):
        new_id = registry.add_evidence(
            evidence_type="acl2_theorem", ref_type="local_id",
            ref_value="local:y", engine="acl2", status="proved",
        )
        args = _args("id", id=str(new_id), output_format="json")
        with patch("isir.cli.query.EvidenceRegistry", return_value=registry):
            ret = query_evidence(args)
        data = json.loads(capsys.readouterr().out)
        assert ret == 0
        assert data["id"] == new_id

    def test_id_not_found(self, registry):
        args = _args("id", id="999999")
        with patch("isir.cli.query.EvidenceRegistry", return_value=registry):
            assert query_evidence(args) == 1

    def test_stats_json(self, registry, capsys):
        args = _args("stats", output_format="json")
        with patch("isir.cli.query.EvidenceRegistry", return_value=registry):
            ret = query_evidence(args)
        data = json.loads(capsys.readouterr().out)
        assert ret == 0
        assert data["total_entries"] == 2
        assert data["by_backend"]["koika"] == 1
        assert data["by_backend"]["BMC"] == 1
        assert data["by_status"]["proved"] == 1
        assert data["by_status"]["counterexample"] == 1

    def test_stats_text(self, registry, capsys):
        args = _args("stats")
        with patch("isir.cli.query.EvidenceRegistry", return_value=registry):
            ret = query_evidence(args)
        out = capsys.readouterr().out
        assert ret == 0
        assert "Total entries: 2" in out

    def test_export_json(self, registry, tmp_path):
        out_file = tmp_path / "export.json"
        args = _args("export", output_file=str(out_file), design="fifo")
        with patch("isir.cli.query.EvidenceRegistry", return_value=registry):
            ret = query_evidence(args)
        assert ret == 0
        assert out_file.exists()
        data = json.loads(out_file.read_text(encoding="utf-8"))
        assert len(data) == 2

    def test_export_csv(self, registry, tmp_path):
        out_file = tmp_path / "export.csv"
        args = _args("export", output_file=str(out_file))
        with patch("isir.cli.query.EvidenceRegistry", return_value=registry):
            ret = query_evidence(args)
        assert ret == 0
        assert out_file.exists()
        assert "coq_theorem" in out_file.read_text(encoding="utf-8")

    def test_filter_json(self, registry, capsys):
        args = _args("filter", design="fifo", status="proved", output_format="json")
        with patch("isir.cli.query.EvidenceRegistry", return_value=registry):
            ret = query_evidence(args)
        data = json.loads(capsys.readouterr().out)
        assert ret == 0
        assert len(data) == 1
        assert data[0]["status"] == "proved"

    def test_filter_empty(self, registry, capsys):
        args = _args("filter", status="nonexistent")
        with patch("isir.cli.query.EvidenceRegistry", return_value=registry):
            ret = query_evidence(args)
        out = capsys.readouterr().out
        assert ret == 0
        assert "No evidence found" in out

    def test_unknown_command(self, registry):
        args = _args("bogus")
        with patch("isir.cli.query.EvidenceRegistry", return_value=registry):
            assert query_evidence(args) == 1

    def test_registry_open_failure(self):
        args = _args("list")
        with patch("isir.cli.query.EvidenceRegistry",
                   side_effect=Exception("db failure")):
            assert query_evidence(args) == 1

    def test_default_command_is_list(self, registry, capsys):
        args = _args(None)
        with patch("isir.cli.query.EvidenceRegistry", return_value=registry):
            ret = query_evidence(args)
        out = capsys.readouterr().out
        assert ret == 0
        assert "Total: 2 entries" in out
