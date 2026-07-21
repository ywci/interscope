# src/specir/verification/proof/koika/prover.py
#
# Generic prover for Kōika/Coq theorems with fallback to rocq_verify
# and LLM proof generation.  All design‑specific heuristics are
# controlled by configuration; the core is purely structural.

import os
import json
import time
import re
import subprocess
import shutil
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Set

from specir.backends.rocq_client import RocqClient, RocqClientError
from specir.backends.llm_client import LLMClient, get_llm_client_from_config
from specir.utils.logger import get_logger
from specir.utils.config_loader import get_config, get_project_root
from lib.koika.assist import PROOF_LIBRARY
from specir.verification.proof.koika.proof_gen import (
    build_interactive_step_prompt,
    extract_tactics_from_response,
    build_skeleton_reflection_prompt,
    extract_proof_script
)

logger = get_logger(__name__)


class KoikaProver:
    """Generic prover for Kōika/Coq theorems.

    The prover follows a strict escalation path:
    1. Already‑proven check
    2. Proof library (fast, config‑controlled)
    3. Built‑in skeleton proofs (generic structural induction)
    4. LLM skeleton reflection (tailored one‑shot proof)
    5. LLM‑driven interactive tactic loop
    6. rocq_verify fallback
    7. LLM full‑proof generation with repair
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

        # Configurable hints for the interactive prompt
        self.base_case_hint = prove_cfg.get(
            "base_case_hint",
            "simpl; auto with *; try lia; try nia."
        )
        self.step_case_hint = prove_cfg.get(
            "step_case_hint",
            "invert the step hypothesis, substitute, simpl, then try to apply the induction hypothesis or use available lemmas; finish with auto/lia/nia."
        )

        # Extra step tactics for the skeleton (empty list → use built‑in defaults)
        self.skeleton_step_tactics: List[str] = prove_cfg.get("skeleton_step_tactics", [])

        self.max_repair = config.get("proof", {}).get("max_repair_attempts", 5)
        self.coqc_path = shutil.which("coqc") or "coqc"
        self.use_proof_library = config.get("provers", {}).get("koika", {}).get(
            "use_proof_library", True
        )

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
            logger.error("coqc not found. Please install Coq or set coqc_path in config.")
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

    def _find_invariant_lemmas(self, coq_file: Path) -> List[str]:
        """Return names of auto‑generated trivial invariant lemmas."""
        try:
            content = coq_file.read_text()
        except Exception:
            return []
        nil_matches = re.findall(r"Lemma\s+(\w+_nil)\s+:", content)
        const_matches = re.findall(r"Lemma\s+(\w+_const)\s+:", content)
        return nil_matches + const_matches

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
        new_block = full_block.replace("Admitted.", PROOF_LIBRARY[theorem_name])
        new_content = original_content.replace(full_block, new_block, 1)
        coq_file.write_text(new_content)

        workspace = self._workspace_for(coq_file)
        if self._compile_with_coqc(coq_file, workspace):
            updated_content = coq_file.read_text()
            if self._theorem_is_closed(updated_content, theorem_name):
                logger.info("Library proof accepted for '%s'", theorem_name)
                return PROOF_LIBRARY[theorem_name]
            else:
                logger.error("Library proof compiled but theorem still not closed for '%s'.", theorem_name)
        else:
            logger.error("Library proof compilation failed for '%s'.", theorem_name)
        coq_file.write_text(original_content)
        logger.info("Library proof for '%s': failed", theorem_name)
        return None

    def _fallback_verify(self, coq_file: Path, theorem_name: str) -> Dict[str, Any]:
        logger.info("Using fallback: rocq_verify (non‑interactive)")
        workspace = self._workspace_for(coq_file)
        self._ensure_project_file(workspace)

        rocq = RocqClient(
            rocq_mcp_path=self.rocq_path,
            timeout=self.proof_timeout,
            cwd=workspace,
            server_args=["--workspace", str(workspace)]
        )
        rocq.start()
        try:
            if not self._compile_with_rocq_fallback(rocq, coq_file, workspace):
                pass
            verify_result = rocq.verify(coq_file, theorem_name)
            error = rocq._extract_error_from_response(verify_result)
            if error:
                content = coq_file.read_text()
                if f"Theorem {theorem_name}" in content and "Admitted." in content.split(f"Theorem {theorem_name}")[1]:
                    logger.error("Theorem '%s' is only Admitted – not actually proven.", theorem_name)
                    return {"success": False, "error": "Theorem is only Admitted, not verified."}
                return {"success": False, "error": f"Theorem verification failed: {error}"}
            return {"success": True, "proof_script": "Proof. (* verified by rocq_verify *) Qed."}
        except RocqClientError as e:
            return {"success": False, "error": f"Verification failed: {e}"}
        finally:
            rocq.stop()

    def _try_skeleton_proof(self, coq_file: Path, theorem_name: str) -> Optional[Dict[str, Any]]:
        """Generic induction + inversion skeleton, config‑extensible step tactics."""
        logger.info("Attempting generic skeleton proof for '%s'.", theorem_name)
        workspace = self._workspace_for(coq_file)
        try:
            state_id, goals = self.rocq.start_session(coq_file, theorem_name, workspace=workspace)
        except RocqClientError:
            return None
        if not goals:
            return None

        # Intro
        res = self.rocq.check(state_id, "intros.")
        if self._extract_error(res):
            return None
        state_id = res.get("structuredContent", {}).get("state_id", state_id)

        # Locate reachable hypothesis
        idtac_res = self.rocq.check(state_id, "idtac.")
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

        # Induction
        res = self.rocq.check(state_id, f"induction {reachable_hyp}.")
        if self._extract_error(res):
            return None
        state_id = res.get("structuredContent", {}).get("state_id", state_id)

        # Base case
        res = self.rocq.check(state_id, "simpl; auto; try lia; try nia.")
        if self._extract_error(res):
            return None
        state_id = res.get("structuredContent", {}).get("state_id", state_id)

        # Step case – inversion
        inv_tactic = "match goal with H : step _ _ _ |- _ => inversion H; subst; clear H end"
        check = self.rocq.check(state_id, inv_tactic)
        if self._extract_error(check):
            return None
        state_id = check.get("structuredContent", {}).get("state_id", state_id)

        # Simplify
        simpl_check = self.rocq.check(state_id, "simpl.")
        if not self._extract_error(simpl_check):
            state_id = simpl_check.get("structuredContent", {}).get("state_id", state_id)

        # Apply extra step tactics (config‑supplied or sensible defaults)
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
            tcheck = self.rocq.check(state_id, tactic)
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

    def _request_skeleton_reflection(self, coq_file: Path, theorem_name: str) -> Optional[Dict[str, Any]]:
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

        try:
            state_id, goals = self.rocq.start_session(coq_file, theorem_name, workspace=self._workspace_for(coq_file))
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

    def _try_interactive_proof(self, coq_file: Path, theorem_name: str,
                               tactic_hints: Optional[List[str]]) -> Tuple[Optional[Dict[str, Any]], Optional[List[str]], Optional[List[str]]]:
        coq_file = coq_file.resolve()
        workspace = self._workspace_for(coq_file)
        self._ensure_project_file(workspace)

        rocq = RocqClient(
            rocq_mcp_path=self.rocq_path,
            timeout=self.proof_timeout,
            cwd=workspace,
            server_args=["--workspace", str(workspace)],
        )
        rocq.start()
        self.rocq = rocq

        if not self._compile_with_rocq_fallback(rocq, coq_file, workspace):
            self.rocq.stop()
            return None, None, None

        # 1. Generic skeleton
        skeleton_result = self._try_skeleton_proof(coq_file, theorem_name)
        if skeleton_result:
            self.rocq.stop()
            logger.info("Skeleton proof proved '%s'.", theorem_name)
            return skeleton_result, None, None

        # 2. Skeleton reflection
        reflected = self._request_skeleton_reflection(coq_file, theorem_name)
        if reflected:
            self.rocq.stop()
            logger.info("Skeleton reflection proved '%s'.", theorem_name)
            return reflected, None, None

        # 3. LLM interactive
        logger.info("Starting LLM‑driven interactive proof for '%s'.", theorem_name)
        try:
            state_id, goals = self.rocq.start_session(coq_file, theorem_name, workspace=workspace)
        except RocqClientError as e:
            if "invalid path" in str(e).lower() or "scanning" in str(e).lower():
                logger.warning("Workspace error; falling back to rocq_verify.")
                self.rocq.stop()
                return None, None, None
            self.rocq.stop()
            return {"success": False, "error": f"Failed to start session: {e}"}, None, None

        if not goals:
            self.rocq.stop()
            return {"success": False, "error": "No goals found."}, None, None

        logger.info("Initial goals for '%s':\n%s", theorem_name, "\n".join(goals))

        if self.pre_simplify:
            try:
                result = self.rocq.check(state_id, "simpl.")
                if not result.get("isError") and not self._extract_error(result):
                    data = result.get("structuredContent", {})
                    new_sid = data.get("state_id")
                    new_goals = data.get("goals", [])
                    if isinstance(new_goals, str):
                        new_goals = [new_goals] if new_goals else []
                    if new_sid is not None and new_goals:
                        state_id = new_sid
                        goals = new_goals
                        logger.debug("Pre‑simplification advanced the proof state.")
            except Exception:
                pass

        # Invariant mining + collect lemma names for prompt
        available_lemmas: List[str] = []
        if self.invariant_mining:
            available_lemmas = self._find_invariant_lemmas(coq_file)
            for lemma in available_lemmas:
                try:
                    result = self.rocq.check(state_id, f"try rewrite ({lemma} _ ?Hreach).")
                    if not self._extract_error(result):
                        data = result.get("structuredContent", {})
                        new_sid = data.get("state_id")
                        if new_sid is not None and new_sid != state_id:
                            state_id = new_sid
                            logger.info("Applied invariant lemma %s", lemma)
                except Exception:
                    continue

        # LLM tactic loop
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
                # Build prompt with configurable hints and available lemmas
                prompt = build_interactive_step_prompt(
                    theorem_name,
                    goals,
                    tactic_hints,
                    applied_tactics,
                    recent_errors,
                    base_case_hint=self.base_case_hint,
                    step_case_hint=self.step_case_hint,
                    available_lemmas=available_lemmas if available_lemmas else None,
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
                    check_result = self.rocq.check(state_id, tactic)
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
                    self.rocq.stop()
                    logger.info("Interactive proof succeeded for '%s'. Script:\n%s", theorem_name, proof_script[:500])
                    return {"success": True, "proof_script": proof_script}, None, None

                if new_state_id_int is not None and new_state_id_int != current_state_id:
                    non_advancing_streak = 0
                    new_goal_hash = hash(tuple(new_goals))
                    count = goal_hashes_seen.get(new_goal_hash, 0)
                    if count >= 2:
                        logger.warning(
                            "Dead‑end detected: tactic '%s' led to a loop (goal seen %d times).",
                            tactic[:80], count + 1
                        )
                        if prev_state_id is not None:
                            try:
                                undo_res = self.rocq.check(state_id, "Undo.")
                                if not self._extract_error(undo_res):
                                    state_id = prev_state_id
                                    goals = prev_goals[:] if prev_goals else goals
                                    logger.debug("Undid looping tactic.")
                            except Exception:
                                pass
                        applied_tactics.append(f"FAILED: {tactic} - dead‑end loop")
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
                        logger.warning("Goal set has not changed for 5 attempts; dead‑end loop detected.")
                        tactic_succeeded = False
                        break
                    if non_advancing_streak >= MAX_NON_ADVANCING:
                        logger.warning("Too many consecutive non‑advancing tactics; aborting LLM loop.")
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
                    self.rocq.stop()
                    logger.error("Interactive proof failed for '%s': too many consecutive tactic failures.", theorem_name)
                    return {
                        "success": False,
                        "error": f"Too many consecutive tactic failures. Last error: {last_error}"
                    }, last_goals, last_errors

                if non_advancing_streak >= MAX_NON_ADVANCING:
                    self.rocq.stop()
                    logger.error("Interactive proof failed for '%s': too many non‑advancing steps.", theorem_name)
                    return {"success": False, "error": "Too many non‑advancing steps"}, last_goals, last_errors

        self.rocq.stop()
        logger.error("Interactive proof failed for '%s': max steps reached.", theorem_name)
        return {"success": False, "error": f"Proof failed after {self.max_steps} steps"}, last_goals, last_errors

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

    def _attempt_llm_proof_generation(self, coq_file: Path, theorem_name: str,
                                      last_goals: Optional[List[str]] = None,
                                      last_errors: Optional[List[str]] = None) -> Optional[str]:
        logger.info("LLM full‑proof generation activated for '%s'.", theorem_name)
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

        prompt = (
            "You are an expert in Coq and hardware verification.\n"
            f"Please provide a complete proof script for the theorem `{theorem_name}`:\n"
            f"```coq\n{statement}\n```\n\n"
            f"Available lemmas: {', '.join(available_lemmas) if available_lemmas else 'none'}\n\n"
            f"Environment (definitions and earlier lemmas):\n```coq\n{context}\n```\n\n"
            "Return ONLY the Coq code from \"Proof.\" to \"Qed.\" (inclusive). Do NOT use Admitted."
        )

        last_error = ""
        workspace = self._workspace_for(coq_file)

        for attempt in range(self.max_repair):
            if attempt == 0:
                final_prompt = prompt
            else:
                final_prompt = prompt + f"\n\nThe previous attempt produced the following compilation error:\n{last_error}\nPlease fix the proof."

            logger.info("LLM full‑proof attempt %d/%d for '%s'.", attempt + 1, self.max_repair, theorem_name)
            response = self.llm.generate(final_prompt)
            proof_match = re.search(r"(Proof\..*?(Qed\.|Admitted\.))", response, re.DOTALL)
            if proof_match:
                current_proof = proof_match.group(1)
            else:
                current_proof = response.strip()

            if "Admitted." in current_proof:
                logger.warning("LLM returned Admitted for '%s'; ignoring.", theorem_name)
                return None

            new_block = full_block.replace("Admitted.", current_proof)
            new_content = original_content.replace(full_block, new_block, 1)
            coq_file.write_text(new_content)

            if self._compile_with_coqc(coq_file, workspace):
                result = self._fallback_verify(coq_file, theorem_name)
                if result.get("success"):
                    logger.info("LLM‑generated proof accepted for '%s'.", theorem_name)
                    return current_proof
                else:
                    last_error = result.get("error", "Verification failed")
            else:
                last_error = self._capture_coqc_error(coq_file, workspace)

            coq_file.write_text(original_content)
            logger.error("LLM proof generation attempt %d for '%s' failed: %s", attempt + 1, theorem_name, last_error[:200])

        logger.warning("LLM proof generation gave up for '%s' after %d attempts.", theorem_name, self.max_repair)
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

    def prove_theorem(self, coq_file: Path, theorem_name: str, tactic_hints: Optional[List[str]] = None) -> Dict[str, Any]:
        logger.info("Attempting proof for '%s' (file: %s)", theorem_name, coq_file)

        if self._theorem_already_proven(coq_file, theorem_name):
            logger.info("Theorem '%s' is already proven; returning its proof.", theorem_name)
            return {"success": True, "proof_script": self._extract_proof_from_file(coq_file, theorem_name)}

        if self.use_proof_library:
            proof_script = self._apply_library_proof(coq_file, theorem_name)
            if proof_script is not None:
                logger.info("Proof for '%s' completed via library.", theorem_name)
                return {"success": True, "proof_script": proof_script}
        else:
            logger.info("Proof library disabled by configuration; skipping library check for '%s'.", theorem_name)

        result, _, _ = self._try_interactive_proof(coq_file, theorem_name, tactic_hints)
        if result is not None and result.get("success"):
            return result

        result = self._fallback_verify(coq_file, theorem_name)
        if result.get("success"):
            logger.info("rocq_verify succeeded for '%s'.", theorem_name)
            return result

        proof_script = self._attempt_llm_proof_generation(coq_file, theorem_name)
        if proof_script is not None:
            return {"success": True, "proof_script": proof_script}

        logger.error("All proof attempts exhausted for '%s'.", theorem_name)
        return {"success": False, "error": "All proof attempts exhausted"}

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

    def close(self):
        if hasattr(self, 'rocq') and self.rocq is not None:
            try:
                self.rocq.stop()
            except Exception:
                pass
