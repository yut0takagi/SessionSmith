"""
SessionManagerクラスと自動バックアップ機能
"""

import inspect
import threading
import time
from typing import Optional, Dict, Any, List, Callable
from .core import save_session, load_session, _is_jupyter_environment, _is_jupyter_internal_var


class SessionManager:
    """
    ノートブックの変数状態をpickleで保存・復元する簡易クラス
    自動バックアップ機能も提供
    """

    def __init__(self, globals_dict: Optional[Dict[str, Any]] = None):
        """
        Args:
            globals_dict (dict, optional): 管理するグローバル変数辞書
        """
        if globals_dict is None:
            frame = inspect.currentframe().f_back
            globals_dict = frame.f_globals
            del frame
        self.globals_dict = globals_dict
        self._auto_save_thread: Optional[threading.Thread] = None
        self._auto_save_running = False
        self._auto_save_interval = 300  # デフォルト5分
        self._auto_save_path = "session_autosave.pkl"

    def save(
        self,
        file_path: str,
        exclude: Optional[List[str]] = None,
        compress: bool = False,
        protocol: Optional[int] = None,
        metadata: bool = False,
        verbose: bool = False,
        on_error: str = "skip",
        serializer: Optional[Callable] = None,
        exclude_jupyter: bool = True,
    ) -> None:
        """
        セッションを保存します

        Args:
            file_path (str): 保存するファイルパス
            exclude (list, optional): 除外したい変数名のリスト
            compress (bool or str): 圧縮形式
            protocol (int, optional): pickleプロトコルバージョン
            metadata (bool): メタデータを保存するか
            verbose (bool): 詳細なログを出力するか
            on_error (str): エラー時の動作
            serializer (callable, optional): カスタムシリアライザー
            exclude_jupyter (bool): Jupyter Notebookの内部変数を自動的に除外するか（デフォルト: True）
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
        file_path: str,
        include: Optional[List[str]] = None,
        exclude: Optional[List[str]] = None,
        verbose: bool = False,
    ) -> Dict[str, Any]:
        """
        セッションをロードします

        Args:
            file_path (str): ロードするファイルパス
            include (list, optional): ロードする変数名のリスト
            exclude (list, optional): ロードから除外する変数名のリスト
            verbose (bool): 詳細なログを出力するか

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
        file_path: Optional[str] = None,
        exclude: Optional[List[str]] = None,
        compress: bool = False,
        metadata: bool = True,
    ) -> None:
        """
        自動バックアップを開始します

        Args:
            interval (int): 自動保存の間隔（秒）
            file_path (str, optional): 自動保存ファイルのパス
            exclude (list, optional): 除外したい変数名のリスト
            compress (bool): 圧縮するか
            metadata (bool): メタデータを保存するか
        """
        if self._auto_save_running:
            self.stop_auto_save()

        self._auto_save_interval = interval
        if file_path:
            self._auto_save_path = file_path

        self._auto_save_running = True
        self._auto_save_thread = threading.Thread(
            target=self._auto_save_loop,
            args=(exclude, compress, metadata),
            daemon=True
        )
        self._auto_save_thread.start()

    def _auto_save_loop(
        self,
        exclude: Optional[List[str]],
        compress: bool,
        metadata: bool,
    ) -> None:
        """自動保存のループ"""
        while self._auto_save_running:
            try:
                self.save(
                    file_path=self._auto_save_path,
                    exclude=exclude,
                    compress=compress,
                    metadata=metadata,
                    verbose=False,
                    exclude_jupyter=True,  # 自動バックアップではJupyter内部変数を除外
                )
            except Exception as e:
                print(f"Auto-save failed: {e}")

            # 指定された間隔だけ待機
            for _ in range(self._auto_save_interval):
                if not self._auto_save_running:
                    break
                time.sleep(1)

    def stop_auto_save(self) -> None:
        """自動バックアップを停止します"""
        self._auto_save_running = False
        if self._auto_save_thread:
            self._auto_save_thread.join(timeout=1.0)

    def is_auto_save_running(self) -> bool:
        """自動バックアップが実行中かどうかを返します"""
        return self._auto_save_running

    def list_variables(self, exclude_jupyter: bool = True, exclude_builtins: bool = True) -> List[str]:
        """
        管理している変数のリストを取得します

        Args:
            exclude_jupyter (bool): Jupyter内部変数を除外するか（デフォルト: True）
            exclude_builtins (bool): 組み込み関数・変数を除外するか（デフォルト: True）

        Returns:
            list: 変数名のリスト
        """
        variables = []
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
                if var_name in ['exit', 'quit', 'open', 'print', 'len', 'str', 'int', 'float', 'list', 'dict', 'tuple', 'set']:
                    continue

            variables.append(var_name)

        return sorted(variables)

    def get_variable_info(self) -> Dict[str, Any]:
        """
        管理している変数の情報を取得します

        Returns:
            dict: 変数情報（変数名、型、数など）
        """
        variables = self.list_variables()
        var_info = {}
        for var_name in variables:
            var_value = self.globals_dict.get(var_name)
            if var_value is not None:
                var_info[var_name] = {
                    "type": type(var_value).__name__,
                    "value": str(var_value)[:50] + "..." if len(str(var_value)) > 50 else str(var_value),
                }
        return var_info

