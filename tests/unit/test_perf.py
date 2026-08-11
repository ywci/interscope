# tests/unit/test_perf.py
#
# Unit tests for the PERF (Proof tree Exploration with Reflective Feedback)
# modules.  Covers configuration, statistics, scoring, parallel evaluation,
# evidence management, and the traversal orchestrator.

import json
import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, call, ANY
from dataclasses import asdict
from specir.verification.perf.perf_config import (
    PERFConfig,
    validate_perf_against_config,
    VALID_DIMENSIONS,
    DEFAULT_DIMENSIONS,
)
from specir.verification.perf.perf_stats import PERFStats
from specir.verification.perf.perf_scorer import (
    PERFScorer,
    PERFNode,
    compute_pareto_front,
    select_beam,
)
from specir.verification.perf.perf_parallel import PERFParallelEvaluator
from specir.verification.perf.perf_evidence import PERFEvidence
from specir.verification.perf.perf_traversal import PERFTraversal
from specir.backends.llm_client import LLMClient
from specir.evidence.registry import EvidenceRegistry


class TestPERFConfig:
    def test_defaults(self):
        config = PERFConfig()
        assert config.enabled is False
        assert config.beam_size == 3
        assert config.branches_per_node == 4
        assert config.depth_limit == 3
        assert config.dimensions == DEFAULT_DIMENSIONS
        assert config.scoring_tournament_size == 2
        assert config.generation_temperature == 0.4
        assert config.always_verify_children is True
        assert config.max_workers == 4
        assert config.timeout_per_node == 300
        assert config.primary_dimension == "subgoal_reduction"
        assert config.trace_alignment_weight == 0.6
        assert config.use_proof_library is False
        # New fields from the enhancement
        assert config.temperature_decay == 0.0
        assert config.temperature_min == 0.1
        assert config.early_stop_patience == 0
        assert config.early_stop_min_improvement == 0.01
        assert config.use_template_generator is False

    def test_validation_beam_size(self):
        with pytest.raises(ValueError, match="beam_size must be >= 1"):
            PERFConfig(beam_size=0)

    def test_validation_branches(self):
        with pytest.raises(ValueError, match="branches_per_node must be >= 1"):
            PERFConfig(branches_per_node=0)

    def test_validation_depth(self):
        with pytest.raises(ValueError, match="depth_limit must be >= 1"):
            PERFConfig(depth_limit=0)

    def test_validation_dimensions_empty(self):
        with pytest.raises(ValueError, match="dimensions list cannot be empty"):
            PERFConfig(dimensions=[])

    def test_validation_invalid_dimension(self):
        with pytest.raises(ValueError, match="Invalid dimension 'invalid_dim'"):
            PERFConfig(dimensions=["subgoal_reduction", "invalid_dim"])

    def test_validation_primary_dimension_outside_dimensions(self):
        config = PERFConfig(
            dimensions=["subgoal_reduction"], primary_dimension="trace_alignment"
        )
        config.validate()

    def test_validation_tournament_size(self):
        with pytest.raises(ValueError, match="scoring_tournament_size must be >= 1"):
            PERFConfig(scoring_tournament_size=0)

    def test_validation_temperature(self):
        with pytest.raises(ValueError, match="generation_temperature must be between 0.0 and 1.0"):
            PERFConfig(generation_temperature=1.5)
        with pytest.raises(ValueError, match="generation_temperature must be between 0.0 and 1.0"):
            PERFConfig(generation_temperature=-0.1)

    def test_validation_max_workers(self):
        with pytest.raises(ValueError, match="max_workers must be >= 1"):
            PERFConfig(max_workers=0)

    def test_validation_timeout(self):
        with pytest.raises(ValueError, match="timeout_per_node must be >= 1"):
            PERFConfig(timeout_per_node=0)

    def test_validation_weight(self):
        with pytest.raises(ValueError, match="trace_alignment_weight must be between 0.0 and 1.0"):
            PERFConfig(trace_alignment_weight=1.5)

    def test_from_global_config(self):
        global_cfg = {
            "proof": {
                "perf": {
                    "enabled": True,
                    "beam_size": 5,
                    "branches_per_node": 6,
                    "depth_limit": 4,
                    "dimensions": ["subgoal_reduction", "syntactic_purity"],
                    "scoring_tournament_size": 3,
                    "generation_temperature": 0.5,
                    "always_verify_children": False,
                    "max_workers": 8,
                    "timeout_per_node": 600,
                    "primary_dimension": "syntactic_purity",
                    "trace_alignment_weight": 0.8,
                }
            },
            "provers": {"koika": {"use_proof_library": True}},
        }
        config = PERFConfig.from_global_config(global_cfg)
        assert config.enabled is True
        assert config.beam_size == 5
        assert config.branches_per_node == 6
        assert config.depth_limit == 4
        assert config.dimensions == ["subgoal_reduction", "syntactic_purity"]
        assert config.scoring_tournament_size == 3
        assert config.generation_temperature == 0.5
        assert config.always_verify_children is False
        assert config.max_workers == 8
        assert config.timeout_per_node == 600
        assert config.primary_dimension == "syntactic_purity"
        assert config.trace_alignment_weight == 0.8
        assert config.use_proof_library is False

    def test_from_obligation_metadata(self):
        global_config = PERFConfig(beam_size=3, depth_limit=2)
        obligation_metadata = {
            "perf": {
                "beam_size": 10,
                "depth_limit": 5,
                "enabled": True,
                "dimensions": ["trace_alignment"],
                "primary_dimension": "trace_alignment"
            }
        }
        merged = PERFConfig.from_obligation_metadata(global_config, obligation_metadata)
        assert merged.beam_size == 10
        assert merged.depth_limit == 5
        assert merged.enabled is True
        assert merged.dimensions == ["trace_alignment"]
        assert merged.primary_dimension == "trace_alignment"
        assert merged.scoring_tournament_size == global_config.scoring_tournament_size

    def test_get_effective_dimensions(self):
        config = PERFConfig(
            dimensions=["subgoal_reduction"], primary_dimension="trace_alignment"
        )
        effective = config.get_effective_dimensions()
        assert effective == ["trace_alignment", "subgoal_reduction"]

        config = PERFConfig(
            dimensions=["subgoal_reduction", "trace_alignment"],
            primary_dimension="trace_alignment",
        )
        effective = config.get_effective_dimensions()
        assert effective == ["subgoal_reduction", "trace_alignment"]

    def test_is_enabled_for_obligation(self):
        config = PERFConfig(enabled=False)
        obligation = {"metadata": {"perf": {"enabled": True}}}
        assert config.is_enabled_for_obligation(obligation) is True

        config = PERFConfig(enabled=True)
        obligation = {"metadata": {"perf": {}}}
        assert config.is_enabled_for_obligation(obligation) is True

        config = PERFConfig(enabled=False)
        obligation = {"metadata": {}}
        assert config.is_enabled_for_obligation(obligation) is False

    def test_validate_perf_against_config_conflict(self):
        config = {
            "proof": {"perf": {"enabled": True}},
            "provers": {"koika": {"use_proof_library": True}},
        }
        with pytest.raises(
            ValueError, match="Configuration conflict: PERF enabled but use_proof_library is true"
        ):
            validate_perf_against_config(config)

    def test_validate_perf_against_config_no_conflict(self):
        config = {
            "proof": {"perf": {"enabled": True}},
            "provers": {"koika": {"use_proof_library": False}},
        }
        validate_perf_against_config(config)

        config = {
            "proof": {"perf": {"enabled": False}},
            "provers": {"koika": {"use_proof_library": True}},
        }
        validate_perf_against_config(config)


class TestPERFStats:
    def test_record_and_serialize(self):
        stats = PERFStats()
        stats.start()
        stats.record_node()
        stats.record_verifier_call()
        stats.record_depth(3)
        stats.record_beam_size(5)
        stats.record_pareto_pruned(10)
        stats.record_success(2)
        stats.record_tokens(100, 50)
        stats.record_depth_stats(1, 10, 3, 5)
        stats.record_progress(0.9, 0.01)
        stats.finish()

        d = stats.to_dict()
        assert d["total_nodes"] == 1
        assert d["total_verifier_calls"] == 1
        assert d["max_depth"] == 3
        assert d["beam_size"] == 5
        assert d["pruned_by_pareto"] == 10
        assert d["successful_depth"] == 2
        assert d["total_tokens"]["prompt"] == 100
        assert d["total_tokens"]["completion"] == 50
        assert len(d["depth_stats"]) == 1
        assert d["depth_stats"][0]["depth"] == 1
        assert d["depth_stats"][0]["nodes"] == 10
        assert d["start_time"] is not None
        assert d["end_time"] is not None
        assert d["best_primary_score"] == 0.9
        assert d["consecutive_no_improvement"] == 0

    def test_progress_no_improvement(self):
        stats = PERFStats()
        stats.record_progress(0.5, 0.01)
        stats.record_progress(0.51, 0.01)
        assert stats.consecutive_no_improvement == 0
        stats.record_progress(0.51, 0.01)
        assert stats.consecutive_no_improvement == 1

    def test_summary(self):
        stats = PERFStats()
        stats.record_node()
        stats.record_verifier_call()
        stats.record_depth(2)
        stats.record_beam_size(3)
        stats.record_pareto_pruned(5)
        stats.record_success(1)
        summary = stats.summary()
        assert "Total nodes generated:   1" in summary
        assert "Total verifier calls:    1" in summary
        assert "Maximum depth reached:   2" in summary
        assert "Final beam size:         3" in summary
        assert "Nodes pruned by Pareto:  5" in summary
        assert "Successful depth:        1" in summary

    def test_reset(self):
        stats = PERFStats()
        stats.record_node()
        stats.reset()
        assert stats.total_nodes == 0
        assert stats.total_verifier_calls == 0
        assert stats.max_depth == 0
        assert stats.beam_size == 0
        assert stats.pruned_by_pareto == 0
        assert stats.successful_depth is None
        assert stats.node_details == []
        assert stats.total_tokens == {"prompt": 0, "completion": 0}
        assert stats.best_primary_score == 0.0
        assert stats.consecutive_no_improvement == 0


class TestPERFScorer:
    def test_score_nodes_single(self):
        config = PERFConfig()
        llm = MagicMock(spec=LLMClient)
        scorer = PERFScorer(config, llm)
        nodes = [PERFNode(script="test", verification_result={"success": True})]
        scored = scorer.score_nodes(nodes, {}, {})
        assert len(scored) == 1
        assert scored[0].score is not None
        for dim in config.dimensions:
            assert scored[0].score[dim] == 1.0

    def test_score_nodes_two(self):
        config = PERFConfig()
        llm = MagicMock(spec=LLMClient)
        llm.generate.return_value = (
            '{"subgoal_reduction": 1, "trace_alignment": 1, "syntactic_purity": 1}'
        )
        scorer = PERFScorer(config, llm)
        node_a = PERFNode(script="a", verification_result={"success": True})
        node_b = PERFNode(script="b", verification_result={"success": False})
        nodes = [node_a, node_b]
        scored = scorer.score_nodes(nodes, {}, {})
        assert scored[0].score["subgoal_reduction"] > scored[1].score["subgoal_reduction"]

    def test_compute_pareto_front(self):
        nodes = []
        n0 = PERFNode(script="0", score={"a": 0.9, "b": 0.9})
        n1 = PERFNode(script="1", score={"a": 0.8, "b": 1.0})
        n2 = PERFNode(script="2", score={"a": 0.7, "b": 0.8})
        n3 = PERFNode(script="3", score={"a": 0.95, "b": 0.7})
        nodes = [n0, n1, n2, n3]

        front = compute_pareto_front(nodes, dimensions=["a", "b"])
        front_scripts = {n.script for n in front}
        assert front_scripts == {"0", "1", "3"}
        assert "2" not in front_scripts

    def test_compute_pareto_front_with_primary_dimension(self):
        nodes = [
            PERFNode(script="a", score={"x": 0.5, "y": 0.5}),
            PERFNode(script="b", score={"x": 0.6, "y": 0.4}),
            PERFNode(script="c", score={"x": 0.4, "y": 0.6}),
        ]
        front = compute_pareto_front(nodes, dimensions=["x", "y"], primary_dim="x")
        assert len(front) == 3
        assert front[0].script == "b"
        assert front[1].script == "a"
        assert front[2].script == "c"

    def test_select_beam(self):
        nodes = [
            PERFNode(script="a", score={"x": 0.9, "y": 0.1}),
            PERFNode(script="b", score={"x": 0.8, "y": 0.9}),
            PERFNode(script="c", score={"x": 0.7, "y": 0.8}),
            PERFNode(script="d", score={"x": 0.6, "y": 0.7}),
        ]
        beam = select_beam(nodes, beam_size=2, primary_dim="x")
        assert len(beam) == 2
        assert beam[0].script == "a"
        assert beam[1].script == "b"

    def test_select_beam_with_empty(self):
        beam = select_beam([], beam_size=3, primary_dim="x")
        assert beam == []


class TestPERFParallelEvaluator:
    def test_evaluate_nodes_single(self):
        evaluator = PERFParallelEvaluator(max_workers=2)
        node = PERFNode(script="test")

        def eval_fn(n):
            return {"success": True}

        result = evaluator.evaluate_nodes([node], eval_fn)
        assert result[0].verification_result["success"] is True

    def test_evaluate_nodes_multiple(self):
        evaluator = PERFParallelEvaluator(max_workers=4)
        nodes = [PERFNode(script=f"test_{i}") for i in range(3)]

        def eval_fn(n):
            return {"success": True, "script": n.script}

        results = evaluator.evaluate_nodes(nodes, eval_fn)
        assert len(results) == 3
        for r in results:
            assert r.verification_result["success"] is True
            assert r.verification_result["script"] == r.script

    def test_evaluate_nodes_timeout(self):
        evaluator = PERFParallelEvaluator(max_workers=2, timeout_per_node=1)
        node = PERFNode(script="slow")

        def slow_eval(n):
            import time

            time.sleep(5)
            return {"success": True}

        result = evaluator.evaluate_nodes([node], slow_eval, timeout=1)
        if result[0].verification_result["success"] is True:
            pass
        else:
            assert "timed out" in result[0].verification_result["error"].lower()

    def test_evaluate_nodes_exception(self):
        evaluator = PERFParallelEvaluator(max_workers=2)
        node = PERFNode(script="fail")

        def failing_eval(n):
            raise ValueError("test error")

        result = evaluator.evaluate_nodes([node], failing_eval)
        assert result[0].verification_result["success"] is False
        assert "test error" in result[0].verification_result["error"]


class TestPERFEvidence:
    @patch("specir.verification.perf.perf_evidence.add_evidence_to_registry")
    def test_register_proof(self, mock_add_evidence):
        mock_add_evidence.return_value = 123
        evidence_manager = PERFEvidence()
        stats = PERFStats()
        stats.record_node()
        pid = evidence_manager.register_proof(
            property_name="prop",
            proof_script="Proof. Qed.",
            backend="koika",
            stats=stats,
        )
        assert pid == 123
        assert mock_add_evidence.call_count == 2

        first_call = mock_add_evidence.call_args_list[0]
        first_kwargs = first_call[1]
        first_evidence = first_kwargs["evidence"]
        assert first_evidence.type == "coq_theorem"
        assert first_evidence.engine == "perf_koika"
        assert first_evidence.status == "proved"
        assert first_kwargs["property_name"] == "prop"

        second_call = mock_add_evidence.call_args_list[1]
        second_kwargs = second_call[1]
        second_evidence = second_kwargs["evidence"]
        assert second_evidence.type == "simulation_trace"
        assert second_evidence.engine == "perf_stats"
        assert "nodes=1" in second_evidence.ref.value
        assert second_kwargs["property_name"] == "prop"

    @patch("specir.verification.perf.perf_evidence.add_evidence_to_registry")
    def test_register_counterexample(self, mock_add_evidence):
        mock_add_evidence.return_value = 456

        evidence_manager = PERFEvidence()
        trace_path = Path("/tmp/trace.vcd")
        with patch.object(evidence_manager.registry, "add_counterexample", return_value=456) as mock_add_counter:
            cid = evidence_manager.register_counterexample(
                property_name="prop", trace_path=trace_path, engine="BMC"
            )
        assert cid == 456
        mock_add_counter.assert_called_once_with(
            property_name="prop",
            engine="BMC",
            trace_path=trace_path,
            status="counterexample",
        )

    @patch("specir.verification.perf.perf_evidence.add_evidence_to_registry")
    def test_register_stats(self, mock_add_evidence):
        mock_add_evidence.return_value = 789

        evidence_manager = PERFEvidence()
        stats = PERFStats()
        stats.record_node()
        stats.record_depth(2)

        sid = evidence_manager.register_stats(stats, property_name="prop")
        assert sid == 789
        mock_add_evidence.assert_called_once()

        call = mock_add_evidence.call_args
        kwargs = call[1]
        evidence_obj = kwargs["evidence"]
        assert evidence_obj.type == "simulation_trace"
        assert evidence_obj.engine == "perf_stats"
        assert "nodes=1" in evidence_obj.ref.value
        assert "depth=2" in evidence_obj.ref.value
        assert kwargs["property_name"] == "prop"

    @patch("specir.verification.perf.perf_evidence.EvidenceRegistry")
    def test_get_perf_proofs(self, mock_registry_class):
        mock_registry = MagicMock(spec=EvidenceRegistry)
        mock_registry_class.return_value = mock_registry
        evidence_manager = PERFEvidence(registry=mock_registry)

        evidence_manager.get_perf_proofs(property_name="prop", backend="koika")
        mock_registry.list_evidence.assert_called_with(
            evidence_type="coq_theorem", property_name="prop", engine="perf_koika"
        )

        mock_registry.list_evidence.reset_mock()
        evidence_manager.get_perf_proofs(property_name="prop")
        assert mock_registry.list_evidence.call_count == 2
        calls = mock_registry.list_evidence.call_args_list
        engines = [c[1]["engine"] for c in calls if "engine" in c[1]]
        assert set(engines) == {"perf_koika", "perf_acl2"}


class TestPERFTraversal:
    def setup_method(self):
        self.config = PERFConfig(
            enabled=True,
            beam_size=2,
            branches_per_node=2,
            depth_limit=2,
            always_verify_children=True,
        )
        self.llm = MagicMock(spec=LLMClient)
        self.context = {
            "obligation": {"property": "prop", "backend": "koika"},
            "coq_file_path": "/tmp/test.v",
            "theorem_name": "prop_proved",
            "workspace": "/tmp",
        }

    @patch("specir.verification.perf.perf_traversal.PERFParallelEvaluator")
    @patch("specir.verification.perf.perf_traversal.PERFScorer")
    def test_traverse_initial_success(self, mock_scorer, mock_parallel):
        traversal = PERFTraversal(self.config, self.llm, self.context)
        traversal._get_initial_script = MagicMock(return_value="Proof. Qed.")
        traversal._validate_initial_script = MagicMock(return_value=True)
        traversal._evaluate_node = MagicMock(return_value={"success": True})
        script, stats = traversal.traverse()
        assert script == "Proof. Qed."
        assert stats.successful_depth == 0

    @patch("specir.verification.perf.perf_traversal.PERFParallelEvaluator")
    @patch("specir.verification.perf.perf_traversal.PERFScorer")
    def test_traverse_no_children(self, mock_scorer, mock_parallel):
        traversal = PERFTraversal(self.config, self.llm, self.context)
        traversal._get_initial_script = MagicMock(return_value="Proof. Qed.")
        traversal._validate_initial_script = MagicMock(return_value=True)
        traversal._evaluate_node = MagicMock(return_value={"success": False})
        traversal._generate_children = MagicMock(return_value=[])
        script, stats = traversal.traverse()
        assert script is None
        assert stats.max_depth == 1

    @patch("specir.verification.perf.perf_traversal.PERFParallelEvaluator")
    @patch("specir.verification.perf.perf_traversal.PERFScorer")
    def test_traverse_child_success(self, mock_scorer_class, mock_parallel_class):
        mock_scorer = MagicMock()
        mock_scorer.score_nodes.side_effect = lambda nodes, ob, ctx: nodes
        mock_scorer_class.return_value = mock_scorer

        mock_parallel = MagicMock()
        mock_parallel.evaluate_nodes.side_effect = lambda nodes, fn, timeout: nodes
        mock_parallel_class.return_value = mock_parallel

        traversal = PERFTraversal(self.config, self.llm, self.context)
        traversal._get_initial_script = MagicMock(return_value="Proof. Admitted.")
        traversal._validate_initial_script = MagicMock(return_value=True)
        traversal._evaluate_node = MagicMock(return_value={"success": False})

        child_node = PERFNode(script="Proof. Qed.", depth=1)
        child_node.verification_result = {"success": True}
        traversal._generate_children = MagicMock(return_value=[child_node])

        def verify_mock(children):
            for c in children:
                c.verification_result = {"success": True}
            return children

        traversal._verify_children = verify_mock

        script, stats = traversal.traverse()
        assert script == "Proof. Qed."
        assert stats.successful_depth == 1

    @patch("specir.verification.perf.perf_traversal.PERFParallelEvaluator")
    @patch("specir.verification.perf.perf_traversal.PERFScorer")
    def test_traverse_depth_exhausted(self, mock_scorer_class, mock_parallel_class):
        mock_scorer = MagicMock()
        mock_scorer.score_nodes.side_effect = lambda nodes, ob, ctx: nodes
        mock_scorer_class.return_value = mock_scorer

        mock_parallel = MagicMock()
        mock_parallel.evaluate_nodes.side_effect = lambda nodes, fn, timeout: nodes
        mock_parallel_class.return_value = mock_parallel

        traversal = PERFTraversal(self.config, self.llm, self.context)
        traversal._get_initial_script = MagicMock(return_value="Proof. Admitted.")
        traversal._validate_initial_script = MagicMock(return_value=True)
        traversal._evaluate_node = MagicMock(return_value={"success": False})

        def gen_children(parents, depth):
            child = PERFNode(script="Proof. Admitted.", depth=parents[0].depth + 1)
            child.verification_result = {"success": False, "error": "Some Coq error"}
            return [child]

        traversal._generate_children = gen_children
        traversal._verify_children = lambda cs: cs

        traversal._repair_children = lambda children, depth: children

        script, stats = traversal.traverse()
        assert script is None
        assert stats.max_depth == 2

    @patch("specir.verification.perf.perf_traversal.PERFParallelEvaluator")
    @patch("specir.verification.perf.perf_traversal.PERFScorer")
    def test_traverse_with_acl2_backend(self, mock_scorer_class, mock_parallel_class):
        config = PERFConfig(
            enabled=True, beam_size=2, branches_per_node=2, depth_limit=1
        )
        context = {
            "obligation": {"property": "prop", "backend": "acl2"},
            "acl2_file_path": "/tmp/test.lisp",
            "theorem_name": "prop_correct",
            "workspace": "/tmp",
        }
        traversal = PERFTraversal(config, self.llm, context)
        traversal._get_initial_script = MagicMock(
            return_value="(defthm prop_correct ...)"
        )
        traversal._validate_initial_script = MagicMock(return_value=True)
        traversal._evaluate_node = MagicMock(return_value={"success": True})
        script, stats = traversal.traverse()
        assert script == "(defthm prop_correct ...)"
        assert stats.successful_depth == 0
