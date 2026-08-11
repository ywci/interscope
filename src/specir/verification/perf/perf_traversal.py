# src/specir/verification/perf/perf_traversal.py
#
# Core PERF traversal engine – effective version.
#
# Implements beam search with Pareto pruning, reflective feedback,
# early‑stopping, initial‑script validation, template generator fallback,
# MC‑lemma injection hooks, tool‑health monitoring with fallback to coqc,
# structural analysis of obligations, fast‑failure diagnostics,
# smart light repair of failed children, cross‑depth error feedback,
# and **MC lemma injection on search stagnation**.

import copy
import time
import tempfile
import os
import shutil
import re
import subprocess
import hashlib
from typing import List, Dict, Any, Optional, Tuple, Set
from pathlib import Path

from specir.backends.llm_client import LLMClient
from specir.verification.perf.perf_config import PERFConfig
from specir.verification.perf.perf_scorer import (
    PERFScorer, PERFNode, compute_pareto_front, select_beam,
)
from specir.verification.perf.perf_stats import PERFStats
from specir.verification.perf.perf_parallel import PERFParallelEvaluator
from specir.verification.perf.perf_evidence import PERFEvidence
from specir.verification.perf.perf_analyzer import PERFAnalyzer, ObligationAnalysis
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
    """Core PERF traversal engine. (see module docstring)"""

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

        self.scorer = PERFScorer(config, llm_client, max_workers=config.max_workers)
        self.parallel_evaluator = PERFParallelEvaluator(
            max_workers=config.max_workers,
            timeout_per_node=config.timeout_per_node,
            config=context.get("config", {})
        )
        self.evidence = PERFEvidence()
        self.stats = PERFStats()
        self._child_cache: Dict[Tuple[int, int], List[str]] = {}

        self._tool_failure_count = 0
        self._MAX_TOOL_FAILURES = config.max_tool_failures_before_fallback
        self._coqc_path = shutil.which("coqc") or "coqc"

        self.analysis: Optional[ObligationAnalysis] = None
        self._analyzer = PERFAnalyzer()

        self._mc_injection_done = False
        self.config_dict = context.get("config", {})

        self._seen_script_hashes: Set[str] = set()

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

    def traverse(self) -> Tuple[Optional[str], PERFStats]:
        logger.info("Starting PERF traversal (backend=%s)", self.backend)
        self.stats.start()

        initial_script = self._get_initial_script()
        if not initial_script:
            logger.error("No initial script available for PERF")
            self.stats.finish()
            return None, self.stats

        if not self._validate_initial_script(initial_script):
            logger.warning("Initial script failed compilation; PERF cannot proceed.")
            self.stats.finish()
            return None, self.stats

        self._register_script_hash(initial_script)

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
                return initial_script, self.stats

        frontier = [root]

        for depth in range(self.config.depth_limit):
            current_depth = depth + 1
            logger.info(
                "PERF depth %d/%d: frontier size = %d",
                current_depth,
                self.config.depth_limit,
                len(frontier),
            )
            self.stats.record_depth(current_depth)

            # Generate children (with weighted budget, diversity tags, deduplication, and optionally unified repair + parallel gen)
            children = self._generate_children(frontier, current_depth)
            self.stats.record_node(len(children))
            if not children:
                logger.warning("No children generated at depth %d", current_depth)
                break

            # Verify children with tool‑health monitoring
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

            # Smart light repair on failed children before scoring.
            #     If unified repair is active, we already included repair‑aware
            #     variants, but some children may still fail unexpectedly.
            #     We still run the light repair pass for those cases.
            children = self._repair_children(children, current_depth)

            # Cross‑depth feedback: update parent errors from child failures
            self._propagate_child_errors(frontier, children)

            # Check for success (including repaired scripts)
            for node in children:
                if node.verification_result and node.verification_result.get("success"):
                    logger.info("PERF found a successful proof at depth %d (after repair)!", current_depth)
                    self.stats.record_success(current_depth)
                    self.stats.record_beam_size(len(frontier))
                    self.stats.finish()
                    self.evidence.register_proof(
                        property_name=self.obligation.get("property", "unknown"),
                        proof_script=node.script,
                        backend=self.backend,
                        stats=self.stats,
                    )
                    return node.script, self.stats

            # Score children
            logger.info("Scoring %d children...", len(children))
            scored_children = self.scorer.score_nodes(
                children, self.obligation, self.context
            )

            # Pareto front & beam selection
            pareto_front = compute_pareto_front(
                scored_children,
                dimensions=self.config.dimensions,
                primary_dim=self.config.primary_dimension,
            )
            pruned_count = len(scored_children) - len(pareto_front)
            self.stats.record_pareto_pruned(pruned_count)
            logger.info("Pareto front: %d nodes (pruned %d)", len(pareto_front), pruned_count)

            frontier = select_beam(
                pareto_front,
                self.config.beam_size,
                self.config.primary_dimension,
            )
            self.stats.record_beam_size(len(frontier))
            logger.info("Beam selected: %d nodes", len(frontier))

            self.stats.record_depth_stats(
                current_depth, len(children), len(frontier), pruned_count
            )

            # Progress tracking & early stopping
            best_primary = 0.0
            for node in frontier:
                if node.score:
                    val = node.score.get(self.config.primary_dimension, 0.0)
                    if val > best_primary:
                        best_primary = val
            self.stats.record_progress(best_primary, self.config.early_stop_min_improvement)

            if self.config.early_stop_patience > 0:
                if self.stats.consecutive_no_improvement >= self.config.early_stop_patience:
                    logger.warning(
                        "Early stopping: no Pareto improvement for %d consecutive depths.",
                        self.stats.consecutive_no_improvement,
                    )
                    break

            # Fast‑failure diagnostics after depth 2 with no success
            if current_depth == 2 and not self._any_progress(frontier):
                diagnosis = self._diagnose_failure()
                logger.error("PERF diagnosis: %s", diagnosis.get("reason"))
                if diagnosis.get("recommendation") == "give_up":
                    self.stats.finish()
                    return None, self.stats

            # MC lemma injection if stuck
            if self.stats.consecutive_no_improvement >= max(1, self.config.early_stop_patience // 2):
                logger.info("Search seems stuck – consider MC lemma injection (not yet implemented).")
                if self.backend.startswith("koi") and not self._mc_injection_done:
                    mc_enabled = self.config_dict.get("provers", {}).get("koika", {}).get("use_mc_lemmas", False)
                    if mc_enabled:
                        logger.info("Attempting MC lemma injection to unstick the search.")
                        try:
                            from specir.verification.proof.koika.prover import KoikaProver
                            prover = KoikaProver(config=self.config_dict)
                            prover.spec_module = self.context.get("spec_module")
                            coq_file = Path(self.context["coq_file_path"])
                            theorem_name = self.context["theorem_name"]
                            prover.inject_mc_lemmas(coq_file, theorem_name)
                            self._mc_injection_done = True
                            logger.info("MC lemmas injected; restarting PERF traversal.")
                            return self.traverse()
                        except Exception as e:
                            logger.error("MC lemma injection failed: %s", e)

        logger.warning("PERF exhausted after %d depths", self.config.depth_limit)
        self.stats.finish()
        return None, self.stats

    def _propagate_child_errors(self, parents: List[PERFNode], children: List[PERFNode]) -> None:
        parent_to_children: Dict[int, List[PERFNode]] = {}
        for child in children:
            if child.parent is not None:
                parent_id = id(child.parent)
                parent_to_children.setdefault(parent_id, []).append(child)

        for parent in parents:
            child_list = parent_to_children.get(id(parent), [])
            if not child_list:
                continue

            errors = []
            for child in child_list:
                if child.verification_result and not child.verification_result.get("success"):
                    err = child.verification_result.get("error", "")
                    if err and not self._is_opaque_tool_error(err):
                        errors.append(self._clean_coq_error(err))

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
        return "\n".join(cleaned)[:2000]

    def _get_initial_script(self) -> Optional[str]:
        if "initial_script" in self.context:
            return self.context["initial_script"]

        if self.backend.startswith("koi"):
            coq_file = self.context.get("coq_file_path")
            if coq_file and Path(coq_file).exists():
                return self._extract_coq_placeholder(Path(coq_file))
        elif self.backend == "acl2":
            acl2_file = self.context.get("acl2_file_path")
            if acl2_file and Path(acl2_file).exists():
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
                logger.info("coqc validation of original file succeeded.")
                return True
            else:
                logger.error("coqc validation failed: %s", result.stderr[:500])
                return False
        except Exception as e:
            logger.error("coqc validation exception: %s", e)
            return False

    def _generate_children(
        self, frontier: List[PERFNode], depth: int
    ) -> List[PERFNode]:
        total_budget = self.config.beam_size * self.config.branches_per_node
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

        all_prompts: List[Dict[str, Any]] = []  # {prompt, parent_idx, variant_idx, is_repair, tag}
        for parent_idx, (parent, num_variants) in enumerate(zip(frontier, raw)):
            prompts_info = self._build_prompts_for_parent(
                parent, depth, num_variants
            )
            for info in prompts_info:
                info["parent_idx"] = parent_idx
                all_prompts.append(info)

        if self._parallel_gen and all_prompts:
            logger.info("Generating %d variants in batch mode", len(all_prompts))
            raw_responses = self.llm.generate_batch(
                prompts=[p["prompt"] for p in all_prompts],
                system=None,
                max_workers=min(self.config.max_workers, len(all_prompts)),
                max_tokens=None
            )
        else:
            raw_responses = []
            for p in all_prompts:
                raw_responses.append(self.llm.generate(p["prompt"]))

        variants_per_parent: Dict[int, List[str]] = {i: [] for i in range(len(frontier))}
        for idx, resp in enumerate(raw_responses):
            meta = all_prompts[idx]
            parent_idx = meta["parent_idx"]
            script = self._extract_script_from_response(
                resp, meta.get("is_repair", False)
            )
            if script:
                variants_per_parent[parent_idx].append(script)

        for parent_idx, parent in enumerate(frontier):
            existing = variants_per_parent[parent_idx]
            needed = raw[parent_idx]
            shortfall = needed - len(existing)
            if shortfall > 0:
                # fill with templates (using ObligationAnalysis)
                if self.backend.startswith("koi"):
                    from specir.verification.proof.koika.template_gen import (
                        generate_coq_proof_variants_template,
                    )
                    extra = generate_coq_proof_variants_template(
                        theorem_name=self.context.get("theorem_name", ""),
                        theorem_statement="",
                        num_variants=shortfall,
                        analysis=self.analysis,
                    )
                else:
                    from specir.verification.proof.acl2.template_gen import (
                        generate_acl2_proof_variants_template,
                    )
                    extra = generate_acl2_proof_variants_template(
                        theorem_name=self.context.get("theorem_name", ""),
                        theorem_statement=self.context.get("theorem_statement", ""),
                        num_variants=shortfall,
                        analysis=self.analysis,
                    )
                variants_per_parent[parent_idx].extend(extra)
            # still short → pad with parent script
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

        logger.debug(
            "Generated %d children across %d parents (budget %d)",
            len(children), len(frontier), total_budget
        )
        return children

    def _build_prompts_for_parent(
        self, parent: PERFNode, depth: int, num_variants: int
    ) -> List[Dict[str, Any]]:
        """
        Return a list of {prompt, is_repair, tag} dicts for a single parent.
        Includes a dedicated repair prompt if unified repair is enabled and
        the parent has a known error.
        """
        prompts = []
        n = num_variants
        temp = self._effective_temperature(depth)
        theorem_name = self.context.get("theorem_name", "unknown")
        theorem_stmt = self.context.get("theorem_statement", "")
        err = None
        if parent.verification_result and not parent.verification_result.get("success"):
            err = parent.verification_result.get("error", "")
            if self._is_opaque_tool_error(err):
                err = None

        # determine if we should inject a repair prompt
        inject_repair = self._unify_repair and err is not None

        # adjust number of normal variants if we add a repair one
        normal_n = n - 1 if inject_repair else n
        if normal_n < 1 and n > 0:
            normal_n = 1
            inject_repair = False  # not enough room for repair

        diversity_tags = _DEFAULT_DIVERSITY_TAGS
        tags_to_use = [diversity_tags[i % len(diversity_tags)] for i in range(normal_n)]

        # Build normal variant prompts
        if self.backend.startswith("koi"):
            from specir.verification.proof.koika.proof_gen import build_coq_proof_prompt
            for i in range(normal_n):
                prompt = build_coq_proof_prompt(
                    theorem_name=theorem_name,
                    theorem_statement=theorem_stmt,
                    context=self.coq_context_str,
                    tactic_hints=None,
                    assumptions=None,
                    previous_attempts=(
                        [{"script": parent.script, "error": err}] if err else None
                    ),
                    structural_hints=self._build_structural_hints(),
                    strategy_hint=tags_to_use[i],
                )
                prompts.append({"prompt": prompt, "is_repair": False, "tag": tags_to_use[i]})
        else:  # ACL2
            from specir.verification.proof.acl2.proof_gen import build_acl2_proof_prompt
            for i in range(normal_n):
                prompt = build_acl2_proof_prompt(
                    theorem_name=theorem_name,
                    theorem_statement=theorem_stmt,
                    context=self.coq_context_str,
                    hint_classes=None,
                    assumptions=None,
                    previous_attempts=(
                        [{"script": parent.script, "error": err}] if err else None
                    ),
                    strategy_hint=tags_to_use[i],
                )
                prompts.append({"prompt": prompt, "is_repair": False, "tag": tags_to_use[i]})

        # Build repair prompt if applicable
        if inject_repair:
            if self.backend.startswith("koi"):
                from specir.verification.proof.koika.proof_gen import build_coq_proof_prompt
                repair_prompt = build_coq_proof_prompt(
                    theorem_name=theorem_name,
                    theorem_statement=theorem_stmt,
                    context=self.coq_context_str,
                    tactic_hints=None,
                    assumptions=None,
                    previous_attempts=[{"script": parent.script, "error": err}],
                    structural_hints=self._build_structural_hints(),
                    strategy_hint="repair the previous failed attempt",
                )
            else:
                from specir.verification.proof.acl2.proof_gen import build_acl2_proof_prompt
                repair_prompt = build_acl2_proof_prompt(
                    theorem_name=theorem_name,
                    theorem_statement=theorem_stmt,
                    context=self.coq_context_str,
                    hint_classes=None,
                    assumptions=None,
                    previous_attempts=[{"script": parent.script, "error": err}],
                    strategy_hint="repair the previous failed attempt",
                )
            prompts.append({"prompt": repair_prompt, "is_repair": True, "tag": "repair"})

        return prompts

    def _extract_script_from_response(self, response: str, is_repair: bool = False) -> Optional[str]:
        """Convert an LLM response into a proof script, using the appropriate extractor."""
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
                    logger.warning(
                        "Detected %d consecutive tool failures. Attempting coqc fallback.",
                        self._tool_failure_count,
                    )
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
        for child in children:
            try:
                res = safe_evaluator(child)
            except ToolFailureError as e:
                logger.error(str(e))
                raise
            child.verification_result = res
            results.append(child)
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
            (temp_dir_path / "_CoqProject").write_text(
                f'-R "{temp_dir_path.resolve()}" Test\n'
            )

            original_content = temp_coq_file.read_text()
            if node.script.strip().startswith("Theorem "):
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
        errors_seen: set = set()
        repairs_done = 0
        max_repairs = max(1, self.config.beam_size * self.config.branches_per_node // 2)

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
            if err_key in errors_seen:
                repaired.append(child)
                continue
            errors_seen.add(err_key)

            if repairs_done >= max_repairs:
                repaired.append(child)
                continue

            clean_err = self._clean_coq_error(err)
            logger.info("Attempting light repair on a child (error: %s)", clean_err[:200])
            new_script = self._repair_child_script(child, clean_err)
            repairs_done += 1

            if new_script is not None and new_script != child.script:
                repaired_node = PERFNode(script=new_script, parent=child.parent, depth=child.depth)
                repaired_node.verification_result = self._evaluate_node(repaired_node)
                self.stats.record_verifier_call()
                repaired.append(repaired_node)
            else:
                repaired.append(child)
        return repaired

    def _error_signature(self, error_msg: str) -> str:
        lines = error_msg.splitlines()
        for line in lines:
            line = line.strip()
            if line and not line.startswith("Warning:") and "deprecated" not in line.lower():
                return line
        return error_msg[:200]

    def _repair_child_script(self, node: PERFNode, error_msg: str) -> Optional[str]:
        theorem_name = self.context.get("theorem_name", "unknown")
        theorem_stmt = self.context.get("theorem_statement", "")
        from specir.verification.proof.koika.proof_gen import build_coq_proof_prompt, extract_proof_script
        prompt = build_coq_proof_prompt(
            theorem_name=theorem_name,
            theorem_statement=theorem_stmt,
            context=self.coq_context_str,
            tactic_hints=None,
            assumptions=None,
            previous_attempts=[{"script": node.script, "error": error_msg}],
            structural_hints=self._build_structural_hints(),
        )
        original_temp = self.llm.temperature
        self.llm.temperature = max(0.3, self.config.generation_temperature + 0.1)
        try:
            response = self.llm.generate(prompt)
            new_script = extract_proof_script(response)
            if new_script and "Proof." in new_script and ("Qed." in new_script or "Admitted." in new_script):
                return new_script
        except Exception as e:
            logger.warning("Repair LLM call failed: %s", e)
        finally:
            self.llm.temperature = original_temp
        return None

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
