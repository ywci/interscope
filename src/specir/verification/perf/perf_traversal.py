# src/specir/verification/perf/perf_traversal.py
#
# Core PERF traversal engine – complete version with all helper methods,
# backtracking, scoring enhancements, forced regeneration, lemma‑aware
# prompt generation, robust LLM error handling (timeout wrapper),
# MC‑lemma restart guard, on‑demand backtracking triggers,
# destruct‑template injection, proof adaptation from successful proofs,
# Coq‑script sanitization, LLM health monitoring, reflection quality
# assessment, improved workspace handling for rocq‑mcp, and **strong
# structural pre‑filtering applied to initial scripts and all generated
# children**.

import copy
import math
import random
import time
import tempfile
import os
import shutil
import re
import subprocess
import hashlib
import concurrent.futures
import threading
from typing import List, Dict, Any, Optional, Tuple, Set
from pathlib import Path

from specir.backends.llm_client import LLMClient, LLMClientError
from specir.verification.perf.perf_config import PERFConfig
from specir.verification.perf.perf_scorer import (
    PERFScorer, PERFNode, compute_pareto_front, select_beam,
)
from specir.verification.perf.perf_stats import PERFStats
from specir.verification.perf.perf_parallel import PERFParallelEvaluator
from specir.verification.perf.perf_evidence import PERFEvidence
from specir.verification.perf.perf_analyzer import PERFAnalyzer, ObligationAnalysis
from specir.verification.perf.error_history import ErrorHistory
from specir.verification.proof.koika.proof_gen import (
    build_destruct_pattern, sanitize_coq_script, adapt_proof,
    build_coq_proof_prompt,
)
from specir.verification.proof.koika.auto_patcher import auto_patch
from specir.verification.proof.domain_tactics import get_koika_tactic_pattern
from specir.verification.proof.structural_validator import validate_structure
from specir.verification.proof.proof_pattern_cache import get_proof_pattern_cache
from specir.utils.logger import get_logger

logger = get_logger(__name__)


class ToolFailureError(Exception):
    """Raised when the underlying verification tool fails systematically."""
    pass


_DEFAULT_DIVERSITY_TAGS = [
    "induction on reachable + auto/lia",
    "induction on reachable + destruct on step cases",
    "case analysis on conditions (remember/destruct)",
    "use available lemmas with rewrite and auto",
    "apply inversion and substitution, then lia/nia",
    "use functional induction instead of structural induction",
    "forward reasoning: assert a helper lemma first",
]


class PERFTraversal:
    """Core PERF traversal engine."""

    def __init__(
        self,
        config: PERFConfig,
        llm_client: LLMClient,
        context: Dict[str, Any]
    ):
        self.config = config
        self.llm = llm_client
        self.context = context
        self.obligation = context.get("obligation", {})
        self.backend = self.obligation.get("backend", "koika").lower()
        self.backend = self.backend.replace("ō", "o")
        if not self.backend.startswith("koi") and self.backend != "acl2":
            self.backend = "koika"

        self.coq_context_str = ""
        if self.backend.startswith("koi"):
            coq_file = self.context.get("coq_file_path")
            if coq_file:
                try:
                    full_content = Path(coq_file).read_text()
                    env_part = full_content.split("(* PERF_Obligation:")[0]
                    self.coq_context_str = env_part.strip()
                except Exception:
                    self.coq_context_str = ""
        self.context["coq_environment"] = self.coq_context_str

        self.available_lemmas = self._get_available_lemmas()

        self.scorer = PERFScorer(config, llm_client, max_workers=config.max_workers)
        self.parallel_evaluator = PERFParallelEvaluator(
            max_workers=config.max_workers,
            timeout_per_node=config.timeout_per_node,
            config=context.get("config", {})
        )
        self.evidence = PERFEvidence()
        self.stats = PERFStats()

        self._tool_failure_count = 0
        self._MAX_TOOL_FAILURES = config.max_tool_failures_before_fallback
        self._coqc_path = shutil.which("coqc") or "coqc"

        self.analysis: Optional[ObligationAnalysis] = None
        self._analyzer = PERFAnalyzer()

        self._mc_injection_attempted = False
        self.config_dict = context.get("config", {})

        self._seen_script_hashes: Set[str] = set()
        self._expanded_node_ids: Set[int] = set()

        self._unify_repair = self.config_dict.get("proof", {}).get("perf", {}).get(
            "unify_repair_and_generation", False
        )
        self._parallel_gen = self.config_dict.get("proof", {}).get("perf", {}).get(
            "parallel_variant_generation", False
        )
        if self._parallel_gen:
            logger.info("Parallel variant generation enabled.")
        if self._unify_repair:
            logger.info("Unified repair‑aware generation enabled.")

        self._frontier_history: List[Dict[str, Any]] = []
        self._backtrack_count = 0
        self._backtrack_just_occurred = False
        self._backtracking_disabled = False

        self._failure_signatures: List[str] = []

        if config.error_history_enabled:
            self.error_history = ErrorHistory(max_entries=config.error_history_max_entries)
        else:
            self.error_history = None

        self._same_error_count = 0
        self._last_error_sig = None
        self._on_demand_cooldown = 0

        self._successful_proofs: Dict[str, str] = {}
        self._proof_patterns: List[str] = []

        self._consecutive_llm_failures = 0
        self._max_consecutive_llm_failures = 5

        self._reflection_eval_pending = False
        self._reflection_depth_counter = 0
        self._reflection_retries = 0

        self.best_candidate_script: Optional[str] = None
        self.best_candidate_score: float = -1.0

        self._force_strategy_switch = False
        self._force_strategy_hint = None

        self._proof_cache = get_proof_pattern_cache(self.config_dict)

        self._design_name = None
        if context.get("spec_module"):
            self._design_name = getattr(context["spec_module"], "name", None)

    def _safe_llm_generate(self, prompt: str, timeout: int = None) -> str:
        if timeout is None:
            timeout = self.config.timeout_per_node

        result_box = {}
        error_box = []

        def _worker():
            try:
                result_box["text"] = self.llm.generate(prompt)
            except Exception as exc:
                error_box.append(exc)

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()
        thread.join(timeout)

        if thread.is_alive():
            logger.error("LLM call timed out after %ds", timeout)
            return ""

        if error_box:
            logger.error("LLM call failed: %s", error_box[0])
            return ""

        return result_box.get("text", "")

    @staticmethod
    def _has_critical_structural_issues(script: str) -> bool:
        """Return True if the script contains critical structural problems."""
        issues = validate_structure(script)
        for issue in issues:
            if ("Unbalanced braces" in issue or
                "Unbalanced parentheses" in issue or
                "Unbalanced square brackets" in issue or
                "Unclosed proof" in issue or
                "Unclosed proof block" in issue or
                "orphan bullet" in issue or
                "[HARD ERROR]" in issue):
                return True
        return False

    def _filter_valid_scripts(self, scripts: List[str]) -> List[str]:
        """Filter out scripts with critical structural issues."""
        valid = []
        for script in scripts:
            if self._has_critical_structural_issues(script):
                logger.debug("Rejected script due to critical structural issues.")
                continue
            valid.append(script)
        return valid

    def _extract_reusable_patterns(self, proof_script: str) -> List[str]:
        """Extract high‑level tactic patterns from a successful proof."""
        patterns = []
        lines = proof_script.splitlines()
        for line in lines:
            stripped = line.strip()
            if re.match(r'^(induction|inversion|destruct|simpl|intros|apply|rewrite|unfold|assert)\b', stripped):
                patterns.append(stripped)
        seen = set()
        unique = []
        for p in patterns:
            if p not in seen:
                seen.add(p)
                unique.append(p)
        return unique[:10]

    def _record_successful_proof(self, prop_name: str, proof_script: str) -> None:
        self._successful_proofs[prop_name] = proof_script
        self._proof_patterns = self._extract_reusable_patterns(proof_script)
        if self._design_name and self._proof_cache:
            try:
                self._proof_cache.store_successful_proof(
                    self._design_name, prop_name, proof_script
                )
            except Exception as e:
                logger.warning("Failed to store proof in pattern cache: %s", e)

    def _get_cached_initial_script(self) -> Optional[str]:
        """Retrieve a cached proof for the current obligation, if available."""
        if not self._design_name:
            return None
        prop_name = self.obligation.get("property", "")
        if not prop_name:
            return None
        try:
            cached = self._proof_cache.get_successful_proof(self._design_name, prop_name)
            if cached:
                logger.info("Using cached proof for '%s/%s'.", self._design_name, prop_name)
                return cached
        except Exception as e:
            logger.warning("Failed to read proof pattern cache: %s", e)
        return None

    def _get_positive_example(self) -> Optional[str]:
        current_prop = self.obligation.get("property", "")
        if not current_prop:
            return None
        for prop_name, proof in self._successful_proofs.items():
            if prop_name != current_prop and _share_prefix(current_prop, prop_name, min_len=10):
                return proof
        return None

    def _try_adapt_successful_proof(self) -> Optional[str]:
        current_prop = self.obligation.get("property", "")
        theorem_name = self.context.get("theorem_name", "")
        theorem_stmt = self.context.get("theorem_statement", "")
        for prop_name, proof in self._successful_proofs.items():
            if prop_name == current_prop:
                continue
            condition_subst = {}
            operation_subst = {}
            if "overflow_implies_result_neq_sum" in prop_name and "overflow_implies_result_neq_diff" in current_prop:
                condition_subst["op_reg s =? 0"] = "op_reg s =? 1"
                operation_subst["a_reg s + b_reg s"] = "a_reg s - b_reg s"
            elif "overflow_implies_result_neq_diff" in prop_name and "overflow_implies_result_neq_sum" in current_prop:
                condition_subst["op_reg s =? 1"] = "op_reg s =? 0"
                operation_subst["a_reg s - b_reg s"] = "a_reg s + b_reg s"
            else:
                continue
            adapted = adapt_proof(
                proof, theorem_name, theorem_stmt,
                condition_subst=condition_subst,
                operation_subst=operation_subst,
            )
            if adapted:
                return adapted
        return None

    def traverse(self) -> Tuple[Optional[str], PERFStats]:
        logger.info("Starting PERF traversal (backend=%s)", self.backend)
        self.stats.start()

        if self.backend.startswith("koi"):
            coq_file = self.context.get("coq_file_path")
            theorem_name = self.context.get("theorem_name")
            if coq_file and theorem_name:
                self.analysis = self._analyzer.analyze(Path(coq_file), theorem_name)
                if self.analysis.suggests_rule_splitting:
                    logger.warning(
                        "Obligation analysis suggests rule splitting would help. "
                        "Consider adding the 'split' attribute to monolithic rules."
                    )
                if self.analysis.suggests_lemma_introduction:
                    logger.info(
                        "Detected duplicated subexpressions: %s. "
                        "PERF may benefit from helper lemmas.",
                        self.analysis.duplicated_subexpressions,
                    )
        else:
            self.analysis = ObligationAnalysis()

        initial_script = self._get_initial_script()
        if not initial_script:
            # Try cached proof.
            initial_script = self._get_cached_initial_script()

        if not initial_script:
            logger.error("No initial script available for PERF")
            self.stats.finish()
            return None, self.stats

        if self._has_critical_structural_issues(initial_script):
            logger.error("Initial script has critical structural issues; PERF cannot proceed.")
            self.stats.finish()
            return None, self.stats

        if not self._validate_initial_script(initial_script):
            logger.warning("Initial script failed compilation; PERF cannot proceed.")
            self.stats.finish()
            return None, self.stats

        self._register_script_hash(initial_script)

        root = PERFNode(script=initial_script, depth=0)
        self.stats.record_node()

        if self.config.always_verify_children:
            logger.info("Verifying initial script...")
            result = self._evaluate_node(root)
            root.verification_result = result
            self.stats.record_verifier_call()
            if result.get("success"):
                logger.info("Initial script already proves the theorem!")
                self.stats.record_success(0)
                self.stats.finish()
                self.evidence.register_proof(
                    property_name=self.obligation.get("property", "unknown"),
                    proof_script=initial_script,
                    backend=self.backend,
                    stats=self.stats,
                )
                self.best_candidate_script = initial_script
                self.best_candidate_score = 1.0
                self._record_successful_proof(self.obligation.get("property", ""), initial_script)
                return initial_script, self.stats

        frontier = [root]

        while True:
            depth = 0
            last_completed_depth = 0

            while depth < self.config.depth_limit:
                current_depth = depth + 1
                logger.info(
                    "PERF depth %d/%d: frontier size = %d",
                    current_depth, self.config.depth_limit, len(frontier),
                )
                self.stats.record_depth(current_depth)

                if self._on_demand_cooldown > 0:
                    self._on_demand_cooldown -= 1

                if self._reflection_eval_pending:
                    self._reflection_depth_counter += 1
                    if self._reflection_depth_counter >= self.config.reflection_quality_window:
                        current_best = self.stats.best_primary_score
                        current_sig = self._last_error_sig
                        quality = self.scorer.compute_reflection_quality(
                            pre_best_primary=self.stats.pre_backtrack_best_primary,
                            post_best_primary=current_best,
                            pre_error_sig=self.stats.pre_backtrack_error_sig,
                            post_error_sig=current_sig,
                            subgoal_reduction=self._estimate_subgoal_reduction(),
                            diversity_score=self._estimate_beam_diversity(frontier),
                        )
                        if quality < self.config.min_reflection_quality:
                            self._reflection_retries += 1
                            if self._reflection_retries <= self.config.max_reflection_retries:
                                logger.warning(
                                    "Reflection quality %.2f below threshold %.2f; attempting another backtrack.",
                                    quality, self.config.min_reflection_quality,
                                )
                                self._reflection_eval_pending = False
                                if self._attempt_backtrack(current_depth):
                                    depth = self._backtrack_new_depth
                                    frontier = self._backtrack_new_frontier
                                    self._backtrack_just_occurred = True
                                    self._on_demand_just_occurred = False
                                    self.stats.consecutive_no_improvement = 0
                                    self._set_force_strategy_switch()
                                    continue
                                else:
                                    logger.warning("Could not perform a new backtrack.")
                                    self._backtracking_disabled = True
                                    self._reflection_eval_pending = False
                            else:
                                logger.warning(
                                    "Reflection quality low and out of retries; disabling further backtracking."
                                )
                                self._backtracking_disabled = True
                                self._reflection_eval_pending = False
                        else:
                            logger.info("Reflection quality %.2f is sufficient.", quality)
                            self._reflection_eval_pending = False
                            self._reflection_retries = 0
                            self._force_strategy_switch = False

                children = self._generate_children(frontier, current_depth)
                self.stats.record_node(len(children))

                if not children and self._backtrack_just_occurred:
                    skip = (self.config.backtracking_on_demand_skip_forced_regeneration
                            and getattr(self, '_on_demand_just_occurred', False))
                    if not skip and self.config.backtracking_force_regeneration:
                        logger.info("No children after backtrack; attempting forced regeneration.")
                        children = self._force_regenerate_children(frontier, current_depth)
                        self.stats.record_node(len(children))
                        if children:
                            self.stats.record_backtrack_details(force_regeneration_used=True)
                    else:
                        logger.info("Skipping forced regeneration (on‑demand skip or global disable).")
                    self._backtrack_just_occurred = False
                    self._on_demand_just_occurred = False

                if not children:
                    logger.warning("No children generated at depth %d", current_depth)
                    break

                # Structural pre-filter before verification.
                children = self._filter_children(children)

                if not children:
                    logger.warning("No structurally valid children after filtering at depth %d", current_depth)
                    break

                if self.config.always_verify_children:
                    logger.info("Verifying %d children in parallel...", len(children))
                    try:
                        children = self._verify_children(children)
                    except ToolFailureError as e:
                        logger.error("Aborting PERF due to persistent tool failures: %s", e)
                        self.stats.finish()
                        return None, self.stats
                    for node in children:
                        self.stats.record_verifier_call()

                children = self._repair_children(children, current_depth)
                self._propagate_child_errors(frontier, children)

                for child in children:
                    if child.verification_result and not child.verification_result.get("success"):
                        err = child.verification_result.get("error", "")
                        if err and not self._is_opaque_tool_error(err):
                            sig = self.scorer._error_signature(self._clean_coq_error(err))
                            if sig not in self._failure_signatures:
                                self._failure_signatures.append(sig)
                            if self.error_history is not None:
                                self.error_history.record_failure(child.script, err)
                            self.stats.record_error_signature(sig)

                for node in children:
                    if node.verification_result and node.verification_result.get("success"):
                        logger.info(
                            "PERF found a successful proof at depth %d (after repair)!",
                            current_depth,
                        )
                        self.stats.record_success(current_depth)
                        self.stats.record_beam_size(len(frontier))
                        self.stats.finish()
                        prop_name = self.obligation.get("property", "unknown")
                        self._record_successful_proof(prop_name, node.script)
                        self.evidence.register_proof(
                            property_name=prop_name,
                            proof_script=node.script,
                            backend=self.backend,
                            stats=self.stats,
                        )
                        self.best_candidate_script = node.script
                        self.best_candidate_score = 1.0
                        return node.script, self.stats

                for node in children:
                    node.structural_issues = validate_structure(node.script)
                    if node.verification_result and not node.verification_result.get("success"):
                        err = node.verification_result.get("error", "")
                        node.error_count = self._count_compiler_errors(err)
                    else:
                        node.error_count = 0

                logger.info("Scoring %d children...", len(children))
                scored_children = self.scorer.score_nodes(
                    children, self.obligation, self.context
                )

                self._adjust_scores_for_quality(scored_children)

                pareto_front = compute_pareto_front(
                    scored_children,
                    dimensions=self.config.dimensions,
                    primary_dim=self.config.primary_dimension,
                )
                pruned_count = len(scored_children) - len(pareto_front)
                self.stats.record_pareto_pruned(pruned_count)
                logger.info(
                    "Pareto front: %d nodes (pruned %d)",
                    len(pareto_front), pruned_count,
                )

                frontier = select_beam(
                    pareto_front,
                    self.config.beam_size,
                    self.config.primary_dimension,
                )

                if len(frontier) < self.config.min_beam_size:
                    logger.info(
                        "Beam size %d is below min_beam_size %d; adding best remaining candidates.",
                        len(frontier), self.config.min_beam_size,
                    )
                    sorted_all = sorted(
                        scored_children,
                        key=lambda n: n.score.get(self.config.primary_dimension, 0.0) if n.score else 0.0,
                        reverse=True,
                    )
                    existing_ids = {id(n) for n in frontier}
                    for node in sorted_all:
                        if len(frontier) >= self.config.min_beam_size:
                            break
                        if id(node) not in existing_ids:
                            frontier.append(node)
                            existing_ids.add(id(node))
                    if len(frontier) < self.config.min_beam_size:
                        logger.warning(
                            "Could not reach min_beam_size %d; beam has %d nodes.",
                            self.config.min_beam_size, len(frontier),
                        )
                        self.stats.record_beam_collapse()

                self.stats.record_beam_size(len(frontier))
                logger.info("Beam selected: %d nodes", len(frontier))

                # Mark selected nodes as expanded for backtracking novelty.
                for node in frontier:
                    self._expanded_node_ids.add(id(node))

                for node in frontier:
                    if node.score:
                        val = node.score.get(self.config.primary_dimension, 0.0)
                        if val > self.best_candidate_score:
                            self.best_candidate_score = val
                            self.best_candidate_script = node.script

                beam_scripts = [n.script for n in frontier]

                snapshot = {
                    "depth": current_depth,
                    "candidates": pareto_front.copy(),
                    "beam_ids": {id(n) for n in frontier},
                    "beam_scripts": beam_scripts,
                }
                if self.config.backtracking_store_all_scored_children:
                    snapshot["all_scored_children"] = scored_children

                self._frontier_history.append(snapshot)

                self.stats.record_depth_stats(
                    current_depth, len(children), len(frontier), pruned_count
                )

                best_primary = 0.0
                for node in frontier:
                    if node.score:
                        val = node.score.get(self.config.primary_dimension, 0.0)
                        if val > best_primary:
                            best_primary = val
                self.stats.record_progress(
                    best_primary, self.config.early_stop_min_improvement
                )

                if (self.config.backtracking_on_demand_enabled and
                    not self._backtracking_disabled and
                    self._on_demand_cooldown == 0):
                    on_demand_triggered = False
                    reason = ""

                    if (self.config.backtracking_on_demand_force_every > 0
                            and current_depth % self.config.backtracking_on_demand_force_every == 0):
                        logger.info("On‑demand backtrack triggered by depth interval.")
                        on_demand_triggered = True
                        reason = "depth_interval"

                    if (not on_demand_triggered
                            and self.config.backtracking_on_demand_time_limit > 0
                            and time.time() - self.stats.start_time_epoch > self.config.backtracking_on_demand_time_limit):
                        logger.info("On‑demand backtrack triggered by time limit.")
                        on_demand_triggered = True
                        reason = "time_limit"

                    if (not on_demand_triggered
                            and self.config.backtracking_on_demand_max_same_error > 0
                            and self._same_error_count >= self.config.backtracking_on_demand_max_same_error):
                        logger.info("On‑demand backtrack triggered by repeated error (%d occurrences).",
                                    self._same_error_count)
                        on_demand_triggered = True
                        reason = "too_many_identical_errors"

                    if on_demand_triggered:
                        if self._on_demand_backtrack(current_depth, reason):
                            depth = self._backtrack_new_depth
                            frontier = self._backtrack_new_frontier
                            self._same_error_count = 0
                            self._last_error_sig = None
                            self._on_demand_cooldown = 2
                            self.stats.consecutive_no_improvement = 0
                            self._set_force_strategy_switch()
                            continue
                        else:
                            logger.warning("On‑demand backtrack failed; continuing normally.")

                if (self.config.backtracking_enabled
                    and not self._backtracking_disabled
                    and self._backtrack_count < self.config.backtracking_max_restarts
                    and self.stats.consecutive_no_improvement >= self.config.backtracking_stagnation_depth):
                    logger.warning(
                        "Stagnation detected at depth %d (no improvement for %d depths). "
                        "Attempting backtrack...",
                        current_depth, self.stats.consecutive_no_improvement,
                    )
                    if self._attempt_backtrack(current_depth):
                        depth = self._backtrack_new_depth
                        frontier = self._backtrack_new_frontier
                        self._backtrack_just_occurred = True
                        self._on_demand_just_occurred = False
                        self.stats.consecutive_no_improvement = 0
                        self._set_force_strategy_switch()
                        continue
                    else:
                        logger.warning("Backtrack failed; continuing normally.")

                if self.config.early_stop_patience > 0:
                    if self.stats.consecutive_no_improvement >= self.config.early_stop_patience:
                        logger.warning(
                            "Early stopping: no Pareto improvement for %d consecutive depths.",
                            self.stats.consecutive_no_improvement,
                        )
                        break

                if current_depth == 2 and not self._any_progress(frontier):
                    diagnosis = self._diagnose_failure()
                    logger.error("PERF diagnosis: %s", diagnosis.get("reason"))
                    if diagnosis.get("recommendation") == "give_up":
                        self.stats.finish()
                        return None, self.stats

                if (self.stats.consecutive_no_improvement >= max(1, self.config.early_stop_patience // 2)
                        and self.backend.startswith("koi")
                        and not self._mc_injection_attempted):
                    mc_enabled = (
                        self.config_dict.get("provers", {}).get("koika", {}).get("use_mc_lemmas", False)
                    )
                    if mc_enabled:
                        logger.info("Attempting MC lemma injection to unstick the search.")
                        self._mc_injection_attempted = True
                        try:
                            from specir.verification.proof.koika.prover import KoikaProver
                            prover = KoikaProver(config=self.config_dict)
                            prover.spec_module = self.context.get("spec_module")
                            coq_file = Path(self.context["coq_file_path"])
                            theorem_name = self.context["theorem_name"]
                            before_content = coq_file.read_text()
                            prover.inject_mc_lemmas(coq_file, theorem_name)
                            after_content = coq_file.read_text()
                            if before_content != after_content:
                                logger.info("MC lemmas successfully injected; restarting PERF traversal.")
                                return self.traverse()
                            else:
                                logger.info("No MC‑proved lemmas could be injected; continuing current search.")
                        except Exception as e:
                            logger.error("MC lemma injection failed: %s", e)

                last_completed_depth = current_depth
                depth += 1

            if (self.config.backtracking_enabled
                and not self._backtracking_disabled
                and self._backtrack_count < self.config.backtracking_max_restarts
                and self._frontier_history):
                logger.info(
                    "Depth budget exhausted or early stopped at depth %d. "
                    "Attempting backtrack before giving up.",
                    last_completed_depth,
                )
                if self._attempt_backtrack(last_completed_depth):
                    depth = self._backtrack_new_depth
                    frontier = self._backtrack_new_frontier
                    self._backtrack_just_occurred = True
                    self._on_demand_just_occurred = False
                    self.stats.consecutive_no_improvement = 0
                    self._set_force_strategy_switch()
                    continue
                else:
                    logger.warning("Backtrack attempt failed; no more alternatives.")
            break

        logger.warning(
            "PERF exhausted after %d depths, %d backtrack restarts.",
            self.config.depth_limit,
            self._backtrack_count,
        )
        self.stats.finish()
        return None, self.stats

    def _on_demand_backtrack(self, current_depth: int, reason: str) -> bool:
        logger.info("On‑demand backtrack triggered: %s", reason)
        self.stats.record_on_demand_backtrack(reason)
        saved = self._backtrack_count
        success = self._attempt_backtrack(current_depth)
        if self._backtrack_count > saved:
            self._backtrack_count = saved
        if success:
            if self.config.backtracking_on_demand_skip_forced_regeneration:
                self._backtrack_just_occurred = False
                self._on_demand_just_occurred = True
            else:
                self._backtrack_just_occurred = True
                self._on_demand_just_occurred = True
        return success

    def _get_available_lemmas(self) -> List[str]:
        if not self.coq_context_str:
            return []
        matches = re.findall(r"Lemma\s+(\w+)\s*:", self.coq_context_str)
        return sorted(set(matches))

    def _attempt_backtrack(self, current_depth: int) -> bool:
        if not self._frontier_history:
            logger.warning("No frontier history available for backtrack.")
            return False

        target_depth = max(
            0, current_depth - self.config.backtracking_max_backtrack_depth
        )
        logger.info(
            "Backtracking: looking for a snapshot at depth %d (current depth %d).",
            target_depth, current_depth,
        )

        snapshot = None
        for entry in reversed(self._frontier_history):
            if entry["depth"] == target_depth:
                snapshot = entry
                break
        if snapshot is None:
            if self._frontier_history:
                snapshot = self._frontier_history[0]
                logger.info(
                    "No exact match; using earliest snapshot at depth %d.",
                    snapshot["depth"],
                )
            else:
                return False

        best_primary = self.stats.best_primary_score
        error_sig = self._last_error_sig
        self.stats.record_pre_backtrack_state(best_primary, error_sig)
        self._reflection_eval_pending = True
        self._reflection_depth_counter = 0

        self._backtrack_count += 1
        self.stats.record_backtrack(snapshot["depth"])
        logger.info(
            "Backtrack #%d: restoring frontier from depth %d.",
            self._backtrack_count, snapshot["depth"],
        )

        if self.config.backtracking_store_all_scored_children and "all_scored_children" in snapshot:
            candidates = snapshot["all_scored_children"]
            logger.info("Using full scored children list (%d nodes) for backtracking.", len(candidates))
        else:
            candidates = snapshot["candidates"]
            logger.info("Using Pareto front (%d nodes) for backtracking.", len(candidates))

        # **Novelty filter**: exclude nodes already expanded in previous iterations.
        novel_candidates = [n for n in candidates if id(n) not in self._expanded_node_ids]
        if not novel_candidates:
            logger.warning("No novel candidates remain for backtracking.")
            return False

        candidates = novel_candidates

        diversity_used = False
        alt_primary_used = False
        experience_used = False
        noise_used = False

        if (self.config.backtracking_diversity_dimensions and "beam_scripts" in snapshot):
            self.scorer.add_diversity_scores(
                candidates,
                snapshot["beam_scripts"],
                diversity_dimensions=self.config.backtracking_diversity_dimensions,
            )
            diversity_used = True

        extended_dimensions = list(self.config.dimensions)
        if diversity_used:
            for dim in self.config.backtracking_diversity_dimensions:
                if dim not in extended_dimensions:
                    extended_dimensions.append(dim)

        if self.config.backtracking_experience_penalty and self._failure_signatures:
            self.scorer.add_experience_penalty(
                candidates,
                self._failure_signatures,
                penalty_factor=0.2,
            )
            experience_used = True

        if self.config.backtracking_avoid_repeated_branches and "beam_ids" in snapshot:
            avoid_ids = snapshot["beam_ids"]
            filtered_candidates = [n for n in candidates if id(n) not in avoid_ids]
            if filtered_candidates:
                candidates = filtered_candidates

        primary_dim = self.config.primary_dimension
        if self.config.backtracking_alternate_primary_dimension:
            primary_dim = self.config.backtracking_alternate_primary_dimension
            alt_primary_used = True

        if self.config.backtracking_scoring_noise_std > 0:
            std = self.config.backtracking_scoring_noise_std
            for node in candidates:
                if node.score:
                    for dim in node.score:
                        node.score[dim] += random.gauss(0, std)
                        node.score[dim] = max(0.0, min(1.0, node.score[dim]))
            noise_used = True

        pareto_front = compute_pareto_front(
            candidates,
            dimensions=extended_dimensions,
            primary_dim=primary_dim,
        )

        restore_size = self.config.backtracking_restore_beam_size
        new_frontier = select_beam(pareto_front, restore_size, primary_dim)

        if len(new_frontier) < self.config.min_beam_size:
            sorted_candidates = sorted(
                candidates,
                key=lambda n: n.score.get(primary_dim, 0.0) if n.score else 0.0,
                reverse=True,
            )
            existing_ids = {id(n) for n in new_frontier}
            for node in sorted_candidates:
                if len(new_frontier) >= self.config.min_beam_size:
                    break
                if id(node) not in existing_ids:
                    new_frontier.append(node)
                    existing_ids.add(id(node))

        if not new_frontier:
            return False

        self.stats.record_backtrack_details(
            diversity_used=diversity_used,
            alternate_primary_used=alt_primary_used,
            experience_penalty_used=experience_used,
            noise_used=noise_used,
        )

        self._backtrack_new_depth = snapshot["depth"] - 1
        self._backtrack_new_frontier = new_frontier
        return True

    def _set_force_strategy_switch(self):
        self._force_strategy_switch = True
        if any("reflexivity" in sig.lower() for sig in self._failure_signatures):
            self._force_strategy_hint = (
                "Do NOT rely solely on `reflexivity`. Use `lia` or `nia` for arithmetic goals, "
                "or `auto` with lemma rewriting."
            )
        elif any("lia" in sig.lower() for sig in self._failure_signatures):
            self._force_strategy_hint = (
                "Avoid `lia` for now; try `reflexivity` after full simplification, "
                "or use `apply IH` after destructing opcode conditions."
            )
        else:
            self._force_strategy_hint = (
                "Try a fundamentally different tactic pattern: split on step constructors, "
                "then destruct opcode and use `simpl; auto` or `simpl; reflexivity`."
            )
        logger.info("Forced strategy switch enabled for next generation.")

    def _force_regenerate_children(self, frontier: List[PERFNode], depth: int) -> List[PERFNode]:
        total_budget = self.config.beam_size * self.config.branches_per_node
        if not frontier:
            return []

        per_parent = max(1, total_budget // len(frontier))
        all_children: List[PERFNode] = []

        failure_hint = ""
        mandatory_avoid = self._get_mandatory_avoid()
        if self._failure_signatures:
            recent = self._failure_signatures[-3:]
            failure_hint = (
                "Common errors in previous attempts:\n" +
                "\n".join(f"- {sig[:200]}" for sig in recent) +
                "\n\n"
            )

        temp = self.config.generation_temperature + self.config.backtracking_regeneration_temperature_boost
        temp = min(1.0, max(0.1, temp))
        combined_hint = failure_hint + self.config.backtracking_regeneration_strategy_hint

        if self._force_strategy_switch and self._force_strategy_hint:
            combined_hint += "\n\n**MANDATORY STRATEGY CHANGE:** " + self._force_strategy_hint

        if (self.config_dict.get("proof", {}).get("perf", {}).get("backtracking", {}).get("use_destruct_template", False)
                and self.analysis and self.analysis.has_nested_ite and self.analysis.max_ite_depth >= 3):
            destruct_pattern = build_destruct_pattern("op_reg s", 4)
            combined_hint += (
                "\n\n**CONCRETE DESTRUCT PATTERN (must be used):**\n"
                f"```coq\n{destruct_pattern}\n```\n"
                "After inversion on Hstep, you MUST insert this destruct chain."
            )

        positive_example = self._get_positive_example()

        for parent in frontier:
            prompts_info = self._build_prompts_for_parent(
                parent, depth, per_parent,
                strategy_hint_override=combined_hint,
                temperature_override=temp,
                bypass_cache=True,
                available_lemmas=self.available_lemmas,
                mandatory_avoid=mandatory_avoid,
                positive_example=positive_example,
            )
            raw_responses = [self._safe_llm_generate(info["prompt"]) for info in prompts_info]

            scripts = []
            for resp in raw_responses:
                script = self._extract_script_from_response(resp, False)
                if script:
                    script = sanitize_coq_script(script)
                    script = auto_patch(script)
                    if not self._has_critical_structural_issues(script):
                        scripts.append(script)
                    else:
                        logger.debug("Rejected force-regenerated script due to structural issues.")

            while len(scripts) < per_parent:
                scripts.append(parent.script)

            for script in scripts:
                child = PERFNode(script=script, parent=parent, depth=depth)
                all_children.append(child)

        logger.info("Force regeneration produced %d children across %d parents.",
                     len(all_children), len(frontier))
        return all_children

    def _generate_children(self, frontier: List[PERFNode], depth: int) -> List[PERFNode]:
        # Adaptive branching using config.
        if (self.config.adaptive_branching_enabled and
                self.analysis is not None and
                self.analysis.has_nested_ite and
                self.analysis.max_ite_depth >= 3):
            branches_per_node = max(
                self.config.min_branches_for_hard_obligations,
                self.config.branches_per_node
            )
            branches_per_node = min(
                branches_per_node,
                self.config.max_branches_for_hard_obligations
            )
            total_budget = self.config.beam_size * branches_per_node
        else:
            branches_per_node = self.config.branches_per_node
            total_budget = self.config.beam_size * branches_per_node

        if not frontier:
            return []

        scores = []
        for parent in frontier:
            if parent.score and self.config.primary_dimension in parent.score:
                scores.append(parent.score[self.config.primary_dimension])
            else:
                scores.append(0.5)
        total = sum(scores) if sum(scores) > 0 else len(frontier)
        weights = [max(0.1, s / total) for s in scores]

        raw = [round(w * total_budget) for w in weights]
        diff = total_budget - sum(raw)
        if diff > 0:
            idx_max = weights.index(max(weights))
            raw[idx_max] += diff
        elif diff < 0:
            idx_max = raw.index(max(raw))
            raw[idx_max] = max(1, raw[idx_max] + diff)

        for i in range(len(raw)):
            if raw[i] < 1:
                raw[i] = 1

        use_llm = self._consecutive_llm_failures < self._max_consecutive_llm_failures

        all_prompts: List[Dict[str, Any]] = []
        mandatory_avoid = self._get_mandatory_avoid()
        positive_example = self._get_positive_example()

        force_hint = None
        if self._force_strategy_switch and self._force_strategy_hint:
            force_hint = self._force_strategy_hint

        if self.error_history is not None:
            repeated_sigs = self.error_history.get_repeated_signatures(min_count=2)
            if repeated_sigs:
                avoid_phrases = [self._format_error_sig_for_avoid(sig) for sig in repeated_sigs[:3]]
                mandatory_avoid = (mandatory_avoid or []) + avoid_phrases

        for parent_idx, (parent, num_variants) in enumerate(zip(frontier, raw)):
            prompts_info = self._build_prompts_for_parent(
                parent, depth, num_variants,
                strategy_hint_override=force_hint,
                available_lemmas=self.available_lemmas,
                mandatory_avoid=mandatory_avoid,
                positive_example=positive_example,
            )
            for info in prompts_info:
                info["parent_idx"] = parent_idx
                all_prompts.append(info)

        if use_llm:
            if self._parallel_gen and all_prompts:
                try:
                    raw_responses = self.llm.generate_batch(
                        prompts=[p["prompt"] for p in all_prompts],
                        system=None,
                        max_workers=min(self.config.max_workers, len(all_prompts)),
                        max_tokens=None,
                    )
                except Exception:
                    raw_responses = [self._safe_llm_generate(p["prompt"]) for p in all_prompts]
            else:
                raw_responses = [self._safe_llm_generate(p["prompt"]) for p in all_prompts]
        else:
            raw_responses = ["Proof. Admitted."] * len(all_prompts)

        variants_per_parent: Dict[int, List[str]] = {i: [] for i in range(len(frontier))}
        for idx, resp in enumerate(raw_responses):
            meta = all_prompts[idx]
            parent_idx = meta["parent_idx"]
            script = self._extract_script_from_response(resp, meta.get("is_repair", False))
            if script:
                script = sanitize_coq_script(script)
                script = auto_patch(script)
                if not self._has_critical_structural_issues(script):
                    variants_per_parent[parent_idx].append(script)
                else:
                    logger.debug("Rejected generated script due to critical structural issues.")

        # Add adapted successful proof as a variant.
        if self._successful_proofs:
            for parent_idx in variants_per_parent:
                adapted = self._try_adapt_successful_proof()
                if adapted and not self._has_critical_structural_issues(adapted):
                    variants_per_parent[parent_idx].insert(0, adapted)

        # Template fallback for shortfall.
        for parent_idx, parent in enumerate(frontier):
            existing = variants_per_parent[parent_idx]
            needed = raw[parent_idx]
            shortfall = needed - len(existing)
            if shortfall > 0:
                if self.backend.startswith("koi"):
                    domain_script = get_koika_tactic_pattern(
                        self.context.get("theorem_name", ""),
                        self.analysis
                    )
                    if domain_script and not self._has_critical_structural_issues(domain_script):
                        extra = [domain_script] * shortfall
                    else:
                        from specir.verification.proof.koika.template_gen import generate_coq_proof_variants_template
                        extra = generate_coq_proof_variants_template(
                            theorem_name=self.context.get("theorem_name", ""),
                            theorem_statement="",
                            num_variants=shortfall,
                            analysis=self.analysis,
                        )
                        extra = [s for s in extra if not self._has_critical_structural_issues(s)]
                else:
                    from specir.verification.proof.acl2.template_gen import generate_acl2_proof_variants_template
                    extra = generate_acl2_proof_variants_template(
                        theorem_name=self.context.get("theorem_name", ""),
                        theorem_statement=self.context.get("theorem_statement", ""),
                        num_variants=shortfall,
                        analysis=self.analysis,
                    )
                    extra = [s for s in extra if not self._has_critical_structural_issues(s)]
                variants_per_parent[parent_idx].extend(extra)
            while len(variants_per_parent[parent_idx]) < raw[parent_idx]:
                variants_per_parent[parent_idx].append(parent.script)

        children: List[PERFNode] = []
        for parent_idx, parent in enumerate(frontier):
            for script in variants_per_parent[parent_idx]:
                h = self._normalize_and_hash(script)
                if h in self._seen_script_hashes:
                    continue
                self._seen_script_hashes.add(h)
                child = PERFNode(script=script, parent=parent, depth=depth)
                children.append(child)

        if self._force_strategy_switch:
            self._force_strategy_switch = False
            self._force_strategy_hint = None

        return children

    def _filter_children(self, children: List[PERFNode]) -> List[PERFNode]:
        """Apply structural pre-filter before verification."""
        filtered = []
        for child in children:
            if self._has_critical_structural_issues(child.script):
                continue
            filtered.append(child)
        return filtered

    def _format_error_sig_for_avoid(self, sig: str) -> str:
        """Convert an error signature into a prompt avoidance rule."""
        if "focused, but cannot be unfocused" in sig or "Wrong bullet" in sig:
            return "Use only explicit braces { } for subgoals; do NOT use bullets (-, +, *)."
        if "Nat.mod_add" in sig or "deprecated" in sig:
            return "Do NOT use Nat.mod_add or other deprecated Nat.mod_* lemmas."
        if "Not a discriminable equality" in sig or "discriminate" in sig:
            return "Do NOT use discriminate on boolean equalities; use inversion or destruct."
        return f"Avoid this error: {sig[:100]}"

    def _build_prompts_for_parent(
        self, parent: PERFNode, depth: int, num_variants: int,
        strategy_hint_override: Optional[str] = None,
        temperature_override: Optional[float] = None,
        bypass_cache: bool = False,
        available_lemmas: Optional[List[str]] = None,
        mandatory_avoid: Optional[List[str]] = None,
        positive_example: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        prompts = []
        n = num_variants
        theorem_name = self.context.get("theorem_name", "unknown")
        theorem_stmt = self.context.get("theorem_statement", "")
        err = None
        if parent.verification_result and not parent.verification_result.get("success"):
            err = parent.verification_result.get("error", "")
            if self._is_opaque_tool_error(err):
                err = None

        inject_repair = self._unify_repair and err is not None
        normal_n = n - 1 if inject_repair else n
        if normal_n < 1 and n > 0:
            normal_n = 1
            inject_repair = False

        diversity_tags = _DEFAULT_DIVERSITY_TAGS
        tags_to_use = [diversity_tags[i % len(diversity_tags)] for i in range(normal_n)]
        default_strategy = strategy_hint_override or None

        mc_trace_info = None
        if self.config.mc_guided_prompt_enabled:
            mc_trace_info = self.context.get("mc_trace_info")

        if self.backend.startswith("koi"):
            for i in range(normal_n):
                hint = default_strategy if default_strategy else tags_to_use[i]
                error_with_loc = self._augment_error_with_location(err) if err else err
                prompt = build_coq_proof_prompt(
                    theorem_name=theorem_name,
                    theorem_statement=theorem_stmt,
                    context=self.coq_context_str,
                    tactic_hints=None,
                    assumptions=None,
                    previous_attempts=(
                        [{"script": parent.script, "error": error_with_loc}] if err else None
                    ),
                    structural_hints=self._build_structural_hints(),
                    strategy_hint=hint,
                    available_lemmas=available_lemmas,
                    mandatory_avoid=mandatory_avoid,
                    positive_example=positive_example,
                    failure_prompt_snippet=None,  # already injected in mandatory_avoid
                    mc_trace_info=mc_trace_info,
                )
                prompts.append({"prompt": prompt, "is_repair": False, "tag": hint})
        else:
            from specir.verification.proof.acl2.proof_gen import build_acl2_proof_prompt
            for i in range(normal_n):
                hint = default_strategy if default_strategy else tags_to_use[i]
                error_with_loc = self._augment_error_with_location(err) if err else err
                prompt = build_acl2_proof_prompt(
                    theorem_name=theorem_name,
                    theorem_statement=theorem_stmt,
                    context=self.coq_context_str,
                    hint_classes=None,
                    assumptions=None,
                    previous_attempts=(
                        [{"script": parent.script, "error": error_with_loc}] if err else None
                    ),
                    strategy_hint=hint,
                )
                prompts.append({"prompt": prompt, "is_repair": False, "tag": hint})

        if inject_repair:
            if self.backend.startswith("koi"):
                error_with_loc = self._augment_error_with_location(err) if err else err
                repair_prompt = build_coq_proof_prompt(
                    theorem_name=theorem_name,
                    theorem_statement=theorem_stmt,
                    context=self.coq_context_str,
                    tactic_hints=None,
                    assumptions=None,
                    previous_attempts=[{"script": parent.script, "error": error_with_loc}],
                    structural_hints=self._build_structural_hints(),
                    strategy_hint="repair the previous failed attempt",
                    available_lemmas=available_lemmas,
                    mandatory_avoid=mandatory_avoid,
                    positive_example=positive_example,
                    mc_trace_info=mc_trace_info,
                )
            else:
                from specir.verification.proof.acl2.proof_gen import build_acl2_proof_prompt
                error_with_loc = self._augment_error_with_location(err) if err else err
                repair_prompt = build_acl2_proof_prompt(
                    theorem_name=theorem_name,
                    theorem_statement=theorem_stmt,
                    context=self.coq_context_str,
                    hint_classes=None,
                    assumptions=None,
                    previous_attempts=[{"script": parent.script, "error": error_with_loc}],
                    strategy_hint="repair the previous failed attempt",
                )
            prompts.append({"prompt": repair_prompt, "is_repair": True, "tag": "repair"})

        return prompts

    def _get_mandatory_avoid(self) -> Optional[List[str]]:
        avoid = []
        if self._failure_signatures:
            if any("Unable to unify" in sig for sig in self._failure_signatures):
                avoid.append("apply IHHreach without destruct")
            if any("false = true" in sig for sig in self._failure_signatures):
                avoid.append("use reflexivity on hypotheses like 'false = true' – use discriminate instead")
            if any("No primitive equality found" in sig for sig in self._failure_signatures):
                avoid.append("use discriminate on non‑Boolean equalities")
            if any("Found no subterm matching" in sig for sig in self._failure_signatures):
                avoid.append("rewrite with an induction hypothesis that does not match the goal")
            if any("Not a discriminable equality" in sig for sig in self._failure_signatures):
                avoid.append("use discriminate on boolean equalities like `(op_reg s =? 0) = true`; use `inversion` or `rewrite Nat.eqb_eq` instead")
        return avoid if avoid else None

    def _get_initial_script(self) -> Optional[str]:
        if "initial_script" in self.context:
            logger.debug("Using initial_script from context.")
            return self.context["initial_script"]

        # Try cached proof first if available.
        cached = self._get_cached_initial_script()
        if cached:
            return cached

        if self.backend.startswith("koi"):
            coq_file = self.context.get("coq_file_path")
            theorem_name = self.context.get("theorem_name")
            if coq_file and theorem_name and self.analysis is not None and self.analysis.has_nested_ite:
                num_branches = 4 if self.analysis.max_ite_depth >= 3 else 2
                destruct_chain = build_destruct_pattern("op_reg s'", num_branches)
                skeleton = (
                    "Proof.\n"
                    "  intros s inputs Hreach.\n"
                    "  induction Hreach as [| s' s'' inputs' Hreach' IH Hstep].\n"
                    "  { simpl. intros Hvalid. discriminate Hvalid. }\n"
                    "  { inversion Hstep; subst; clear Hstep; simpl.\n"
                    f"    {destruct_chain}\n"
                    "    all: try (simpl; reflexivity); try (apply IH; auto).\n"
                    "  }\n"
                    "Qed."
                )
                logger.debug("Built pre‑skeleton from destruct pattern for initial script.")
                return skeleton

            if coq_file and Path(coq_file).exists():
                logger.debug("Using placeholder from Coq file as initial script.")
                return self._extract_coq_placeholder(Path(coq_file))
        elif self.backend == "acl2":
            acl2_file = self.context.get("acl2_file_path")
            if acl2_file and Path(acl2_file).exists():
                logger.debug("Using ACL2 placeholder as initial script.")
                return self._extract_acl2_placeholder(Path(acl2_file))
        return None

    def _extract_coq_placeholder(self, coq_file: Path) -> Optional[str]:
        content = coq_file.read_text()
        theorem_name = self.context.get("theorem_name")
        if theorem_name:
            pattern1 = re.compile(
                rf"(Theorem\s+{re.escape(theorem_name)}.*?)(?:Proof\..*?)Admitted\.", re.DOTALL
            )
        else:
            pattern1 = re.compile(r"(Theorem\s+\w+.*?)(?:Proof\..*?)Admitted\.", re.DOTALL)
        match = pattern1.search(content)
        if match:
            return match.group(0).strip()
        if theorem_name:
            pattern2 = re.compile(
                rf"(Theorem\s+{re.escape(theorem_name)}\s+.*?)Admitted\.", re.DOTALL
            )
        else:
            pattern2 = re.compile(r"(Theorem\s+\w+\s+.*?)Admitted\.", re.DOTALL)
        match2 = pattern2.search(content)
        if match2:
            return match2.group(0).strip()
        return None

    def _extract_acl2_placeholder(self, acl2_file: Path) -> Optional[str]:
        content = acl2_file.read_text()
        theorem_name = self.context.get("theorem_name")
        if not theorem_name:
            pattern = re.compile(r"(defthm\s+\w+.*?\)?)", re.DOTALL)
            match = pattern.search(content)
            return match.group(0).strip() if match else None
        pattern = re.compile(rf"(defthm\s+{re.escape(theorem_name)}.*?\)?)", re.DOTALL)
        match = pattern.search(content)
        return match.group(0).strip() if match else None

    def _validate_initial_script(self, script: str) -> bool:
        if self.backend.startswith("koi"):
            return self._validate_coq_script(script)
        return True

    def _validate_coq_script(self, script: str) -> bool:
        coq_file = self.context.get("coq_file_path")
        if not coq_file or not Path(coq_file).exists():
            return False
        theorem_name = self.context.get("theorem_name")
        if not theorem_name:
            return False

        workspace = self.context.get("workspace")
        if workspace is None:
            workspace = Path(coq_file).parent
        else:
            workspace = Path(workspace)
        workspace = workspace.resolve()

        project_file = workspace / "_CoqProject"
        if not project_file.exists():
            project_file.write_text(f'-R "{workspace}" Test\n')

        cmd = [self._coqc_path, "-R", str(workspace), "Test", str(coq_file)]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
                cwd=str(workspace),
            )
            if result.returncode == 0:
                return True
            else:
                logger.error("coqc validation failed: %s", result.stderr[:500])
                return False
        except Exception as e:
            logger.error("coqc validation exception: %s", e)
            return False

    def _extract_script_from_response(self, response: str, is_repair: bool = False) -> Optional[str]:
        if self.backend.startswith("koi"):
            from specir.verification.proof.koika.proof_gen import extract_proof_script
            return extract_proof_script(response)
        else:
            from specir.verification.proof.acl2.proof_gen import extract_acl2_proof
            return extract_acl2_proof(response)

    @staticmethod
    def _normalize_script(script: str) -> str:
        s = re.sub(r'\(\*.*?\*\)', '', script, flags=re.DOTALL)
        s = re.sub(r';[^\n]*', '', s)
        s = re.sub(r'\s+', ' ', s).strip()
        return s

    def _normalize_and_hash(self, script: str) -> str:
        normalized = self._normalize_script(script)
        return hashlib.sha256(normalized.encode('utf-8')).hexdigest()

    def _register_script_hash(self, script: str) -> None:
        self._seen_script_hashes.add(self._normalize_and_hash(script))

    def _effective_temperature(self, depth: int) -> float:
        base = self.config.generation_temperature
        if self.config.temperature_decay <= 0:
            return base
        decayed = base * (self.config.temperature_decay ** (depth - 1))
        return max(decayed, self.config.temperature_min)

    def _build_structural_hints(self) -> Optional[str]:
        if not self.analysis or not self.analysis.has_nested_ite:
            return None
        hints = []
        if self.analysis.num_step_constructors == 1 and self.analysis.max_ite_depth >= 3:
            hints.append(
                "The step constructor contains a deeply nested if-then-else chain "
                f"(depth {self.analysis.max_ite_depth}). "
                "Consider using 'destruct' on the condition variables to split into cases."
            )
        if self.analysis.suggests_lemma_introduction:
            hints.append(
                "Duplicated subexpressions detected: "
                + "; ".join(self.analysis.duplicated_subexpressions)
                + ". A helper lemma could simplify the proof."
            )
        return "\n".join(hints) if hints else None

    def _verify_children(self, children: List[PERFNode]) -> List[PERFNode]:
        if not children:
            return children
        evaluator = (
            self._evaluate_koika_node
            if self.backend.startswith("koi")
            else self._evaluate_acl2_node
        )

        def safe_evaluator(node):
            result = evaluator(node)
            if isinstance(result, dict) and self._is_tool_error(result):
                self._tool_failure_count += 1
                if self._tool_failure_count >= self._MAX_TOOL_FAILURES:
                    fallback_result = self._evaluate_with_coqc(node)
                    if fallback_result.get("success"):
                        self._tool_failure_count = 0
                        return fallback_result
                    else:
                        raise ToolFailureError(
                            "Both rocq-mcp and coqc failed. Possible environment issue."
                        )
            else:
                self._tool_failure_count = 0
            return result

        results = []
        any_success_llm = False
        for child in children:
            try:
                res = safe_evaluator(child)
            except ToolFailureError as e:
                logger.error(str(e))
                raise
            child.verification_result = res
            results.append(child)
            if res.get("success"):
                any_success_llm = True

        if any_success_llm:
            self._consecutive_llm_failures = 0
        else:
            self._consecutive_llm_failures += 1
        return results

    def _evaluate_node(self, node: PERFNode) -> Dict[str, Any]:
        return (
            self._evaluate_koika_node(node)
            if self.backend.startswith("koi")
            else self._evaluate_acl2_node(node)
        )

    def _evaluate_koika_node(self, node: PERFNode) -> Dict[str, Any]:
        coq_file = self.context.get("coq_file_path")
        if not coq_file or not Path(coq_file).exists():
            return {"success": False, "error": "Coq file not available"}

        theorem_name = self.context.get("theorem_name")
        if not theorem_name:
            return {"success": False, "error": "Theorem name not available"}

        original_workspace = self.context.get("workspace")
        if original_workspace is None:
            original_workspace = Path(coq_file).parent
        original_workspace = Path(original_workspace).resolve()
        original_workspace.mkdir(parents=True, exist_ok=True)

        temp_dir = tempfile.mkdtemp(prefix="perf_eval_", dir=str(original_workspace))
        temp_dir_path = Path(temp_dir)
        temp_coq_file = temp_dir_path / Path(coq_file).name

        try:
            shutil.copy2(coq_file, temp_coq_file)
            for compiled in Path(coq_file).parent.glob(f"{Path(coq_file).stem}.*"):
                if compiled.suffix in (".vo", ".glob", ".vos", ".vok"):
                    shutil.copy2(compiled, temp_dir_path / compiled.name)

            (temp_dir_path / "_CoqProject").write_text(
                f'-R "{temp_dir_path.resolve()}" Test\n'
            )

            original_content = temp_coq_file.read_text()
            if node.script.strip().startswith("Theorem "):
                pattern = re.compile(
                    rf"(Theorem\s+{re.escape(theorem_name)}.*?)Admitted\.", re.DOTALL
                )
                match = pattern.search(original_content)
                if match:
                    proof_match = re.search(r"Proof\..*?(Qed\.|Admitted\.)", node.script, re.DOTALL)
                    proof_script = proof_match.group(0) if proof_match else node.script
                    full_block = match.group(0)
                    new_block = full_block.replace("Admitted.", proof_script)
                    new_content = original_content.replace(full_block, new_block, 1)
                else:
                    new_content = node.script
            else:
                pattern = re.compile(
                    rf"(Theorem\s+{re.escape(theorem_name)}.*?)Admitted\.", re.DOTALL
                )
                match = pattern.search(original_content)
                if not match:
                    return {"success": False, "error": "Theorem not found in Coq file"}
                full_block = match.group(0)
                new_block = full_block.replace("Admitted.", node.script)
                new_content = original_content.replace(full_block, new_block, 1)
            temp_coq_file.write_text(new_content)

            from specir.backends.rocq_client import RocqClient

            rocq = RocqClient(
                rocq_mcp_path=self.context.get("rocq_path", "rocq-mcp"),
                timeout=self.config.timeout_per_node,
                cwd=temp_dir_path,
                server_args=["--workspace", str(temp_dir_path)],
            )
            rocq_error = None
            try:
                rocq.start()
                compile_result = rocq.compile_file(temp_coq_file, workspace=temp_dir_path)
                err = rocq._extract_error_from_response(compile_result)
                if err:
                    rocq_error = f"Compilation failed: {err}"
                else:
                    verify_result = rocq.verify(temp_coq_file, theorem_name, workspace=temp_dir_path)
                    err = rocq._extract_error_from_response(verify_result)
                    if err:
                        rocq_error = f"Verification failed: {err}"
                    else:
                        return {"success": True, "goals_remaining": 0}
            except Exception as e:
                rocq_error = str(e)
            finally:
                rocq.stop()

            if rocq_error and self._is_opaque_tool_error(rocq_error):
                logger.info("rocq_verify returned opaque error; trying direct coqc check.")
                try:
                    result = subprocess.run(
                        [self._coqc_path, "-R", str(temp_dir_path), "Test", str(temp_coq_file)],
                        capture_output=True,
                        text=True,
                        timeout=self.config.coqc_timeout,
                        cwd=str(temp_dir_path),
                    )
                    if result.returncode == 0:
                        content = temp_coq_file.read_text()
                        if self._theorem_is_closed(content, theorem_name):
                            return {"success": True, "goals_remaining": 0, "verified_by": "coqc_fallback"}
                        else:
                            return {"success": False, "error": "coqc compiled but theorem not closed"}
                    else:
                        rocq_error = f"coqc fallback failed: {result.stderr[:1000]}"
                        logger.debug("coqc fallback also failed: %s", result.stderr[:200])
                except Exception as e:
                    logger.debug("coqc fallback exception: %s", e)

            return {"success": False, "error": rocq_error}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def _theorem_is_closed(self, content: str, theorem_name: str) -> bool:
        pattern = re.compile(
            rf"Theorem\s+{re.escape(theorem_name)}\s+.*?Qed\.", re.DOTALL
        )
        match = pattern.search(content)
        if not match:
            return False
        block = match.group(0)
        return "Admitted." not in block

    @staticmethod
    def _is_opaque_tool_error(error_msg: str) -> bool:
        msg = error_msg.lower()
        return (
            "unknown error" in msg
            or "not found in the current environment" in msg
            or "theorem_not_found" in msg
        )

    def _evaluate_with_coqc(self, node: PERFNode) -> Dict[str, Any]:
        coq_file = self.context.get("coq_file_path")
        theorem_name = self.context.get("theorem_name")
        if not coq_file or not theorem_name:
            return {"success": False, "error": "Missing coq_file or theorem_name"}

        workspace = Path(coq_file).parent
        temp_dir = tempfile.mkdtemp(prefix="perf_coqc_eval_", dir=str(workspace))
        temp_dir_path = Path(temp_dir)
        temp_coq_file = temp_dir_path / Path(coq_file).name

        try:
            shutil.copy2(coq_file, temp_coq_file)
            (temp_dir_path / "_CoqProject").write_text(
                f'-R "{temp_dir_path.resolve()}" Test\n'
            )

            original_content = temp_coq_file.read_text()
            if node.script.strip().startswith("Theorem "):
                pattern = re.compile(
                    rf"(Theorem\s+{re.escape(theorem_name)}.*?)Admitted\.", re.DOTALL
                )
                match = pattern.search(original_content)
                if match:
                    proof_match = re.search(r"Proof\..*?(Qed\.|Admitted\.)", node.script, re.DOTALL)
                    proof_script = proof_match.group(0) if proof_match else node.script
                    full_block = match.group(0)
                    new_block = full_block.replace("Admitted.", proof_script)
                    new_content = original_content.replace(full_block, new_block, 1)
                else:
                    new_content = node.script
            else:
                pattern = re.compile(
                    rf"(Theorem\s+{re.escape(theorem_name)}.*?)Admitted\.", re.DOTALL
                )
                match = pattern.search(original_content)
                if not match:
                    return {"success": False, "error": "Theorem not found"}
                full_block = match.group(0)
                new_block = full_block.replace("Admitted.", node.script)
                new_content = original_content.replace(full_block, new_block, 1)
            temp_coq_file.write_text(new_content)

            cmd = [self._coqc_path, "-R", str(temp_dir_path), "Test", str(temp_coq_file)]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.config.coqc_timeout,
                cwd=str(temp_dir_path),
            )
            if result.returncode == 0:
                return {"success": True, "goals_remaining": 0, "verified_by": "coqc"}
            else:
                return {"success": False, "error": result.stderr[:2000]}
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "coqc verification timed out"}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def _evaluate_acl2_node(self, node: PERFNode) -> Dict[str, Any]:
        acl2_file = self.context.get("acl2_file_path")
        if not acl2_file or not Path(acl2_file).exists():
            return {"success": False, "error": "ACL2 file not available"}

        theorem_name = self.context.get("theorem_name")
        if not theorem_name:
            return {"success": False, "error": "Theorem name not available"}

        from specir.backends.acl2_client import ACL2Client
        acl2 = ACL2Client(
            mcp_path=self.context.get("acl2_mcp_path", "acl2-mcp"),
            timeout=self.config.timeout_per_node,
            init_commands=[],
        )
        try:
            acl2.start()
            acl2.load_file(Path(acl2_file))
            result = acl2.send(node.script)
            if "Error" in result or "ACL2 Error" in result:
                return {"success": False, "error": result}
            if "Q.E.D." in result or "Proof succeeded" in result:
                return {"success": True}
            verify_result = acl2.send(f"(verify {theorem_name})")
            if "Q.E.D." in verify_result or "Proof succeeded" in verify_result:
                return {"success": True}
            return {"success": False, "error": "The theorem was not proven"}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            acl2.stop()

    def _repair_children(self, children: List[PERFNode], depth: int) -> List[PERFNode]:
        repaired = []
        repair_attempts_by_error: Dict[str, int] = {}
        max_repairs_total = max(1, self.config.beam_size * self.config.branches_per_node)

        for child in children:
            if child.verification_result is None:
                repaired.append(child)
                continue
            if child.verification_result.get("success"):
                repaired.append(child)
                continue

            err = child.verification_result.get("error", "")
            if not err or self._is_opaque_tool_error(err):
                repaired.append(child)
                continue

            err_key = self._error_signature(err)
            attempt_count = repair_attempts_by_error.get(err_key, 0)
            if attempt_count >= self.config.perf_light_repair_attempts:
                repaired.append(child)
                continue

            if len(repaired) >= max_repairs_total:
                repaired.append(child)
                continue

            if attempt_count == 0:
                strategy_hint = None
            else:
                strategy_hint = "Use `destruct` on the opcode condition BEFORE applying the induction hypothesis. " \
                                "Do not apply IH directly; first split the goal into cases using `destruct (op_reg s' =? 0) eqn:Hop0`, " \
                                "then `destruct (op_reg s' =? 1) eqn:Hop1`, etc."

            logger.info(
                "Attempting light repair on a child (error: %s, attempt %d/%d)",
                err[:200],
                attempt_count + 1,
                self.config.perf_light_repair_attempts,
            )
            new_script = self._repair_child_script(
                child,
                err,
                strategy_hint_override=strategy_hint,
            )
            repair_attempts_by_error[err_key] = attempt_count + 1

            if new_script is not None and new_script != child.script:
                if self._has_critical_structural_issues(new_script):
                    logger.debug("Rejected repaired script due to critical structural issues.")
                    repaired.append(child)
                else:
                    repaired_node = PERFNode(script=new_script, parent=child.parent, depth=child.depth)
                    repaired_node.verification_result = self._evaluate_node(repaired_node)
                    self.stats.record_verifier_call()
                    repaired.append(repaired_node)
            else:
                repaired.append(child)
        return repaired

    def _propagate_child_errors(self, parents: List[PERFNode], children: List[PERFNode]) -> None:
        parent_to_children: Dict[int, List[PERFNode]] = {}
        for child in children:
            if child.parent is not None:
                parent_to_children.setdefault(id(child.parent), []).append(child)

        for parent in parents:
            child_list = parent_to_children.get(id(parent), [])
            if not child_list:
                continue

            errors = []
            for child in child_list:
                if child.verification_result and not child.verification_result.get("success"):
                    err = child.verification_result.get("error", "")
                    if err and not self._is_opaque_tool_error(err):
                        errors.append(err)
            if not errors:
                continue
            best_err = self._select_best_error(errors)
            if parent.verification_result is None:
                parent.verification_result = {}
            parent.verification_result["error"] = best_err
            parent.verification_result["error_from_child"] = True

    def _select_best_error(self, errors: List[str]) -> str:
        for err in errors:
            if "unable to unify" in err.lower():
                return err
        for err in errors:
            if "found no subterm matching" in err.lower():
                return err
        return min(errors, key=len)

    def _clean_coq_error(self, error_msg: str) -> str:
        lines = error_msg.splitlines()
        cleaned = []
        for line in lines:
            if "Warning:" in line or "deprecated" in line.lower():
                continue
            cleaned.append(line)
        return "\n".join(cleaned)

    def _error_signature(self, error_msg: str) -> str:
        lines = error_msg.splitlines()
        for line in lines:
            line = line.strip()
            if line and not line.startswith("Warning:") and "deprecated" not in line.lower():
                return line
        return error_msg[:200]

    def _repair_child_script(
        self,
        node: PERFNode,
        error_msg: str,
        strategy_hint_override: Optional[str] = None,
    ) -> Optional[str]:
        theorem_name = self.context.get("theorem_name", "unknown")
        theorem_stmt = self.context.get("theorem_statement", "")

        if strategy_hint_override is not None:
            repair_hint = strategy_hint_override
        else:
            repair_hint = self._classify_error_for_repair(error_msg)

        error_with_loc = self._augment_error_with_location(error_msg)

        mc_trace_info = None
        if self.config.mc_guided_prompt_enabled:
            mc_trace_info = self.context.get("mc_trace_info")

        prompt = build_coq_proof_prompt(
            theorem_name=theorem_name,
            theorem_statement=theorem_stmt,
            context=self.coq_context_str,
            tactic_hints=None,
            assumptions=None,
            previous_attempts=[{"script": node.script, "error": error_with_loc}],
            structural_hints=self._build_structural_hints(),
            available_lemmas=self.available_lemmas,
            mandatory_avoid=self._get_mandatory_avoid(),
            positive_example=self._get_positive_example(),
            strategy_hint=repair_hint,
            mc_trace_info=mc_trace_info,
        )

        response = self._safe_llm_generate(prompt)
        if response:
            new_script = self._extract_script_from_response(response)
            if new_script and "Proof." in new_script and ("Qed." in new_script or "Admitted." in new_script):
                new_script = sanitize_coq_script(new_script)
                new_script = auto_patch(new_script, error_msg)
                return new_script
        return None

    def _classify_error_for_repair(self, error_msg: str) -> str:
        err_lower = error_msg.lower()
        if "unable to unify" in err_lower:
            if "true" in err_lower and "false" in err_lower:
                return (
                    "Your proof attempted to use `reflexivity` on a contradictory equality "
                    "(e.g., `false = true`).  Use `discriminate` or `inversion` on that hypothesis instead."
                )
            if "valid s" in err_lower or "IHHreach" in err_lower:
                return (
                    "The induction hypothesis could not be applied directly.  Destruct the opcode "
                    "condition (`op_reg s =? ...`) before applying IH, and `simpl` the state projections."
                )
        if "no such hypothesis" in err_lower and "hstep" in err_lower:
            return (
                "The script references `Hstep`, but it was not named during induction.  Use "
                "`induction Hreach as [| s' s'' inputs' Hreach' IH Hstep]` to name it explicitly."
            )
        if "found no subterm matching" in err_lower:
            return (
                "A rewrite failed because the term does not appear in the goal.  Check that the "
                "rewritten expression matches exactly; use `simpl` before rewriting if needed."
            )
        if "not a discriminable equality" in err_lower:
            return (
                "`discriminate` was used on a non‑constructor equality, likely a boolean equality "
                "such as `(op_reg s =? 0) = true`.  Use `inversion` or `rewrite Nat.eqb_eq` instead."
            )
        if "wrong bullet" in err_lower:
            return (
                "The script contains a bullet (`-`, `+`, `*`) that is not properly nested.  Remove "
                "standalone bullets or restructure the proof with explicit `{` and `}`."
            )
        return "Please fix the error described above."

    @staticmethod
    def _is_tool_error(result: Dict[str, Any]) -> bool:
        error = result.get("error", "")
        if not error:
            return False
        error_lower = error.lower()
        return (
            "unknown error" in error_lower
            or "not found in the current environment" in error_lower
            or "theorem_not_found" in error_lower
            or "the reference" in error_lower
        )

    def _count_compiler_errors(self, error_msg: str) -> int:
        if not error_msg:
            return 0
        lines = error_msg.splitlines()
        count = 0
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("Error:") or "Error:" in stripped:
                count += 1
            elif stripped.startswith("Warning:") and "deprecated" in stripped.lower():
                continue
        return max(1, count) if count > 0 else 0

    def _augment_error_with_location(self, error_msg: str) -> str:
        if not error_msg:
            return error_msg
        match = re.search(r'File ".*?", line (\d+), characters (\d+)-(\d+):', error_msg)
        if match:
            line = match.group(1)
            char = match.group(2)
            return f"Location: line {line}, char {char}\n{error_msg}"
        return error_msg

    def _adjust_scores_for_quality(self, scored_children: List[PERFNode]):
        primary_dim = self.config.primary_dimension
        for node in scored_children:
            if not node.score:
                continue
            struct_count = len(getattr(node, "structural_issues", []))
            if struct_count > 0:
                penalty = min(0.6, struct_count * 0.3)
                node.score[primary_dim] = max(0.0, node.score.get(primary_dim, 0.0) - penalty)
            err_count = getattr(node, "error_count", 0)
            if err_count > 0:
                penalty = min(0.8, err_count * 0.2)
                node.score[primary_dim] = max(0.0, node.score.get(primary_dim, 0.0) - penalty)

    def _any_progress(self, frontier: List[PERFNode]) -> bool:
        for node in frontier:
            if node.score and node.score.get(self.config.primary_dimension, 0.0) > 0.0:
                return True
        return False

    def _diagnose_failure(self) -> Dict[str, Any]:
        if self.analysis and self.analysis.suggests_rule_splitting:
            return {
                "recommendation": "rule_splitting",
                "reason": (
                    "The design has a monolithic rule with deeply nested conditionals. "
                    "Enable rule splitting or add the 'split' attribute to the execute rule."
                ),
            }
        return {"recommendation": "continue", "reason": "No clear failure pattern yet."}

    def get_stats(self) -> PERFStats:
        return self.stats

    def get_best_candidate(self) -> Optional[str]:
        return self.best_candidate_script

    def _estimate_subgoal_reduction(self) -> float:
        if not hasattr(self, "_last_children_goals"):
            return 0.0
        goals = self._last_children_goals
        if not goals:
            return 0.0
        min_goals = min(goals)
        return max(0.0, 1.0 - min_goals / 10.0)

    def _estimate_beam_diversity(self, frontier: List[PERFNode]) -> float:
        if not frontier:
            return 0.0
        scripts = [n.script for n in frontier]
        if len(scripts) < 2:
            return 0.0
        distances = []
        token_sets = [self.scorer._tokenize(s) for s in scripts]
        for i in range(len(token_sets)):
            for j in range(i+1, len(token_sets)):
                sim = self.scorer._jaccard_similarity(token_sets[i], token_sets[j])
                distances.append(1.0 - sim)
        return sum(distances) / len(distances) if distances else 0.0


def _share_prefix(a: str, b: str, min_len: int = 5) -> bool:
    i = 0
    for ca, cb in zip(a, b):
        if ca == cb:
            i += 1
        else:
            break
    return i >= min_len
