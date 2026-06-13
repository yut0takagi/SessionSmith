"""
logging_config.py のテスト（構造化ロギング）
"""

import json
import logging

import pytest

from SessionSmith import logging_config
from SessionSmith.logging_config import (
    ROOT_LOGGER_NAME,
    JsonFormatter,
    configure_from_env,
    enable_debug,
    get_log_level,
    set_log_level,
    setup_logging,
)


@pytest.fixture(autouse=True)
def _reset_logger():
    """各テスト後に SessionSmith ロガーを初期化"""
    yield
    logger = logging.getLogger(ROOT_LOGGER_NAME)
    for h in list(logger.handlers):
        logger.removeHandler(h)
    logger.setLevel(logging.WARNING)
    logger.addHandler(logging.NullHandler())


class TestSetupLogging:
    def test_sets_level(self):
        setup_logging(level="DEBUG", console=True)
        assert get_log_level() == "DEBUG"

    def test_set_log_level(self):
        setup_logging(level="INFO")
        set_log_level("ERROR")
        assert get_log_level() == "ERROR"

    def test_invalid_level_raises(self):
        with pytest.raises(ValueError):
            setup_logging(level="NOPE")

    def test_writes_to_file(self, tmp_path):
        log_file = tmp_path / "out.log"
        setup_logging(level="INFO", log_file=log_file, console=False)
        logging.getLogger("SessionSmith.test").info("hello-log")
        # ハンドラーをフラッシュ
        for h in logging.getLogger(ROOT_LOGGER_NAME).handlers:
            h.flush()
        assert log_file.exists()
        assert "hello-log" in log_file.read_text()

    def test_no_duplicate_handlers_on_reconfigure(self):
        setup_logging(level="INFO", console=True)
        setup_logging(level="INFO", console=True)
        managed = [
            h
            for h in logging.getLogger(ROOT_LOGGER_NAME).handlers
            if getattr(h, "_sessionsmith_handler", False)
        ]
        assert len(managed) == 1

    def test_enable_debug(self):
        enable_debug()
        assert get_log_level() == "DEBUG"


class TestJsonFormatter:
    def test_outputs_valid_json(self):
        formatter = JsonFormatter()
        record = logging.LogRecord(
            "SessionSmith.x", logging.INFO, "f", 1, "msg %s", ("arg",), None
        )
        out = formatter.format(record)
        payload = json.loads(out)
        assert payload["level"] == "INFO"
        assert payload["logger"] == "SessionSmith.x"
        assert payload["message"] == "msg arg"

    def test_json_file_output(self, tmp_path):
        log_file = tmp_path / "out.jsonl"
        setup_logging(level="INFO", log_file=log_file, console=False, json_format=True)
        logging.getLogger("SessionSmith.test").info("structured")
        for h in logging.getLogger(ROOT_LOGGER_NAME).handlers:
            h.flush()
        line = log_file.read_text().strip().splitlines()[0]
        payload = json.loads(line)
        assert payload["message"] == "structured"


class TestConfigureFromEnv:
    def test_no_env_returns_none(self, monkeypatch):
        monkeypatch.delenv("SESSIONSMITH_LOG_LEVEL", raising=False)
        monkeypatch.delenv("SESSIONSMITH_LOG_FILE", raising=False)
        assert configure_from_env() is None

    def test_env_level(self, monkeypatch):
        monkeypatch.setenv("SESSIONSMITH_LOG_LEVEL", "DEBUG")
        monkeypatch.delenv("SESSIONSMITH_LOG_FILE", raising=False)
        logger = configure_from_env()
        assert logger is not None
        assert get_log_level() == "DEBUG"
