# tests/unit/test_evidence.py
#
# Unit tests for evidence registry, annotator, and registration helpers.
# Covers SQLite operations, annotation of AST nodes, and the new
# model-checking/theorem-proving evidence registration functions.
# Patches global config to direct evidence to a temporary database.

import pytest
from pathlib import Path
from unittest.mock import patch
from specir.evidence.registry import EvidenceRegistry
from specir.evidence.annotator import (
    create_evidence_ref,
    add_evidence_to_registry,
    annotate_module,
    annotate_state,
    annotate_rule,
    annotate_property,
    annotate_component,
    annotate_proof_obligation
)
from specir.parser.ast import (
    Module, State, Rule, Property, ProofObligation,
    Evidence, EvidenceRef, ComponentInstance
)
from specir.cli.verify import _safe_register_mc_evidence, _safe_register_evidence
from specir.verification.proof.proof import ProofResult


@pytest.fixture
def db_path(tmp_path):
    """Return a temporary database path."""
    return tmp_path / "test_evidence.db"


@pytest.fixture
def registry(db_path):
    """Return a fresh EvidenceRegistry using a temporary database."""
    return EvidenceRegistry(db_path=db_path)


class TestRegistry:
    def test_add_and_get(self, registry):
        ev_id = registry.add_evidence(
            evidence_type="coq_theorem",
            ref_type="uri",
            ref_value="file://proofs/test.v",
            engine="theorem_proving",
            status="proved",
            property_name="test_prop"
        )
        assert ev_id is not None
        entry = registry.get_evidence(ev_id)
        assert entry is not None
        assert entry["type"] == "coq_theorem"
        assert entry["ref_type"] == "uri"
        assert entry["status"] == "proved"

    def test_list_evidence(self, registry):
        registry.add_evidence("coq_theorem", "uri", "u1", "engine1", "p1", "prop_a")
        registry.add_evidence("counterexample_trace", "local_id", "l1", "BMC", "counterexample", "prop_b")
        all_entries = registry.list_evidence()
        assert len(all_entries) == 2

        filtered = registry.list_evidence(evidence_type="counterexample_trace")
        assert len(filtered) == 1
        assert filtered[0]["type"] == "counterexample_trace"

    def test_get_by_ref(self, registry):
        registry.add_evidence("simulation_trace", "uri", "file://trace.vcd", "sim", "active", "prop")
        entries = registry.get_evidence_by_ref("file://trace.vcd")
        assert len(entries) == 1
        assert entries[0]["ref_value"] == "file://trace.vcd"

    def test_update_status(self, registry):
        ev_id = registry.add_evidence("inductive_invariant", "local_id", "inv1", "IC3", "unproved", "prop")
        registry.update_status(ev_id, "proved")
        entry = registry.get_evidence(ev_id)
        assert entry["status"] == "proved"

    def test_delete(self, registry):
        ev_id = registry.add_evidence("coq_theorem", "uri", "del", "koika", "proved")
        assert registry.delete_evidence(ev_id)
        assert registry.get_evidence(ev_id) is None

    def test_statistics(self, registry):
        registry.add_evidence("coq_theorem", "uri", "a", "koika", "p")
        registry.add_evidence("coq_theorem", "uri", "b", "koika", "p")
        registry.add_evidence("counterexample_trace", "local_id", "c", "BMC", "c")
        stats = registry.get_statistics()
        assert stats["by_type"]["coq_theorem"] == 2
        assert stats["by_type"]["counterexample_trace"] == 1

    def test_add_counterexample(self, registry, tmp_path):
        trace = tmp_path / "trace.vcd"
        trace.write_text("dummy")
        ev_id = registry.add_counterexample("fail_prop", engine="BMC", trace_path=trace)
        entry = registry.get_evidence(ev_id)
        assert entry["type"] == "counterexample_trace"
        assert entry["ref_type"] == "uri"
        assert "trace.vcd" in entry["ref_value"]
        assert entry["status"] == "counterexample"

    def test_add_counterexample_no_trace(self, registry):
        ev_id = registry.add_counterexample("fail_prop", engine="BMC")
        entry = registry.get_evidence(ev_id)
        assert entry["ref_type"] == "local_id"
        assert "fail_prop" in entry["ref_value"]


class TestAnnotator:
    def test_create_evidence_ref(self):
        ev = create_evidence_ref(
            evidence_type="coq_theorem",
            ref_type="uri",
            ref_value="file://x",
            engine="koika",
            status="proved",
            property_name="p"
        )
        assert ev.type == "coq_theorem"
        assert ev.ref.type == "uri"
        assert ev.ref.value == "file://x"
        assert ev.engine == "koika"
        assert ev.status == "proved"

    def test_annotate_module(self):
        mod = Module(name="test")
        ev = Evidence(
            type="simulation_trace",
            ref=EvidenceRef(type="uri", value="file://sim.vcd"),
            engine="sim",
        )
        with patch("specir.evidence.annotator.add_evidence_to_registry"):
            annotate_module(mod, ev, property_name="prop")
        assert len(mod.evidence) == 1
        assert mod.evidence[0].type == "simulation_trace"

    def test_annotate_state(self):
        st = State(name="x", kind="register", type="bool")
        ev = Evidence(
            type="inductive_invariant",
            ref=EvidenceRef(type="local_id", value="inv_x"),
            engine="IC3"
        )
        with patch("specir.evidence.annotator.add_evidence_to_registry"):
            annotate_state(st, ev)
        assert st.evidence is not None
        assert st.evidence.value == "inv_x"

    def test_annotate_rule(self):
        r = Rule(name="r1")
        ev = Evidence(
            type="coq_theorem",
            ref=EvidenceRef(type="uri", value="file://proof.v"),
            engine="koika"
        )
        with patch("specir.evidence.annotator.add_evidence_to_registry"):
            annotate_rule(r, ev)
        assert r.evidence.value == "file://proof.v"

    def test_annotate_property(self):
        p = Property(name="prop1", kind="safety", expression=None)
        ev = Evidence(
            type="counterexample_trace",
            ref=EvidenceRef(type="uri", value="file://ce.vcd"),
            engine="BMC"
        )
        with patch("specir.evidence.annotator.add_evidence_to_registry"):
            annotate_property(p, ev, property_name="prop1")
        assert len(p.evidence) == 1
        assert p.evidence[0].value == "file://ce.vcd"

    def test_annotate_component(self):
        comp = ComponentInstance(name="u0", module="sub")
        ev = Evidence(
            type="simulation_trace",
            ref=EvidenceRef(type="uri", value="file://trace.vcd"),
            engine="sim"
        )
        with patch("specir.evidence.annotator.add_evidence_to_registry"):
            annotate_component(comp, ev)
        assert comp.evidence.value == "file://trace.vcd"

    def test_annotate_proof_obligation(self):
        po = ProofObligation(property="p", status="unproved", engine="theorem_proving")
        ev = Evidence(
            type="coq_theorem",
            ref=EvidenceRef(type="uri", value="file://proof.v"),
            engine="koika"
        )
        with patch("specir.evidence.annotator.add_evidence_to_registry"):
            annotate_proof_obligation(po, ev)
        assert po.artifact["type"] == "coq_theorem"
        assert po.artifact["ref"] == "file://proof.v"


class TestModelCheckingEvidence:
    @patch("specir.evidence.registry.get_config")
    def test_proved_registers_inductive_invariant(self, mock_cfg, tmp_path):
        db_path = tmp_path / "evidence.db"
        mock_cfg.return_value = {"evidence": {"db_path": str(db_path)}}

        mc_result = {"status": "proved", "counterexample_trace": None}
        _safe_register_mc_evidence(None, "mc_pass", mc_result)

        registry = EvidenceRegistry(db_path=db_path)
        entries = registry.list_evidence(property_name="mc_pass")
        assert len(entries) == 1
        assert entries[0]["type"] == "inductive_invariant"
        assert entries[0]["status"] == "proved"
        assert entries[0]["ref_type"] == "local_id"

    @patch("specir.evidence.registry.get_config")
    def test_counterexample_registers_trace(self, mock_cfg, tmp_path):
        db_path = tmp_path / "evidence.db"
        mock_cfg.return_value = {"evidence": {"db_path": str(db_path)}}

        trace = tmp_path / "ce.vcd"
        trace.write_text("dummy")
        mc_result = {"status": "disproved", "counterexample_trace": trace}
        _safe_register_mc_evidence(None, "mc_fail", mc_result)

        registry = EvidenceRegistry(db_path=db_path)
        entries = registry.list_evidence(property_name="mc_fail")
        assert len(entries) == 1
        assert entries[0]["type"] == "counterexample_trace"
        assert entries[0]["status"] == "counterexample"
        assert entries[0]["ref_type"] == "uri"
        assert "ce.vcd" in entries[0]["ref_value"]

    @patch("specir.evidence.registry.get_config")
    def test_counterexample_no_trace_uses_local_id(self, mock_cfg, tmp_path):
        db_path = tmp_path / "evidence.db"
        mock_cfg.return_value = {"evidence": {"db_path": str(db_path)}}

        mc_result = {"status": "disproved", "counterexample_trace": None}
        _safe_register_mc_evidence(None, "mc_fail_no_trace", mc_result)

        registry = EvidenceRegistry(db_path=db_path)
        entries = registry.list_evidence(property_name="mc_fail_no_trace")
        assert len(entries) == 1
        assert entries[0]["type"] == "counterexample_trace"
        assert entries[0]["status"] == "counterexample"
        assert entries[0]["ref_type"] == "local_id"
        assert "mc_fail_no_trace" in entries[0]["ref_value"]


class TestTheoremProvingEvidence:
    @patch("specir.evidence.registry.get_config")
    def test_koika_proof_registers_coq_theorem(self, mock_cfg, tmp_path):
        db_path = tmp_path / "evidence.db"
        mock_cfg.return_value = {"evidence": {"db_path": str(db_path)}}

        result = ProofResult(success=True, proof_script="Proof. trivial. Qed.")
        _safe_register_evidence(None, "koika_thm", "koika", result)

        registry = EvidenceRegistry(db_path=db_path)
        entries = registry.list_evidence(property_name="koika_thm")
        assert len(entries) == 1
        assert entries[0]["type"] == "coq_theorem"
        assert entries[0]["status"] == "proved"
        assert "file://Proof. trivial. Qed." in entries[0]["ref_value"]

    @patch("specir.evidence.registry.get_config")
    def test_acl2_proof_registers_acl2_theorem(self, mock_cfg, tmp_path):
        db_path = tmp_path / "evidence.db"
        mock_cfg.return_value = {"evidence": {"db_path": str(db_path)}}

        result = ProofResult(success=True, proof_script="(defthm ...)")
        _safe_register_evidence(None, "acl2_thm", "acl2", result)

        registry = EvidenceRegistry(db_path=db_path)
        entries = registry.list_evidence(property_name="acl2_thm")
        assert len(entries) == 1
        assert entries[0]["type"] == "acl2_theorem"
        assert entries[0]["status"] == "proved"
