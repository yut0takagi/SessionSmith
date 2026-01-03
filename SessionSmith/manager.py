"""
SessionManagerクラスと自動バックアップ機能

Note:
    バージョン管理機能は `ssm` モジュールに統合されました。
    `from SessionSmith import ssm` を使用してください。
"""

import inspect
import threading
import time
import warnings
from pathlib import Path
from typing import Any, Callable, Optional, Union

from .core import load_session, save_session
from .jupyter_utils import is_jupyter_environment, is_jupyter_internal_var


class SessionManager:
    """
    ノートブックの変数状態をpickleで保存・復元する簡易クラス
    自動バックアップ機能を提供

    Note:
        バージョン管理機能を使用する場合は `ssm` モジュールを使用してください：

        >>> from SessionSmith import ssm
        >>> ssm.init()
        >>> ssm.commit("message")
    """

    def __init__(
        self,
        globals_dict: Optional[dict[str, Any]] = None,
        enable_version_control: bool = False,
        vc_base_path: Optional[Union[str, Path]] = None
    ):
        """
        Args:
            globals_dict: 管理するグローバル変数辞書（Noneの場合は自動取得）
            enable_version_control: 非推奨。`ssm` モジュールを使用してください
            vc_base_path: 非推奨。`ssm` モジュールを使用してください
        """
        self.globals_dict = self._get_globals_dict(globals_dict)
        self._auto_save_thread: Optional[threading.Thread] = None
        self._auto_save_running = False
        self._auto_save_lock = threading.Lock()
        self._auto_save_interval = 300  # デフォルト5分
        self._auto_save_path = "session_autosave.pkl"
        self._auto_save_exclude: Optional[list[str]] = None
        self._auto_save_compress = False
        self._auto_save_metadata = True

        # 現在のセッションファイル
        self._current_session_file: Optional[Path] = None

        # 常時記録モード関連
        self._continuous_save_enabled = False
        self._continuous_save_path: Optional[Path] = None
        self._continuous_save_exclude: Optional[list[str]] = None
        self._continuous_save_compress: Union[bool, str] = False
        self._continuous_save_verbose = False
        self._continuous_save_on_error = "skip"

        # 非推奨の警告
        if enable_version_control:
            warnings.warn(
                "enable_version_control is deprecated. "
                "Use `from SessionSmith import ssm; ssm.init()` instead.",
                DeprecationWarning,
                stacklevel=2
            )

    def _get_globals_dict(self, globals_dict: Optional[dict[str, Any]], depth: int = 2) -> dict[str, Any]:
        """
        グローバル変数辞書を取得します

        Args:
            globals_dict: グローバル変数辞書（Noneの場合は自動取得）
            depth: 呼び出し元からのフレーム深度（デフォルトは2：_get_globals_dict -> __init__ -> ユーザーコード）

        Returns:
            dict: グローバル変数辞書（参照、コピーではない）
        """
        if globals_dict is not None:
            if not isinstance(globals_dict, dict):
                raise TypeError(f"globals_dict must be a dict, got {type(globals_dict).__name__}")
            return globals_dict

        try:
            frame = inspect.currentframe()
            if frame is None:
                raise RuntimeError("Cannot access calling frame")

            # 指定された深度までフレームを遡る
            caller_frame = frame
            for _ in range(depth):
                if caller_frame.f_back is None:
                    raise RuntimeError("Cannot access calling frame at specified depth")
                caller_frame = caller_frame.f_back

            # SessionManagerは変数を変更する必要があるため、参照を返す（コピーではない）
            result = caller_frame.f_globals
            del frame
            return result
        except Exception as e:
            raise RuntimeError(f"Failed to get globals dict: {e}") from e

    def save(
        self,
        file_path: Union[str, Path],
        exclude: Optional[list[str]] = None,
        compress: Union[bool, str] = False,
        protocol: Optional[int] = None,
        metadata: bool = False,
        verbose: bool = False,
        on_error: str = "skip",
        serializer: Optional[Callable[[Any], Any]] = None,
        exclude_jupyter: bool = True,
        format: Optional[str] = None,
    ) -> None:
        """
        セッションを保存します

        Args:
            file_path: 保存するファイルパス
            exclude: 除外したい変数名のリスト
            compress: 圧縮形式
            protocol: pickleプロトコルバージョン
            metadata: メタデータを保存するか
            verbose: 詳細なログを出力するか
            on_error: エラー時の動作
            serializer: カスタムシリアライザー
            exclude_jupyter: Jupyter Notebookの内部変数を自動的に除外するか
        """
        file_path = Path(file_path)

        # 通常の保存
        save_session(
            file_path=file_path,
            globals_dict=self.globals_dict,
            exclude=exclude,
            compress=compress,
            protocol=protocol,
            metadata=metadata,
            verbose=verbose,
            on_error=on_error,
            serializer=serializer,
            exclude_jupyter=exclude_jupyter,
            format=format,
        )

        self._current_session_file = file_path

    def load(
        self,
        file_path: Union[str, Path],
        include: Optional[list[str]] = None,
        exclude: Optional[list[str]] = None,
        verbose: bool = False,
        format: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        セッションをロードします

        Args:
            file_path: ロードするファイルパス
            include: ロードする変数名のリスト
            exclude: ロードから除外する変数名のリスト
            verbose: 詳細なログを出力するか

        Returns:
            dict: ロードされた変数の辞書
        """
        result = load_session(
            file_path=file_path,
            globals_dict=self.globals_dict,
            include=include,
            exclude=exclude,
            verbose=verbose,
            format=format,
        )

        # 現在のセッションファイルを更新
        self._current_session_file = Path(file_path)

        return result

    # ========== 常時記録モード（Continuous Save） ==========

    def enable_continuous_save(
        self,
        file_path: Union[str, Path],
        exclude: Optional[list[str]] = None,
        compress: Union[bool, str] = False,
        verbose: bool = False,
        on_error: str = "skip",
    ) -> None:
        """
        セル実行ごとの自動保存（常時記録モード）を有効化

        Jupyter Notebook/IPython環境でセルが実行されるたびに
        自動的にセッションを保存します。クラッシュ対策に有効です。

        Args:
            file_path: 保存先ファイルパス
            exclude: 除外する変数名のリスト
            compress: 圧縮形式（True, 'gzip', 'bz2', または False）
            verbose: 詳細ログを出力するか
            on_error: エラー時の動作（'skip', 'warn', 'raise'）

        Example:
            >>> sm = SessionManager()
            >>> sm.enable_continuous_save("autosave.pkl")
            >>> # 以降、セル実行ごとに自動保存される
        """
        if not is_jupyter_environment():
            warnings.warn(
                "Continuous save is only available in Jupyter/IPython environment. "
                "Consider using auto_save() for periodic backups instead.",
                UserWarning, stacklevel=2
            )
            return

        self._continuous_save_path = Path(file_path)
        self._continuous_save_exclude = exclude or []
        self._continuous_save_compress = compress
        self._continuous_save_verbose = verbose
        self._continuous_save_on_error = on_error
        self._continuous_save_enabled = True

        # IPythonのイベントフックを登録
        try:
            ip = get_ipython()  # type: ignore

            # 既存のフックを削除（重複防止）
            self._unregister_continuous_save_hook()

            # post_run_cellイベントに登録
            ip.events.register('post_run_cell', self._continuous_save_callback)

            if verbose:
                print(f"✓ Continuous save enabled: {file_path}")
                print("  Sessions will be saved after each cell execution.")
        except Exception as e:
            warnings.warn(f"Failed to enable continuous save: {e}", UserWarning, stacklevel=2)
            self._continuous_save_enabled = False

    def _continuous_save_callback(self, result=None) -> None:
        """セル実行後に呼ばれるコールバック（内部メソッド）"""
        if not self._continuous_save_enabled:
            return

        if self._continuous_save_path is None:
            return

        try:
            self.save(
                file_path=self._continuous_save_path,
                exclude=self._continuous_save_exclude,
                compress=self._continuous_save_compress,
                verbose=False,  # 毎回表示しない
                on_error=self._continuous_save_on_error,
                metadata=True,
            )
            if self._continuous_save_verbose:
                print(f"  ✓ Auto-saved to {self._continuous_save_path}")
        except Exception as e:
            if self._continuous_save_on_error == "warn":
                warnings.warn(f"Continuous save failed: {e}", UserWarning, stacklevel=2)
            elif self._continuous_save_on_error == "raise":
                raise

    def _unregister_continuous_save_hook(self) -> None:
        """IPythonのイベントフックを解除（内部メソッド）"""
        try:
            ip = get_ipython()  # type: ignore
            ip.events.unregister('post_run_cell', self._continuous_save_callback)
        except Exception:
            pass

    def disable_continuous_save(self) -> None:
        """
        常時記録モードを無効化

        Example:
            >>> sm.disable_continuous_save()
            >>> # 以降、自動保存は行われない
        """
        was_enabled = self._continuous_save_enabled
        self._continuous_save_enabled = False
        self._unregister_continuous_save_hook()

        if was_enabled and self._continuous_save_verbose:
            print("✓ Continuous save disabled")

    def is_continuous_save_enabled(self) -> bool:
        """
        常時記録モードが有効かどうかを確認

        Returns:
            bool: 有効な場合はTrue
        """
        return self._continuous_save_enabled

    # ========== 自動バックアップ ==========

    def auto_save(
        self,
        interval: int = 300,
        file_path: Optional[Union[str, Path]] = None,
        exclude: Optional[list[str]] = None,
        compress: Union[bool, str] = False,
        metadata: bool = True,
    ) -> None:
        """
        自動バックアップを開始します

        Args:
            interval: 自動保存の間隔（秒、最小値は10秒）
            file_path: 自動保存ファイルのパス
            exclude: 除外したい変数名のリスト
            compress: 圧縮するか
            metadata: メタデータを保存するか

        Raises:
            ValueError: intervalが10未満の場合
        """
        if interval < 10:
            raise ValueError("interval must be at least 10 seconds")

        with self._auto_save_lock:
            if self._auto_save_running:
                self.stop_auto_save()

            self._auto_save_interval = interval
            if file_path:
                self._auto_save_path = str(file_path)

            self._auto_save_exclude = exclude
            self._auto_save_compress = compress
            self._auto_save_metadata = metadata

            self._auto_save_running = True
            self._auto_save_thread = threading.Thread(
                target=self._auto_save_loop,
                daemon=True,
                name="SessionManager-auto-save"
            )
            self._auto_save_thread.start()

    def _auto_save_loop(self) -> None:
        """自動保存のループ（スレッドで実行）"""
        while True:
            with self._auto_save_lock:
                if not self._auto_save_running:
                    break
                running = self._auto_save_running
                interval = self._auto_save_interval
                path = self._auto_save_path
                exclude = self._auto_save_exclude
                compress = self._auto_save_compress
                metadata = self._auto_save_metadata

            if not running:
                break

            try:
                self.save(
                    file_path=path,
                    exclude=exclude,
                    compress=compress,
                    metadata=metadata,
                    verbose=False,
                    exclude_jupyter=True,
                )
            except Exception as e:
                warnings.warn(f"Auto-save failed: {e}", UserWarning, stacklevel=2)

            # 指定された間隔だけ待機（1秒ずつチェックして中断可能にする）
            for _ in range(interval):
                with self._auto_save_lock:
                    if not self._auto_save_running:
                        break
                time.sleep(1)

    def stop_auto_save(self) -> None:
        """自動バックアップを停止します"""
        with self._auto_save_lock:
            self._auto_save_running = False

        if self._auto_save_thread and self._auto_save_thread.is_alive():
            self._auto_save_thread.join(timeout=2.0)
            if self._auto_save_thread.is_alive():
                warnings.warn("Auto-save thread did not stop within timeout", UserWarning, stacklevel=2)

    def is_auto_save_running(self) -> bool:
        """自動バックアップが実行中かどうかを返します"""
        with self._auto_save_lock:
            return self._auto_save_running

    def list_variables(
        self,
        exclude_jupyter: bool = True,
        exclude_builtins: bool = True
    ) -> list[str]:
        """
        管理している変数のリストを取得します

        Args:
            exclude_jupyter: Jupyter内部変数を除外するか（デフォルト: True）
            exclude_builtins: 組み込み関数・変数を除外するか（デフォルト: True）

        Returns:
            list: 変数名のリスト
        """
        variables: list[str] = []

        # 組み込み関数・変数のリスト（拡張可能）
        builtin_names = {
            'exit', 'quit', 'open', 'print', 'len', 'str', 'int', 'float',
            'list', 'dict', 'tuple', 'set', 'bool', 'bytes', 'bytearray',
            'complex', 'range', 'slice', 'type', 'isinstance', 'hasattr',
            'getattr', 'setattr', 'delattr', 'property', 'super', 'object',
            'classmethod', 'staticmethod', 'abs', 'all', 'any', 'bin', 'chr',
            'ord', 'hex', 'oct', 'repr', 'eval', 'exec', 'compile', 'dir',
            'globals', 'locals', 'vars', 'hash', 'id', 'input', 'iter',
            'next', 'pow', 'round', 'sorted', 'sum', 'zip', 'enumerate',
            'filter', 'map', 'max', 'min', 'reversed'
        }

        for var_name in self.globals_dict.keys():
            # 特別な変数（__xxx__）を除外
            if var_name.startswith("__") and var_name.endswith("__"):
                continue

            # Jupyter内部変数を除外
            if exclude_jupyter and is_jupyter_environment():
                if is_jupyter_internal_var(var_name):
                    continue

            # 組み込み関数・変数を除外
            if exclude_builtins:
                if var_name in builtin_names:
                    continue

            variables.append(var_name)

        return sorted(variables)

    def get_variable_info(self) -> dict[str, dict[str, Any]]:
        """
        管理している変数の情報を取得します

        Returns:
            dict: 変数情報（変数名をキー、型と値のプレビューを含む辞書）
        """
        variables = self.list_variables()
        var_info: dict[str, dict[str, Any]] = {}

        for var_name in variables:
            var_value = self.globals_dict.get(var_name)
            if var_value is not None:
                try:
                    value_str = str(var_value)
                    if len(value_str) > 50:
                        value_str = value_str[:50] + "..."
                    var_info[var_name] = {
                        "type": type(var_value).__name__,
                        "value": value_str,
                    }
                except Exception:
                    var_info[var_name] = {
                        "type": type(var_value).__name__,
                        "value": "<unable to represent>",
                    }

        return var_info
