# src/specir/verification/perf/error_history.py
#
# Dedicated error‑history tracker for PERF.
#
# The class records failures as (error_signature, script_fingerprint)
# pairs.  This allows the traversal and scorer to:
#   - detect when a newly generated script is very similar to one that
#     already failed with the same dominant error;
#   - avoid re‑exploring such scripts;
#   - keep a bounded, memory‑efficient cache of the most recent failures.
#
# The error signature is derived from the first meaningful line of an
# error message (skipping deprecation warnings).  The script fingerprint
# is a normalized prefix of the proof script, sufficient to detect
# near‑identical scripts without storing the full text.

import re
from typing import Dict, List, Tuple
from specir.utils.logger import get_logger

logger = get_logger(__name__)


class ErrorHistory:
    """Tracks failures to avoid re‑generating similar scripts.

    Each entry is keyed by a tuple ``(error_signature, script_fingerprint)``.
    The cache is bounded by ``max_entries``; when the limit is exceeded,
    the oldest entries are discarded.

    Typical usage:
        history = ErrorHistory(max_entries=200)
        if history.has_similar_failure(script, error_msg):
            # skip or penalize this script
        else:
            # evaluate script ...
            history.record_failure(script, error_msg)
    """

    def __init__(self, max_entries: int = 200):
        """
        Args:
            max_entries: Maximum number of failure entries to keep.
                         Must be at least 1.
        """
        if max_entries < 1:
            raise ValueError("max_entries must be >= 1")
        self._max_entries = max_entries
        # Internal store: dict mapping (signature, fingerprint) -> True.
        # Python dict preserves insertion order, so we can prune oldest.
        self._seen: Dict[Tuple[str, str], bool] = {}

    @staticmethod
    def _signature(error_msg: str) -> str:
        """
        Extract a stable error signature from an error message.

        The signature is the first non‑empty line that is not a warning
        or a deprecation notice.  If no such line exists, fall back to
        the first 200 characters of the whole message.
        """
        if not error_msg:
            return ""
        lines = [l.strip() for l in error_msg.splitlines() if l.strip()]
        for line in lines:
            low = line.lower()
            if "warning:" in low or "deprecated" in low:
                continue
            return line[:200]
        return error_msg[:200]

    @staticmethod
    def _script_fingerprint(script: str) -> str:
        """
        Create a short, normalized fingerprint for a proof script.

        Comments are removed, whitespace is collapsed, and the result is
        truncated to 500 characters.  This is enough to identify
        near‑identical scripts while keeping memory usage bounded.
        """
        if not script:
            return ""
        s = re.sub(r"\(\*.*?\*\)", "", script, flags=re.DOTALL)
        s = re.sub(r";[^\n]*", "", s)
        s = re.sub(r"\s+", " ", s).strip()
        return s[:500]

    def has_similar_failure(self, script: str, error_msg: str) -> bool:
        """
        Return True if a script with the same error signature and a very
        similar fingerprint has already been recorded.
        """
        key = (self._signature(error_msg), self._script_fingerprint(script))
        return key in self._seen

    def record_failure(self, script: str, error_msg: str) -> None:
        """
        Record a failed (script, error) pair.

        If the cache size exceeds ``max_entries``, the oldest entries are
        removed first.
        """
        key = (self._signature(error_msg), self._script_fingerprint(script))
        self._seen[key] = True

        if len(self._seen) > self._max_entries:
            # Remove oldest entries (insertion order).
            overflow = len(self._seen) - self._max_entries
            for _ in range(overflow):
                self._seen.pop(next(iter(self._seen)))

    def get_repeated_signatures(self, min_count: int = 2) -> List[str]:
        """
        Return error signatures that have been seen at least *min_count*
        times, sorted by descending frequency.

        This is useful for prompt hardening: repeated signatures can be
        injected as mandatory avoidance rules.
        """
        counts: Dict[str, int] = {}
        for (sig, _) in self._seen.keys():
            counts[sig] = counts.get(sig, 0) + 1

        repeated = [
            sig for sig, cnt in counts.items()
            if cnt >= min_count
        ]
        # Sort by count descending, then by signature for stability.
        repeated.sort(key=lambda s: (-counts[s], s))
        return repeated

    def clear(self) -> None:
        """Remove all recorded failures."""
        self._seen.clear()

    def __len__(self) -> int:
        """Return the number of recorded failure entries."""
        return len(self._seen)

    def __contains__(self, key: Tuple[str, str]) -> bool:
        """Check if a specific (signature, fingerprint) pair is recorded."""
        return key in self._seen

    def __repr__(self) -> str:
        return f"ErrorHistory(entries={len(self._seen)}, max_entries={self._max_entries})"
