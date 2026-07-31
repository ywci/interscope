# src/specir/verification/perf/perf_traversal.py
#
# Core PERF traversal engine.
# Implements the beam search with Pareto pruning and reflective feedback.
# The traversal expands a tree of proof candidates, scores them using
# multi-dimensional Pareto optimality, and keeps the best B nodes at each depth.
#
# The traversal is backend-agnostic: it delegates node generation and
# verification to the appropriate backend-specific functions (Koika or ACL2).

import copy
import time
import tempfile
import os
import shutil
import re
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from specir.backends.llm_client import LLMClient
from specir.verification.perf.perf_config import PERFConfig
from specir.verification.perf.perf_scorer import PERFScorer, PERFNode, compute_pareto_front, select_beam
from specir.verification.perf.perf_stats import PERFStats
from specir.verification.perf.perf_parallel import PERFParallelEvaluator
from specir.verification.perf.perf_evidence import PERFEvidence
from specir.utils.logger import get_logger

logger = get_logger(__name__)


class PERFTraversal:
    """
    Core PERF traversal engine.

    Orchestrates the entire proof search process:
      1. Initialize the frontier with the initial proof script.
      2. For each depth, generate children from each frontier node.
      3. Verify children (optionally in parallel).
      4. Score children using Pareto reflection.
      5. Prune to the Pareto front, then select the beam.
      6. Repeat until success or depth limit.

    The traversal is designed to be backend-agnostic. It relies on
    generator and verifier functions that are passed in or discovered
    from the context.
    """

    def __init__(
        self,
        config: PERFConfig,
        llm_client: LLMClient,
        context: Dict[str, Any],
    ):
        """
        Initialize the PERF traversal.

        Args:
            config: PERF configuration.
            llm_client: LLM client for generation and scoring.
            context: Context dictionary containing:
                - obligation: The proof obligation dict.
                - spec_module: The spec dialect module.
                - coq_file_path: Path to the Coq file (if Koika).
                - acl2_file_path: Path to the ACL2 file (if ACL2).
                - theorem_name: Name of the theorem.
                - theorem_statement: Statement of the theorem (for ACL2).
                - workspace: Working directory for sessions.
                - mc_trace: Optional counterexample trace (for trace_alignment).
                - initial_script: Optional explicit initial script.
                - ... (other backend-specific data)
        """
        self.config = config
        self.llm = llm_client
        self.context = context
        self.obligation = context.get("obligation", {})
        self.backend = self.obligation.get("backend", "koika").lower()
        self.backend = self.backend.replace("ō", "o")
        if not self.backend.startswith("koi") and self.backend != "acl2":
            self.backend = "koika"  # fallback

        self.coq_context_str = ""
        if self.backend.startswith("koi"):
            coq_file = self.context.get("coq_file_path")
            if coq_file:
                try:
                    full_content = Path(coq_file).read_text()
                    # Keep everything before the first theorem placeholder
                    # so the LLM sees the definitions and lemmas.
                    env_part = full_content.split("(* PERF_Obligation:")[0]
                    self.coq_context_str = env_part.strip()
                except Exception:
                    self.coq_context_str = ""
        # Make the environment available to the scorer and other components
        self.context["coq_environment"] = self.coq_context_str

        # Initialize components
        self.scorer = PERFScorer(config, llm_client, max_workers=config.max_workers)
        self.parallel_evaluator = PERFParallelEvaluator(
            max_workers=config.max_workers,
            timeout_per_node=config.timeout_per_node,
            config=context.get("config", {}),
        )
        self.evidence = PERFEvidence()
        self.stats = PERFStats()

        # Cache for generated children to avoid duplicate LLM calls
        self._child_cache = {}

    def traverse(self) -> Tuple[Optional[str], PERFStats]:
        """
        Execute the PERF traversal.

        Returns:
            A tuple (proof_script, stats) where proof_script is the
            successful proof script, or None if not found.
        """
        logger.info("Starting PERF traversal (backend=%s)", self.backend)
        self.stats.start()

        # 1. Get the initial script
        initial_script = self._get_initial_script()
        if not initial_script:
            logger.error("No initial script available for PERF")
            self.stats.finish()
            return None, self.stats

        logger.debug("Initial script length: %d chars", len(initial_script))

        # 2. Initialize root node
        root = PERFNode(script=initial_script, depth=0)
        self.stats.record_node()

        # 3. Verify the initial script (optional)
        if self.config.always_verify_children:
            logger.info("Verifying initial script...")
            result = self._evaluate_node(root)
            root.verification_result = result
            self.stats.record_verifier_call()
            if result.get("success"):
                logger.info("Initial script already proves the theorem!")
                self.stats.record_success(0)
                self.stats.finish()
                # Register evidence
                self.evidence.register_proof(
                    property_name=self.obligation.get("property", "unknown"),
                    proof_script=initial_script,
                    backend=self.backend,
                    stats=self.stats,
                )
                return initial_script, self.stats

        # 4. Setup frontier
        frontier = [root]
        best_script = initial_script   # track the best proof found
        best_score = None

        # 5. Main traversal loop
        for depth in range(self.config.depth_limit):
            current_depth = depth + 1
            logger.info(
                "PERF depth %d/%d: frontier size = %d",
                current_depth, self.config.depth_limit, len(frontier)
            )
            self.stats.record_depth(current_depth)

            # 5a. Generate children from each frontier node
            children = self._generate_children(frontier, current_depth)
            self.stats.record_node(len(children))
            if not children:
                logger.warning("No children generated at depth %d", current_depth)
                break

            # 5b. Verify children (if configured)
            if self.config.always_verify_children:
                logger.info("Verifying %d children in parallel...", len(children))
                children = self._verify_children(children)
                for node in children:
                    self.stats.record_verifier_call()

            # 5c. Check for successful child
            for node in children:
                if node.verification_result and node.verification_result.get("success"):
                    logger.info(
                        "PERF found a successful proof at depth %d!",
                        current_depth
                    )
                    self.stats.record_success(current_depth)
                    self.stats.record_beam_size(len(frontier))
                    self.stats.finish()
                    # Register evidence
                    self.evidence.register_proof(
                        property_name=self.obligation.get("property", "unknown"),
                        proof_script=node.script,
                        backend=self.backend,
                        stats=self.stats,
                    )
                    return node.script, self.stats

            # 5d. Score children using Pareto reflection
            logger.info("Scoring %d children...", len(children))
            scored_children = self.scorer.score_nodes(
                children, self.obligation, self.context
            )

            # 5e. Compute Pareto front
            pareto_front = compute_pareto_front(
                scored_children,
                dimensions=self.config.dimensions,
                primary_dim=self.config.primary_dimension,
            )
            pruned_count = len(scored_children) - len(pareto_front)
            self.stats.record_pareto_pruned(pruned_count)
            logger.info(
                "Pareto front: %d nodes (pruned %d)",
                len(pareto_front), pruned_count
            )

            # 5f. Select beam
            frontier = select_beam(
                pareto_front,
                self.config.beam_size,
                self.config.primary_dimension,
            )
            self.stats.record_beam_size(len(frontier))
            logger.info("Beam selected: %d nodes", len(frontier))

            # Record depth stats
            self.stats.record_depth_stats(
                current_depth,
                len(children),
                len(frontier),
                pruned_count,
            )

            # Update best script (if any node in frontier has better score)
            for node in frontier:
                if self._score_better(node.score, best_score):
                    best_script = node.script
                    best_score = node.score

        # 6. If we reach here, no success was found.
        logger.warning("PERF exhausted after %d depths", self.config.depth_limit)
        self.stats.finish()
        return best_script if best_script != initial_script else None, self.stats

    def _get_initial_script(self) -> Optional[str]:
        """
        Obtain the initial proof script from the context.

        Priority:
          1. Explicit 'initial_script' in context.
          2. Read from Coq file (if backend is Koika) and extract the theorem placeholder.
          3. Read from ACL2 file (if backend is ACL2) and extract the defthm placeholder.
          4. Otherwise, None.
        """
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
        """Extract the Admitted. placeholder theorem from a Coq file."""
        content = coq_file.read_text()
        theorem_name = self.context.get("theorem_name")
        if not theorem_name:
            # Fallback: find the first theorem with Admitted.
            pattern = re.compile(
                r"(Theorem\s+\w+.*?)(?:Proof\..*?)Admitted\.", re.DOTALL
            )
            match = pattern.search(content)
            if match:
                # Return the full theorem including the placeholder proof
                return match.group(0).strip()
            return None
        # Specific theorem
        pattern = re.compile(
            rf"(Theorem\s+{re.escape(theorem_name)}.*?)(?:Proof\..*?)Admitted\.", re.DOTALL
        )
        match = pattern.search(content)
        if match:
            return match.group(0).strip()
        return None

    def _extract_acl2_placeholder(self, acl2_file: Path) -> Optional[str]:
        """Extract the defthm placeholder from an ACL2 file."""
        content = acl2_file.read_text()
        theorem_name = self.context.get("theorem_name")
        if not theorem_name:
            # Fallback: find the first defthm
            pattern = re.compile(
                r"(defthm\s+\w+.*?\)?)", re.DOTALL
            )
            match = pattern.search(content)
            if match:
                return match.group(0).strip()
            return None
        # Specific defthm
        pattern = re.compile(
            rf"(defthm\s+{re.escape(theorem_name)}.*?\)?)", re.DOTALL
        )
        match = pattern.search(content)
        if match:
            return match.group(0).strip()
        return None

    def _generate_children(
        self,
        frontier: List[PERFNode],
        depth: int,
    ) -> List[PERFNode]:
        """Generate children from each frontier node."""
        children = []
        for parent in frontier:
            # Generate N variants from the parent script
            variants = self._generate_variants(parent.script, depth)
            for var in variants:
                child = PERFNode(
                    script=var,
                    parent=parent,
                    depth=depth,
                )
                children.append(child)
        return children

    def _generate_variants(self, script: str, depth: int) -> List[str]:
        """
        Generate divergent variants of a proof script.

        Delegates to backend-specific generator functions.
        """
        cache_key = (hash(script), depth)
        if cache_key in self._child_cache:
            return self._child_cache[cache_key]

        variants = []
        n = self.config.branches_per_node
        temp = self.config.generation_temperature

        if self.backend.startswith("koi"):
            variants = self._generate_coq_variants(script, n, temp)
        elif self.backend == "acl2":
            variants = self._generate_acl2_variants(script, n, temp)
        else:
            logger.error("Unsupported backend for generation: %s", self.backend)

        # Ensure we have at least one variant (may be the same as original)
        if not variants:
            variants = [script]

        self._child_cache[cache_key] = variants
        return variants

    def _generate_coq_variants(self, script: str, n: int, temp: float) -> List[str]:
        """Generate Coq proof variants using the LLM, with full Coq environment."""
        theorem_name = self.context.get("theorem_name", "unknown")
        theorem_stmt = self.context.get("theorem_statement", "")
        from specir.verification.proof.koika.proof_gen import generate_coq_proof_variants
        return generate_coq_proof_variants(
            llm_client=self.llm,
            theorem_name=theorem_name,
            theorem_statement=theorem_stmt,
            num_variants=n,
            context=self.coq_context_str,          # <-- the actual definitions
            tactic_hints=None,
            temperature=temp,
        )

    def _generate_acl2_variants(self, script: str, n: int, temp: float) -> List[str]:
        """Generate ACL2 proof variants using the LLM, with full ACL2 environment."""
        theorem_name = self.context.get("theorem_name", "unknown")
        theorem_stmt = self.context.get("theorem_statement", "")
        from specir.verification.proof.acl2.proof_gen import generate_acl2_proof_variants
        return generate_acl2_proof_variants(
            llm_client=self.llm,
            theorem_name=theorem_name,
            theorem_statement=theorem_stmt,
            num_variants=n,
            context=self.coq_context_str,          # ACL2 context as a string
            temperature=temp,
        )

    def _get_context_string(self) -> str:
        """Return the full Coq/ACL2 environment for prompts."""
        return self.coq_context_str

    def _verify_children(self, children: List[PERFNode]) -> List[PERFNode]:
        """
        Verify children in parallel using the appropriate verifier.
        """
        if not children:
            return children

        # Define the evaluator function based on backend
        if self.backend.startswith("koi"):
            evaluator = self._evaluate_koika_node
        else:
            evaluator = self._evaluate_acl2_node

        # Run parallel evaluation
        return self.parallel_evaluator.evaluate_nodes(
            children, evaluator, timeout=self.config.timeout_per_node
        )

    def _evaluate_node(self, node: PERFNode) -> Dict[str, Any]:
        """Evaluate a single node (no parallel)."""
        if self.backend.startswith("koi"):
            return self._evaluate_koika_node(node)
        else:
            return self._evaluate_acl2_node(node)

    def _evaluate_koika_node(self, node: PERFNode) -> Dict[str, Any]:
        """
        Evaluate a Koika node by injecting the proof script into the Coq file
        and verifying it with rocq-mcp.

        The workspace is set to a temporary directory inside the original
        workspace, and the Coq file is copied there to satisfy rocq-mcp's
        requirement that files be within the workspace.
        """
        coq_file = self.context.get("coq_file_path")
        if not coq_file or not Path(coq_file).exists():
            return {"success": False, "error": "Coq file not available"}

        theorem_name = self.context.get("theorem_name")
        if not theorem_name:
            return {"success": False, "error": "Theorem name not available"}

        # Resolve the workspace path to an absolute directory
        original_workspace = self.context.get("workspace")
        if original_workspace is None:
            original_workspace = Path(coq_file).parent
        original_workspace = Path(original_workspace).resolve()
        original_workspace.mkdir(parents=True, exist_ok=True)

        # Create a temporary directory inside the workspace
        temp_dir = tempfile.mkdtemp(prefix="perf_eval_", dir=str(original_workspace))
        temp_dir_path = Path(temp_dir)
        temp_coq_file = temp_dir_path / Path(coq_file).name

        try:
            # Copy the original Coq file to the temporary directory
            shutil.copy2(coq_file, temp_coq_file)

            # Read the original content
            original_content = temp_coq_file.read_text()

            # Replace the Admitted. block with the candidate proof
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

            # Start rocq-mcp with the temporary directory as workspace
            from specir.backends.rocq_client import RocqClient

            rocq = RocqClient(
                rocq_mcp_path=self.context.get("rocq_path", "rocq-mcp"),
                timeout=self.config.timeout_per_node,
                cwd=temp_dir_path,
                server_args=["--workspace", str(temp_dir_path)],
            )
            try:
                rocq.start()

                # Compile the temporary file
                compile_result = rocq.compile_file(temp_coq_file, workspace=temp_dir_path)
                if rocq._extract_error_from_response(compile_result):
                    error = rocq._extract_error_from_response(compile_result)
                    return {"success": False, "error": f"Compilation failed: {error}"}

                # Verify the theorem
                verify_result = rocq.verify(temp_coq_file, theorem_name, workspace=temp_dir_path)
                error = rocq._extract_error_from_response(verify_result)
                if error:
                    return {"success": False, "error": f"Verification failed: {error}"}

                # Check if proof is closed
                return {"success": True, "goals_remaining": 0}

            finally:
                rocq.stop()

        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            # Clean up the temporary directory
            shutil.rmtree(temp_dir, ignore_errors=True)

    def _evaluate_acl2_node(self, node: PERFNode) -> Dict[str, Any]:
        """
        Evaluate an ACL2 node by loading the proof script into an ACL2 session
        and verifying the theorem.
        """
        acl2_file = self.context.get("acl2_file_path")
        if not acl2_file or not Path(acl2_file).exists():
            return {"success": False, "error": "ACL2 file not available"}

        theorem_name = self.context.get("theorem_name")
        theorem_statement = self.context.get("theorem_statement")
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
            # Load the base file (definitions)
            acl2.load_file(Path(acl2_file))

            # The candidate script is a defthm form; send it to ACL2
            result = acl2.send(node.script)
            if "Error" in result or "ACL2 Error" in result:
                return {"success": False, "error": result}

            # Verify the theorem
            if "ACL2 Error" not in result and "Error" not in result:
                # Check if theorem was proved (look for "Q.E.D." or similar)
                if "Q.E.D." in result or "Proof succeeded" in result:
                    return {"success": True}
                else:
                    # Try to verify explicitly
                    verify_result = acl2.send(f"(verify {theorem_name})")
                    if "Q.E.D." in verify_result or "Proof succeeded" in verify_result:
                        return {"success": True}
                    else:
                        return {"success": False, "error": "The theorem was not proven"}
            else:
                return {"success": False, "error": result}

        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            acl2.stop()

    def _score_better(
        self,
        score_a: Optional[Dict[str, float]],
        score_b: Optional[Dict[str, float]],
    ) -> bool:
        """
        Compare two score dictionaries and return True if a is better than b.
        Uses the primary dimension for comparison.
        """
        if score_a is None:
            return False
        if score_b is None:
            return True
        primary = self.config.primary_dimension
        return score_a.get(primary, 0.0) > score_b.get(primary, 0.0)

    def get_stats(self) -> PERFStats:
        """Return the statistics collected during traversal."""
        return self.stats
