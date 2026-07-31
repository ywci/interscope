# src/specir/verification/perf/perf_scorer.py
#
# PERF scoring with LLM reflection and Pareto optimality.
# Implements multi‑dimensional scoring via tournament‑style pairwise comparisons
# using a reflection LLM. The reflection model compares two proof scripts
# (candidate nodes) and returns a preference vector across the configured
# dimensions (e.g., subgoal_reduction, trace_alignment, syntactic_purity).
#
# The Pareto front is computed from the resulting scores, allowing the
# traversal to keep trade‑offs between conflicting objectives.

import json
import random
import re
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
      1. For each node, collect verification result (success/failure, subgoals).
      2. Run a tournament: each node is compared against K others.
      3. For each comparison, the LLM returns a preference vector.
      4. Win counts are accumulated per dimension and normalised to scores.
      5. Scores are attached to each node.
      6. Optionally, the Pareto front can be computed from the scores.
    """

    def __init__(
        self,
        config: PERFConfig,
        llm_client: LLMClient,
        max_workers: int = 1,
    ):
        """
        Args:
            config: PERF configuration (beam, dimensions, tournament size, etc.)
            llm_client: LLM client for reflection prompts.
            max_workers: If > 1, use parallel LLM calls for comparisons.
        """
        self.config = config
        self.llm = llm_client
        self.max_workers = max_workers
        self.dimensions = config.get_effective_dimensions()
        self.tournament_size = config.scoring_tournament_size
        self.trace_weight = config.trace_alignment_weight

        # Cache for comparison results to avoid re-computing the same pair
        self._comparison_cache: Dict[Tuple[str, str], Dict[str, int]] = {}

    def score_nodes(
        self,
        nodes: List[PERFNode],
        obligation: Dict[str, Any],
        context: Dict[str, Any],
    ) -> List[PERFNode]:
        """
        Score all nodes using tournament‑style pairwise LLM comparisons.

        Each node is compared against at most `tournament_size` other nodes.
        Win counts are accumulated per dimension and normalised to [0,1].

        Args:
            nodes: List of nodes to score.
            obligation: The proof obligation (for context in prompts).
            context: Additional context (spec, MC trace, Coq environment, etc.)

        Returns:
            The same list of nodes with `node.score` populated.
        """
        if not nodes:
            return nodes

        # If only one node, assign default scores (1.0 for all dims)
        if len(nodes) == 1:
            nodes[0].score = {dim: 1.0 for dim in self.dimensions}
            return nodes

        # 1. Compute base scores from verification results (tool feedback)
        base_scores = self._compute_base_scores(nodes)

        # 2. Run tournament comparisons
        wins = {id(node): {dim: 0.0 for dim in self.dimensions} for node in nodes}
        comparisons = {id(node): 0 for node in nodes}

        # Determine which nodes to compare (tournament sampling)
        comparison_pairs = self._sample_tournament_pairs(nodes)
        logger.debug(
            "Running %d pairwise comparisons for %d nodes (tournament size=%d)",
            len(comparison_pairs), len(nodes), self.tournament_size
        )

        # Perform comparisons (parallel if max_workers > 1)
        if self.max_workers > 1 and len(comparison_pairs) > 1:
            results = self._parallel_compare(nodes, comparison_pairs, obligation, context)
        else:
            results = self._sequential_compare(nodes, comparison_pairs, obligation, context)

        # Accumulate wins
        for (id_a, id_b), pref in results:
            comparisons[id_a] += 1
            comparisons[id_b] += 1
            for dim in self.dimensions:
                # +1 if a is better, -1 if b is better, 0 for tie
                val = pref.get(dim, 0)
                if val > 0:
                    wins[id_a][dim] += 1.0
                elif val < 0:
                    wins[id_b][dim] += 1.0
                else:
                    wins[id_a][dim] += 0.5
                    wins[id_b][dim] += 0.5

        # 3. Normalise scores
        for node in nodes:
            node_id = id(node)
            total = comparisons[node_id] or 1
            # Combine base scores (from tool) and tournament wins (from LLM)
            # Weight: 0.4 tool, 0.6 reflection (tunable)
            tool_weight = 0.4
            refl_weight = 0.6
            node.score = {}
            for dim in self.dimensions:
                base = base_scores.get(node_id, {}).get(dim, 0.5)
                refl = wins[node_id][dim] / total
                # Ensure score in [0,1]
                node.score[dim] = max(0.0, min(1.0, tool_weight * base + refl_weight * refl))

        return nodes

    def _compute_base_scores(self, nodes: List[PERFNode]) -> Dict[int, Dict[str, float]]:
        """
        Compute initial scores from tool verification results.

        This provides a grounding for the LLM reflection, reducing hallucination.

        Dimensions:
          - subgoal_reduction: 1.0 if proof succeeded, else 0.0 + (reduction in subgoals)
          - trace_alignment: 1.0 if the proof explicitly handles the MC trace, else 0.0
          - syntactic_purity: 1.0 for short, simple proofs; lower for complex/long scripts
        """
        base = {}
        for node in nodes:
            res = node.verification_result or {}
            success = res.get("success", False)
            goals_remaining = res.get("goals_remaining", None)

            # subgoal_reduction: if success, 1.0; else based on remaining goals
            if success:
                subgoal_score = 1.0
            else:
                if goals_remaining is not None:
                    # Assume max subgoals around 10; if >10, cap at 0.0
                    remaining = min(goals_remaining, 10)
                    subgoal_score = max(0.0, 1.0 - (remaining / 10.0))
                else:
                    subgoal_score = 0.0

            # trace_alignment: if verification result includes a handled_trace flag,
            # or if the proof script contains references to the trace
            trace_score = 0.0
            if res.get("handled_trace", False) or self._script_handles_trace(node.script):
                trace_score = 1.0

            # syntactic_purity: simple heuristic: shorter script is "purer"
            script_len = len(node.script)
            if script_len < 500:
                purity = 1.0
            elif script_len < 2000:
                purity = 0.7
            else:
                purity = 0.3

            node_id = id(node)
            base[node_id] = {
                "subgoal_reduction": subgoal_score,
                "trace_alignment": trace_score,
                "syntactic_purity": purity,
            }
            # Add any extra dimensions with default 0.5
            for dim in self.dimensions:
                if dim not in base[node_id]:
                    base[node_id][dim] = 0.5

        return base

    def _script_handles_trace(self, script: str) -> bool:
        """Heuristic: checks if a proof script mentions trace or counterexample."""
        keywords = ["trace", "counterexample", "MC", "model_check", "vcd", "simulation"]
        script_lower = script.lower()
        return any(kw in script_lower for kw in keywords)

    def _sample_tournament_pairs(self, nodes: List[PERFNode]) -> List[Tuple[int, int]]:
        """Sample tournament pairs so each node is compared to K others."""
        n = len(nodes)
        if n <= 1:
            return []
        k = min(self.tournament_size, n - 1)
        pairs = []
        # Shuffle to avoid bias
        indices = list(range(n))
        random.shuffle(indices)
        for i in range(n):
            # For each node, pick k distinct opponents (excluding itself)
            opponents = indices[:i] + indices[i+1:]
            if len(opponents) >= k:
                selected = random.sample(opponents, k)
            else:
                selected = opponents
            for j in selected:
                # Ensure each unordered pair is included only once
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
        """Sequential comparison (fallback)."""
        results = []
        for (i, j) in pairs:
            pref = self._compare_nodes(nodes[i], nodes[j], obligation, context)
            # Use node IDs, not indices
            results.append(((id(nodes[i]), id(nodes[j])), pref))
        return results

    def _parallel_compare(
        self,
        nodes: List[PERFNode],
        pairs: List[Tuple[int, int]],
        obligation: Dict[str, Any],
        context: Dict[str, Any],
    ) -> List[Tuple[Tuple[int, int], Dict[str, int]]]:
        """Parallel comparison using ThreadPoolExecutor."""
        import concurrent.futures

        def _compare_wrapper(idx1, idx2):
            # Return node IDs
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
                    # Fallback: neutral preference
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
        """
        Compare two nodes using the reflection LLM.

        Returns a dictionary mapping dimension name to:
          +1 if node_a is better,
          -1 if node_b is better,
           0 if tie.

        Uses a cache to avoid re-comparing identical pairs.
        """
        # Cache key: sorted script hashes
        key = tuple(sorted((hash(node_a.script), hash(node_b.script))))
        if key in self._comparison_cache:
            return self._comparison_cache[key]

        prompt = self._build_comparison_prompt(node_a, node_b, obligation, context)
        try:
            response = self.llm.generate(prompt)
            pref = self._parse_preference_response(response)
        except Exception as e:
            logger.warning("LLM comparison failed: %s", e)
            # Fallback: neutral
            pref = {dim: 0 for dim in self.dimensions}

        # Cache
        self._comparison_cache[key] = pref
        return pref

    def _build_comparison_prompt(
        self,
        node_a: PERFNode,
        node_b: PERFNode,
        obligation: Dict[str, Any],
        context: Dict[str, Any],
    ) -> str:
        """
        Build a prompt for the reflection LLM to compare two proof scripts.

        The prompt includes:
          - The theorem statement
          - Both proof scripts
          - Their verification results (success/failure, subgoals, errors)
          - Any available counterexample trace (if context has one)
          - The actual Coq/ACL2 environment so the LLM can use correct names
          - The dimensions to score on
        """
        theorem_name = obligation.get("property", "unknown")
        theorem_stmt = context.get("theorem_statement", "unknown")

        # Extract verification results
        res_a = node_a.verification_result or {}
        res_b = node_b.verification_result or {}

        success_a = "SUCCESS" if res_a.get("success") else "FAILED"
        success_b = "SUCCESS" if res_b.get("success") else "FAILED"
        goals_a = res_a.get("goals_remaining", "N/A")
        goals_b = res_b.get("goals_remaining", "N/A")
        error_a = res_a.get("error", "No error")[:200]
        error_b = res_b.get("error", "No error")[:200]

        # Trace information (for trace_alignment dimension)
        trace_info = ""
        if context.get("mc_trace"):
            trace_info = (
                "A model checking counterexample trace is available. "
                "Evaluate which proof better addresses the failing trace.\n"
                f"Trace snippet: {context['mc_trace'][:500]}"
            )

        # Coq/ACL2 environment (if available)
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
        """
        Parse the LLM response into a preference vector.

        Expected format: JSON with dimension names as keys and 1/-1/0 as values.
        """
        # Clean response
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
            # Fallback: attempt to extract numeric preferences from text
            return self._fallback_parse(cleaned)

        # Validate and convert
        pref = {}
        for dim in self.dimensions:
            val = data.get(dim)
            if val in (1, -1, 0):
                pref[dim] = int(val)
            else:
                # Try to infer from other fields
                if isinstance(val, (int, float)):
                    pref[dim] = 1 if val > 0 else (-1 if val < 0 else 0)
                else:
                    pref[dim] = 0
        return pref

    def _fallback_parse(self, text: str) -> Dict[str, int]:
        """Fallback parsing: look for numbers in the text."""
        pref = {dim: 0 for dim in self.dimensions}
        for dim in self.dimensions:
            # Try to find a pattern like "dimension: 1" or "dimension: better"
            if dim in text:
                segment = text[text.index(dim):]
                if "better" in segment[:50]:
                    pref[dim] = 1
                elif "worse" in segment[:50]:
                    pref[dim] = -1
                else:
                    # Look for a number
                    numbers = re.findall(r'[-+]?\d+', segment[:50])
                    if numbers:
                        val = int(numbers[0])
                        pref[dim] = 1 if val > 0 else (-1 if val < 0 else 0)
        return pref


def compute_pareto_front(
    nodes: List[PERFNode],
    dimensions: Optional[List[str]] = None,
    primary_dim: Optional[str] = None,
) -> List[PERFNode]:
    """
    Compute the Pareto front from scored nodes.

    A node dominates another if it is >= in all dimensions and strictly > in at least one.

    Args:
        nodes: List of nodes with `score` attribute (dict of dim -> float).
        dimensions: List of dimension names to consider (default: all present).
        primary_dim: If provided, used for tie-breaking (higher is better).

    Returns:
        List of non‑dominated nodes.
    """
    if not nodes:
        return []

    if dimensions is None:
        # Use the first node's score keys (assume all have same dims)
        sample = next((n for n in nodes if n.score), None)
        if sample is None:
            return nodes
        dimensions = list(sample.score.keys())

    # Remove nodes without scores
    scored = [n for n in nodes if n.score is not None]
    if not scored:
        return nodes

    pareto = []
    for i, node_i in enumerate(scored):
        dominated = False
        for j, node_j in enumerate(scored):
            if i == j:
                continue
            # Check if node_j dominates node_i
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

    # If primary dimension is given, sort by it for deterministic order
    if primary_dim and primary_dim in dimensions:
        pareto.sort(key=lambda n: n.score.get(primary_dim, 0.0), reverse=True)

    return pareto


def select_beam(
    pareto_front: List[PERFNode],
    beam_size: int,
    primary_dim: str,
) -> List[PERFNode]:
    """
    Select the top `beam_size` nodes from the Pareto front.

    Uses the primary dimension for tie‑breaking.
    """
    if not pareto_front:
        return []

    if len(pareto_front) <= beam_size:
        return pareto_front

    # Sort by primary dimension (higher is better)
    sorted_front = sorted(
        pareto_front,
        key=lambda n: n.score.get(primary_dim, 0.0) if n.score else 0.0,
        reverse=True
    )
    return sorted_front[:beam_size]
