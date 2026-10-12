# tests/unit/test_logger.py
#
# Unit tests for the logging utility.
# Covers get_logger name resolution and setup_logging level/handler
# configuration, including file handlers, rotation parameters, and idempotency.

import pytest
import logging
import logging.handlers
import isir.utils.logger as logger_mod
from isir.utils.logger import get_logger, setup_logging
from unittest.mock import Mock


@pytest.fixture(autouse=True)
def _clean_logging_state(monkeypatch):
    """Reset setup flag and preserve the root logger state across tests."""
    monkeypatch.setattr(logger_mod, "_LOGGER_SETUP_DONE", False)

    root = logging.getLogger()
    orig_handlers = list(root.handlers)
    orig_level = root.level
    suppressed = ["httpx", "openai", "urllib3"]
    orig_suppressed = {name: logging.getLogger(name).level for name in suppressed}

    yield

    for h in list(root.handlers):
        if h not in orig_handlers:
            h.close()
    root.handlers[:] = orig_handlers
    root.setLevel(orig_level)
    for name, level in orig_suppressed.items():
        logging.getLogger(name).setLevel(level)


class TestGetLogger:
    def test_returns_named_logger(self, monkeypatch):
        monkeypatch.setattr(logger_mod, "_LOGGER_SETUP_DONE", True)
        lg = get_logger("isir.test.module")
        assert isinstance(lg, logging.Logger)
        assert lg.name == "isir.test.module"
        assert lg is logging.getLogger("isir.test.module")

    def test_triggers_setup_when_not_done(self, monkeypatch):
        monkeypatch.setattr(logger_mod, "_LOGGER_SETUP_DONE", False)
        fake_setup = Mock()
        monkeypatch.setattr(logger_mod, "setup_logging", fake_setup)
        get_logger("isir.x")
        fake_setup.assert_called_once_with()


class TestSetupLogging:
    def test_console_and_file_handlers(self, tmp_path):
        log_file = tmp_path / "logs" / "isir.log"
        setup_logging(level="DEBUG", log_file=log_file, force=True)

        root = logging.getLogger()
        assert root.level == logging.DEBUG

        console = [h for h in root.handlers if type(h) is logging.StreamHandler]
        files = [
            h
            for h in root.handlers
            if type(h) is logging.handlers.RotatingFileHandler
        ]
        assert len(console) == 1
        assert len(files) == 1
        assert log_file.parent.is_dir()

        root.info("hello-logger-test")
        assert "hello-logger-test" in log_file.read_text(encoding="utf-8")

    def test_level_from_config(self, monkeypatch):
        monkeypatch.setattr(
            logger_mod, "get_config", lambda key, default=None: "WARNING"
        )
        setup_logging(file_enabled=False, force=True)
        assert logging.getLogger().level == logging.WARNING

    def test_invalid_level_falls_back_to_info(self):
        setup_logging(
            level="NOT_A_REAL_LEVEL",
            console_enabled=False,
            file_enabled=False,
            force=True,
        )
        assert logging.getLogger().level == logging.INFO

    def test_no_handlers_when_both_disabled(self):
        setup_logging(
            level="INFO", console_enabled=False, file_enabled=False, force=True
        )
        assert len(logging.getLogger().handlers) == 0

    def test_console_disabled(self, tmp_path):
        log_file = tmp_path / "isir.log"
        setup_logging(
            level="INFO", log_file=log_file, console_enabled=False, force=True
        )
        root = logging.getLogger()
        assert not any(type(h) is logging.StreamHandler for h in root.handlers)
        assert any(
            isinstance(h, logging.handlers.RotatingFileHandler) for h in root.handlers
        )

    def test_file_handler_rotation_parameters(self, tmp_path):
        log_file = tmp_path / "isir.log"
        setup_logging(
            level="INFO",
            log_file=log_file,
            max_bytes=12345,
            backup_count=7,
            force=True,
        )
        root = logging.getLogger()
        fh = next(
            h
            for h in root.handlers
            if isinstance(h, logging.handlers.RotatingFileHandler)
        )
        assert fh.maxBytes == 12345
        assert fh.backupCount == 7
        assert str(fh.baseFilename) == str(log_file)

    def test_repeated_calls_are_safe(self, tmp_path):
        log_file = tmp_path / "isir.log"
        setup_logging(level="INFO", log_file=log_file, force=True)
        root = logging.getLogger()
        count = len(root.handlers)

        setup_logging(level="DEBUG", log_file=tmp_path / "other.log")
        assert len(root.handlers) == count
        assert root.level == logging.INFO

        setup_logging(level="WARNING", log_file=log_file, force=True)
        assert root.level == logging.WARNING
        assert len(root.handlers) == count

    def test_suppresses_http_loggers_above_debug(self):
        setup_logging(level="INFO", file_enabled=False, force=True)
        assert logging.getLogger("httpx").level == logging.WARNING
        assert logging.getLogger("openai").level == logging.WARNING
        assert logging.getLogger("urllib3").level == logging.WARNING

    def test_debug_does_not_suppress_http_loggers(self):
        for name in ("httpx", "openai", "urllib3"):
            logging.getLogger(name).setLevel(logging.NOTSET)

        setup_logging(level="DEBUG", file_enabled=False, force=True)

        assert logging.getLogger("httpx").level == logging.NOTSET
        assert logging.getLogger("openai").level == logging.NOTSET
        assert logging.getLogger("urllib3").level == logging.NOTSET
