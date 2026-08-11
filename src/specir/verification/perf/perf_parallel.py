# src/specir/verification/perf/perf_parallel.py
#
# PERF parallel node evaluation.
# Provides a thread-pool based evaluator for verifying multiple candidate
# proof scripts (nodes) concurrently. Each verification runs in its own
# thread and creates its own isolated prover session (rocq-mcp or acl2-mcp)
# to avoid state interference.
#
# Supports both Koika/Coq and ACL2 backends, and is compatible with
# the existing LLM client and verification infrastructure.

import concurrent.futures
import threading
import time
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable, Tuple
from pathlib import Path
from specir.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class PERFNode:
    """
    A node in the PERF search tree.

    Attributes:
        script: The proof script (Coq or ACL2) to evaluate.
        parent: Optional reference to the parent node.
        depth: The depth in the tree.
        score: Pareto scores populated by the scorer.
        verification_result: Result from the verifier (success, error, subgoals, etc.).
        children: List of child nodes.
    """
    script: str
    parent: Optional["PERFNode"] = None
    depth: int = 0
    score: Optional[Dict[str, float]] = None
    verification_result: Optional[Dict[str, Any]] = None
    children: List["PERFNode"] = field(default_factory=list)


class PERFParallelEvaluator:
    """
    Evaluates PERF nodes in parallel using a ThreadPoolExecutor.

    Each node verification is independent and runs in its own thread.
    The evaluator creates separate prover sessions (RocqClient/ACL2Client)
    per thread to ensure isolation and thread safety.

    The evaluator is compatible with both Ollama (local) and OpenAI (cloud)
    APIs for any LLM calls that might be needed during verification, though
    the primary use is for running the verifier (Coq/ACL2) which is CPU-bound.
    """

    def __init__(
        self,
        max_workers: int = 4,
        timeout_per_node: int = 300,
        config: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize the parallel evaluator.

        Args:
            max_workers: Maximum number of concurrent workers (threads).
            timeout_per_node: Default timeout in seconds for each node verification.
            config: Optional global configuration dictionary (for backend paths).
        """
        self.max_workers = max_workers
        self.timeout_per_node = timeout_per_node
        self.config = config or {}
        self._thread_local = threading.local()

    def evaluate_nodes(
        self,
        nodes: List[PERFNode],
        evaluator_fn: Callable[[PERFNode], Dict[str, Any]],
        timeout: Optional[float] = None
    ) -> List[PERFNode]:
        """
        Evaluate multiple nodes in parallel.

        Args:
            nodes: List of nodes to evaluate.
            evaluator_fn: A callable that takes a PERFNode and returns a
                          dictionary with at least a 'success' boolean key,
                          and optionally 'error', 'goals_remaining', etc.
            timeout: Optional per-node timeout in seconds (overrides default).

        Returns:
            The same list of nodes with their `verification_result` field populated.
        """
        if not nodes:
            return nodes

        if len(nodes) == 1:
            nodes[0].verification_result = self._evaluate_single(
                nodes[0], evaluator_fn, timeout
            )
            return nodes

        effective_timeout = timeout or self.timeout_per_node
        results = [None] * len(nodes)

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(self.max_workers, len(nodes))
        ) as executor:
            future_to_index = {
                executor.submit(
                    self._evaluate_with_timeout,
                    node,
                    evaluator_fn,
                    effective_timeout
                ): idx
                for idx, node in enumerate(nodes)
            }

            for future in concurrent.futures.as_completed(future_to_index):
                idx = future_to_index[future]
                try:
                    result = future.result(timeout=effective_timeout + 5)
                    nodes[idx].verification_result = result
                except concurrent.futures.TimeoutError:
                    logger.warning(
                        "Node %d evaluation timed out after %ds",
                        idx, effective_timeout
                    )
                    nodes[idx].verification_result = {
                        "success": False,
                        "error": f"Verification timed out after {effective_timeout}s"
                    }
                except Exception as e:
                    logger.error("Node %d evaluation failed: %s", idx, e)
                    nodes[idx].verification_result = {
                        "success": False,
                        "error": str(e)
                    }

        return nodes

    def _evaluate_single(
        self,
        node: PERFNode,
        evaluator_fn: Callable[[PERFNode], Dict[str, Any]],
        timeout: Optional[float] = None
    ) -> Dict[str, Any]:
        """Evaluate a single node (no parallel overhead)."""
        try:
            return evaluator_fn(node)
        except Exception as e:
            logger.error("Single node evaluation failed: %s", e)
            return {"success": False, "error": str(e)}

    def _evaluate_with_timeout(
        self,
        node: PERFNode,
        evaluator_fn: Callable[[PERFNode], Dict[str, Any]],
        timeout: float
    ) -> Dict[str, Any]:
        """Wrapper to enforce a timeout on node evaluation."""
        result_container = {}
        exception_container = []

        def target():
            try:
                result_container["result"] = evaluator_fn(node)
            except Exception as e:
                exception_container.append(e)

        thread = threading.Thread(target=target)
        thread.daemon = True
        thread.start()
        thread.join(timeout=timeout)

        if thread.is_alive():
            logger.warning("Node evaluation timed out after %ds", timeout)
            return {"success": False, "error": f"Verification timed out after {timeout}s"}

        if exception_container:
            raise exception_container[0]

        return result_container.get("result", {"success": False, "error": "Unknown error"})

    @staticmethod
    def create_rocq_client(
        coq_file: Path,
        workspace: Path,
        rocq_path: str = "rocq-mcp",
        timeout: int = 300
    ) -> Any:
        """
        Create a RocqClient instance for use in a thread.
        Each thread should create its own client to avoid session conflicts.
        """
        from specir.backends.rocq_client import RocqClient
        return RocqClient(
            rocq_mcp_path=rocq_path,
            timeout=timeout,
            cwd=workspace,
            server_args=["--workspace", str(workspace)],
        )

    @staticmethod
    def create_acl2_client(
        mcp_path: str = "acl2-mcp",
        timeout: int = 300,
        init_commands: Optional[List[str]] = None
    ) -> Any:
        """
        Create an ACL2Client instance for use in a thread.
        """
        from specir.backends.acl2_client import ACL2Client
        return ACL2Client(
            mcp_path=mcp_path,
            timeout=timeout,
            init_commands=init_commands or []
        )
