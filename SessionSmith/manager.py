"""
SessionManagerクラスと自動バックアップ機能
"""

import inspect
import threading
import time
from typing import Optional, Dict, Any, List, Callable, Union
from pathlib import Path
import warnings
from .core import save_session, load_session
from .jupyter_utils import is_jupyter_environment, is_jupyter_internal_var
from .version_control import VersionControl


class SessionManager:
    """
    ノートブックの変数状態をpickleで保存・復元する簡易クラス
    自動バックアップ機能とバージョン管理機能を提供
    """

    def __init__(
        self,
        globals_dict: Optional[Dict[str, Any]] = None,
        enable_version_control: bool = False,
        vc_base_path: Optional[Union[str, Path]] = None
    ):
        """
        Args:
            globals_dict: 管理するグローバル変数辞書（Noneの場合は自動取得）
            enable_version_control: バージョン管理を有効化するか
            vc_base_path: バージョン管理のベースパス（Noneの場合は次回のsave()時に自動設定）
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
        
        # バージョン管理関連
        self._version_control_enabled = enable_version_control
        self._vc_base_path = Path(vc_base_path) if vc_base_path else None
        self._version_control: Optional[VersionControl] = None
        self._current_session_file: Optional[Path] = None
        
        if enable_version_control and vc_base_path:
            self._init_version_control()

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

    def _init_version_control(self) -> None:
        """バージョン管理を初期化"""
        if self._vc_base_path is None:
            # 最初のsave()呼び出し時に設定される
            return
        
        self._version_control = VersionControl(self._vc_base_path)

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
        auto_commit: Optional[bool] = None,
        commit_message: Optional[str] = None,
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
            exclude_jupyter: Jupyter Notebookの内部変数を自動的に除外するか（デフォルト: True）
            auto_commit: 自動的にコミットするか（Noneの場合はバージョン管理が有効な時のみ自動コミット）
            commit_message: コミットメッセージ（auto_commit=Trueの場合）
        """
        file_path = Path(file_path)
        
        # バージョン管理のベースパスを設定（初回のみ）
        if self._version_control_enabled and self._vc_base_path is None:
            self._vc_base_path = file_path.parent
            self._init_version_control()
        
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
        
        # 自動コミット（バージョン管理が有効で、auto_commitがTrueまたはNoneの場合）
        if self._version_control_enabled and self._version_control:
            should_commit = auto_commit if auto_commit is not None else True
            if should_commit:
                message = commit_message or f"Save session to {file_path.name}"
                try:
                    self.commit(message, file_path=file_path, author=None)
                except Exception as e:
                    if verbose:
                        warnings.warn(f"Auto-commit failed: {e}", UserWarning)

    def load(
        self,
        file_path: Union[str, Path],
        include: Optional[List[str]] = None,
        exclude: Optional[List[str]] = None,
        verbose: bool = False,
        format: Optional[str] = None,
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

    def commit(
        self,
        message: str,
        file_path: Optional[Union[str, Path]] = None,
        author: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> Optional[str]:
        """
        現在のセッションをコミット（バージョン管理が有効な場合のみ）
        
        Args:
            message: コミットメッセージ
            file_path: コミットするセッションファイル（Noneの場合は最後に保存したファイル）
            author: 作成者名
            tags: タグのリスト
            
        Returns:
            str: コミットハッシュ（バージョン管理が無効な場合はNone）
        """
        if not self._version_control_enabled or not self._version_control:
            warnings.warn("Version control is not enabled. Use enable_version_control() to enable it.")
            return None
        
        if file_path is None:
            file_path = self._current_session_file
            if file_path is None:
                raise ValueError(
                    "No session file specified. "
                    "Either provide file_path or call save() first."
                )
        
        file_path = Path(file_path)
        
        # バージョン管理のベースパスを設定（初回のみ）
        if self._vc_base_path is None:
            self._vc_base_path = file_path.parent
            self._init_version_control()
        
        return self._version_control.commit(message, file_path, author, tags)

    def enable_version_control(
        self,
        base_path: Optional[Union[str, Path]] = None
    ) -> None:
        """
        バージョン管理を有効化
        
        Args:
            base_path: バージョン管理のベースパス（Noneの場合は次回のsave()時に自動設定）
        """
        self._version_control_enabled = True
        if base_path:
            self._vc_base_path = Path(base_path)
            self._init_version_control()

    def disable_version_control(self) -> None:
        """バージョン管理を無効化"""
        self._version_control_enabled = False
        self._version_control = None

    def log(
        self,
        limit: Optional[int] = None,
        oneline: bool = False
    ) -> List[Dict[str, Any]]:
        """
        コミット履歴を表示
        
        Args:
            limit: 表示するコミット数の上限（Noneの場合は全て）
            oneline: 1行形式で表示するか
            
        Returns:
            list: コミット情報のリスト
        """
        if not self._version_control_enabled or not self._version_control:
            raise RuntimeError("Version control is not enabled")
        
        return self._version_control.log(limit=limit, oneline=oneline)

    def checkout(
        self,
        commit_hash: Optional[str] = None,
        message: Optional[str] = None,
        target_file: Optional[Union[str, Path]] = None
    ) -> None:
        """
        以前のコミット状態に戻す
        
        Args:
            commit_hash: コミットハッシュ（Noneの場合はメッセージで検索）
            message: コミットメッセージ（部分一致で検索）
            target_file: 復元先のファイルパス（Noneの場合は元のファイルに復元）
        """
        if not self._version_control_enabled or not self._version_control:
            raise RuntimeError("Version control is not enabled")
        
        restored_file = self._version_control.checkout(
            commit_hash=commit_hash,
            message=message,
            target_file=Path(target_file) if target_file else None
        )
        
        # 復元したファイルをロード
        self.load(restored_file)
        
        print(f"Checked out to commit: {restored_file}")

    def diff(
        self,
        commit1: Optional[str] = None,
        commit2: Optional[str] = None,
        detailed: bool = True
    ) -> Dict[str, Any]:
        """
        2つのコミット間の差分を表示
        
        Args:
            commit1: 最初のコミットハッシュ（Noneの場合はHEAD）
            commit2: 2番目のコミットハッシュ（Noneの場合はHEAD）
            detailed: 詳細な差分を含めるか
            
        Returns:
            dict: 差分情報
        """
        if not self._version_control_enabled or not self._version_control:
            raise RuntimeError("Version control is not enabled")
        
        return self._version_control.diff(commit1=commit1, commit2=commit2, detailed=detailed)

    def status(self) -> Dict[str, Any]:
        """
        現在の状態を確認
        
        Returns:
            dict: 状態情報
        """
        if not self._version_control_enabled or not self._version_control:
            return {"version_control": False}
        
        status_info = self._version_control.status()
        status_info["version_control"] = True
        return status_info

    def tag(
        self,
        tag_name: str,
        commit_hash: Optional[str] = None
    ) -> None:
        """
        コミットにタグを追加
        
        Args:
            tag_name: タグ名
            commit_hash: コミットハッシュ（Noneの場合はHEAD）
        """
        if not self._version_control_enabled or not self._version_control:
            raise RuntimeError("Version control is not enabled")
        
        self._version_control.tag(tag_name, commit_hash)

    def show(
        self,
        commit_hash: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        コミットの詳細情報を表示
        
        Args:
            commit_hash: コミットハッシュ（Noneの場合はHEAD）
            
        Returns:
            dict: コミット情報
        """
        if not self._version_control_enabled or not self._version_control:
            raise RuntimeError("Version control is not enabled")
        
        return self._version_control.show(commit_hash)

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
                    auto_commit=False,  # 自動バックアップではコミットしない
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
            if exclude_jupyter and is_jupyter_environment():
                if is_jupyter_internal_var(var_name):
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
