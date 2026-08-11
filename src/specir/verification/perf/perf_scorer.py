# src/specir/verification/perf/perf_scorer.py
#
# PERF scoring with LLM reflection and Pareto optimality.

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
      1. For each node, compute a base score from the verification result.
      2. If all failing nodes share the same error signature, skip the
         tournament and assign uniform scores.
      3. Otherwise, run a tournament: each node is compared against K others.
      4. Win counts are accumulated per dimension and normalised to scores.
      5. Scores are attached to each node.
    """

    def __init__(
        self,
        config: PERFConfig,
        llm_client: LLMClient,
        max_workers: int = 1,
    ):
        self.config = config
        self.llm = llm_client
        self.max_workers = max_workers
        self.dimensions = config.get_effective_dimensions()
        self.tournament_size = config.scoring_tournament_size
        self.trace_weight = config.trace_alignment_weight
        self._comparison_cache: Dict[Tuple[str, str], Dict[str, int]] = {}

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

        return nodes

    def _compute_base_scores(self, nodes: List[PERFNode]) -> Dict[int, Dict[str, float]]:
        base = {}
        for node in nodes:
            res = node.verification_result or {}
            success = res.get("success", False)
            error_msg = res.get("error", "")

            if success:
                subgoal_score = 1.0
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
            for dim in self.dimensions:
                if dim not in base[node_id]:
                    base[node_id][dim] = 0.5

        return base

    def _subgoal_score_from_error(self, error_msg: str) -> float:
        """Map common Coq errors to a subgoal‑reduction score."""
        msg = error_msg.lower()
        # Very specific, close to a proof
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
        # generic failure
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
        key = tuple(sorted((hash(node_a.script), hash(node_b.script))))
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


def compute_pareto_front(
    nodes: List[PERFNode],
    dimensions: Optional[List[str]] = None,
    primary_dim: Optional[str] = None,
) -> List[PERFNode]:
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
