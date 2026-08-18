# src/specir/verification/proof/proof_pattern_cache.py
#
# Proof pattern cache for successful proofs.
#
# This module stores successful proof scripts per design/property and
# extracts reusable tactic sequences from them.  The cache is persistent
# (JSON file) and can be used by PERF, the linear prover, and the proof
# orchestrator to:
#   - reuse a successful proof directly when the same property is attempted
#     again;
#   - adapt a successful proof for similar properties;
#   - extract high-level tactic patterns that are known to work for a
#     design and inject them into LLM prompts.
#
# Typical reusable patterns include:
#   induction Hreach as [| s' s'' inputs' Hreach' IH Hstep]
#   inversion Hstep; subst; clear Hstep; simpl
#   destruct (op_reg s' =? 0) eqn:Hop0
#
# The cache is thread-safe for concurrent writes from parallel PERF
# evaluations and is saved atomically.

import json
import re
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from specir.utils.logger import get_logger
from specir.utils.config_loader import get_config

logger = get_logger(__name__)

# Tactic patterns that are considered reusable across properties.
# Each pattern is a regular expression that matches the beginning of a
# line.  The matched line is stored as a reusable tactic.
REUSABLE_TACTIC_PATTERNS = [
    r"^\s*induction\b.*\breachable\b.*$",
    r"^\s*inversion\s+Hstep\b.*$",
    r"^\s*destruct\s*\(.*=\?.*\)\s*eqn:.*$",
    r"^\s*simpl\b.*$",
    r"^\s*intros\b.*$",
    r"^\s*apply\s+IH\b.*$",
    r"^\s*rewrite\b.*$",
    r"^\s*unfold\b.*$",
    r"^\s*assert\b.*$",
]

# Tactic sequences that are common in Koika proofs and can be reused as
# complete multi‑line patterns.
COMMON_TACTIC_SEQUENCES = [
    "induction Hreach as [| s' s'' inputs' Hreach' IH Hstep].",
    "inversion Hstep; subst; clear Hstep; simpl.",
    "destruct (op_reg s' =? 0) eqn:Hop0.",
    "destruct (op_reg s' =? 1) eqn:Hop1.",
    "destruct (op_reg s' =? 2) eqn:Hop2.",
]


class ProofPatternCache:
    """
    Persistent cache of successful proof scripts and reusable tactic patterns.

    The cache is stored as a JSON file.  The internal structure is:

        {
          "design_name": {
            "property_name": "full proof script"
          }
        }

    If no cache file exists, the cache starts empty and is created on the
    first save.
    """

    def __init__(self, cache_path: Optional[Path] = None):
        """
        Args:
            cache_path: Path to the JSON cache file.  If None, the default
                path from configuration is used
                (``directories.build`` / ``proof_pattern_cache``), or
                ``build/perf_proof_patterns.json`` if not configured.
        """
        if cache_path is None:
            config = get_config()
            cache_path_str = config.get("proof", {}).get(
                "perf", {}
            ).get(
                "proof_pattern_cache_path",
                "build/perf_proof_patterns.json",
            )
            cache_path = Path(cache_path_str)

        self._cache_path = Path(cache_path)
        self._lock = threading.RLock()
        self._cache: Dict[str, Dict[str, str]] = {}

        # Ensure the parent directory exists.
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)

        # Load existing cache if available.
        self._load()

    def _load(self) -> None:
        """Load the cache from the JSON file, if it exists."""
        if not self._cache_path.exists():
            logger.debug("Proof pattern cache file not found: %s", self._cache_path)
            return

        try:
            with open(self._cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                # Validate and coerce to expected structure.
                for design, props in data.items():
                    if isinstance(design, str) and isinstance(props, dict):
                        clean_props = {
                            str(prop): str(script)
                            for prop, script in props.items()
                            if isinstance(prop, str) and isinstance(script, str)
                        }
                        self._cache[design] = clean_props
                logger.info(
                    "Loaded proof pattern cache from %s (%d designs)",
                    self._cache_path,
                    len(self._cache),
                )
            else:
                logger.warning(
                    "Proof pattern cache file is not a valid dict; starting empty."
                )
        except json.JSONDecodeError as e:
            logger.error("Failed to parse proof pattern cache: %s", e)
        except Exception as e:
            logger.error("Failed to load proof pattern cache: %s", e)

    def _save(self) -> None:
        """Save the cache to the JSON file atomically."""
        try:
            # Write to a temporary file first, then replace.
            tmp_path = self._cache_path.with_suffix(".tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self._cache, f, indent=2, sort_keys=True)
            tmp_path.replace(self._cache_path)
            logger.debug(
                "Saved proof pattern cache to %s (%d designs)",
                self._cache_path,
                len(self._cache),
            )
        except Exception as e:
            logger.error("Failed to save proof pattern cache: %s", e)

    def store_successful_proof(
        self,
        design_name: str,
        property_name: str,
        proof_script: str,
    ) -> None:
        """
        Store a successful proof script for a design/property.

        Args:
            design_name: Name of the design (e.g., 'alu').
            property_name: Name of the property (e.g., 'zero_flag_correct').
            proof_script: The complete proof script (Coq or ACL2).
        """
        if not design_name or not property_name or not proof_script:
            return

        with self._lock:
            design_cache = self._cache.setdefault(design_name, {})
            if design_cache.get(property_name) == proof_script:
                # Already stored; nothing to do.
                return
            design_cache[property_name] = proof_script
            logger.info(
                "Stored successful proof for '%s/%s' in pattern cache.",
                design_name,
                property_name,
            )
            self._save()

    def get_successful_proof(
        self,
        design_name: str,
        property_name: str,
    ) -> Optional[str]:
        """
        Return the stored proof script for a design/property, or None.
        """
        with self._lock:
            return self._cache.get(design_name, {}).get(property_name)

    def get_reusable_patterns(
        self,
        property_name: str,
        design_name: Optional[str] = None,
    ) -> List[str]:
        """
        Extract reusable tactic patterns from successful proofs.

        Args:
            property_name: Name of the property for which patterns are
                requested.  This may be used to find similar properties
                if the exact property is not stored.
            design_name: Optional design name.  If provided, only proofs
                from that design are considered.  If None, all designs
                are searched.

        Returns:
            A list of reusable tactic strings (deduplicated, preserving
            order).  If no successful proof is available, returns an empty
            list.
        """
        with self._lock:
            # 1. Try exact match first.
            if design_name is not None:
                proof = self._cache.get(design_name, {}).get(property_name)
                if proof:
                    return self.extract_reusable_tactics(proof)
            else:
                # Search all designs for exact property.
                for d in self._cache:
                    proof = self._cache[d].get(property_name)
                    if proof:
                        return self.extract_reusable_tactics(proof)

            # 2. Find a similar property (prefix match) if exact not found.
            best_match = None
            best_prefix_len = 0
            for d, props in self._cache.items():
                if design_name is not None and d != design_name:
                    continue
                for prop, proof in props.items():
                    # Compute common prefix length between property_name and prop.
                    prefix_len = _common_prefix_len(property_name, prop)
                    if prefix_len > best_prefix_len:
                        best_prefix_len = prefix_len
                        best_match = proof

            if best_match is not None:
                logger.info(
                    "Using similar property for reusable patterns (prefix len %d).",
                    best_prefix_len,
                )
                return self.extract_reusable_tactics(best_match)

            return []

    @staticmethod
    def extract_reusable_tactics(proof_script: str) -> List[str]:
        """
        Extract high‑level reusable tactic lines from a proof script.

        The function looks for lines that match any of the
        ``REUSABLE_TACTIC_PATTERNS`` and also checks for known multi‑line
        sequences in ``COMMON_TACTIC_SEQUENCES``.

        Args:
            proof_script: The full proof script.

        Returns:
            A deduplicated list of tactic strings.
        """
        if not proof_script:
            return []

        reusable: List[str] = []
        seen = set()

        def add(tactic: str) -> None:
            tactic = tactic.strip()
            if tactic and tactic not in seen:
                seen.add(tactic)
                reusable.append(tactic)

        # 1. Check for known common sequences first (more specific).
        for seq in COMMON_TACTIC_SEQUENCES:
            if seq in proof_script:
                add(seq)

        # 2. Line‑by‑line regex extraction.
        for line in proof_script.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            for pattern in REUSABLE_TACTIC_PATTERNS:
                if re.match(pattern, stripped):
                    add(stripped)
                    break

        return reusable

    def clear(self) -> None:
        """Remove all entries from the cache and delete the cache file."""
        with self._lock:
            self._cache.clear()
            if self._cache_path.exists():
                try:
                    self._cache_path.unlink()
                except OSError as e:
                    logger.warning("Failed to remove cache file: %s", e)

    def __len__(self) -> int:
        """Return the total number of stored proofs."""
        with self._lock:
            return sum(len(props) for props in self._cache.values())

    def __repr__(self) -> str:
        return f"ProofPatternCache(path={self._cache_path}, designs={len(self._cache)})"


def _common_prefix_len(a: str, b: str) -> int:
    """Return the length of the common prefix of two strings."""
    i = 0
    for ca, cb in zip(a, b):
        if ca == cb:
            i += 1
        else:
            break
    return i


_cache_instance: Optional[ProofPatternCache] = None
_cache_lock = threading.Lock()


def get_proof_pattern_cache(config: Optional[Dict[str, Any]] = None) -> ProofPatternCache:
    """
    Return a shared ProofPatternCache instance.

    The instance is created lazily and reused for the lifetime of the
    process.  If *config* is provided and the cache already exists, the
    existing instance is returned (the path is not changed).

    Args:
        config: Optional configuration dictionary.  If None, the global
            config is used to determine the cache path.

    Returns:
        The singleton ProofPatternCache instance.
    """
    global _cache_instance
    with _cache_lock:
        if _cache_instance is None:
            if config is not None:
                cache_path_str = config.get("proof", {}).get(
                    "perf", {}
                ).get("proof_pattern_cache_path", "build/perf_proof_patterns.json")
                cache_path = Path(cache_path_str)
                _cache_instance = ProofPatternCache(cache_path)
            else:
                _cache_instance = ProofPatternCache()
        return _cache_instance
