"""
構造化ロギング設定モジュール

SessionSmith 全体のロガー（``SessionSmith`` 名前空間）を一元的に設定します。

- コンソール／ファイルへの出力
- ログレベルの設定
- 通常形式 / JSON 形式（構造化ログ）の切り替え
- ローテーション（サイズベース）
- 環境変数による設定

環境変数:
    SESSIONSMITH_LOG_LEVEL  ログレベル（DEBUG/INFO/WARNING/ERROR/CRITICAL）
    SESSIONSMITH_LOG_FILE   ログファイルの出力先パス
    SESSIONSMITH_LOG_JSON   "1"/"true" で JSON 形式の構造化ログを有効化

使用例:
    >>> from SessionSmith import setup_logging, enable_debug
    >>> setup_logging(level="INFO", log_file="ssm.log")
    >>> enable_debug()  # デバッグモードを有効化
"""

import json
import logging
import logging.handlers
import os
from pathlib import Path
from typing import Optional, Union

# SessionSmith 全体のルートロガー
ROOT_LOGGER_NAME = "SessionSmith"

DEFAULT_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# setup_logging で追加したハンドラーを識別するためのマーカー属性
_HANDLER_MARKER = "_sessionsmith_handler"

_configured = False


class JsonFormatter(logging.Formatter):
    """ログレコードを JSON 1行で出力するフォーマッター（構造化ログ）。"""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, DEFAULT_DATE_FORMAT),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        # 追加の文脈情報（extra=...）を含める
        standard = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__)
        standard.update({"message", "asctime"})
        for key, value in record.__dict__.items():
            if key not in standard and not key.startswith("_"):
                payload[key] = value
        return json.dumps(payload, ensure_ascii=False, default=str)


def _normalize_level(level: Union[int, str]) -> int:
    """ログレベルを int に正規化します。"""
    if isinstance(level, int):
        return level
    resolved = logging.getLevelName(str(level).upper())
    if not isinstance(resolved, int):
        raise ValueError(f"Invalid log level: {level}")
    return resolved


def _remove_managed_handlers(logger: logging.Logger) -> None:
    """setup_logging が以前に追加したハンドラーを取り除きます（多重設定防止）。"""
    for handler in list(logger.handlers):
        if getattr(handler, _HANDLER_MARKER, False):
            logger.removeHandler(handler)
            try:
                handler.close()
            except Exception:
                pass


def setup_logging(
    level: Union[int, str] = "INFO",
    log_file: Optional[Union[str, Path]] = None,
    *,
    console: bool = True,
    json_format: bool = False,
    fmt: str = DEFAULT_FORMAT,
    max_bytes: int = 5 * 1024 * 1024,
    backup_count: int = 3,
) -> logging.Logger:
    """
    SessionSmith のロギングを設定します。

    Args:
        level: ログレベル（"DEBUG" 等の文字列または ``logging.DEBUG`` 等の int）
        log_file: ログファイルの出力先（None でファイル出力なし）
        console: コンソール（stderr）へ出力するか
        json_format: JSON 形式の構造化ログを使用するか
        fmt: 通常形式のフォーマット文字列
        max_bytes: ログファイルのローテーション閾値（バイト）
        backup_count: 保持するローテーションファイル数

    Returns:
        logging.Logger: 設定済みの SessionSmith ルートロガー
    """
    global _configured

    logger = logging.getLogger(ROOT_LOGGER_NAME)
    logger.setLevel(_normalize_level(level))
    # ルートロガーへの伝播を止め、重複出力を防ぐ
    logger.propagate = False

    _remove_managed_handlers(logger)

    formatter: logging.Formatter = JsonFormatter() if json_format else logging.Formatter(
        fmt, datefmt=DEFAULT_DATE_FORMAT
    )

    if console:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        setattr(stream_handler, _HANDLER_MARKER, True)
        logger.addHandler(stream_handler)

    if log_file is not None:
        log_path = Path(log_file)
        if log_path.parent and not log_path.parent.exists():
            log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            str(log_path),
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        setattr(file_handler, _HANDLER_MARKER, True)
        logger.addHandler(file_handler)

    # ハンドラーが何も無い場合は NullHandler を入れて警告を抑制
    if not logger.handlers:
        logger.addHandler(logging.NullHandler())

    _configured = True
    return logger


def set_log_level(level: Union[int, str]) -> None:
    """SessionSmith ロガーのログレベルを変更します。"""
    logging.getLogger(ROOT_LOGGER_NAME).setLevel(_normalize_level(level))


def get_log_level() -> str:
    """現在の SessionSmith ロガーのログレベル名を返します。"""
    return logging.getLevelName(logging.getLogger(ROOT_LOGGER_NAME).level)


def enable_debug(log_file: Optional[Union[str, Path]] = None) -> logging.Logger:
    """
    デバッグモードを有効化します（DEBUG レベル + コンソール出力）。

    Args:
        log_file: 併せてファイル出力する場合のパス

    Returns:
        logging.Logger: 設定済みのロガー
    """
    return setup_logging(level="DEBUG", log_file=log_file, console=True)


def configure_from_env() -> Optional[logging.Logger]:
    """
    環境変数からロギングを設定します。

    ``SESSIONSMITH_LOG_LEVEL`` または ``SESSIONSMITH_LOG_FILE`` のいずれかが
    設定されている場合のみ設定を行います。

    Returns:
        logging.Logger or None: 設定した場合はロガー、未設定なら None
    """
    level = os.environ.get("SESSIONSMITH_LOG_LEVEL")
    log_file = os.environ.get("SESSIONSMITH_LOG_FILE")
    json_format = os.environ.get("SESSIONSMITH_LOG_JSON", "").lower() in ("1", "true", "yes")

    if not level and not log_file:
        return None

    return setup_logging(
        level=level or "INFO",
        log_file=log_file,
        json_format=json_format,
    )
