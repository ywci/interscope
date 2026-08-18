# src/specir/verification/perf/perf_scorer.py
#
# PERF scoring with LLM reflection and Pareto optimality.
# Extended with diversity scoring for backtracking, reflection quality
# assessment utilities, and configurable reflection weights.

import json
import random
import re
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Set, Union
from dataclasses import dataclass, field
from specir.backends.llm_client import LLMClient
from specir.verification.perf.perf_config import PERFConfig, VALID_DIMENSIONS
from specir.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class PERFNode:
    """A node in the PERF search tree."""
    script: str
    parent: Optional["PERFNode"] = None
    depth: int = 0
    score: Optional[Dict[str, float]] = None
    verification_result: Optional[Dict[str, Any]] = None
    children: List["PERFNode"] = field(default_factory=list)


class PERFScorer:
    """
    Scores PERF nodes using LLM reflection and Pareto optimality.

    The scoring process:
      1. For each node, compute a base score from the verification result.
      2. If all failing nodes share the same error signature, skip the
         tournament and assign uniform scores.
      3. Otherwise, run a tournament: each node is compared against K others.
      4. Win counts are accumulated per dimension and normalised to scores.
      5. Scores are attached to each node.

    Diversity scoring for backtracking:
      - add_diversity_scores() computes novelty and structural_difference
        dimensions based on the content of proof scripts.

    Reflection quality utilities:
      - compute_reflection_quality() provides a lightweight metric combining
        primary improvement, error shift, subgoal reduction, and diversity.
      - error_signature_shift() returns 1.0 if the dominant error changed.

    Persistent cache:
      - If *cache_file* is provided to the constructor, comparison results
        are loaded from/saved to a JSON file.  The cache key is a
        SHA‑256 hash of the two normalised scripts, ensuring stable keys
        across processes.

    Novelty:
      - `set_expanded_scripts()` lets the traversal supply a list of
        scripts that have already been expanded.  `novelty` is then
        computed as 1 minus the maximum Jaccard similarity between the
        candidate and any expanded script.

    Error‑history penalty:
      - `apply_error_history_penalty()` reduces all dimension scores of a
        node if its script+error signature is similar to a previously
        recorded failure.
    """

    def __init__(
        self,
        config: PERFConfig,
        llm_client: LLMClient,
        max_workers: int = 1,
        cache_file: Optional[str] = None,
    ):
        self.config = config
        self.llm = llm_client
        self.max_workers = max_workers
        self.dimensions = config.get_effective_dimensions()
        self.tournament_size = config.scoring_tournament_size
        self.trace_weight = config.trace_alignment_weight

        # In‑memory comparison cache (fast path).  The disk cache is
        # used only when cache_file is provided.
        self._comparison_cache: Dict[Tuple[str, str], Dict[str, int]] = {}
        self._cache_file: Optional[Path] = Path(cache_file) if cache_file else None
        if self._cache_file is not None:
            self._load_persistent_cache()

        # Default reflection weights; can be overridden by PERFConfig if
        # future versions add configurable weights.
        self.reflection_weights = {
            "primary_delta": 0.4,
            "error_shift": 0.2,
            "subgoal_reduction": 0.25,
            "diversity": 0.15,
        }

        # Scripts that have already been expanded (for novelty scoring).
        self._expanded_scripts: List[str] = []

        # Error history reference (optional).  If set, apply_error_history_penalty
        # can be used.
        self._error_history: Any = None

    def _load_persistent_cache(self) -> None:
        """Load comparison cache from disk if it exists."""
        if self._cache_file is None or not self._cache_file.exists():
            return
        try:
            with open(self._cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            # The disk cache stores keys as "hash1|hash2" and values as
            # preference dicts with integer values.
            for key_str, val in data.items():
                parts = key_str.split("|")
                if len(parts) == 2:
                    self._comparison_cache[(parts[0], parts[1])] = {
                        k: int(v) for k, v in val.items()
                    }
            logger.info(
                "Loaded %d comparison entries from persistent cache %s",
                len(self._comparison_cache), self._cache_file,
            )
        except Exception as e:
            logger.warning("Failed to load persistent comparison cache: %s", e)

    def _save_persistent_cache(self) -> None:
        """Save comparison cache to disk."""
        if self._cache_file is None:
            return
        try:
            data = {}
            for (a, b), pref in self._comparison_cache.items():
                key = f"{a}|{b}"
                data[key] = {k: int(v) for k, v in pref.items()}
            # Write atomically.
            tmp = self._cache_file.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            tmp.replace(self._cache_file)
            logger.debug("Saved %d comparison entries to %s", len(data), self._cache_file)
        except Exception as e:
            logger.warning("Failed to save persistent comparison cache: %s", e)

    @staticmethod
    def _normalize_for_cache(script: str) -> str:
        """Normalize a script for stable hashing."""
        s = re.sub(r'\(\*.*?\*\)', '', script, flags=re.DOTALL)
        s = re.sub(r';[^\n]*', '', s)
        s = re.sub(r'\s+', ' ', s).strip()
        return s

    def _make_cache_key(self, script_a: str, script_b: str) -> Tuple[str, str]:
        """Return a stable cache key for two scripts."""
        norm_a = self._normalize_for_cache(script_a)
        norm_b = self._normalize_for_cache(script_b)
        # Sort the two hashes so that (a,b) and (b,a) map to the same key.
        h1 = hashlib.sha256(norm_a.encode('utf-8')).hexdigest()
        h2 = hashlib.sha256(norm_b.encode('utf-8')).hexdigest()
        return tuple(sorted((h1, h2)))

    def set_expanded_scripts(self, scripts: List[str]) -> None:
        """Set the list of previously expanded scripts used for novelty scoring."""
        self._expanded_scripts = list(scripts)

    def set_error_history(self, error_history: Any) -> None:
        """Attach an ErrorHistory instance for penalty computation."""
        self._error_history = error_history

    def apply_error_history_penalty(
        self,
        nodes: List[PERFNode],
        penalty_factor: float = 0.25,
    ) -> None:
        """
        Reduce scores of nodes whose script+error signature matches a known
        failure in the attached ErrorHistory.  The penalty is applied to all
        dimensions present in the node's score.
        """
        if self._error_history is None or not nodes:
            return

        for node in nodes:
            if node.score is None:
                continue
            err = ""
            if node.verification_result and not node.verification_result.get("success"):
                err = node.verification_result.get("error", "")
            if not err:
                continue
            try:
                if self._error_history.has_similar_failure(node.script, err):
                    for dim in list(node.score.keys()):
                        node.score[dim] = max(0.0, node.score[dim] - penalty_factor)
            except Exception as e:
                logger.debug("Error-history penalty lookup failed: %s", e)

    def score_nodes(
        self,
        nodes: List[PERFNode],
        obligation: Dict[str, Any],
        context: Dict[str, Any],
    ) -> List[PERFNode]:
        if not nodes:
            return nodes

        if len(nodes) == 1:
            nodes[0].score = {dim: 1.0 for dim in self.dimensions}
            return nodes

        # 1. Compute base scores from verification results
        base_scores = self._compute_base_scores(nodes)

        # 2. Check if all non‑successful nodes have the same error signature
        non_success = [n for n in nodes if not (n.verification_result and n.verification_result.get("success"))]
        all_same_error = False
        if non_success and len(non_success) >= len(nodes) // 2:
            signatures = set()
            for node in non_success:
                err = node.verification_result.get("error", "") if node.verification_result else ""
                signatures.add(self._error_signature(err))
            if len(signatures) == 1:
                all_same_error = True

        # 3. Run tournament comparisons (or skip if all same error)
        if all_same_error:
            logger.info("All failing nodes have the same error; skipping tournament and using base scores only.")
            for node in nodes:
                node.score = {dim: base_scores.get(id(node), {}).get(dim, 0.5) for dim in self.dimensions}
            return nodes

        wins = {id(node): {dim: 0.0 for dim in self.dimensions} for node in nodes}
        comparisons = {id(node): 0 for node in nodes}
        comparison_pairs = self._sample_tournament_pairs(nodes)

        logger.debug(
            "Running %d pairwise comparisons for %d nodes (tournament size=%d)",
            len(comparison_pairs), len(nodes), self.tournament_size
        )

        if self.max_workers > 1 and len(comparison_pairs) > 1:
            results = self._parallel_compare(nodes, comparison_pairs, obligation, context)
        else:
            results = self._sequential_compare(nodes, comparison_pairs, obligation, context)

        for (id_a, id_b), pref in results:
            comparisons[id_a] += 1
            comparisons[id_b] += 1
            for dim in self.dimensions:
                val = pref.get(dim, 0)
                if val > 0:
                    wins[id_a][dim] += 1.0
                elif val < 0:
                    wins[id_b][dim] += 1.0
                else:
                    wins[id_a][dim] += 0.5
                    wins[id_b][dim] += 0.5

        # 4. Normalise scores
        for node in nodes:
            node_id = id(node)
            total = comparisons[node_id] or 1
            tool_weight = 0.4
            refl_weight = 0.6
            node.score = {}
            for dim in self.dimensions:
                base = base_scores.get(node_id, {}).get(dim, 0.5)
                refl = wins[node_id][dim] / total
                node.score[dim] = max(0.0, min(1.0, tool_weight * base + refl_weight * refl))

        # Apply error-history penalty if an ErrorHistory is attached.
        self.apply_error_history_penalty(nodes)

        return nodes

    def _compute_base_scores(self, nodes: List[PERFNode]) -> Dict[int, Dict[str, float]]:
        base = {}
        for node in nodes:
            res = node.verification_result or {}
            success = res.get("success", False)
            error_msg = res.get("error", "")
            goals_remaining = res.get("goals_remaining")

            if success:
                subgoal_score = 1.0
            elif goals_remaining is not None:
                subgoal_score = max(0.0, 1.0 - goals_remaining / 10.0)
            else:
                subgoal_score = self._subgoal_score_from_error(error_msg)

            # trace_alignment: only non‑zero if explicit trace handling detected
            trace_score = 0.0
            if res.get("handled_trace", False) or self._script_handles_trace(node.script):
                trace_score = 1.0

            # syntactic_purity: shorter scripts preferred
            script_len = len(node.script)
            if script_len < 500:
                purity = 1.0
            elif script_len < 2000:
                purity = 0.7
            else:
                purity = 0.3

            # Structural progress bonus (induction, inversion)
            if self._has_structural_progress(node.script):
                subgoal_score = min(1.0, subgoal_score + 0.2)

            node_id = id(node)
            base[node_id] = {
                "subgoal_reduction": subgoal_score,
                "trace_alignment": trace_score,
                "syntactic_purity": purity,
            }

            # Novelty score: 1 - max similarity to expanded scripts.
            if "novelty" in self.dimensions:
                novelty = self._compute_novelty(node.script)
                base[node_id]["novelty"] = novelty

            for dim in self.dimensions:
                if dim not in base[node_id]:
                    base[node_id][dim] = 0.5

        return base

    def _compute_novelty(self, script: str) -> float:
        """Compute novelty as 1 minus maximum Jaccard similarity to expanded scripts."""
        if not self._expanded_scripts:
            return 1.0
        tokens = self._tokenize(script)
        max_sim = 0.0
        for prev in self._expanded_scripts:
            prev_tokens = self._tokenize(prev)
            sim = self._jaccard_similarity(tokens, prev_tokens)
            if sim > max_sim:
                max_sim = sim
        return 1.0 - max_sim

    def _subgoal_score_from_error(self, error_msg: str) -> float:
        """Map common Coq errors to a subgoal‑reduction score."""
        msg = error_msg.lower()
        if "unable to unify" in msg:
            return 0.5
        if "found no subterm matching" in msg:
            return 0.4
        if "not a discriminable equality" in msg or "discriminate" in msg:
            return 0.3
        if "theorem not closed" in msg or "still admitted" in msg:
            return 0.2
        if "compilation failed" in msg:
            return 0.1
        return 0.0

    def _has_structural_progress(self, script: str) -> bool:
        """Check if the script performs induction on reachable and case‑split on step."""
        return bool(
            re.search(r"\binduction\b.*\breachable\b", script) and
            re.search(r"\binversion\b.*\bstep\b", script)
        )

    def _script_handles_trace(self, script: str) -> bool:
        keywords = ["trace", "counterexample", "MC", "model_check", "vcd", "simulation"]
        script_lower = script.lower()
        return any(kw in script_lower for kw in keywords)

    @staticmethod
    def _error_signature(error_msg: str) -> str:
        lines = error_msg.splitlines()
        for line in lines:
            line = line.strip()
            if line and not line.startswith("Warning:") and "deprecated" not in line.lower():
                return line
        return error_msg[:200]

    def _sample_tournament_pairs(self, nodes: List[PERFNode]) -> List[Tuple[int, int]]:
        n = len(nodes)
        if n <= 1:
            return []
        k = min(self.tournament_size, n - 1)
        pairs = []
        indices = list(range(n))
        random.shuffle(indices)
        for i in range(n):
            opponents = indices[:i] + indices[i+1:]
            if len(opponents) >= k:
                selected = random.sample(opponents, k)
            else:
                selected = opponents
            for j in selected:
                pair = tuple(sorted((i, j)))
                if pair not in pairs:
                    pairs.append(pair)
        return pairs

    def _sequential_compare(
        self,
        nodes: List[PERFNode],
        pairs: List[Tuple[int, int]],
        obligation: Dict[str, Any],
        context: Dict[str, Any],
    ) -> List[Tuple[Tuple[int, int], Dict[str, int]]]:
        results = []
        for (i, j) in pairs:
            pref = self._compare_nodes(nodes[i], nodes[j], obligation, context)
            results.append(((id(nodes[i]), id(nodes[j])), pref))
        return results

    def _parallel_compare(
        self,
        nodes: List[PERFNode],
        pairs: List[Tuple[int, int]],
        obligation: Dict[str, Any],
        context: Dict[str, Any],
    ) -> List[Tuple[Tuple[int, int], Dict[str, int]]]:
        import concurrent.futures

        def _compare_wrapper(idx1, idx2):
            return (id(nodes[idx1]), id(nodes[idx2])), self._compare_nodes(
                nodes[idx1], nodes[idx2], obligation, context
            )

        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(_compare_wrapper, i, j): (i, j)
                for (i, j) in pairs
            }
            for future in concurrent.futures.as_completed(futures):
                try:
                    pair, pref = future.result()
                    results.append((pair, pref))
                except Exception as e:
                    logger.warning("Comparison failed: %s", e)
                    pair = futures[future]
                    results.append(((id(nodes[pair[0]]), id(nodes[pair[1]])), {dim: 0 for dim in self.dimensions}))
        return results

    def _compare_nodes(
        self,
        node_a: PERFNode,
        node_b: PERFNode,
        obligation: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, int]:
        # Use stable cache key based on script content.
        key = self._make_cache_key(node_a.script, node_b.script)
        if key in self._comparison_cache:
            return self._comparison_cache[key]

        prompt = self._build_comparison_prompt(node_a, node_b, obligation, context)
        try:
            response = self.llm.generate(prompt)
            pref = self._parse_preference_response(response)
        except Exception as e:
            logger.warning("LLM comparison failed: %s", e)
            pref = {dim: 0 for dim in self.dimensions}

        self._comparison_cache[key] = pref
        # Save cache to disk if enabled.
        if self._cache_file is not None:
            self._save_persistent_cache()
        return pref

    def _build_comparison_prompt(
        self,
        node_a: PERFNode,
        node_b: PERFNode,
        obligation: Dict[str, Any],
        context: Dict[str, Any],
    ) -> str:
        theorem_name = obligation.get("property", "unknown")
        theorem_stmt = context.get("theorem_statement", "unknown")

        res_a = node_a.verification_result or {}
        res_b = node_b.verification_result or {}

        success_a = "SUCCESS" if res_a.get("success") else "FAILED"
        success_b = "SUCCESS" if res_b.get("success") else "FAILED"
        goals_a = res_a.get("goals_remaining", "N/A")
        goals_b = res_b.get("goals_remaining", "N/A")
        error_a = res_a.get("error", "No error")[:200]
        error_b = res_b.get("error", "No error")[:200]

        trace_info = ""
        if context.get("mc_trace"):
            trace_info = (
                "A model checking counterexample trace is available. "
                "Evaluate which proof better addresses the failing trace.\n"
                f"Trace snippet: {context['mc_trace'][:500]}"
            )

        coq_env = context.get("coq_environment", "")
        if coq_env:
            env_section = (
                "\n**Coq/ACL2 definitions and lemmas available (use exact names):**\n"
                f"```\n{coq_env[:3000]}\n```\n"
            )
        else:
            env_section = ""

        dims_str = ", ".join(self.dimensions)

        prompt = f"""
You are an expert in formal verification and proof engineering.

We are trying to prove the following theorem:
**{theorem_name}**: `{theorem_stmt}`

Two candidate proof scripts have been proposed.

---

**Candidate A:**
```
{node_a.script[:1500]}
```

**Verification result:** {success_a}
**Remaining subgoals:** {goals_a}
**Error (if any):** {error_a}

---

**Candidate B:**
```
{node_b.script[:1500]}
```

**Verification result:** {success_b}
**Remaining subgoals:** {goals_b}
**Error (if any):** {error_b}

---

{trace_info}
{env_section}
Please compare these two candidates across the following dimensions:
{chr(10).join(f'- {dim}' for dim in self.dimensions)}

For each dimension, decide which candidate is better, or if they are tied.
Return your answer as a JSON object with keys equal to the dimension names,
and values one of: 1 (Candidate A is better), -1 (Candidate B is better), or 0 (tie).

Example output:
```json
{{
  "subgoal_reduction": 1,
  "trace_alignment": -1,
  "syntactic_purity": 0
}}
```

Return ONLY the JSON object, without any extra text.
"""
        return prompt.strip()

    def _parse_preference_response(self, response: str) -> Dict[str, int]:
        cleaned = response.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning("Failed to parse LLM response as JSON: %s", cleaned[:200])
            return self._fallback_parse(cleaned)

        pref = {}
        for dim in self.dimensions:
            val = data.get(dim)
            if val in (1, -1, 0):
                pref[dim] = int(val)
            else:
                if isinstance(val, (int, float)):
                    pref[dim] = 1 if val > 0 else (-1 if val < 0 else 0)
                else:
                    pref[dim] = 0
        return pref

    def _fallback_parse(self, text: str) -> Dict[str, int]:
        pref = {dim: 0 for dim in self.dimensions}
        for dim in self.dimensions:
            if dim in text:
                segment = text[text.index(dim):]
                if "better" in segment[:50]:
                    pref[dim] = 1
                elif "worse" in segment[:50]:
                    pref[dim] = -1
                else:
                    numbers = re.findall(r'[-+]?\d+', segment[:50])
                    if numbers:
                        val = int(numbers[0])
                        pref[dim] = 1 if val > 0 else (-1 if val < 0 else 0)
        return pref

    def add_diversity_scores(
        self,
        nodes: List[PERFNode],
        previous_beam_scripts: List[str],
        diversity_dimensions: Optional[List[str]] = None,
    ) -> None:
        """
        Compute novelty and structural_difference scores for the given nodes
        relative to the previously selected beam scripts, and attach them to
        each node's score dictionary.

        Args:
            nodes: List of nodes to score.
            previous_beam_scripts: List of proof scripts from the previous
                beam (used as reference for diversity).
            diversity_dimensions: Which dimensions to compute.
                Defaults to ["novelty", "structural_difference"] if None.
        """
        if diversity_dimensions is None:
            diversity_dimensions = ["novelty", "structural_difference"]

        if not nodes:
            return

        ref_token_sets = [self._tokenize(s) for s in previous_beam_scripts]

        for node in nodes:
            if node.score is None:
                node.score = {}

            tokens = self._tokenize(node.script)

            if "novelty" in diversity_dimensions:
                similarities = [self._jaccard_similarity(tokens, ref) for ref in ref_token_sets]
                max_sim = max(similarities) if similarities else 0.0
                node.score["novelty"] = 1.0 - max_sim

            if "structural_difference" in diversity_dimensions:
                node.score["structural_difference"] = self._structural_difference_score(
                    node.script, previous_beam_scripts
                )

    @staticmethod
    def _tokenize(script: str) -> Set[str]:
        script = re.sub(r'\(\*.*?\*\)', '', script, flags=re.DOTALL)
        script = re.sub(r'"[^"]*"', '', script)
        tokens = re.findall(r'\b\w+\b', script.lower())
        stopwords = {'the', 'a', 'an', 'is', 'of', 'in', 'to', 'for', 'and', 'or', 'not', 'with', 'by', 'on', 'as'}
        return {t for t in tokens if t not in stopwords}

    @staticmethod
    def _jaccard_similarity(set_a: Set[str], set_b: Set[str]) -> float:
        if not set_a and not set_b:
            return 1.0
        intersection = len(set_a & set_b)
        union = len(set_a | set_b)
        return intersection / union if union > 0 else 0.0

    def _structural_difference_score(
        self,
        script: str,
        previous_beam_scripts: List[str],
    ) -> float:
        indicators = [
            r'\binduction\b',
            r'\bintros\b',
            r'\binversion\b',
            r'\bdestruct\b',
            r'\bcase\b',
            r'\bexpand\b',
            r'\bauto\b',
            r'\beauto\b',
            r'\blia\b',
            r'\bnia\b',
            r'\brewrite\b',
            r'\bsimpl\b',
            r'\breflexivity\b',
            r'\bdiscriminate\b',
            r'\bcongruence\b',
            r'\bapply\b',
            r'\bassert\b',
            r'\brewrite\s+.*\s+in\b',
            r'\bdestruct\s+.*\s+eqn\b',
        ]

        script_vector = [1 if re.search(ind, script) else 0 for ind in indicators]

        distances = []
        for prev_script in previous_beam_scripts:
            prev_vector = [1 if re.search(ind, prev_script) else 0 for ind in indicators]
            diff = sum(a != b for a, b in zip(script_vector, prev_vector))
            distances.append(diff / len(indicators))

        avg_distance = sum(distances) / len(distances) if distances else 1.0
        return max(0.0, min(1.0, avg_distance))

    def add_experience_penalty(
        self,
        nodes: List[PERFNode],
        failure_signatures: List[str],
        penalty_dimensions: Optional[List[str]] = None,
        penalty_factor: float = 0.2,
    ) -> None:
        if not failure_signatures or not nodes:
            return

        if penalty_dimensions is None:
            all_dims = set()
            for node in nodes:
                if node.score:
                    all_dims.update(node.score.keys())
            penalty_dimensions = list(all_dims)

        for node in nodes:
            if node.verification_result is None:
                continue
            err = node.verification_result.get("error", "")
            if not err:
                continue
            node_sig = self._error_signature(err)
            for fail_sig in failure_signatures:
                if node_sig == fail_sig:
                    if node.score is None:
                        node.score = {}
                    for dim in penalty_dimensions:
                        if dim in node.score:
                            node.score[dim] = max(0.0, node.score[dim] - penalty_factor)
                    break

    @staticmethod
    def error_signature_shift(old_sig: Optional[str], new_sig: Optional[str]) -> float:
        """Return 1.0 if the error signature changed meaningfully, else 0.0."""
        if old_sig is None and new_sig is None:
            return 0.0
        if old_sig is None or new_sig is None:
            return 1.0
        return 1.0 if old_sig.strip().lower() != new_sig.strip().lower() else 0.0

    def compute_reflection_quality(
        self,
        pre_best_primary: float,
        post_best_primary: float,
        pre_error_sig: Optional[str],
        post_error_sig: Optional[str],
        subgoal_reduction: float = 0.0,
        diversity_score: float = 0.0,
        weights: Optional[Dict[str, float]] = None,
    ) -> float:
        """
        Compute a more informative reflection quality score.

        The score combines four weighted components:
          - primary_delta: relative improvement in the best primary dimension.
          - error_shift: whether the dominant error signature changed.
          - subgoal_reduction: normalized reduction in subgoals (0..1).
          - diversity: diversity of the new beam vs the old beam (0..1).

        All sub-scores are clamped to [0,1].  Weights default to those
        stored in `self.reflection_weights`, but can be overridden per call.
        """
        if weights is None:
            weights = self.reflection_weights

        # Primary score improvement (relative)
        if post_best_primary > pre_best_primary:
            primary_delta = min(
                1.0,
                (post_best_primary - pre_best_primary) / max(0.01, pre_best_primary)
            )
        else:
            primary_delta = 0.0

        # Error signature shift (0 or 1)
        error_shift = self.error_signature_shift(pre_error_sig, post_error_sig)

        # Subgoal reduction is already expected to be between 0 and 1.
        subgoal_reduction = max(0.0, min(1.0, subgoal_reduction))
        diversity_score = max(0.0, min(1.0, diversity_score))

        weighted_sum = (
            weights.get("primary_delta", 0.4) * primary_delta +
            weights.get("error_shift", 0.2) * error_shift +
            weights.get("subgoal_reduction", 0.25) * subgoal_reduction +
            weights.get("diversity", 0.15) * diversity_score
        )
        total_weight = sum(weights.values())
        if total_weight <= 0:
            return 0.0

        quality = weighted_sum / total_weight
        return max(0.0, min(1.0, quality))


def compute_pareto_front(
    nodes: List[PERFNode],
    dimensions: Optional[List[str]] = None,
    primary_dim: Optional[str] = None,
) -> List[PERFNode]:
    """
    Compute the Pareto front (non‑dominated set) among the given nodes.

    Args:
        nodes: List of nodes with scores.
        dimensions: List of dimension names to consider (default: all
            dimensions found in the first scored node).
        primary_dim: Optional dimension for tie‑breaking (not used in
            dominance check, only for sorting the front).

    Returns:
        List of Pareto‑optimal nodes.
    """
    if not nodes:
        return []

    if dimensions is None:
        sample = next((n for n in nodes if n.score), None)
        if sample is None:
            return nodes
        dimensions = list(sample.score.keys())

    scored = [n for n in nodes if n.score is not None]
    if not scored:
        return nodes

    pareto = []
    for i, node_i in enumerate(scored):
        dominated = False
        for j, node_j in enumerate(scored):
            if i == j:
                continue
            dom = True
            strict = False
            for dim in dimensions:
                vi = node_i.score.get(dim, 0.0)
                vj = node_j.score.get(dim, 0.0)
                if vj < vi:
                    dom = False
                    break
                if vj > vi:
                    strict = True
            if dom and strict:
                dominated = True
                break
        if not dominated:
            pareto.append(node_i)

    if primary_dim and primary_dim in dimensions:
        pareto.sort(key=lambda n: n.score.get(primary_dim, 0.0), reverse=True)

    return pareto


def select_beam(
    pareto_front: List[PERFNode],
    beam_size: int,
    primary_dim: str,
) -> List[PERFNode]:
    """
    Select a beam of size at most *beam_size* from the Pareto front,
    sorted by *primary_dim*.

    Args:
        pareto_front: List of Pareto‑optimal nodes.
        beam_size: Maximum number of nodes to select.
        primary_dim: Dimension used for sorting.

    Returns:
        List of selected nodes.
    """
    if not pareto_front:
        return []

    if len(pareto_front) <= beam_size:
        return pareto_front

    sorted_front = sorted(
        pareto_front,
        key=lambda n: n.score.get(primary_dim, 0.0) if n.score else 0.0,
        reverse=True
    )
    return sorted_front[:beam_size]
