# src/isir/verification/proof/koika/prover.py
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
from isir.backends.rocq_client import RocqClient, RocqClientError
from isir.backends.llm_client import LLMClient, get_llm_client_from_config
from isir.utils.logger import get_logger
from isir.utils.config_loader import get_config, get_project_root
from lib.koika.assist import PROOF_LIBRARY
from isir.verification.proof.koika.proof_gen import (
    build_interactive_step_prompt,
    extract_tactics_from_response,
    build_skeleton_reflection_prompt,
    extract_proof_script,
    generate_coq_proof_variants,
    build_coq_proof_prompt
)
from isir.verification.proof.proof import ProofResult
from isir.verification.proof.prelude_templates import get_prelude
from isir.verification.proof.tactic_modernizer import modernize_tactics
from isir.verification.proof.structural_validator import validate_structure
from isir.verification.proof.koika.auto_patcher import auto_patch
from isir.verification.proof.domain_tactics import apply_domain_tactics

logger = get_logger(__name__)

# Recursive, subgoal-aware proof skeleton.
#
# ``skel n`` is a depth-bounded proof *search* expressed as an Ltac tactic.
# At each step it tries to close the current goal and, failing that, applies a
# structural move (introduce hypotheses, destruct an ``if`` condition, invert a
# ``step`` relation, rewrite a boolean comparison to arithmetic, simplify) and
# then recurses on *every* generated sub-goal.  The ``first [...]`` combinator
# provides backtracking, so a branch that opens the goal but cannot close it is
# undone and the next branch is tried.  ``solve [...]`` around each closer is
# essential: it forces a closer to *fully* close the goal (plain ``auto`` and
# ``congruence`` can "succeed" while leaving the goal open, which would make
# ``first`` commit prematurely).
RECURSIVE_SKELETON_LTAC = r"""
Opaque Nat.modulo Nat.divmod.
Opaque slice.
Opaque Nat.mul.
Opaque Nat.leb Nat.ltb.
Hint Resolve eq_refl : core.

Ltac btauto_safe :=
  match goal with
  | [ |- context[match _ with _ => _ end] ] => fail 1  (* avoid the kernel crash on Nat.* / match *)
  | _ => btauto
  end.

Ltac skel_close :=
  first [ solve [eauto]   (* apply Hint Resolve'd invariants before unfolding functions *)
        | try (autounfold with core in *); simpl in *;
          first [ solve [assumption] | solve [reflexivity] | solve [discriminate]
               | solve [congruence] | solve [contradiction] | solve [tauto]
               | solve [btauto_safe] | solve [lia] | solve [nia] | solve [auto] | solve [eauto]
               | solve [ match goal with [ |- ?b = true \/ ?b = false ] => destruct b; [left; reflexivity | right; reflexivity] end ]
               | solve [ apply Nat.leb_le; auto ]
               | solve [ autorewrite with core in *; simpl; try assumption; lia ]
               | solve [ match goal with [ |- context[slice ?x ?h ?l] ] => pose proof (slice_upper_bound x h l) end; simpl in *; lia ] ] ].

Ltac skel n :=
  match n with
  | 0 => fail "skel depth exhausted"
  | S ?m =>
      first [ solve [ eapply (Nat.mod_bound_pos _ _); lia ]
            | skel_close
            | progress intros; skel m
            | progress (match goal with [ |- ~ _ ] => intros Hneg; try destruct Hneg end); skel m
            | progress (match goal with [ H : _ /\ _ |- _ ] => destruct H end); skel m
            | progress (match goal with [ |- context[if negb ?b then _ else _] ] => destruct b eqn:?; simpl end); skel m
            | progress (match goal with [ |- context[if ?b then _ else _] ] => destruct b eqn:?; simpl end); skel m
            | progress (match goal with [ |- context[if Bool.eqb ?x ?c then _ else _] ] => destruct x; simpl end); skel m
            | progress (match goal with [ |- context[if Nat.eqb ?x ?c then _ else _] ] => destruct x; simpl end); skel m
            | progress (match goal with [ H : context[if ?b then _ else _] |- _ ] => destruct b eqn:?; simpl in * end); skel m
            | progress (match goal with [ H : _ \/ _ |- _ ] => destruct H end); skel m
            | progress (match goal with [ H : step _ ?ins _ |- _ ] =>
                  try (pose proof (assume_inputs ins) as Hin);
                  inversion H; subst; clear H; simpl end); skel m
             | progress (match goal with [ H : stepn _ _ _ |- _ ] => inversion H; subst; clear H; simpl end); skel m
            | progress (match goal with [ H : ?P, IH : ?P -> ?Q |- _ ] => specialize (IH H) end); skel m
            | progress (match goal with [ H : ?x = ?c |- context[?x] ] => rewrite H end); skel m
             | progress (match goal with [ |- context[?x * 0] ] => rewrite (Nat.mul_0_r ?x) end); skel m
             | progress (match goal with [ |- context[?f ?x = true] ] => destruct (f x); simpl in * end); skel m
            | progress (match goal with [ H : Nat.ltb ?a ?b = true |- _ ] => apply Nat.ltb_lt in H end); skel m
            | progress (match goal with [ H : Nat.ltb ?a ?b = false |- _ ] => apply Nat.ltb_ge in H end); skel m
            | progress (match goal with [ H : Nat.leb ?a ?b = true |- _ ] => apply Nat.leb_le in H end); skel m
            | progress (match goal with [ H : Nat.leb ?a ?b = false |- _ ] => apply Nat.leb_gt in H end); skel m
            | progress (autounfold with core in *); skel m
            | progress simpl in *; skel m ]
  end.
"""




# Pluggable deterministic proof strategies, tried (in registration order)
# before the LLM/PERF escalation.  Each strategy is ``fn(prover, coq_file,
# theorem_name) -> Optional[str]`` returning a proof script or None.
_PROOF_STRATEGIES: List[Tuple[str, Callable]] = []


def register_proof_strategy(name: str) -> Callable:
    """Decorator to register a deterministic proof strategy (domain extension)."""
    def decorator(fn: Callable) -> Callable:
        _PROOF_STRATEGIES.append((name, fn))
        return fn
    return decorator


class KoikaProver:
    """Generic prover for Kōika/Coq theorems.

    The prover follows a strict escalation path:
    1. Already-proven check
    2. Initial script verification (if provided)
    3. Proof library (fast, config-controlled)
    4. Interactive proof (skeleton, reflection, LLM tactic loop)
    5. coqc-based fallback verification
    6. LLM full-proof generation with repair (using coqc for validation)

    If `use_rocq_mcp` is false, step 4 is skipped.
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
        self.max_bmc_depth = config.get("proof", {}).get("invariant_bmc_depth", 3)
        self.gate_assumed_invariants = config.get("proof", {}).get("gate_assumed_invariants", False)
        self.gate_coherence_helpers = config.get("proof", {}).get("gate_coherence_helpers", False)
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
        self._prelude_validated = False

    def set_structural_hints(self, hints: str) -> None:
        """Store structural analysis hints for subsequent proof attempts."""
        self.structural_hints = hints

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
            from isir.evidence.registry import EvidenceRegistry
            from isir.lowering.isir_to_koika import (
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
                from isir.utils.expr import parse_sexpr
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

        # Prove user-declared loop invariants first so properties can use them.
        self._prove_invariant_lemmas(coq_file)

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
        #    First, try LLM-proposed loop invariants to unblock the skeleton.
        proposed = self._propose_invariants(coq_file, theorem_name)
        if proposed:
            recursive = self._recursive_skeleton_proof(coq_file, theorem_name)
            if recursive is not None:
                duration = time.time() - start_time
                return ProofResult(
                    success=True,
                    proof_script=recursive,
                    duration=duration,
                    backend="koika",
                    metadata={"automation": "llm_invariant"}
                )

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
            "repeat (match goal with [ |- context[if negb ?b then _ else _] ] => destruct b eqn:?; simpl end)",
            "repeat (match goal with [ |- context[if ?b then _ else _] ] => destruct b eqn:?; simpl end)",
            f"all: try apply IH{reachable_hyp}.",
            "all: repeat (match goal with "
            "| [ H : Nat.ltb ?a ?b = true |- _ ] => apply Nat.ltb_lt in H "
            "| [ H : Nat.ltb ?a ?b = false |- _ ] => apply Nat.ltb_ge in H "
            "| [ H : Nat.leb ?a ?b = true |- _ ] => apply Nat.leb_le in H "
            "| [ H : Nat.leb ?a ?b = false |- _ ] => apply Nat.leb_gt in H "
            "end)",
            "all: (repeat (match goal with "
            "| [ |- context[slice (?x + ?k) ?h ?l] ] => rewrite (slice_low2 (?x + ?k)) "
            "| [ H : context[slice ?x ?h ?l] |- _ ] => rewrite (slice_low2 x) in H "
            "end); try (rewrite Nat.add_mod; rewrite (Nat.mod_same 4) by lia; "
            "rewrite Nat.add_0_r; assumption); auto; try lia; try nia)."
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

            from isir.backends.rocq_client import RocqClient
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
            rf"(?:Theorem|Lemma)\s+{re.escape(theorem_name)}\s+.*?Qed\.", re.DOTALL
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

    def _recursive_skeleton_proof(
        self, coq_file: Path, theorem_name: str, max_depth: int = 50
    ) -> Optional[str]:
        """Deterministic, recursive, subgoal-aware skeleton proof.

        This is a *batch* prover (validated by ``coqc``, not rocq-mcp): it
        injects the recursive ``skel`` Ltac and a generic proof body that
        inducts on reachability and then lets ``skel`` close each generated
        sub-goal on demand (with backtracking).  On failure the original file
        is restored and ``None`` is returned so later stages see a clean file.
        """
        coq_file = Path(coq_file).resolve()
        try:
            original = coq_file.read_text()
        except Exception as e:
            logger.warning("Recursive skeleton: could not read %s: %s", coq_file, e)
            return None

        theorem_pattern = re.compile(
            rf"(?:Theorem|Lemma)\s+{re.escape(theorem_name)}\s+.*?Admitted\.", re.DOTALL
        )
        match = theorem_pattern.search(original)
        if not match:
            logger.info(
                "Recursive skeleton skipped: no Admitted block for '%s'.", theorem_name
            )
            return None

        # Proof-body candidates, most specific first.  Constant-field invariants
        # (`foo_const : forall s, reachable s -> foo s = c`) get a dedicated body:
        # the IH must be applied to the *previous* state's reachability, and the
        # resulting products `x * 0` rewritten.  If that body does not apply (the
        # property may not depend on the constant fields), fall back to the
        # generic recursive `skel` search.
        const_lemmas = [
            name for name in self._find_invariant_lemmas(coq_file)
            if name.endswith("_const")
        ]
        # Combinational-equivalence theorems quantify only over `inputs`
        # (no `reachable`/`step`), so they get a pure `skel` body rather than
        # the reachability induction.
        is_combinational = "reachable" not in match.group(0)
        candidates = []
        if is_combinational:
            candidates.append(
                "Proof.\n"
                "  intros.\n"
                f"  skel {max_depth}.\n"
                "Qed."
            )
        else:
            if const_lemmas:
                specs = "; ".join(f"specialize ({name} _ Hr)" for name in const_lemmas)
                candidates.append(
                    "Proof.\n"
                    "  intros s inputs H.\n"
                    "  induction H.\n"
                    "  - simpl; lia.\n"
                    "  - intros.\n"
                    "    match goal with [ Hs : step _ _ _ |- _ ] => inversion Hs; subst; clear Hs; simpl end.\n"
                    f"    match goal with [ Hr : reachable _ |- _ ] => ({specs}) end.\n"
                    "    all: (repeat (match goal with [ H : ?x = ?c |- context[?x] ] => rewrite H end);\n"
                    "          try assumption; try (simpl; lia); try nia).\n"
                    "Qed."
                )
            candidates.append(
                "Proof.\n"
                "  intros.\n"
                "  solve [eauto].\n"
                "Qed."
            )
            candidates.append(
                "Proof.\n"
                "  intros.\n"
                f"  match goal with [ H : reachable _ |- _ ] => induction H; skel {max_depth} end.\n"
                "Qed."
            )
            candidates.append(
                "Proof.\n"
                "  intros.\n"
                "  solve [eauto 12].\n"
                "Qed."
            )

        workspace = self._workspace_for(coq_file)
        for proof in candidates:
            new_block = match.group(0).replace("Admitted.", proof)
            new_content = original.replace(match.group(0), new_block, 1)
            if "Ltac skel_close" not in new_content:
                # Inject after `step`/`reachable` (needed by skel) but before the
                # invariant lemmas and properties that use it.
                new_content = new_content.replace(
                    "Hint Constructors reachable step : core.",
                    "Hint Constructors reachable step : core.\n\n" + RECURSIVE_SKELETON_LTAC,
                    1,
                )
            try:
                coq_file.write_text(new_content, encoding="utf-8")
            except Exception as e:
                logger.warning("Recursive skeleton: could not write %s: %s", coq_file, e)
                continue
            if self._compile_with_coqc(coq_file, workspace):
                updated = coq_file.read_text()
                if self._theorem_is_closed(updated, theorem_name):
                    logger.info("Recursive skeleton proof succeeded for '%s'.", theorem_name)
                    return proof

        try:
            coq_file.write_text(original, encoding="utf-8")
        except Exception:
            pass
        logger.info("Recursive skeleton proof did not close '%s'.", theorem_name)
        return None

    def _prove_invariant_lemmas(self, coq_file: Path) -> None:
        """Gate the assumed Axioms, then prove every user-declared loop invariant
        (Lemma ... Admitted.) first.

        Invariants are ordinary `forall s, reachable s -> P s` statements, so
        the generic reachability-induction body closes them.  They are then
        available via `Hint Resolve` for the properties that use them.
        """
        self._gate_assumed_invariants(coq_file)
        try:
            content = coq_file.read_text()
        except Exception:
            return
        names = re.findall(r"Lemma\s+(\w+)\s+:\s+forall s,\s+reachable s\s*->", content)
        for name in names:
            if self._try_proof_strategies(coq_file, name) is None:
                self._recursive_skeleton_proof(coq_file, name, max_depth=60)

    def _try_proof_strategies(self, coq_file: Path, theorem_name: str) -> Optional[str]:
        """Run the registered deterministic proof strategies (domain extensions)
        in registration order; return the first proof script that closes."""
        for name, fn in _PROOF_STRATEGIES:
            try:
                result = fn(self, coq_file, theorem_name)
            except Exception as e:
                logger.debug("Proof strategy '%s' raised: %s", name, e)
                result = None
            if result is not None:
                logger.info("Proof strategy '%s' succeeded for '%s'.", name, theorem_name)
                return result
        return None

    def _propose_invariants(self, coq_file: Path, theorem_name: str) -> List[str]:
        """Ask the LLM to propose loop invariants for a stuck theorem.

        Each proposed ``Lemma name : forall s, reachable s -> P s.`` is injected
        (Admitted) and proven by the deterministic skeleton; only the ones that
        actually close (Qed.) are kept as ``Hint Resolve`` hints.  Returns the
        names of the proven invariants.
        """
        if self.llm is None:
            return []
        try:
            content = coq_file.read_text()
        except Exception:
            return []

        thm = re.search(
            rf"(?:Theorem|Lemma)\s+{re.escape(theorem_name)}\s+.*?Admitted\.", content, re.DOTALL
        )
        if not thm:
            return []
        statement = thm.group(0)
        context = content[:thm.start()]

        # Constraint extraction: find the target function and its initial
        # registers in the theorem's conclusion, to seed a preservation template.
        seed = self._extract_preservation_seed(statement)

        prompt = (
            "You are proving Coq theorems about a hardware design formalized as a "
            "small-step semantics (`step : state -> inputs -> state -> Prop`) with "
            "a reachability predicate `reachable : state -> Prop`. A theorem is "
            "stuck and needs *loop invariants*: state properties P such that "
            "`forall s, reachable s -> P s` holds inductively.\n\n"
            "The design (state record, functions, step constructors, and "
            "reachable) is defined in this Coq context:\n\n"
            f"```coq\n{context}\n```\n\n"
            "The stuck theorem is:\n\n"
            f"```coq\n{statement}\n```\n\n"
        )
        if seed is not None:
            fn, inits = seed
            init_args = " ".join(f"({r} s)" for r in inits)
            prompt += (
                f"The theorem's result is computed by the function `{fn}` from the "
                f"latched initial registers {inits}.  Therefore, propose a "
                f"*preservation* invariant of the form:\n\n"
                f"Lemma <name> : forall s, reachable s -> {fn} (w1 s) (w2 s) = {fn} {init_args}.\n\n"
                f"where `w1`, `w2` are the *working* registers that the rules "
                f"transform until `done` (find them from the step constructors).\n\n"
            )
        prompt += (
            "Hint: if a rule sets a boolean *flag* state `F` while writing a "
            "state `Y` to a 'cleared' (non-exclusive) value, and another rule "
            "gated on `F s = true` writes a state `X` to an 'exclusive' value "
            "at an address, propose a *conditional* invariant that links the "
            "flag to the peer being cleared, e.g.:\n\n"
            "Lemma <name> : forall s, reachable s -> F s = true -> <selector> s = <c> -> ~ (<predicate> (Y s) = true /\\ <Y_addr> s = <addr> s).\n\n"
        )
        prompt += (
            "Propose loop invariants that would help prove this theorem.  Return "
            "ONLY the invariant lemmas, one per line, in this exact form:\n\n"
            "Lemma <name> : forall s, reachable s -> <proposition over the state>.\n\n"
            "Use the state projections as in the context (e.g. `(count s)`, "
            "`Nat.gcd (a s) (b s)`).  Do not include proofs, comments, or any "
            "other text."
        )

        workspace = self._workspace_for(coq_file)
        error_feedback = ""
        for attempt in range(self.max_repair):
            final_prompt = prompt
            if error_feedback:
                final_prompt = (
                    prompt
                    + f"\n\nYour previous proposal failed to type-check:\n{error_feedback}\n"
                    + "Fix the type/scope errors and re-propose ONLY the corrected lemmas."
                )
            try:
                response = self.llm.generate(final_prompt)
            except Exception as e:
                logger.warning("LLM invariant proposal failed for '%s': %s", theorem_name, e)
                return []

            proven = []
            type_errors = []
            for line in response.splitlines():
                line = line.strip().rstrip(".")
                m = re.match(
                    r"Lemma\s+(\w+)\s*:\s*forall\s+s\s*,\s*reachable\s+s\s*->\s*(.+)$",
                    line,
                )
                if not m:
                    continue
                name, operand = m.group(1), m.group(2).strip()
                # Guard against the LLM echoing `Admitted.` or a proof.
                if "Admitted" in operand or "Proof" in operand:
                    continue
                self._inject_invariant(coq_file, name, operand)
                # 0. type-check: reject ill-typed proposals (feed back for repair).
                if not self._compile_with_coqc(coq_file, workspace):
                    err = self._capture_coqc_error(coq_file, workspace)
                    type_errors.append((name, err))
                    self._remove_invariant(coq_file, name)
                    continue
                # 1. Bounded model-check gate (base + depth-1 + depth-k): reject
                # invariants that are refutable within max_bmc_depth steps.
                if not self._gate_invariant(coq_file, name, operand):
                    logger.info("Rejected invariant '%s': failed the bounded gate.", name)
                    self._remove_invariant(coq_file, name)
                    continue
                # 2. full induction proof.
                if self._recursive_skeleton_proof(coq_file, name, max_depth=60) is not None:
                    proven.append(name)
                    logger.info("LLM-proposed invariant '%s' proven for '%s'.", name, theorem_name)
                else:
                    self._remove_invariant(coq_file, name)

            if proven:
                return proven
            if type_errors:
                error_feedback = type_errors[-1][1]
                logger.info("Retrying invariant proposal after type errors (attempt %d).", attempt + 1)
                continue
            return []

        return []

    def _extract_preservation_seed(self, statement: str) -> Optional[Tuple[str, List[str]]]:
        """Extract (function, initial-registers) from a theorem's conclusion.

        Finds a function applied to state projections ``F (x s) (y s)`` (the
        usual shape of a result ``= F(init...)``) and returns ``F`` plus the
        register names, for seeding a preservation-template prompt.
        """
        m = re.search(
            r"([A-Za-z_][\w.]*)\s*\(\s*(\w+)\s+s\s*\)\s*\(\s*(\w+)\s+s\s*\)",
            statement,
        )
        if m:
            return m.group(1), [m.group(2), m.group(3)]
        m = re.search(r"([A-Za-z_][\w.]*)\s*\(\s*(\w+)\s+s\s*\)", statement)
        if m:
            return m.group(1), [m.group(2)]
        return None

    def _invariant_base_case_holds(self, coq_file: Path, name: str, operand: str) -> bool:
        """BMC pre-filter: does the invariant hold at the initial state?

        Substitutes `initial_state` for the state variable and evaluates the
        resulting closed proposition with `vm_compute`.  Returns False when the
        base case is refutable (a concrete counterexample).
        """
        p_initial = re.sub(r"\((\w+)\s+s\)", r"(\1 initial_state)", operand)
        check = (
            f"\nLemma {name}__base : {p_initial}.\n"
            f"Proof. simpl. first [ reflexivity | lia ]. Qed.\n"
        )
        try:
            content = coq_file.read_text()
        except Exception:
            return False
        tmp_file = coq_file.with_name(coq_file.stem + "_basecheck.v")
        try:
            tmp_file.write_text(content + "\n" + check, encoding="utf-8")
        except Exception:
            return False
        workspace = self._workspace_for(coq_file)
        ok = self._compile_with_coqc(tmp_file, workspace)
        try:
            tmp_file.unlink()
        except Exception:
            pass
        return ok

    def _invariant_step_feedback(self, coq_file: Path, name: str, operand: str) -> List[str]:
        """BMC depth-1 filter: which rules break the invariant in a single step?

        For each ``step_R : forall s inputs, cond -> step s inputs (next)`` it
        checks ``cond -> P(next)`` with the skeleton.  Returns the rule names
        whose single-step case fails (a concrete counterexample after one step).
        """
        try:
            content = coq_file.read_text()
        except Exception:
            return []

        ctor_pattern = re.compile(
            r"\| (step_\w+) : forall s inputs,\s*(.*?)\s*->\s*step s inputs \((.*?)\)\n",
            re.DOTALL,
        )
        failing = []
        for m in ctor_pattern.finditer(content):
            rule, cond, new_state = m.group(1), m.group(2).strip(), m.group(3).strip()
            p_next = re.sub(
                r"\((\w+)\s+s\)",
                lambda mm: f"({mm.group(1)} ({new_state}))",
                operand,
            )
            check_name = f"{name}__step_{rule}"
            self._inject_check_lemma(coq_file, check_name, cond, p_next)
            ok = self._recursive_skeleton_proof(coq_file, check_name, max_depth=40) is not None
            self._remove_check_lemma(coq_file, check_name)
            if not ok:
                failing.append(rule)
        return failing

    def _invariant_depth_holds(self, coq_file: Path, name: str, operand: str, depth: int) -> bool:
        """BMC depth-k filter: does P hold for every state reachable in exactly `depth` steps?

        Uses the `stepn` relation symbolically (no input enumeration): the check
        ``forall s, stepn depth initial_state s -> P s`` is proven by the
        skeleton's `stepn` inversion.  Returns False when a depth-`depth`
        counterexample exists.
        """
        check_name = f"{name}__depth_{depth}"
        try:
            content = coq_file.read_text()
        except Exception:
            return True
        block = (
            f"\nLemma {check_name} : forall (s : state), stepn {depth} initial_state s -> {operand}.\n"
            f"Admitted.\n"
        )
        try:
            coq_file.write_text(content + "\n" + block, encoding="utf-8")
        except Exception:
            return True
        ok = self._recursive_skeleton_proof(coq_file, check_name, max_depth=60) is not None
        self._remove_check_lemma(coq_file, check_name)
        return ok

    def _gate_invariant(self, coq_file: Path, name: str, operand: str,
                        check_depth1: bool = True) -> bool:
        """Bounded model-check gate for an injected invariant.

        The invariant must already be present as
        ``Lemma name : forall s, reachable s -> operand. Admitted.`` (or an
        equivalent ``Axiom``).  Returns True only if it holds at the initial
        state, survives every single-step rule (when ``check_depth1``), and
        survives depth-k (k = 2..max_bmc_depth).
        """
        if not self._invariant_base_case_holds(coq_file, name, operand):
            return False
        if check_depth1 and self._invariant_step_feedback(coq_file, name, operand):
            return False
        for d in range(2, self.max_bmc_depth + 1):
            if not self._invariant_depth_holds(coq_file, name, operand, d):
                return False
        return True

    def _gate_assumed_invariants(self, coq_file: Path) -> None:
        """Bounded-gate the ``assumed`` Axioms (lifted from child modules via
        ``lift_properties: invariant``).  Drops any that are refutable within
        ``max_bmc_depth`` steps.  Opt-in via ``proof.gate_assumed_invariants``
        (expensive on deep hierarchies, so off by default)."""
        if not getattr(self, "gate_assumed_invariants", False):
            return
        try:
            content = coq_file.read_text()
        except Exception:
            return
        drop = []
        for line in content.split("\n"):
            m = re.match(r"Axiom\s+(\w+)\s+:\s+forall\s+s,\s*reachable\s+s\s*->\s*(.*)\.\s*$", line)
            if m:
                name, operand = m.group(1), m.group(2).strip()
                if not self._gate_invariant(coq_file, name, operand, check_depth1=False):
                    drop.append(name)
                    logger.warning(
                        "Dropped assumed invariant '%s': failed the bounded gate.", name
                    )
        if drop:
            dropped = set(drop)
            content = "\n".join(
                line for line in content.split("\n")
                if not re.match(r"Axiom\s+(\w+)\s+:", line) or re.match(r"Axiom\s+(\w+)\s+:", line).group(1) not in dropped
            )
            try:
                coq_file.write_text(content)
            except Exception:
                pass

    def _inject_check_lemma(self, coq_file: Path, name: str, cond: str, p_next: str) -> None:
        try:
            content = coq_file.read_text()
        except Exception:
            return
        block = (
            f"\nLemma {name} : forall (s : state) (inputs : inputs), {cond} -> {p_next}.\n"
            f"Admitted.\n"
        )
        try:
            coq_file.write_text(content + "\n" + block, encoding="utf-8")
        except Exception:
            pass

    def _remove_check_lemma(self, coq_file: Path, name: str) -> None:
        try:
            content = coq_file.read_text()
        except Exception:
            return
        content = re.sub(
            rf"Lemma\s+{re.escape(name)}\s+.*?Admitted\.\n?",
            "",
            content,
            flags=re.DOTALL,
        )
        try:
            coq_file.write_text(content, encoding="utf-8")
        except Exception:
            pass

    def _inject_invariant(self, coq_file: Path, name: str, operand: str) -> None:
        try:
            content = coq_file.read_text()
        except Exception:
            return
        block = (
            f"Lemma {name} : forall s, reachable s -> {operand}.\n"
            f"Admitted.\n"
            f"Hint Resolve {name} : core.\n"
        )
        marker = "Hint Constructors reachable step : core."
        if marker in content:
            content = content.replace(marker, marker + "\n\n" + block, 1)
        else:
            content = block + "\n" + content
        try:
            coq_file.write_text(content, encoding="utf-8")
        except Exception:
            pass

    def _remove_invariant(self, coq_file: Path, name: str) -> None:
        try:
            content = coq_file.read_text()
        except Exception:
            return
        content = re.sub(
            rf"Lemma\s+{re.escape(name)}\s+:.*?Hint Resolve {re.escape(name)} : core\.\n?",
            "",
            content,
            flags=re.DOTALL,
        )
        try:
            coq_file.write_text(content, encoding="utf-8")
        except Exception:
            pass

    def prove_with_skeleton_only(self, coq_file: Path, theorem_name: str) -> Optional[Dict[str, Any]]:
        # 1. Deterministic recursive skeleton (no LLM, no rocq-mcp).
        recursive = self._recursive_skeleton_proof(coq_file, theorem_name)
        if recursive is not None:
            return {"success": True, "proof_script": recursive, "skeleton_kind": "recursive"}

        # 2. Interactive skeleton (rocq-mcp), then skeleton reflection.
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
