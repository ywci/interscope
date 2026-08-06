# src/specir/utils/logger.py
#
# Logging utility for InterScope.
# Configures console and file logging with rotation support.
# Log level is read from conf/config.yaml (logging.level).
# Log file is written to build/logs/specir.log (rotates at 10MB, keeps 5 backups).
# HTTP-related loggers (httpx, openai) are suppressed at INFO level
# to keep proof-progress output readable.

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Optional
from specir.utils.config_loader import get_config

_LOGGER_SETUP_DONE = False


def setup_logging(
    level: Optional[str] = None,
    log_file: Optional[Path] = None,
    console_enabled: bool = True,
    file_enabled: bool = True,
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 5,
    force: bool = False,
) -> None:
    """
    Configure the root logger with console and file handlers.

    Args:
        level: Log level as string (DEBUG, INFO, WARNING, ERROR, CRITICAL).
               If None, reads from config under 'logging.level' (default 'INFO').
        log_file: Path to the log file. If None, uses 'build/logs/specir.log'.
                  The directory will be created if it does not exist.
        console_enabled: Enable console logging (stderr).
        file_enabled: Enable file logging.
        max_bytes: Maximum size of a log file before rotation (bytes).
        backup_count: Number of backup files to keep.
        force: If True, force re‑configuration even if setup has already been done.
               Otherwise subsequent calls are silently ignored.
    """
    global _LOGGER_SETUP_DONE
    if _LOGGER_SETUP_DONE and not force:
        return

    if level is None:
        config_level = get_config("logging.level", "INFO")
        level = config_level
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    console_formatter = logging.Formatter(
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_formatter = logging.Formatter(
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    if console_enabled:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(numeric_level)
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)

    if file_enabled:
        if log_file is None:
            log_dir = get_config("directories.logs", "build/logs")
            log_file = Path(log_dir) / "specir.log"
        log_file = Path(log_file)
        log_file.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)

    if numeric_level > logging.DEBUG:
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("openai").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)

    _LOGGER_SETUP_DONE = True


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for a module.

    Args:
        name: Typically __name__ of the calling module.

    Returns:
        Configured Logger instance.
    """
    if not _LOGGER_SETUP_DONE:
        setup_logging()
    return logging.getLogger(name)
