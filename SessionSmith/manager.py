"""
SessionManagerクラスと自動バックアップ機能
"""

import inspect
import threading
import time
from typing import Optional, Dict, Any, List, Callable, Union
from pathlib import Path
import warnings
from .core import save_session, load_session, _is_jupyter_environment, _is_jupyter_internal_var


class SessionManager:
    """
    ノートブックの変数状態をpickleで保存・復元する簡易クラス
    自動バックアップ機能も提供
    """

    def __init__(self, globals_dict: Optional[Dict[str, Any]] = None):
        """
        Args:
            globals_dict: 管理するグローバル変数辞書（Noneの場合は自動取得）
        """
        self.globals_dict = self._get_globals_dict(globals_dict)
        self._auto_save_thread: Optional[threading.Thread] = None
        self._auto_save_running = False
        self._auto_save_lock = threading.Lock()
        self._auto_save_interval = 300  # デフォルト5分
        self._auto_save_path = "session_autosave.pkl"
        self._auto_save_exclude: Optional[List[str]] = None
        self._auto_save_compress = False
        self._auto_save_metadata = True

    def _get_globals_dict(self, globals_dict: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """
        グローバル変数辞書を取得します
        
        Args:
            globals_dict: グローバル変数辞書（Noneの場合は自動取得）
            
        Returns:
            dict: グローバル変数辞書
        """
        if globals_dict is not None:
            if not isinstance(globals_dict, dict):
                raise TypeError(f"globals_dict must be a dict, got {type(globals_dict).__name__}")
            return globals_dict
        
        try:
            frame = inspect.currentframe()
            if frame is None or frame.f_back is None:
                raise RuntimeError("Cannot access calling frame")
            caller_frame = frame.f_back
            result = caller_frame.f_globals.copy()
            del frame
            return result
        except Exception as e:
            raise RuntimeError(f"Failed to get globals dict: {e}")

    def save(
        self,
        file_path: Union[str, Path],
        exclude: Optional[List[str]] = None,
        compress: Union[bool, str] = False,
        protocol: Optional[int] = None,
        metadata: bool = False,
        verbose: bool = False,
        on_error: str = "skip",
        serializer: Optional[Callable[[Any], Any]] = None,
        exclude_jupyter: bool = True,
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
            exclude_jupyter: Jupyter Notebookの内部変数を自動的に除外するか（デフォルト: True）
        """
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
        )

    def load(
        self,
        file_path: Union[str, Path],
        include: Optional[List[str]] = None,
        exclude: Optional[List[str]] = None,
        verbose: bool = False,
    ) -> Dict[str, Any]:
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
        return load_session(
            file_path=file_path,
            globals_dict=self.globals_dict,
            include=include,
            exclude=exclude,
            verbose=verbose,
        )

    def auto_save(
        self,
        interval: int = 300,
        file_path: Optional[Union[str, Path]] = None,
        exclude: Optional[List[str]] = None,
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
                    exclude_jupyter=True,  # 自動バックアップではJupyter内部変数を除外
                )
            except Exception as e:
                warnings.warn(f"Auto-save failed: {e}", UserWarning)

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
                warnings.warn("Auto-save thread did not stop within timeout", UserWarning)

    def is_auto_save_running(self) -> bool:
        """自動バックアップが実行中かどうかを返します"""
        with self._auto_save_lock:
            return self._auto_save_running

    def list_variables(
        self, 
        exclude_jupyter: bool = True, 
        exclude_builtins: bool = True
    ) -> List[str]:
        """
        管理している変数のリストを取得します

        Args:
            exclude_jupyter: Jupyter内部変数を除外するか（デフォルト: True）
            exclude_builtins: 組み込み関数・変数を除外するか（デフォルト: True）

        Returns:
            list: 変数名のリスト
        """
        variables: List[str] = []
        
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
            if exclude_jupyter and _is_jupyter_environment():
                if _is_jupyter_internal_var(var_name):
                    continue

            # 組み込み関数・変数を除外
            if exclude_builtins:
                if var_name in builtin_names:
                    continue

            variables.append(var_name)

        return sorted(variables)

    def get_variable_info(self) -> Dict[str, Dict[str, Any]]:
        """
        管理している変数の情報を取得します

        Returns:
            dict: 変数情報（変数名をキー、型と値のプレビューを含む辞書）
        """
        variables = self.list_variables()
        var_info: Dict[str, Dict[str, Any]] = {}
        
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
