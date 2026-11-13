# src/isir/verification/perf/mcts_traversal.py
#
# Monte Carlo Tree Search over proof candidates.

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from isir.utils.logger import get_logger
from isir.verification.perf.perf_scorer import PERFNode
from isir.verification.perf.perf_stats import PERFStats
from isir.verification.perf.perf_traversal import PERFTraversal

logger = get_logger(__name__)


@dataclass
class MCTSConfig:
    """MCTS-specific search parameters (independent of PERFConfig)."""
    c: float = 1.4142135623730951   # UCB1 exploration constant (sqrt(2))
    iterations: int = 36            # number of select-expand-backprop iterations
    branches_per_node: int = 4      # children generated per expansion


class MCTSTraversal(PERFTraversal):
    """Monte Carlo Tree Search (UCB1 + backpropagation) over proof candidates."""

    def __init__(self, config, llm_client, context, mcts: Optional[MCTSConfig] = None):
        super().__init__(config, llm_client, context)
        self.mcts = mcts or MCTSConfig()

    def traverse(self) -> Tuple[Optional[str], PERFStats]:
        root = self._prepare()
        if root is None:
            return None, self.stats

        # Verify the root (initial script).
        if self.config.always_verify_children:
            result = self._evaluate_node(root)
            root.verification_result = result
            if result.get("success"):
                self._finish_success(root)
                return root.script, self.stats

        visits: Dict[int, int] = {id(root): 1}
        values: Dict[int, float] = {id(root): 0.0}

        for _ in range(max(self.mcts.iterations, 1)):
            # SELECT — UCB1 descent to a leaf.
            node, path = self._select(root, visits, values)
            if node is None:
                break

            # EXPAND — generate + verify + repair children (shared with PERF).
            children = self._generate_children([node], node.depth + 1)
            if not children:
                break
            children = self._filter_children(children)
            if not children:
                continue
            children = self._verify_children(children)
            for c in children:
                self.stats.record_verifier_call()
            children = self._repair_children(children, node.depth + 1)
            node.children = children

            # EVALUATE — success short-circuits; otherwise a cheap scalar reward
            # (no PERF Pareto/LLM tournament scorer).
            best_reward = 0.0
            for child in children:
                if child.verification_result and child.verification_result.get("success"):
                    self._finish_success(child)
                    return child.script, self.stats
                reward = self._cheap_reward(child)
                best_reward = max(best_reward, reward)
                visits[id(child)] = 1
                values[id(child)] = reward

            # BACKPROPAGATE — push the best child value up the selected path.
            for n in path:
                nid = id(n)
                v = visits.get(nid, 0) + 1
                visits[nid] = v
                old = values.get(nid, 0.0)
                values[nid] = old + (best_reward - old) / v

        return self.best_candidate_script, self.stats

    def _select(self, root: PERFNode, visits: Dict[int, int],
                values: Dict[int, float]) -> Tuple[Optional[PERFNode], List[PERFNode]]:
        """UCB1 descent from root to a leaf (a node with no children)."""
        node = root
        path: List[PERFNode] = [root]
        while node.children:
            best = None
            best_score = -math.inf
            for child in node.children:
                u = self._ucb(child, node, visits, values)
                if u > best_score:
                    best_score = u
                    best = child
            if best is None:
                return node, path
            node = best
            path.append(node)
        return node, path

    def _ucb(self, child: PERFNode, parent: PERFNode,
             visits: Dict[int, int], values: Dict[int, float]) -> float:
        n_parent = visits.get(id(parent), 1)
        n_child = visits.get(id(child), 0)
        q = values.get(id(child), 0.0)
        if n_child == 0:
            return math.inf  # always expand unvisited children first
        return q + self.mcts.c * math.sqrt(math.log(n_parent) / n_child)

    def _cheap_reward(self, node: PERFNode) -> float:
        """Cheap scalar reward in [0,1] from the verification result.

        LLM-free (no Pareto tournament): success → 1.0; otherwise fewer errors
        → higher reward, so UCB still has a gradient among failing nodes.
        """
        vr = node.verification_result or {}
        if vr.get("success"):
            return 1.0
        err = vr.get("error", "") or ""
        n = err.count("Error") + err.count("error")
        return 1.0 / (1.0 + n)

    def _finish_success(self, node: PERFNode) -> None:
        self.stats.record_success(node.depth)
        self.stats.finish()
        prop_name = self.obligation.get("property", "unknown")
        self._record_successful_proof(prop_name, node.script)
        self.best_candidate_script = node.script
        self.best_candidate_score = 1.0
