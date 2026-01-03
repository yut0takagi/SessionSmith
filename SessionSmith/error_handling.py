"""
エラーハンドリングと堅牢性のためのユーティリティ

リトライ、エラーコンテキスト、詳細なエラー情報を提供します。
"""

import functools
import logging
import time
import traceback
from contextlib import contextmanager
from typing import Any, Callable, Optional, TypeVar

from .exceptions import SessionSmithError

logger = logging.getLogger("SessionSmith.error_handling")

T = TypeVar('T')


def retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple = (Exception,),
    on_retry: Optional[Callable[[Exception, int], None]] = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    リトライデコレータ

    Args:
        max_attempts: 最大試行回数
        delay: 初期待機時間（秒）
        backoff: バックオフ係数（各リトライで delay *= backoff）
        exceptions: リトライする例外のタプル
        on_retry: リトライ時に呼ばれるコールバック関数

    Example:
        @retry(max_attempts=3, delay=1.0)
        def save_file(path):
            # ファイル保存処理
            pass
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            current_delay = delay
            last_exception = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    if attempt < max_attempts:
                        if on_retry:
                            try:
                                on_retry(e, attempt)
                            except Exception:
                                pass

                        logger.debug(
                            f"Retry {attempt}/{max_attempts} for {func.__name__}: {e}"
                        )
                        time.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logger.error(
                            f"Failed after {max_attempts} attempts: {func.__name__}: {e}"
                        )
                        raise

            # ここには到達しないはずだが、型チェッカーのために
            if last_exception:
                raise last_exception
            raise RuntimeError("Unexpected error in retry decorator")

        return wrapper
    return decorator


@contextmanager
def error_context(operation: str, **context: Any):
    """
    エラーコンテキストマネージャー

    エラー発生時に詳細なコンテキスト情報を提供します。

    Args:
        operation: 操作名
        **context: 追加のコンテキスト情報

    Example:
        with error_context("save_session", file_path="data.pkl"):
            save_session("data.pkl")
    """
    try:
        yield
    except Exception as e:
        # コンテキスト情報をエラーに追加
        if isinstance(e, SessionSmithError):
            e.details.update({
                "operation": operation,
                **context
            })

        # ログに記録
        logger.error(
            f"Error in {operation}: {e}",
            extra={"context": context, "exception": e},
            exc_info=True
        )
        raise


def safe_execute(
    func: Callable[..., T],
    *args: Any,
    default: Optional[T] = None,
    on_error: Callable[[Exception], Optional[T]] = None,
    **kwargs: Any
) -> Optional[T]:
    """
    安全に関数を実行し、エラーをキャッチ

    Args:
        func: 実行する関数
        *args: 関数の引数
        default: エラー時のデフォルト値
        on_error: エラー時のコールバック関数
        **kwargs: 関数のキーワード引数

    Returns:
        関数の戻り値、または default/on_error の戻り値
    """
    try:
        return func(*args, **kwargs)
    except Exception as e:
        logger.debug(f"Error in safe_execute: {e}", exc_info=True)

        if on_error:
            try:
                return on_error(e)
            except Exception:
                pass

        return default


def get_error_summary(exception: Exception) -> dict[str, Any]:
    """
    例外のサマリー情報を取得

    Args:
        exception: 例外オブジェクト

    Returns:
        サマリー情報の辞書
    """
    summary: dict[str, Any] = {
        "type": type(exception).__name__,
        "message": str(exception),
        "traceback": traceback.format_exc(),
    }

    if isinstance(exception, SessionSmithError):
        summary.update({
            "error_type": exception.__class__.__name__,
            "details": exception.details,
        })

    # 特定の例外タイプの追加情報
    if hasattr(exception, "file_path"):
        summary["file_path"] = exception.file_path
    if hasattr(exception, "path"):
        summary["path"] = exception.path
    if hasattr(exception, "commit_hash"):
        summary["commit_hash"] = exception.commit_hash

    return summary


def format_error_message(exception: Exception, include_traceback: bool = False) -> str:
    """
    エラーメッセージを整形

    Args:
        exception: 例外オブジェクト
        include_traceback: トレースバックを含めるか

    Returns:
        整形されたエラーメッセージ
    """
    summary = get_error_summary(exception)

    lines = [
        f"Error: {summary['type']}",
        f"Message: {summary['message']}",
    ]

    if "details" in summary and summary["details"]:
        lines.append("Details:")
        for key, value in summary["details"].items():
            lines.append(f"  {key}: {value}")

    if include_traceback:
        lines.append("\nTraceback:")
        lines.append(summary["traceback"])

    return "\n".join(lines)


class ErrorHandler:
    """
    エラーハンドリングの設定と実行を管理するクラス
    """

    def __init__(
        self,
        default_on_error: str = "raise",  # "raise", "warn", "ignore"
        log_errors: bool = True,
        include_traceback: bool = False,
    ):
        """
        Args:
            default_on_error: デフォルトのエラー処理方法
            log_errors: エラーをログに記録するか
            include_traceback: トレースバックを含めるか
        """
        self.default_on_error = default_on_error
        self.log_errors = log_errors
        self.include_traceback = include_traceback

    def handle(
        self,
        exception: Exception,
        operation: str = "",
        on_error: Optional[str] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        """
        エラーを処理

        Args:
            exception: 例外オブジェクト
            operation: 操作名
            on_error: エラー処理方法（Noneの場合は default_on_error を使用）
            context: 追加のコンテキスト情報
        """
        if on_error is None:
            on_error = self.default_on_error

        # ログに記録
        if self.log_errors:
            error_msg = format_error_message(exception, self.include_traceback)
            if operation:
                error_msg = f"[{operation}] {error_msg}"

            logger.error(error_msg, extra={"context": context or {}})

        # エラー処理
        if on_error == "raise":
            raise
        elif on_error == "warn":
            import warnings
            warnings.warn(str(exception), UserWarning, stacklevel=2)
        elif on_error == "ignore":
            pass
        else:
            raise ValueError(f"Invalid on_error value: {on_error}")


# デフォルトのエラーハンドラー
_default_error_handler = ErrorHandler()


def set_default_error_handler(handler: ErrorHandler) -> None:
    """デフォルトのエラーハンドラーを設定"""
    global _default_error_handler
    _default_error_handler = handler


def get_default_error_handler() -> ErrorHandler:
    """デフォルトのエラーハンドラーを取得"""
    return _default_error_handler

