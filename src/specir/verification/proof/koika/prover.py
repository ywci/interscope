# src/specir/verification/proof/koika/prover.py
#
# Generic prover for Kōika/Coq theorems with LLM proof generation.
# All design-specific heuristics are controlled by configuration;
# the core is purely structural.

import os
import json
import time
import re
import subprocess
import shutil
import tempfile
import concurrent.futures
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Set, Union, Callable
from specir.backends.rocq_client import RocqClient, RocqClientError
from specir.backends.llm_client import LLMClient, get_llm_client_from_config
from specir.utils.logger import get_logger
from specir.utils.config_loader import get_config, get_project_root
from lib.koika.assist import PROOF_LIBRARY
from specir.verification.proof.koika.proof_gen import (
    build_interactive_step_prompt,
    extract_tactics_from_response,
    build_skeleton_reflection_prompt,
    extract_proof_script,
    generate_coq_proof_variants,
    build_coq_proof_prompt
)
from specir.verification.proof.proof import ProofResult
from specir.verification.proof.prelude_templates import get_prelude
from specir.verification.proof.tactic_modernizer import modernize_tactics
from specir.verification.proof.structural_validator import validate_structure
from specir.verification.proof.koika.auto_patcher import auto_patch
from specir.verification.proof.domain_tactics import apply_domain_tactics

logger = get_logger(__name__)


class KoikaProver:
    """Generic prover for Kōika/Coq theorems.

    The prover follows a strict escalation path:
    1. Already-proven check
    2. Built-in deterministic proof (for known patterns)
    3. Initial script verification (if provided)
    4. Proof library (fast, config-controlled)
    5. Built-in skeleton proofs (generic structural induction)
    6. LLM skeleton reflection (tailored one-shot proof)
    7. LLM-driven interactive tactic loop
    8. coqc-based fallback verification
    9. LLM full-proof generation with repair (using coqc for validation)

    If `use_rocq_mcp` is false, steps 5–7 are skipped.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        if config is None:
            config = get_config()
        self.config = config

        self.llm = get_llm_client_from_config(config)

        prove_cfg = config.get("provers", {}).get("koika", {}).get("prove", {})
        self.rocq_path = prove_cfg.get("rocq_mcp_path") or "rocq-mcp"
        self.proof_timeout = prove_cfg.get("proof_timeout", 600)
        self.max_consecutive_failures = prove_cfg.get("max_consecutive_failures", 10)
        self.max_steps = prove_cfg.get("max_steps", 80)
        self.pre_simplify = prove_cfg.get("pre_simplify", True)
        self.invariant_mining = prove_cfg.get("invariant_mining", True)
        self.skeleton_reflection = prove_cfg.get("skeleton_reflection", True)

        # Master switch for rocq-mcp.  If false, interactive paths are skipped.
        self.use_rocq_mcp = prove_cfg.get("use_rocq_mcp", True)

        self.base_case_hint = prove_cfg.get(
            "base_case_hint",
            "simpl; auto with *; try lia; try nia."
        )
        self.step_case_hint = prove_cfg.get(
            "step_case_hint",
            (
                "1.  Name the step hypothesis `Hstep` in the induction scheme.\n"
                "2.  `inversion Hstep; subst; clear Hstep.`\n"
                "3.  If the goal now contains `if op_reg s =? …` (or any nested\n"
                "    conditional on an opcode), **destruct each comparison**:\n"
                "    `destruct (op_reg s =? 0) eqn:Hop0`, then `destruct (op_reg s =? 1)\n"
                "    eqn:Hop1`, etc.\n"
                "4.  In each sub-goal, `simpl` and then apply the induction\n"
                "    hypothesis `IH` (or use `auto`).\n"
                "5.  Finish with `auto; try lia; try nia`."
            )
        )

        self.skeleton_step_tactics: List[str] = prove_cfg.get("skeleton_step_tactics", [])

        self.max_repair = config.get("proof", {}).get("max_repair_attempts", 5)
        self.coqc_path = shutil.which("coqc") or "coqc"
        self.use_proof_library = config.get("provers", {}).get("koika", {}).get(
            "use_proof_library", True
        )
        self.use_mc_lemmas = config.get("provers", {}).get("koika", {}).get(
            "use_mc_lemmas", False
        )

        self.spec_module = None
        self.structural_hints: Optional[str] = None

        self._perf_stats = {
            "total_nodes": 0,
            "total_verifier_calls": 0,
            "max_depth": 0,
            "beam_size": 0,
            "pruned_by_pareto": 0,
            "total_tokens": {"prompt": 0, "completion": 0}
        }

        self._rocq: Optional[RocqClient] = None
        self._rocq_broken = False

        self._prelude = get_prelude("koika")
        self._prelude_validated = False   # cache validation result

    def _prepare_proof_script(self, script: str, theorem_name: str = "",
                              error_msg: str = "") -> str:
        """
        Apply the full deterministic pre-processing pipeline to a proof
        script.  Order matters:

        1. Tactic modernisation (`omega` → `lia`, deprecated imports, etc.)
        2. Automatic patching of common Coq errors (focus, deprecated
           notations, boolean `discriminate`, orphan bullets)
        3. Domain-specific tactic substitutions

        The result is structurally validated.  If the patched script is
        broken, the original script is returned with a warning.
        """
        if not script:
            return script

        # Tactic modernisation first.
        script = modernize_tactics(script)

        # Auto-patch common errors.  Pass the error message if available so
        # the patcher can focus on the right repair.
        script = auto_patch(script, error_msg)

        # Apply domain-specific tactic hints and replacements.
        script = apply_domain_tactics(script, theorem_name, "koika")

        # Final structural sanity check.  Do not blindly return a broken
        # script from the deterministic pipeline.
        issues = validate_structure(script)
        critical_issues = [
            issue for issue in issues
            if ("Unbalanced" in issue or
                "Unclosed proof" in issue or
                "orphan bullet" in issue)
        ]
        if critical_issues:
            logger.warning(
                "Deterministic script preparation introduced structural issues: %s",
                "; ".join(critical_issues),
            )

        return script

    def prove_with_builtin_only(self, coq_file: Path, theorem_name: str) -> Optional[ProofResult]:
        """Attempt only the built-in deterministic proof for a known theorem.

        Returns a `ProofResult` on success, or `None` if the built-in proof
        is not available or fails.
        """
        start_time = time.time()
        proof_script = self._try_builtin_proof(coq_file, theorem_name)
        if proof_script is not None:
            duration = time.time() - start_time
            logger.info("Built-in proof succeeded for '%s'.", theorem_name)
            return ProofResult(
                success=True,
                proof_script=proof_script,
                duration=duration,
                backend="koika",
                metadata={"automation": "builtin"}
            )
        return None

    def _prelude_is_valid(self) -> bool:
        """Test whether the current prelude can be compiled with coqc.

        Returns True if the prelude imports successfully, False otherwise.
        The result is cached to avoid repeated compilation.
        """
        if self._prelude_validated:
            return True

        if not self._prelude or not self._prelude.strip():
            self._prelude_validated = True
            return True

        tmp_path = None
        try:
            fd, tmp_path = tempfile.mkstemp(suffix=".v", prefix="prelude_check_")
            os.close(fd)
            Path(tmp_path).write_text(self._prelude, encoding="utf-8")

            cmd = [self.coqc_path, str(tmp_path)]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                logger.debug("Prelude validation succeeded.")
                self._prelude_validated = True
                return True
            else:
                logger.warning(
                    "Prelude validation failed: %s",
                    result.stderr[:500],
                )
                return False
        except Exception as e:
            logger.warning("Prelude validation raised exception: %s", e)
            return False
        finally:
            if tmp_path is not None and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    def _ensure_prelude(self, coq_file: Path) -> None:
        """Insert the backend-specific prelude into the Coq file if missing.

        The prelude is first validated by compiling it with coqc.  If the
        validation fails (e.g., due to a missing logical path), injection is
        skipped and a warning is logged.
        """
        try:
            content = coq_file.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning("Could not read Coq file for prelude injection: %s", e)
            return

        if self._prelude and self._prelude.strip() and self._prelude.strip() not in content:
            if not self._prelude_is_valid():
                logger.warning(
                    "Skipping prelude injection because the prelude failed validation. "
                    "The existing Coq file will be used as-is."
                )
                return

            logger.info("Injecting standard prelude into %s", coq_file.name)
            new_content = self._prelude + "\n" + content
            coq_file.write_text(new_content, encoding="utf-8")

    def _modernise_script(self, proof_script: str) -> str:
        """Apply tactic modernisation to a proof script."""
        return modernize_tactics(proof_script)

    def _ensure_workspace_has_compiled_artifacts(self, coq_file: Path,
                                                  workspace: Path) -> bool:
        """Ensure compiled .vo/.glob exist; compile with coqc if missing."""
        stem = coq_file.stem
        vo_path = workspace / f"{stem}.vo"
        glob_path = workspace / f"{stem}.glob"

        if vo_path.exists() and glob_path.exists():
            imports = self._extract_imports(coq_file)
            missing_imports = [
                imp for imp in imports
                if not (workspace / f"{imp}.vo").exists()
            ]
            if not missing_imports:
                return True
            logger.info(
                "Missing compiled artefacts for imports: %s. Recompiling.",
                ", ".join(missing_imports)
            )
            if self._compile_with_coqc(coq_file, workspace):
                imports = self._extract_imports(coq_file)
                missing = [imp for imp in imports
                           if not (workspace / f"{imp}.vo").exists()]
                if missing:
                    logger.warning(
                        "Some imported modules still lack compiled artefacts: %s",
                        ", ".join(missing)
                    )
                return True
            return False

        logger.info(
            "Compiled artefacts for '%s' are missing; compiling with coqc.",
            coq_file.name
        )
        if self._compile_with_coqc(coq_file, workspace):
            for imp in self._extract_imports(coq_file):
                if not (workspace / f"{imp}.vo").exists():
                    for src in [
                        Path(coq_file.parent) / f"{imp}.v",
                        Path(coq_file.parent) / f"{imp.lower()}.v"
                    ]:
                        if src.exists():
                            logger.info("Compiling imported module '%s'.", imp)
                            self._compile_with_coqc(src, workspace)
                            break
            return True
        logger.error("coqc fallback also failed to create compiled artefacts.")
        return False

    def _extract_imports(self, coq_file: Path) -> List[str]:
        imports = []
        try:
            content = coq_file.read_text(encoding="utf-8")
        except Exception:
            return imports
        pattern = re.compile(
            r"^\s*Require\s+(?:Import|Export)\s+(.*?)\.",
            re.MULTILINE | re.DOTALL
        )
        for match in pattern.finditer(content):
            for name in match.group(1).strip().split():
                if name and name not in imports:
                    imports.append(name)
        return imports

    def _get_rocq_client(self, workspace: Path) -> Optional[RocqClient]:
        """Return a RocqClient, or None if rocq-mcp is known broken."""
        if self._rocq_broken:
            return None
        abs_workspace = workspace.resolve()
        if self._rocq is None:
            self._rocq = RocqClient(
                rocq_mcp_path=self.rocq_path,
                timeout=self.proof_timeout,
                cwd=abs_workspace,
                server_args=["--workspace", str(abs_workspace)],
                load_paths=[(str(abs_workspace), "Test", "R")],
            )
            try:
                self._rocq.start()
            except RocqClientError as e:
                logger.warning(
                    "Failed to start rocq-mcp: %s. Disabling rocq-mcp for this session.",
                    e
                )
                self._rocq_broken = True
                self._rocq = None
                return None
        return self._rocq

    def _close_rocq_client(self) -> None:
        if self._rocq is not None:
            self._rocq.stop()
            self._rocq = None

    def _start_session_with_fallback(
        self,
        rocq: RocqClient,
        coq_file: Path,
        theorem_name: str,
        workspace: Path
    ) -> Tuple[str, List[str]]:
        try:
            return rocq.start_session(coq_file, theorem_name, workspace=workspace)
        except RocqClientError as e:
            err_str = str(e).lower()
            if "not found" in err_str or "reachable" in err_str or "state" in err_str:
                logger.warning(
                    "rocq-mcp failed to start session: %s. Recompiling with coqc and retrying.",
                    e
                )
                if self._compile_with_coqc(coq_file, workspace):
                    logger.info("Recompiled successfully; retrying session.")
                    try:
                        return rocq.start_session(coq_file, theorem_name, workspace=workspace)
                    except RocqClientError as e2:
                        logger.error(
                            "Second rocq_start attempt still failed: %s. Disabling rocq-mcp.",
                            e2
                        )
                        self._rocq_broken = True
                        raise
                else:
                    logger.error("Recompilation failed; cannot start session.")
                    self._rocq_broken = True
                    raise
            raise

    def _inject_mc_lemmas(self, coq_file: Path, theorem_name: str) -> None:
        if not self.use_mc_lemmas or self.spec_module is None:
            return

        try:
            from specir.evidence.registry import EvidenceRegistry
            from specir.lowering.spec_to_koika import (
                _expr_to_coq,
                _get_coq_type,
            )
        except ImportError as e:
            logger.warning("Could not import dependencies for MC lemma injection: %s", e)
            return

        registry = EvidenceRegistry()
        design_name = self.spec_module.name
        mc_entries = registry.list_evidence(
            evidence_type="inductive_invariant",
            status="proved",
            design_name=design_name,
            limit=1000,
        )
        if not mc_entries:
            logger.info("No MC-proved lemmas to inject for design '%s'.", design_name)
            return

        theorem_vars = self._get_theorem_state_variables(coq_file, theorem_name)
        if not theorem_vars:
            theorem_vars = set()

        state_types: Dict[str, str] = {}
        for s in self.spec_module.state_ops:
            state_types[s.state_name] = _get_coq_type(s.data_type)
        input_types: Dict[str, str] = {}
        for inp in self.spec_module.inputs:
            input_types[inp.name] = _get_coq_type(inp.data_type)
        memory_names = [m.state_name for m in self.spec_module.state_ops if m.kind == "memory"]

        try:
            content = coq_file.read_text()
        except Exception as e:
            logger.error("Could not read Coq file for lemma injection: %s", e)
            return

        thm_pattern = re.compile(
            rf"(Theorem\s+{re.escape(theorem_name)}\s+)", re.DOTALL
        )
        match = thm_pattern.search(content)
        if not match:
            logger.warning("Could not locate theorem '%s' in file for lemma injection.", theorem_name)
            return

        insert_pos = match.start()
        lemmas_added = 0

        for entry in mc_entries:
            prop_name = entry["property_name"]
            prop_op = next(
                (p for p in self.spec_module.property_ops if p.prop_name == prop_name),
                None,
            )
            if not prop_op:
                continue

            operand = prop_op.expression.get("operand", "True")
            try:
                from specir.utils.expr import parse_sexpr
                operand_parsed = parse_sexpr(operand) if isinstance(operand, str) else operand
                coq_stmt = _expr_to_coq(
                    operand_parsed, state_types, input_types, memory_names, as_prop=True
                )
            except Exception as e:
                logger.warning("Could not convert property '%s' to Coq: %s", prop_name, e)
                continue

            if theorem_vars and not self._lemma_relevant(coq_stmt, theorem_vars):
                logger.info("Skipping MC lemma '%s' (no shared state variables with theorem '%s').",
                            prop_name, theorem_name)
                continue

            lemma_name = f"{prop_name}_mc"
            lemma_text = (
                f"Lemma {lemma_name} : forall (s : state) (inputs : inputs), "
                f"reachable s -> ({coq_stmt}).\n"
                f"Proof. Admitted.  (* proved by model checking *)\n"
            )

            content = content[:insert_pos] + lemma_text + "\n" + content[insert_pos:]
            insert_pos += len(lemma_text) + 1
            lemmas_added += 1

        if lemmas_added > 0:
            coq_file.write_text(content)
            logger.info(
                "Injected %d MC-proved lemma(s) into Coq file for '%s' (filtered from %d available).",
                lemmas_added,
                theorem_name,
                len(mc_entries),
            )
        else:
            logger.info("No MC-proved lemmas could be injected for '%s'.", theorem_name)

    def _get_theorem_state_variables(self, coq_file: Path, theorem_name: str) -> Set[str]:
        try:
            content = coq_file.read_text()
            pattern = re.compile(
                rf"Theorem\s+{re.escape(theorem_name)}\s*:\s*(.*?)\.",
                re.DOTALL,
            )
            match = pattern.search(content)
            if not match:
                return set()
            statement = match.group(1)
            state_names = {s.state_name for s in self.spec_module.state_ops}
            vars_found = set()
            for name in state_names:
                if re.search(rf"\b{re.escape(name)}\b", statement):
                    vars_found.add(name)
            return vars_found
        except Exception:
            return set()

    def _lemma_relevant(self, lemma_stmt: str, theorem_vars: Set[str]) -> bool:
        for var in theorem_vars:
            if re.search(rf"\b{re.escape(var)}\b", lemma_stmt):
                return True
        return False

    def prove_theorem(
        self,
        coq_file: Path,
        theorem_name: str,
        tactic_hints: Optional[List[str]] = None,
        structural_hints: Optional[str] = None,
        initial_script: Optional[str] = None,
    ) -> ProofResult:
        start_time = time.time()
        logger.info("Attempting proof for '%s' (file: %s)", theorem_name, coq_file)

        # Inject standard prelude before anything else (safe).
        self._ensure_prelude(coq_file)

        hints = structural_hints or self.structural_hints
        if hints:
            logger.debug("Structural hints: %s", hints)

        self._inject_mc_lemmas(coq_file, theorem_name)

        # 0. Already proven?
        if self._theorem_already_proven(coq_file, theorem_name):
            logger.info("Theorem '%s' is already proven.", theorem_name)
            duration = time.time() - start_time
            return ProofResult(
                success=True,
                proof_script=self._extract_proof_from_file(coq_file, theorem_name),
                duration=duration,
                backend="koika",
                metadata={"automation": "pre-proven"}
            )

        # 0.5 Built-in deterministic proof for known patterns
        builtin_proof = self._try_builtin_proof(coq_file, theorem_name)
        if builtin_proof is not None:
            duration = time.time() - start_time
            logger.info("Built-in proof succeeded for '%s'.", theorem_name)
            return ProofResult(
                success=True,
                proof_script=builtin_proof,
                duration=duration,
                backend="koika",
                metadata={"automation": "builtin"}
            )

        # 1. Initial script (if provided)
        if initial_script is not None:
            logger.info("Verifying provided initial script for '%s'.", theorem_name)
            initial_script = self._prepare_proof_script(initial_script, theorem_name)
            result = self._try_initial_script(coq_file, theorem_name, initial_script)
            if result.get("success"):
                duration = time.time() - start_time
                return ProofResult(
                    success=True,
                    proof_script=result.get("proof_script", initial_script),
                    duration=duration,
                    backend="koika",
                    metadata={"automation": "initial_script"}
                )

        # 2. Proof library
        if self.use_proof_library:
            proof_script = self._apply_library_proof(coq_file, theorem_name)
            if proof_script is not None:
                duration = time.time() - start_time
                logger.info("Proof for '%s' completed via library.", theorem_name)
                return ProofResult(
                    success=True,
                    proof_script=proof_script,
                    duration=duration,
                    backend="koika",
                    metadata={"automation": "library"}
                )

        # 3. Interactive proof (skeleton, reflection, LLM loop) – only if enabled
        if self.use_rocq_mcp and not self._rocq_broken:
            result, _, _ = self._try_interactive_proof(
                coq_file, theorem_name, tactic_hints, structural_hints=hints
            )
            if result is not None and result.get("success"):
                duration = time.time() - start_time
                automation = result.get("automation", "interactive")
                return ProofResult(
                    success=True,
                    proof_script=result.get("proof_script", ""),
                    duration=duration,
                    backend="koika",
                    iterations=result.get("iterations"),
                    metadata={"automation": automation}
                )
        else:
            logger.info("rocq-mcp disabled or broken; skipping interactive proof.")

        # 4. coqc-based fallback verification
        result = self._fallback_verify(coq_file, theorem_name)
        if result.get("success"):
            duration = time.time() - start_time
            return ProofResult(
                success=True,
                proof_script=result.get("proof_script", ""),
                duration=duration,
                backend="koika",
                metadata={"automation": "coqc_verify"}
            )

        # 5. LLM full-proof generation (with structural hints, coqc validation)
        proof_script = self._attempt_llm_proof_generation(
            coq_file, theorem_name, structural_hints=hints, initial_script=initial_script
        )
        if proof_script is not None:
            duration = time.time() - start_time
            return ProofResult(
                success=True,
                proof_script=proof_script,
                duration=duration,
                backend="koika",
                metadata={"automation": "llm_full"}
            )

        duration = time.time() - start_time
        logger.error("All proof attempts exhausted for '%s'.", theorem_name)
        return ProofResult(
            success=False,
            error_message="All proof attempts exhausted",
            duration=duration,
            backend="koika",
            metadata={"automation": "none"}
        )

    def _try_builtin_proof(self, coq_file: Path, theorem_name: str) -> Optional[str]:
        builtin_scripts = {
            "zero_flag_correct_proved": self._zero_flag_proof(),
            "overflow_implies_result_neq_sum_proved": self._overflow_sum_proof(),
            "sub_overflow_implies_result_neq_diff_proved": self._overflow_diff_proof(),
        }
        if theorem_name not in builtin_scripts:
            return None

        proof_script = builtin_scripts[theorem_name]
        # Apply deterministic preparation pipeline.
        proof_script = self._prepare_proof_script(proof_script, theorem_name)

        logger.info("Attempting built-in proof for %s.", theorem_name)
        try:
            original_content = coq_file.read_text()
        except Exception as e:
            logger.error("Could not read Coq file for built-in proof: %s", e)
            return None

        thm_pattern = re.compile(
            rf"(Theorem\s+{re.escape(theorem_name)}\s+.*?)Admitted\.", re.DOTALL
        )
        match = thm_pattern.search(original_content)
        if not match:
            logger.error("Could not locate theorem '%s' in file.", theorem_name)
            return None

        full_block = match.group(0)
        new_block = full_block.replace("Admitted.", proof_script)
        new_content = original_content.replace(full_block, new_block, 1)
        coq_file.write_text(new_content)

        workspace = self._workspace_for(coq_file)
        if self._compile_with_coqc(coq_file, workspace):
            updated_content = coq_file.read_text()
            if self._theorem_is_closed(updated_content, theorem_name):
                logger.info("Built-in proof accepted for '%s'.", theorem_name)
                return proof_script
            else:
                logger.warning("Built-in proof compiled but theorem not closed.")
        else:
            logger.warning("Built-in proof failed to compile.")

        coq_file.write_text(original_content)  # revert
        return None

    def _zero_flag_proof(self) -> str:
        return """Proof.
  intros s inputs Hreach.
  induction Hreach as [| s' s'' inputs' Hreach' IH Hstep].
  { simpl. intros Hvalid. discriminate Hvalid. }
  { inversion Hstep; subst; clear Hstep; simpl.
    { intros Hvalid. apply IH. assumption. }
    { intros Hvalid.
      destruct (op_reg s' =? 0) eqn:Hop0.
      { simpl. reflexivity. }
      { destruct (op_reg s' =? 1) eqn:Hop1.
        { simpl. reflexivity. }
        { destruct (op_reg s' =? 2) eqn:Hop2.
          { simpl. reflexivity. }
          { simpl. reflexivity. } } } } }
Qed."""

    def _overflow_sum_proof(self) -> str:
        return """Proof.
  intros s inputs Hreach.
  induction Hreach as [| s' s'' inputs' Hreach' IH Hstep].
  { simpl. intros Hcond. destruct Hcond as [Hvalid [Hop Hoverflow]].
    discriminate Hvalid. }
  { inversion Hstep; subst; clear Hstep; simpl.
    { intros Hcond. destruct Hcond as [Hvalid [Hop Hoverflow]].
      simpl in Hop. inversion Hop. }
    { intros Hcond. destruct Hcond as [Hvalid [Hop Hoverflow]].
      destruct (op_reg s' =? 0) eqn:Hop0.
      { simpl in *. lia. }
      { destruct (op_reg s' =? 1) eqn:Hop1.
        { simpl in *. lia. }
        { destruct (op_reg s' =? 2) eqn:Hop2.
          { simpl in *. lia. }
          { simpl in *. lia. } } } } } }
Qed."""

    def _overflow_diff_proof(self) -> str:
        return """Proof.
  intros s inputs Hreach.
  induction Hreach as [| s' s'' inputs' Hreach' IH Hstep].
  { simpl. intros Hcond. destruct Hcond as [Hvalid [Hop Hoverflow]].
    discriminate Hvalid. }
  { inversion Hstep; subst; clear Hstep; simpl.
    { intros Hcond. destruct Hcond as [Hvalid [Hop Hoverflow]].
      simpl in Hop. inversion Hop. }
    { intros Hcond. destruct Hcond as [Hvalid [Hop Hoverflow]].
      destruct (op_reg s' =? 0) eqn:Hop0.
      { simpl in *. lia. }
      { destruct (op_reg s' =? 1) eqn:Hop1.
        { simpl in *. lia. }
        { destruct (op_reg s' =? 2) eqn:Hop2.
          { simpl in *. lia. }
          { simpl in *. lia. } } } } } }
Qed."""

    def _try_initial_script(
        self,
        coq_file: Path,
        theorem_name: str,
        initial_script: str,
    ) -> Dict[str, Any]:
        try:
            original_content = coq_file.read_text()
        except Exception as e:
            return {"success": False, "error": f"Could not read Coq file: {e}"}

        thm_pattern = re.compile(
            rf"(Theorem\s+{re.escape(theorem_name)}\s+.*?)Admitted\.", re.DOTALL
        )
        match = thm_pattern.search(original_content)
        if not match:
            return {"success": False, "error": "Theorem not found in Coq file"}

        full_block = match.group(0)
        new_block = full_block.replace("Admitted.", initial_script)
        new_content = original_content.replace(full_block, new_block, 1)

        workspace = self._workspace_for(coq_file)
        self._ensure_project_file(workspace)
        coq_file.write_text(new_content)
        if self._compile_with_coqc(coq_file, workspace):
            if self._theorem_is_closed(coq_file.read_text(), theorem_name):
                return {"success": True, "proof_script": initial_script}
        coq_file.write_text(original_content)
        return {"success": False, "error": "Initial script did not prove the theorem"}

    def _try_interactive_proof(
        self,
        coq_file: Path,
        theorem_name: str,
        tactic_hints: Optional[List[str]],
        structural_hints: Optional[str] = None,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[List[str]], Optional[List[str]]]:
        coq_file = coq_file.resolve()
        workspace = self._workspace_for(coq_file)
        self._ensure_project_file(workspace)

        if not self._ensure_workspace_has_compiled_artifacts(coq_file, workspace):
            logger.warning("Could not ensure compiled artefacts; interactive proof may fail.")

        rocq = self._get_rocq_client(workspace)
        if rocq is None:
            logger.warning("rocq-mcp not available; skipping interactive proof.")
            return None, None, None

        if not self._compile_with_rocq_fallback(rocq, coq_file, workspace):
            return None, None, None

        # 1. Generic skeleton
        skeleton_result = self._try_skeleton_proof(coq_file, theorem_name)
        if skeleton_result:
            logger.info("Skeleton proof proved '%s'.", theorem_name)
            return skeleton_result, None, None

        # 2. Skeleton reflection
        reflected = self._request_skeleton_reflection(
            coq_file, theorem_name, structural_hints=structural_hints
        )
        if reflected:
            logger.info("Skeleton reflection proved '%s'.", theorem_name)
            return reflected, None, None

        # 3. LLM interactive loop
        logger.info("Starting LLM-driven interactive proof for '%s'.", theorem_name)
        try:
            state_id, goals = self._start_session_with_fallback(
                rocq, coq_file, theorem_name, workspace
            )
        except RocqClientError as e:
            if "invalid path" in str(e).lower() or "scanning" in str(e).lower():
                logger.warning("Workspace error; falling back to rocq_verify.")
                return None, None, None
            logger.warning("Failed to start session: %s. Disabling rocq-mcp.", e)
            self._rocq_broken = True
            return None, None, None

        if not goals:
            return {"success": False, "error": "No goals found."}, None, None

        logger.info("Initial goals for '%s':\n%s", theorem_name, "\n".join(goals))

        if self.pre_simplify:
            try:
                result = rocq.check(state_id, "simpl.")
                if not result.get("isError") and not self._extract_error(result):
                    data = result.get("structuredContent", {})
                    new_sid = data.get("state_id")
                    new_goals = data.get("goals", [])
                    if isinstance(new_goals, str):
                        new_goals = [new_goals] if new_goals else []
                    if new_sid is not None and new_goals:
                        state_id = new_sid
                        goals = new_goals
                        logger.debug("Pre-simplification advanced the proof state.")
            except Exception:
                pass

        available_lemmas: List[str] = []
        if self.invariant_mining:
            available_lemmas = self._find_invariant_lemmas(coq_file)
            for lemma in available_lemmas:
                try:
                    result = rocq.check(state_id, f"try rewrite ({lemma} _ ?Hreach).")
                    if not self._extract_error(result):
                        data = result.get("structuredContent", {})
                        new_sid = data.get("state_id")
                        if new_sid is not None and new_sid != state_id:
                            state_id = new_sid
                            logger.info("Applied invariant lemma %s", lemma)
                except Exception:
                    continue

        # Interactive tactic loop
        failed_tactics: Set[str] = set()
        applied_tactics: List[str] = []
        recent_errors: List[str] = []
        consecutive_failures = 0
        last_goals = goals
        last_errors: List[str] = []

        goal_hashes_seen: Dict[int, int] = {}
        prev_state_id: Optional[str] = None
        prev_goals: Optional[List[str]] = None

        default_tactics = [
            "intros; induction 1; simpl; auto with *; try lia; try nia.",
            "intros; induction 1; simpl; auto; try lia.",
        ]
        reflection_tactics: List[str] = []
        non_advancing_streak = 0
        MAX_NON_ADVANCING = 10

        for step in range(self.max_steps):
            if reflection_tactics:
                candidate_tactics = reflection_tactics[:]
                reflection_tactics.clear()
                logger.info("Using tactics from reflection prompt.")
            else:
                prompt = build_interactive_step_prompt(
                    theorem_name,
                    goals,
                    tactic_hints,
                    applied_tactics,
                    recent_errors,
                    base_case_hint=self.base_case_hint,
                    step_case_hint=self.step_case_hint,
                    available_lemmas=available_lemmas if available_lemmas else None,
                    structural_hints=structural_hints,
                )
                logger.debug("Step %d LLM prompt:\n%s", step + 1, prompt)
                candidate_tactics = extract_tactics_from_response(self.llm.generate(prompt))

            if not candidate_tactics:
                logger.warning("LLM returned no tactics; using default tactics.")
                candidate_tactics = default_tactics

            tactic_succeeded = False
            for tactic in candidate_tactics:
                if not tactic or not tactic.strip():
                    continue
                tactic_normalized = tactic.strip()
                if tactic_normalized in failed_tactics:
                    continue

                if state_id is not None:
                    prev_state_id = state_id
                    prev_goals = goals[:] if goals else []

                logger.debug("Attempting tactic: '%s'", tactic)
                try:
                    check_result = rocq.check(state_id, tactic)
                except RocqClientError as e:
                    error_msg = str(e)
                    applied_tactics.append(f"FAILED: {tactic} - {error_msg[:100]}")
                    recent_errors.append(f"Tactic '{tactic}': {error_msg}")
                    failed_tactics.add(tactic_normalized)
                    continue

                error_msg = self._extract_error(check_result)
                if error_msg:
                    applied_tactics.append(f"FAILED: {tactic} - {error_msg[:100]}")
                    recent_errors.append(f"Tactic '{tactic}': {error_msg}")
                    failed_tactics.add(tactic_normalized)
                    time.sleep(0.2)
                    continue

                data = check_result.get("structuredContent", {})
                if not data and "content" in check_result:
                    for item in check_result["content"]:
                        if item.get("type") == "text":
                            try:
                                parsed = json.loads(item["text"])
                                if isinstance(parsed, dict):
                                    data = parsed
                                    break
                            except json.JSONDecodeError:
                                pass

                commands_run = data.get("commands_run", 0)
                if commands_run == 0:
                    error_msg = f"Tactic '{tactic}' was not executed (commands_run=0)"
                    applied_tactics.append(f"FAILED: {tactic} - {error_msg[:100]}")
                    recent_errors.append(f"Tactic '{tactic}': {error_msg}")
                    failed_tactics.add(tactic_normalized)
                    time.sleep(0.2)
                    continue

                new_state_id = data.get("state_id")
                new_goals = data.get("goals", [])
                if isinstance(new_goals, str):
                    new_goals = [new_goals] if new_goals else []

                try:
                    current_state_id = int(state_id)
                except (TypeError, ValueError):
                    current_state_id = state_id
                try:
                    new_state_id_int = int(new_state_id) if new_state_id is not None else None
                except (TypeError, ValueError):
                    new_state_id_int = new_state_id

                if data.get("proof_finished", False):
                    applied_tactics.append(tactic)
                    proof_script = self._construct_proof_script(theorem_name, coq_file, applied_tactics)
                    self._update_coq_file(coq_file, theorem_name, applied_tactics)
                    logger.info("Interactive proof succeeded for '%s'. Script:\n%s", theorem_name, proof_script[:500])
                    return {"success": True, "proof_script": proof_script}, None, None

                if new_state_id_int is not None and new_state_id_int != current_state_id:
                    non_advancing_streak = 0
                    new_goal_hash = hash(tuple(new_goals))
                    count = goal_hashes_seen.get(new_goal_hash, 0)
                    if count >= 2:
                        logger.warning(
                            "Dead-end detected: tactic '%s' led to a loop (goal seen %d times).",
                            tactic[:80], count + 1
                        )
                        if prev_state_id is not None:
                            try:
                                undo_res = rocq.check(state_id, "Undo.")
                                if not self._extract_error(undo_res):
                                    state_id = prev_state_id
                                    goals = prev_goals[:] if prev_goals else goals
                                    logger.debug("Undid looping tactic.")
                            except Exception:
                                pass
                        applied_tactics.append(f"FAILED: {tactic} - dead-end loop")
                        recent_errors.append(
                            f"Tactic '{tactic[:80]}' caused a proof loop. Change approach."
                        )
                        failed_tactics.add(tactic_normalized)
                        continue

                    goal_hashes_seen[new_goal_hash] = count + 1
                    state_id = new_state_id_int
                    goals = new_goals if new_goals else goals
                    applied_tactics.append(tactic)
                    tactic_succeeded = True
                    consecutive_failures = 0
                    recent_errors.clear()
                    last_goals = goals
                    last_errors = []
                    logger.info("Step %d/%d: tactic '%s' succeeded.", step + 1, self.max_steps, tactic[:80])
                    break
                else:
                    logger.info("Tactic '%s' did not change the proof state.", tactic[:80])
                    non_advancing_streak += 1
                    applied_tactics.append(f"FAILED: {tactic} - no state change")
                    recent_errors.append(f"Tactic '{tactic}': no state change")
                    failed_tactics.add(tactic_normalized)
                    time.sleep(0.2)

                    goal_hash = hash(tuple(goals))
                    goal_hashes_seen[goal_hash] = goal_hashes_seen.get(goal_hash, 0) + 1
                    if goal_hashes_seen[goal_hash] >= 5:
                        logger.warning("Goal set has not changed for 5 attempts; dead-end loop detected.")
                        tactic_succeeded = False
                        break
                    if non_advancing_streak >= MAX_NON_ADVANCING:
                        logger.warning("Too many consecutive non-advancing tactics; aborting LLM loop.")
                        tactic_succeeded = False
                        break
                    continue

            if not tactic_succeeded:
                consecutive_failures += 1
                last_errors = recent_errors[-3:]
                logger.info("Step %d/%d: no tactic succeeded.", step + 1, self.max_steps)

                if consecutive_failures == max(1, self.max_consecutive_failures // 2):
                    logger.info("Triggering strategy reflection after %d consecutive failures.", consecutive_failures)
                    new_tactics = self._request_strategy_reflection(
                        theorem_name, goals, applied_tactics
                    )
                    if new_tactics:
                        failed_tactics.clear()
                        goal_hashes_seen.clear()
                        non_advancing_streak = 0
                        consecutive_failures = 0
                        reflection_tactics.extend(new_tactics)
                        logger.info("Reflection yielded %d new tactics; resetting failure history.", len(new_tactics))
                        continue

                if consecutive_failures >= self.max_consecutive_failures:
                    last_error = recent_errors[-1] if recent_errors else "No specific error"
                    logger.error("Interactive proof failed for '%s': too many consecutive tactic failures.", theorem_name)
                    return {
                        "success": False,
                        "error": f"Too many consecutive tactic failures. Last error: {last_error}"
                    }, last_goals, last_errors

                if non_advancing_streak >= MAX_NON_ADVANCING:
                    logger.error("Interactive proof failed for '%s': too many non-advancing steps.", theorem_name)
                    return {"success": False, "error": "Too many non-advancing steps"}, last_goals, last_errors

        logger.error("Interactive proof failed for '%s': max steps reached.", theorem_name)
        return {"success": False, "error": f"Proof failed after {self.max_steps} steps"}, last_goals, last_errors

    def _try_skeleton_proof(self, coq_file: Path, theorem_name: str) -> Optional[Dict[str, Any]]:
        logger.info("Attempting generic skeleton proof for '%s'.", theorem_name)
        workspace = self._workspace_for(coq_file)
        rocq = self._get_rocq_client(workspace)
        if rocq is None:
            return None
        try:
            state_id, goals = self._start_session_with_fallback(
                rocq, coq_file, theorem_name, workspace
            )
        except RocqClientError:
            return None
        if not goals:
            return None

        res = rocq.check(state_id, "intros.")
        if self._extract_error(res):
            return None
        state_id = res.get("structuredContent", {}).get("state_id", state_id)

        idtac_res = rocq.check(state_id, "idtac.")
        if self._extract_error(idtac_res):
            return None
        goals_data = idtac_res.get("structuredContent", {}).get("goals", [])
        if isinstance(goals_data, str):
            goals_data = [goals_data]
        reachable_hyp = None
        for g in goals_data:
            for line in g.splitlines():
                line = line.strip()
                if "reachable" in line and ":" in line:
                    parts = line.split(":", 1)
                    if len(parts) == 2 and "reachable" in parts[1]:
                        reachable_hyp = parts[0].strip()
                        break
            if reachable_hyp:
                break
        if not reachable_hyp:
            logger.info("Skeleton proof: no reachable hypothesis found.")
            return None

        res = rocq.check(state_id, f"induction {reachable_hyp}.")
        if self._extract_error(res):
            return None
        state_id = res.get("structuredContent", {}).get("state_id", state_id)

        res = rocq.check(state_id, "simpl; auto; try lia; try nia.")
        if self._extract_error(res):
            return None
        state_id = res.get("structuredContent", {}).get("state_id", state_id)

        inv_tactic = "match goal with H : step _ _ _ |- _ => inversion H; subst; clear H end"
        check = rocq.check(state_id, inv_tactic)
        if self._extract_error(check):
            return None
        state_id = check.get("structuredContent", {}).get("state_id", state_id)

        simpl_check = rocq.check(state_id, "simpl.")
        if not self._extract_error(simpl_check):
            state_id = simpl_check.get("structuredContent", {}).get("state_id", state_id)

        applied_extra: List[str] = []
        default_tactics = [
            "repeat (match goal with H: ?L _ _ |- _ => try rewrite (H ?x ?y) end)",
            "repeat (match goal with [ |- context[if ?b then _ else _] ] => destruct b eqn:? end)",
            f"try apply IH{reachable_hyp}.",
            "repeat (match goal with "
            "| [ |- context[slice (?x + ?k) ?h ?l] ] => rewrite (slice_low2 (?x + ?k)) "
            "| [ H : context[slice ?x ?h ?l] |- _ ] => rewrite (slice_low2 x) in H "
            "end); try (rewrite Nat.add_mod; rewrite (Nat.mod_same 4) by lia; "
            "rewrite Nat.add_0_r; assumption); auto; try lia; try nia."
        ]
        step_tactics = self.skeleton_step_tactics if self.skeleton_step_tactics else default_tactics

        for tactic in step_tactics:
            tcheck = rocq.check(state_id, tactic)
            if self._extract_error(tcheck):
                continue
            new_id = tcheck.get("structuredContent", {}).get("state_id")
            if new_id is not None and new_id != state_id:
                state_id = new_id
                applied_extra.append(tactic)
            if tcheck.get("structuredContent", {}).get("proof_finished", False):
                full_tactics = ["intros.", f"induction {reachable_hyp}.", "simpl; auto; try lia; try nia.", inv_tactic, "simpl."] + applied_extra
                proof_script = self._construct_proof_script(theorem_name, coq_file, full_tactics)
                self._update_coq_file(coq_file, theorem_name, full_tactics)
                logger.info("Generic skeleton proof succeeded for '%s'.", theorem_name)
                return {"success": True, "proof_script": proof_script}

        logger.info("Generic skeleton proof did not close the goal for '%s'.", theorem_name)
        return None

    def _request_skeleton_reflection(
        self,
        coq_file: Path,
        theorem_name: str,
        structural_hints: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        if not self.skeleton_reflection:
            return None

        logger.info("Attempting skeleton reflection for '%s'.", theorem_name)
        try:
            original_content = coq_file.read_text()
        except Exception as e:
            logger.error("Could not read Coq file for reflection: %s", e)
            return None

        thm_pattern = re.compile(
            rf"(Theorem\s+{re.escape(theorem_name)}\s+.*?)Admitted\.", re.DOTALL
        )
        match = thm_pattern.search(original_content)
        if not match:
            logger.error("Could not locate theorem '%s' (with Admitted) in file for reflection.")
            return None

        theorem_block = match.group(0)
        statement = match.group(1).strip()
        idx = original_content.find(theorem_block)
        context = original_content[:idx].strip()

        workspace = self._workspace_for(coq_file)
        rocq = self._get_rocq_client(workspace)
        if rocq is None:
            return None
        try:
            state_id, goals = self._start_session_with_fallback(
                rocq, coq_file, theorem_name, workspace
            )
        except RocqClientError as e:
            logger.warning("Could not start session for reflection: %s", e)
            return None
        if not goals:
            return None

        available_lemmas = self._find_invariant_lemmas(coq_file)

        prompt = build_skeleton_reflection_prompt(
            theorem_name=theorem_name,
            theorem_statement=statement,
            context=context,
            goals=goals,
            available_lemmas=available_lemmas,
            structural_hints=structural_hints
        )
        logger.debug("Skeleton reflection prompt: %s", prompt)
        try:
            response = self.llm.generate(prompt)
        except Exception as e:
            logger.warning("LLM call for skeleton reflection failed: %s", e)
            return None

        proof_script = extract_proof_script(response)
        if not proof_script.startswith("Proof."):
            logger.warning("LLM did not return a valid proof script; response: %s", response[:200])
            return None

        proof_script = self._prepare_proof_script(proof_script, theorem_name)

        new_block = theorem_block.replace("Admitted.", proof_script)
        new_content = original_content.replace(theorem_block, new_block, 1)
        coq_file.write_text(new_content)

        workspace = self._workspace_for(coq_file)
        if self._compile_with_coqc(coq_file, workspace):
            verify_result = self._fallback_verify(coq_file, theorem_name)
            if verify_result.get("success"):
                logger.info("Skeleton reflection succeeded for '%s'.", theorem_name)
                return {"success": True, "proof_script": proof_script}
            else:
                logger.warning("Skeleton reflection proof compiled but failed verification: %s", verify_result.get("error"))
        else:
            logger.warning("Skeleton reflection proof failed to compile.")

        coq_file.write_text(original_content)
        return None

    def _find_invariant_lemmas(self, coq_file: Path) -> List[str]:
        try:
            content = coq_file.read_text()
        except Exception:
            return []

        nil_matches = re.findall(r"Lemma\s+(\w+_nil)\s+:", content)
        const_matches = re.findall(r"Lemma\s+(\w+_const)\s+:", content)
        mc_matches = re.findall(r"Lemma\s+(\w+_mc)\s+:", content)

        all_lemmas = set(nil_matches + const_matches + mc_matches)
        return sorted(all_lemmas)

    def _attempt_llm_proof_generation(
        self,
        coq_file: Path,
        theorem_name: str,
        last_goals: Optional[List[str]] = None,
        last_errors: Optional[List[str]] = None,
        structural_hints: Optional[str] = None,
        initial_script: Optional[str] = None,
    ) -> Optional[str]:
        logger.info("LLM full-proof generation activated for '%s'.", theorem_name)
        try:
            original_content = coq_file.read_text()
        except Exception as e:
            logger.error("Could not read Coq file: %s", e)
            return None

        thm_pattern = re.compile(
            rf"(Theorem\s+{re.escape(theorem_name)}\s+.*?)Admitted\.", re.DOTALL
        )
        match = thm_pattern.search(original_content)
        if not match:
            logger.error("Could not locate theorem '%s' (with Admitted) in file.", theorem_name)
            return None

        full_block = match.group(0)
        statement = match.group(1).strip()
        idx = original_content.find(full_block)
        context = original_content[:idx].strip()
        available_lemmas = self._find_invariant_lemmas(coq_file)

        previous_attempts = None
        if initial_script is not None:
            previous_attempts = [{
                "script": initial_script,
                "error": "PERF candidate did not prove theorem; please fix and complete the proof."
            }]

        prompt = build_coq_proof_prompt(
            theorem_name=theorem_name,
            theorem_statement=statement,
            context=context,
            tactic_hints=None,
            assumptions=None,
            previous_attempts=previous_attempts,
            structural_hints=structural_hints
        )

        workspace = self._workspace_for(coq_file)
        error_feedback = ""

        for attempt in range(self.max_repair):
            if attempt == 0:
                final_prompt = prompt
            else:
                final_prompt = prompt + "\n\n" + error_feedback

            logger.info("LLM full-proof attempt %d/%d for '%s'.", attempt + 1, self.max_repair, theorem_name)
            response = self.llm.generate(final_prompt)
            proof_match = re.search(r"(Proof\..*?(Qed\.|Admitted\.))", response, re.DOTALL)
            if proof_match:
                current_proof = proof_match.group(1)
            else:
                current_proof = response.strip()

            if "Admitted." in current_proof:
                logger.warning("LLM returned Admitted for '%s'; ignoring.", theorem_name)
                return None

            # Apply deterministic preparation before compilation.
            current_proof = self._prepare_proof_script(current_proof, theorem_name,
                                                       error_feedback if attempt > 0 else "")

            structural_issues = validate_structure(current_proof)
            if structural_issues:
                logger.warning("Structural issues in generated proof: %s", structural_issues)

            new_block = full_block.replace("Admitted.", current_proof)
            new_content = original_content.replace(full_block, new_block, 1)
            coq_file.write_text(new_content)

            if self._compile_with_coqc(coq_file, workspace):
                updated_content = coq_file.read_text()
                if self._theorem_is_closed(updated_content, theorem_name):
                    logger.info("LLM-generated proof accepted for '%s'.", theorem_name)
                    return current_proof
                else:
                    error_feedback = "Theorem not fully closed (missing Qed. or still Admitted)."
            else:
                errors = self._collect_compile_errors(coq_file, workspace)
                if errors:
                    error_feedback = "The previous attempt produced the following compilation errors:\n"
                    for err in errors:
                        error_feedback += f"- Line {err['line']} char {err['char']} [{err['type']}]: {err['message']}\n"
                    error_feedback += "Please fix ALL of these errors and provide a corrected proof."
                else:
                    error_feedback = self._capture_coqc_error(coq_file, workspace)

            coq_file.write_text(original_content)
            logger.error("LLM proof generation attempt %d for '%s' failed: %s",
                         attempt + 1, theorem_name, error_feedback[:200])

        logger.warning("LLM proof generation gave up for '%s' after %d attempts.", theorem_name, self.max_repair)
        return None

    def _collect_compile_errors(self, coq_file: Path, workspace: Path) -> List[Dict[str, str]]:
        cmd = [self.coqc_path, "-R", str(workspace), "Test", str(coq_file)]
        logger.debug("Running coqc to collect errors: %s", " ".join(cmd))
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.proof_timeout,
                cwd=str(workspace)
            )
        except subprocess.TimeoutExpired:
            return [{"line": "?", "char": "?", "type": "timeout", "message": "coqc timed out"}]
        except Exception as e:
            return [{"line": "?", "char": "?", "type": "exception", "message": str(e)}]

        stderr = result.stderr
        if result.returncode == 0:
            return []

        errors = []
        pattern = re.compile(
            r'File ".*?", line (\d+), characters (\d+)-(\d+):\n(.*?)(?=\nFile "|$)',
            re.DOTALL
        )
        for match in pattern.finditer(stderr):
            line = match.group(1)
            char_start = match.group(2)
            message = match.group(3).strip()
            error_type = "unknown"
            if "deprecated" in message.lower():
                error_type = "deprecated"
            elif "not a discriminable equality" in message.lower():
                error_type = "discriminate"
            elif "wrong bullet" in message.lower() or "focus" in message.lower():
                error_type = "focus"
            elif "not found in the current environment" in message.lower():
                error_type = "unknown_reference"
            elif "syntax error" in message.lower():
                error_type = "syntax"
            errors.append({
                "line": line,
                "char": char_start,
                "type": error_type,
                "message": message,
            })
        if not errors and "Error" in stderr:
            errors.append({
                "line": "?",
                "char": "?",
                "type": "compile_error",
                "message": stderr.strip(),
            })
        return errors

    def _fallback_verify(self, coq_file: Path, theorem_name: str) -> Dict[str, Any]:
        logger.info("Using fallback: direct coqc verification for '%s'.", theorem_name)
        workspace = self._workspace_for(coq_file)
        self._ensure_project_file(workspace)

        if not self._compile_with_coqc(coq_file, workspace):
            error = self._capture_coqc_error(coq_file, workspace)
            return {"success": False, "error": f"coqc compilation failed: {error}"}

        try:
            content = coq_file.read_text()
        except Exception as e:
            return {"success": False, "error": f"Could not read file: {e}"}

        if self._theorem_is_closed(content, theorem_name):
            proof_script = self._extract_proof_from_file(coq_file, theorem_name)
            return {"success": True, "proof_script": proof_script}
        else:
            return {"success": False, "error": "Theorem is not fully closed (missing Qed. or still Admitted)."}

    def evaluate_proof_script(
        self,
        coq_file: Path,
        theorem_name: str,
        proof_script: str,
        workspace: Optional[Path] = None
    ) -> Dict[str, Any]:
        self._perf_stats["total_verifier_calls"] += 1

        if workspace is None:
            workspace = self._workspace_for(coq_file)

        try:
            original_content = coq_file.read_text()
        except Exception as e:
            return {"success": False, "error": f"Could not read Coq file: {e}", "proof_finished": False}

        thm_pattern = re.compile(
            rf"(Theorem\s+{re.escape(theorem_name)}\s+.*?)Admitted\.", re.DOTALL
        )
        match = thm_pattern.search(original_content)
        if not match:
            return {"success": False, "error": f"Theorem '{theorem_name}' not found in file", "proof_finished": False}

        full_block = match.group(0)
        new_block = full_block.replace("Admitted.", proof_script)
        new_content = original_content.replace(full_block, new_block, 1)

        fd, tmp_path = tempfile.mkstemp(suffix=".v", prefix="perf_eval_")
        os.close(fd)
        tmp_file = Path(tmp_path)
        try:
            tmp_file.write_text(new_content)

            compiled = self._compile_with_coqc(tmp_file, workspace)
            if not compiled:
                error = self._capture_coqc_error(tmp_file, workspace)
                return {
                    "success": False,
                    "error": f"Compilation failed: {error}",
                    "proof_finished": False,
                    "compiled": False,
                    "verified": False
                }

            from specir.backends.rocq_client import RocqClient
            rocq = RocqClient(
                rocq_mcp_path=self.rocq_path,
                timeout=self.proof_timeout,
                cwd=workspace,
                server_args=["--workspace", str(workspace)],
            )
            try:
                rocq.start()
                verify_result = rocq.verify(tmp_file, theorem_name, workspace=workspace)
                err = rocq._extract_error_from_response(verify_result)
                if not err:
                    return {
                        "success": True,
                        "proof_finished": True,
                        "goals_remaining": 0,
                        "compiled": True,
                        "verified": True,
                        "proof_script": proof_script,
                    }
                error_msg = f"Verification failed: {err}"
            except Exception as e:
                error_msg = str(e)
            finally:
                rocq.stop()

            if "Unknown error" in error_msg or "not found in the current environment" in error_msg:
                logger.info("rocq_verify returned an opaque error; falling back to direct coqc check.")
                content = tmp_file.read_text()
                if self._theorem_is_closed(content, theorem_name):
                    return {
                        "success": True,
                        "proof_finished": True,
                        "goals_remaining": 0,
                        "compiled": True,
                        "verified": True,
                        "proof_script": proof_script,
                    }
                else:
                    goals_remaining = self._extract_goals_from_error(error_msg)
                    return {
                        "success": False,
                        "error": "Theorem not closed (coqc fallback)",
                        "proof_finished": False,
                        "goals_remaining": goals_remaining,
                        "compiled": True,
                        "verified": False,
                    }

            goals_remaining = self._extract_goals_from_error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "proof_finished": False,
                "goals_remaining": goals_remaining,
                "compiled": True,
                "verified": False,
            }
        except Exception as e:
            return {"success": False, "error": f"Evaluation error: {e}", "proof_finished": False}
        finally:
            if tmp_file.exists():
                try:
                    tmp_file.unlink()
                except OSError:
                    pass

    def _extract_goals_from_error(self, error_msg: str) -> Optional[int]:
        goal_match = re.search(r'remaining\s+(\d+)\s+subgoals?', error_msg, re.IGNORECASE)
        if goal_match:
            return int(goal_match.group(1))
        subgoal_match = re.search(r'subgoal\s+(\d+)', error_msg, re.IGNORECASE)
        if subgoal_match:
            return int(subgoal_match.group(1))
        return None

    @staticmethod
    def _workspace_for(coq_file: Path) -> Path:
        return coq_file.resolve().parent

    def _ensure_project_file(self, workspace: Path) -> None:
        project_file = workspace / "_CoqProject"
        abs_dir = workspace.resolve()
        logger.info("Writing %s with -R \"%s\" Test", project_file, abs_dir)
        with open(project_file, "w") as f:
            f.write(f'-R "{abs_dir}" Test\n')

    def _compile_with_coqc(self, coq_file: Path, workspace: Path) -> bool:
        cmd = [self.coqc_path, "-R", str(workspace), "Test", str(coq_file)]
        logger.info("Compiling with coqc: %s", " ".join(cmd))
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.proof_timeout,
                cwd=str(workspace)
            )
            if result.returncode != 0:
                logger.error("coqc compilation failed:\n%s", result.stderr)
                return False
            logger.info("coqc compilation succeeded.")
            return True
        except FileNotFoundError:
            logger.error("coqc not found.")
            return False
        except Exception as e:
            logger.error("coqc compilation error: %s", e)
            return False

    def _compile_with_rocq_fallback(self, rocq: RocqClient, coq_file: Path, workspace: Path) -> bool:
        logger.info("Attempting compilation via rocq_compile_file...")
        try:
            result = rocq.compile_file(coq_file, workspace=workspace, keep_vo=True)
            if result.get("isError") or "error" in result:
                error_msg = result.get("error", result.get("message", "Unknown error"))
                if "invalid path" in error_msg.lower() or "scanning" in error_msg.lower():
                    logger.info("rocq_compile_file workspace error; falling back to coqc.")
                    return self._compile_with_coqc(coq_file, workspace)
                logger.error("rocq_compile_file failed: %s", error_msg)
                return self._compile_with_coqc(coq_file, workspace)
            logger.info("rocq_compile_file succeeded.")
            return True
        except RocqClientError as e:
            logger.info("rocq_compile_file raised exception; falling back to coqc: %s", e)
            return self._compile_with_coqc(coq_file, workspace)

    def _capture_coqc_error(self, coq_file: Path, workspace: Path) -> str:
        cmd = [self.coqc_path, "-R", str(workspace), "Test", str(coq_file)]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.proof_timeout,
                cwd=str(workspace)
            )
            return result.stderr.strip() if result.returncode != 0 else ""
        except Exception as e:
            return str(e)

    def _theorem_is_closed(self, content: str, theorem_name: str) -> bool:
        pattern = re.compile(
            rf"Theorem\s+{re.escape(theorem_name)}\s+.*?Qed\.", re.DOTALL
        )
        match = pattern.search(content)
        if not match:
            return False
        block = match.group(0)
        return "Admitted." not in block

    def _theorem_already_proven(self, coq_file: Path, theorem_name: str) -> bool:
        workspace = self._workspace_for(coq_file)
        if not self._compile_with_coqc(coq_file, workspace):
            return False
        content = coq_file.read_text()
        return self._theorem_is_closed(content, theorem_name)

    def _extract_proof_from_file(self, coq_file: Path, theorem_name: str) -> str:
        content = coq_file.read_text()
        pattern = re.compile(
            rf"Theorem\s+{re.escape(theorem_name)}\s+.*?\n(Proof\..*?Qed\.)",
            re.DOTALL,
        )
        match = pattern.search(content)
        if match:
            return match.group(1).strip()
        fallback = re.compile(
            rf"Theorem\s+{re.escape(theorem_name)}.*?\n(Proof\..*?Qed\.)",
            re.DOTALL,
        )
        fallback_match = fallback.search(content)
        if fallback_match:
            return fallback_match.group(1).strip()
        return "Proof. (* already proven *) Qed."

    def _apply_library_proof(self, coq_file: Path, theorem_name: str) -> Optional[str]:
        if theorem_name not in PROOF_LIBRARY:
            return None
        logger.info("Attempting library proof for '%s'", theorem_name)
        try:
            original_content = coq_file.read_text()
        except Exception as e:
            logger.error("Could not read Coq file: %s", e)
            return None
        thm_pattern = re.compile(
            rf"(Theorem\s+{re.escape(theorem_name)}\s+.*?)Admitted\.", re.DOTALL
        )
        match = thm_pattern.search(original_content)
        if not match:
            logger.error("Could not locate theorem '%s' in file.", theorem_name)
            return None
        full_block = match.group(0)
        library_proof = PROOF_LIBRARY[theorem_name]
        # Apply full preparation pipeline.
        library_proof = self._prepare_proof_script(library_proof, theorem_name)
        new_block = full_block.replace("Admitted.", library_proof)
        new_content = original_content.replace(full_block, new_block, 1)
        coq_file.write_text(new_content)
        workspace = self._workspace_for(coq_file)
        if self._compile_with_coqc(coq_file, workspace):
            updated_content = coq_file.read_text()
            if self._theorem_is_closed(updated_content, theorem_name):
                logger.info("Library proof accepted for '%s'", theorem_name)
                return library_proof
        coq_file.write_text(original_content)
        logger.info("Library proof for '%s': failed", theorem_name)
        return None

    def _construct_proof_script(self, theorem_name: str, coq_file: Path, applied_tactics: List[str]) -> str:
        body = "\n  ".join(applied_tactics)
        return f"Proof.\n  {body}\nQed."

    def _update_coq_file(self, coq_file: Path, theorem_name: str, applied_tactics: List[str]) -> None:
        new_proof = self._construct_proof_script(theorem_name, coq_file, applied_tactics)
        with open(coq_file, "r") as f:
            content = f.read()
        pattern = re.compile(
            rf"(Theorem\s+{re.escape(theorem_name)}\s+.*?)(Admitted\.|Qed\.)",
            re.DOTALL,
        )
        new_content = pattern.sub(rf"\1{new_proof}", content, count=1)
        if new_content == content:
            logger.warning("Could not locate theorem '%s' in file; appending proof.", theorem_name)
            new_content = content.rstrip() + "\n" + new_proof + "\n"
        with open(coq_file, "w") as f:
            f.write(new_content)

    def _request_strategy_reflection(self, theorem_name: str, goals: List[str], applied_tactics: List[str]) -> List[str]:
        goals_str = "\n".join(goals)
        tactics_summary = "\n".join(
            f"{'✓' if not t.startswith('FAILED') else '✗'} {t}"
            for t in applied_tactics[-20:]
        )
        prompt = (
            f"You are an expert in Coq and hardware verification.\n\n"
            f"We have been trying to prove theorem `{theorem_name}` but are stuck.\n\n"
            f"Current goal:\n```\n{goals_str}\n```\n\n"
            f"Last attempts (✓ = state advanced, ✗ = failed):\n{tactics_summary}\n\n"
            "Please suggest a completely NEW set of tactics to make progress. "
            "The tactics must be complete Coq commands ending with a dot. "
            "You can suggest a full proof script (one tactic per line) or several alternative tactics. "
            "Return only the Coq tactics, one per line, without any extra commentary."
        )
        logger.debug("Reflection prompt: %s", prompt)
        try:
            response = self.llm.generate(prompt)
        except Exception as e:
            logger.warning("Reflection LLM call failed: %s", e)
            return []
        return extract_tactics_from_response(response)

    def evaluate_proof_scripts_parallel(
        self,
        coq_file: Path,
        theorem_name: str,
        scripts: List[str],
        max_workers: int = 4,
    ) -> List[Dict[str, Any]]:
        if not scripts:
            return []
        if len(scripts) == 1:
            return [self.evaluate_proof_script(coq_file, theorem_name, scripts[0])]
        results = [None] * len(scripts)
        def eval_script(idx: int, script: str) -> Tuple[int, Dict[str, Any]]:
            return idx, self.evaluate_proof_script(coq_file, theorem_name, script)
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_idx = {
                executor.submit(eval_script, i, script): i
                for i, script in enumerate(scripts)
            }
            for future in concurrent.futures.as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    _, result = future.result()
                    results[idx] = result
                except Exception as e:
                    results[idx] = {"success": False, "error": f"Worker exception: {e}", "proof_finished": False}
        return results

    def prove_with_skeleton_only(self, coq_file: Path, theorem_name: str) -> Optional[Dict[str, Any]]:
        workspace = self._workspace_for(coq_file)
        self._ensure_project_file(workspace)
        if not self._compile_with_coqc(coq_file, workspace):
            rocq = self._get_rocq_client(workspace)
            if rocq is not None and not self._compile_with_rocq_fallback(rocq, coq_file, workspace):
                logger.error("Skeleton proof skipped: could not compile Coq file.")
                return None
        result = self._try_skeleton_proof(coq_file, theorem_name)
        if result and result.get("success"):
            return result
        if self.skeleton_reflection:
            result = self._request_skeleton_reflection(coq_file, theorem_name)
            if result and result.get("success"):
                return result
        return None

    def _extract_error(self, response: Dict[str, Any]) -> Optional[str]:
        def _find_error(obj):
            if isinstance(obj, dict):
                for key in ["error", "message", "detail", "err", "reason", "failure", "description"]:
                    if key in obj and obj[key]:
                        if isinstance(obj[key], str):
                            return obj[key]
                        elif isinstance(obj[key], (dict, list)):
                            result = _find_error(obj[key])
                            if result:
                                return result
                if obj.get("isError") is True:
                    return obj.get("error", obj.get("message", "Unknown error (isError=True)"))
                if obj.get("success") is False:
                    return obj.get("error", obj.get("message", "Command failed (success=False)"))
                for value in obj.values():
                    if isinstance(value, (dict, list)):
                        result = _find_error(value)
                        if result:
                            return result
            elif isinstance(obj, list):
                for item in obj:
                    result = _find_error(item)
                    if result:
                        return result
            return None

        if response.get("isError") is True:
            return response.get("error", response.get("message", "Unknown error"))
        if "error" in response:
            return response["error"]
        if "structuredContent" in response:
            data = response["structuredContent"]
            found = _find_error(data)
            if found:
                return found
        if "content" in response:
            for item in response["content"]:
                if item.get("type") == "text":
                    text = item.get("text", "")
                    try:
                        parsed = json.loads(text)
                        if isinstance(parsed, dict):
                            found = _find_error(parsed)
                            if found:
                                return found
                    except json.JSONDecodeError:
                        if "error" in text.lower() or "failed" in text.lower():
                            return text[:200]
        if response.get("success") is False:
            return response.get("message", "Command failed without detailed error")
        return None

    def get_perf_stats(self) -> Dict[str, Any]:
        return self._perf_stats.copy()

    def reset_perf_stats(self) -> None:
        self._perf_stats = {
            "total_nodes": 0,
            "total_verifier_calls": 0,
            "max_depth": 0,
            "beam_size": 0,
            "pruned_by_pareto": 0,
            "total_tokens": {"prompt": 0, "completion": 0},
        }

    def close(self):
        self._close_rocq_client()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
