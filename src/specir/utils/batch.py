# src/specir/utils/batch.py
#
# Batch processing utilities for InterScope.
# Provides functions to locate .specir files and execute a
# command function over them with optional progress reporting
# and timeout handling.

import os
import signal
import time
from pathlib import Path
from typing import Callable, List, Optional, TypeVar, Any, Dict
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from contextlib import contextmanager

from specir.utils.logger import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


def find_specir_files(
    directory: Path,
    pattern: str = "*.specir",
    recursive: bool = True,
) -> List[Path]:
    """
    Recursively locate all .specir files under *directory*.

    Args:
        directory: Root directory to scan.
        pattern: Glob pattern (default ``*.specir``).
        recursive: If True (the default), search subdirectories.

    Returns:
        Sorted list of absolute paths to matching files.
    """
    directory = Path(directory).resolve()
    if not directory.is_dir():
        raise NotADirectoryError(f"Not a directory: {directory}")

    if recursive:
        files = list(directory.rglob(pattern))
    else:
        files = list(directory.glob(pattern))
    return sorted(files)


@contextmanager
def _time_limit(seconds: float):
    """
    Context manager that raises TimeoutError if the block takes
    longer than *seconds* (UNIX only, uses SIGALRM).
    """
    if hasattr(signal, "SIGALRM"):
        signal.signal(signal.SIGALRM, _raise_timeout)
        signal.alarm(int(seconds))
        try:
            yield
        finally:
            signal.alarm(0)
    else:
        yield


def _raise_timeout(signum, frame):
    raise TimeoutError("operation timed out")


def run_batch(
    func: Callable[[Path, ...], T],
    file_list: List[Path],
    *,
    timeout_per_file: Optional[float] = None,
    show_progress: bool = True,
    **kwargs: Any,
) -> List[Dict[str, Any]]:
    """
    Execute *func* on each file in *file_list* and collect results.

    Each invocation receives the file path plus any additional keyword
    arguments (``**kwargs``).  A dictionary with keys ``file`` (str),
    ``success`` (bool), ``result`` (the return value of *func* on
    success), ``error`` (exception message on failure), and
    ``duration`` (float seconds) is stored for every file.

    If *timeout_per_file* is given, each call is wrapped in a
    :class:`ThreadPoolExecutor` so that it can be interrupted after
    *timeout_per_file* seconds.  The timeout uses an OS alarm on
    UNIX; on Windows the timeout may not be enforced.

    Args:
        func: Callable that accepts a Path as first argument and
              returns a result.
        file_list: List of absolute paths to process.
        timeout_per_file: Maximum seconds per invocation (None for no
                          limit).
        show_progress: If True, print a progress message for every
                       file.
        **kwargs: Additional keyword arguments forwarded to *func*.

    Returns:
        List of result dictionaries, one per input file, in the same
        order as *file_list*.
    """
    results: List[Dict[str, Any]] = []

    for idx, file_path in enumerate(file_list):
        if show_progress:
            logger.info(
                "[%d/%d] Processing %s",
                idx + 1,
                len(file_list),
                file_path.name
            )

        start = time.time()
        success = False
        result = None
        error = None

        def _worker() -> T:
            return func(file_path, **kwargs)

        try:
            if timeout_per_file is not None:
                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(_worker)
                    result = future.result(timeout=timeout_per_file)
            else:
                result = _worker()
            success = True
        except (FuturesTimeoutError, TimeoutError):
            error = f"timed out after {timeout_per_file}s"
            logger.error(
                "[%d/%d] TIMEOUT %s: %s",
                idx + 1,
                len(file_list),
                file_path.name,
                error
            )
        except Exception as e:
            error = str(e)
            logger.error(
                "[%d/%d] ERROR %s: %s",
                idx + 1,
                len(file_list),
                file_path.name,
                error
            )

        duration = time.time() - start
        results.append(
            {
                "file": str(file_path),
                "success": success,
                "result": result,
                "error": error,
                "duration": duration
            }
        )

    return results
