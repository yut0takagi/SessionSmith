"""
SessionSmith Manager (SSM) - Git風のセッション管理

.ssm/ ディレクトリベースでセッションを管理します。

使用例:
    >>> from SessionSmith import ssm
    >>> ssm.init()  # 初期化
    >>> ssm.commit("Initial state")  # コミット
    >>> ssm.log()  # 履歴表示
    >>> ssm.checkout("abc123")  # 復元
    
    # 長時間実行対応
    >>> with ssm.checkpoint(interval=300) as cp:  # 5分ごとに自動保存
    ...     for epoch in range(1000):
    ...         train()
    ...         cp.step()  # 手動チェックポイント（オプション）
"""

import os
import sys
import json
import pickle
import hashlib
import gzip
import shutil
import inspect
import logging
import threading
import time
import atexit
import functools
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List, Union, Callable, TypeVar, Generic
from contextlib import contextmanager
import warnings

from .jupyter_utils import is_jupyter_environment, is_jupyter_internal_var
from .exceptions import (
    SSMError,
    SSMNotInitializedError,
    SSMCommitNotFoundError,
    SSMNoCommitsError,
    SSMConfigError,
    ValidationError,
)
from . import i18n

# リソース管理（オプショナル）
try:
    from .resource_manager import ResourceManager
    HAS_RESOURCE_MANAGER = True
except ImportError:
    HAS_RESOURCE_MANAGER = False
    ResourceManager = None

# ロガー設定
logger = logging.getLogger("SessionSmith.ssm")
logger.addHandler(logging.NullHandler())


# グローバルインスタンス
_ssm_instance: Optional['SSM'] = None


class CheckpointContext:
    """
    チェックポイントコンテキスト
    
    長時間実行タスク（機械学習の学習ループなど）で使用します。
    - 定期的な自動チェックポイント
    - 手動チェックポイント（step()）
    - メトリクスの追跡
    - エラー時の緊急保存
    """
    
    def __init__(
        self,
        ssm: 'SSM',
        interval: int = 300,
        max_checkpoints: int = 5,
        on_error: str = "warn",
        compress: bool = True,
        message: str = "Checkpoint",
    ):
        self.ssm = ssm
        self.interval = interval
        self.max_checkpoints = max_checkpoints
        self.on_error = on_error
        self.compress = compress
        self.message = message
        
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._last_checkpoint = time.time()
        self._checkpoint_count = 0
        self._step_count = 0
        self._start_time = time.time()
        
        # メトリクス追跡
        self._metrics: Dict[str, List[float]] = {}
        
        # シグナルハンドラー
        self._original_sigint = None
        self._original_sigterm = None
    
    @property
    def checkpoint_dir(self) -> Path:
        """チェックポイントディレクトリ"""
        return self.ssm.ssm_path / self.ssm.CHECKPOINTS_DIR
    
    @property
    def elapsed(self) -> float:
        """経過時間（秒）"""
        return time.time() - self._start_time
    
    @property
    def elapsed_str(self) -> str:
        """経過時間（文字列）"""
        return str(timedelta(seconds=int(self.elapsed)))
    
    def start(self) -> None:
        """バックグラウンドチェックポイントを開始"""
        if self._running:
            return
        
        self._running = True
        self._start_time = time.time()
        self._last_checkpoint = time.time()
        
        # ディレクトリ作成
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        
        # シグナルハンドラーを登録（中断時にチェックポイント）
        self._register_signal_handlers()
        
        # 終了時のクリーンアップを登録
        atexit.register(self._on_exit)
        
        # バックグラウンドスレッドを開始
        self._thread = threading.Thread(
            target=self._checkpoint_loop,
            daemon=True,
            name="SSM-Checkpoint"
        )
        self._thread.start()
        
        print(f"✓ Checkpoint started (interval: {self.interval}s)")
        logger.info(f"Checkpoint started (interval: {self.interval}s)")
    
    def stop(self) -> None:
        """バックグラウンドチェックポイントを停止"""
        self._running = False
        
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        
        self._restore_signal_handlers()
        
        try:
            atexit.unregister(self._on_exit)
        except Exception:
            pass
        
        # 最終チェックポイントを保存
        self._save_checkpoint("Final checkpoint")
        
        print(f"✓ Checkpoint stopped (elapsed: {self.elapsed_str})")
        logger.info("Checkpoint stopped")
    
    def step(self, force: bool = False, **metrics) -> bool:
        """
        手動チェックポイント（学習ループ内で呼び出し）
        
        Args:
            force: 強制的にチェックポイント
            **metrics: 記録するメトリクス（例: loss=0.5, accuracy=0.9）
            
        Returns:
            bool: チェックポイントが作成されたか
            
        Example:
            >>> for epoch in range(1000):
            ...     loss, acc = train()
            ...     cp.step(loss=loss, accuracy=acc)
        """
        self._step_count += 1
        
        # メトリクスを記録
        for key, value in metrics.items():
            if key not in self._metrics:
                self._metrics[key] = []
            self._metrics[key].append(float(value))
        
        elapsed = time.time() - self._last_checkpoint
        
        if force or elapsed >= self.interval:
            return self._save_checkpoint(f"{self.message} (step {self._step_count})")
        
        return False
    
    def _checkpoint_loop(self) -> None:
        """バックグラウンドチェックポイントループ"""
        while self._running:
            time.sleep(1)  # 1秒ごとにチェック
            
            with self._lock:
                if not self._running:
                    break
                
                elapsed = time.time() - self._last_checkpoint
                if elapsed >= self.interval:
                    self._save_checkpoint(f"Auto {self.message}")
    
    def _save_checkpoint(self, message: str = "") -> bool:
        """チェックポイントを保存"""
        with self._lock:
            try:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"checkpoint_{timestamp}.gz"
                filepath = self.checkpoint_dir / filename
                
                # グローバル変数を取得
                globals_dict = self.ssm._get_globals_dict(depth=5)
                variables = self.ssm._get_saveable_vars(globals_dict, verbose=False)
                
                if not variables:
                    return False
                
                # チェックポイントデータ
                checkpoint_data = {
                    "timestamp": datetime.now().isoformat(),
                    "message": message,
                    "step_count": self._step_count,
                    "checkpoint_count": self._checkpoint_count,
                    "elapsed": self.elapsed,
                    "metrics": self._get_metrics_summary(),
                    "variables": variables,
                }
                
                # 保存
                with gzip.open(filepath, 'wb') as f:
                    pickle.dump(checkpoint_data, f)
                
                self._checkpoint_count += 1
                self._last_checkpoint = time.time()
                
                # 古いチェックポイントを削除
                self._cleanup_old_checkpoints()
                
                logger.info(f"Checkpoint saved: {filepath}")
                return True
                
            except Exception as e:
                if self.on_error == "raise":
                    raise
                elif self.on_error == "warn":
                    warnings.warn(f"Checkpoint failed: {e}")
                logger.error(f"Checkpoint failed: {e}")
                return False
    
    def _cleanup_old_checkpoints(self) -> None:
        """古いチェックポイントを削除"""
        checkpoints = sorted(
            self.checkpoint_dir.glob("checkpoint_*.gz"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )
        
        for old_cp in checkpoints[self.max_checkpoints:]:
            try:
                old_cp.unlink()
                logger.debug(f"Deleted old checkpoint: {old_cp}")
            except Exception as e:
                logger.warning(f"Failed to delete checkpoint: {e}")
    
    def _get_metrics_summary(self) -> Dict[str, Any]:
        """メトリクスのサマリーを取得"""
        summary = {}
        for key, values in self._metrics.items():
            if values:
                summary[key] = {
                    "last": values[-1],
                    "mean": sum(values) / len(values),
                    "min": min(values),
                    "max": max(values),
                    "count": len(values),
                }
        return summary
    
    def _register_signal_handlers(self) -> None:
        """シグナルハンドラーを登録"""
        try:
            import signal
            self._original_sigint = signal.signal(signal.SIGINT, self._signal_handler)
            self._original_sigterm = signal.signal(signal.SIGTERM, self._signal_handler)
        except Exception:
            pass  # メインスレッド以外では失敗する可能性
    
    def _restore_signal_handlers(self) -> None:
        """シグナルハンドラーを復元"""
        try:
            import signal
            if self._original_sigint:
                signal.signal(signal.SIGINT, self._original_sigint)
            if self._original_sigterm:
                signal.signal(signal.SIGTERM, self._original_sigterm)
        except Exception:
            pass
    
    def _signal_handler(self, signum, frame) -> None:
        """シグナルハンドラー"""
        import signal
        logger.info(f"Signal {signum} received, saving checkpoint...")
        self._save_checkpoint(f"Emergency (signal {signum})")
        
        # 元のハンドラーを呼び出し
        if signum == signal.SIGINT and self._original_sigint:
            self._original_sigint(signum, frame)
        elif signum == signal.SIGTERM and self._original_sigterm:
            self._original_sigterm(signum, frame)
    
    def _on_exit(self) -> None:
        """終了時のクリーンアップ"""
        if self._running:
            logger.info("Saving final checkpoint on exit...")
            self._save_checkpoint("Final (exit)")
    
    def summary(self) -> Dict[str, Any]:
        """進捗サマリーを取得"""
        return {
            "elapsed": self.elapsed_str,
            "step_count": self._step_count,
            "checkpoint_count": self._checkpoint_count,
            "metrics": self._get_metrics_summary(),
        }


class SSM:
    """
    SessionSmith Manager - Git風のセッション管理クラス
    
    .ssm/ ディレクトリ構造:
        .ssm/
        ├── config              # 設定ファイル
        ├── HEAD                # 現在のコミットを指す
        ├── objects/            # オブジェクトストレージ
        ├── commits/            # コミット情報
        ├── snapshots/          # スナップショット
        │   └── latest          # 最新の状態
        └── continuous/         # 常時記録用
            └── autosave
    """
    
    SSM_DIR = ".ssm"
    CONFIG_FILE = "config"
    HEAD_FILE = "HEAD"
    OBJECTS_DIR = "objects"
    COMMITS_DIR = "commits"
    SNAPSHOTS_DIR = "snapshots"
    CONTINUOUS_DIR = "continuous"
    CHECKPOINTS_DIR = "checkpoints"
    BRANCHES_DIR = "branches"
    TAGS_DIR = "tags"
    REMOTES_DIR = "remotes"
    
    # 制限値（堅牢性のため）
    MAX_VARIABLE_SIZE_MB = 500  # 1変数の最大サイズ（MB）
    MAX_VARIABLE_SIZE_WARN_MB = 100  # 警告を出すサイズ（MB）
    MAX_TOTAL_SIZE_MB = 2000  # 総サイズの上限（MB）
    MAX_RETRY_ATTEMPTS = 3  # リトライ回数
    RETRY_DELAY_SECONDS = 0.5  # リトライ間隔
    
    def __init__(self, path: Optional[Union[str, Path]] = None, globals_dict: Optional[Dict[str, Any]] = None):
        """
        Args:
            path: .ssm ディレクトリを作成する親ディレクトリ（Noneの場合はカレントディレクトリ）
            globals_dict: 管理するグローバル変数辞書（Noneの場合は自動取得）
        """
        self.base_path = Path(path) if path else Path.cwd()
        self.ssm_path = self.base_path / self.SSM_DIR
        self.globals_dict = globals_dict
        
        # 常時記録モード関連
        self._continuous_enabled = False
        self._continuous_verbose = False
        
        # チェックポイント関連
        self._checkpoint_manager: Optional['CheckpointManager'] = None
        
        # スレッドセーフのためのロック
        self._lock = threading.RLock()
        
        # 除外リスト（デフォルト）
        self._default_exclude = [
            'ssm', '_ssm_instance', 'SSM',  # SSM自体
            'In', 'Out', '_ih', '_oh', '_dh',  # Jupyter内部
            'get_ipython', 'exit', 'quit',  # IPython
        ]
        
        # 統計情報
        self._stats = {
            "commits": 0,
            "checkpoints": 0,
            "total_saved_bytes": 0,
            "last_commit_time": None,
        }
        
        # リソース管理（オプショナル）
        self._resource_manager: Optional['ResourceManager'] = None
        if HAS_RESOURCE_MANAGER:
            try:
                self._resource_manager = ResourceManager(self.ssm_path)
            except Exception as e:
                logger.warning(f"Failed to initialize ResourceManager: {e}")
        
        # ファイルロック（簡易版）
        self._file_locks: Dict[str, threading.Lock] = {}
        self._locks_lock = threading.Lock()
    
    def _get_file_lock(self, file_path: str) -> threading.Lock:
        """
        ファイルパスに対応するロックを取得
        
        Args:
            file_path: ファイルパス
            
        Returns:
            threading.Lock: ファイルロック
        """
        with self._locks_lock:
            if file_path not in self._file_locks:
                self._file_locks[file_path] = threading.Lock()
            return self._file_locks[file_path]
    
    def _verify_file_integrity(self, file_path: Path) -> bool:
        """
        ファイルの整合性を検証
        
        Args:
            file_path: 検証するファイルパス
            
        Returns:
            bool: ファイルが有効な場合True
        """
        if not file_path.exists():
            return False
        
        try:
            # JSONファイルの場合
            if file_path.suffix == '.json':
                with open(file_path, 'r', encoding='utf-8') as f:
                    json.load(f)
                return True
            # pickleファイルの場合
            elif file_path.suffix in ['.pkl', '.pickle']:
                with open(file_path, 'rb') as f:
                    pickle.load(f)
                return True
            # gzip圧縮ファイルの場合
            elif file_path.suffix == '.gz' or file_path.name.endswith('.gz'):
                with gzip.open(file_path, 'rb') as f:
                    pickle.load(f)
                return True
            else:
                # その他のファイルは存在確認のみ
                return True
        except (json.JSONDecodeError, pickle.UnpicklingError, EOFError, OSError) as e:
            logger.warning(f"File integrity check failed for {file_path}: {e}")
            return False
    
    def _recover_from_backup(self, file_path: Path) -> bool:
        """
        バックアップからファイルを復旧
        
        Args:
            file_path: 復旧するファイルパス
            
        Returns:
            bool: 復旧に成功した場合True
        """
        backup_path = file_path.with_suffix(file_path.suffix + '.bak')
        
        if not backup_path.exists():
            return False
        
        try:
            # バックアップファイルの整合性を確認
            if not self._verify_file_integrity(backup_path):
                logger.warning(f"Backup file is corrupted: {backup_path}")
                return False
            
            # バックアップから復旧
            shutil.copy2(backup_path, file_path)
            logger.info(f"Recovered {file_path} from backup")
            return True
        except Exception as e:
            logger.error(f"Failed to recover from backup: {e}")
            return False
    
    def _get_globals_dict(self, depth: int = 2) -> Dict[str, Any]:
        """呼び出し元のグローバル変数辞書を取得"""
        if self.globals_dict is not None:
            return self.globals_dict
        
        try:
            frame = inspect.currentframe()
            if frame is None:
                raise RuntimeError("Cannot access calling frame")
            
            caller_frame = frame
            for _ in range(depth):
                if caller_frame.f_back is None:
                    raise RuntimeError("Cannot access calling frame")
                caller_frame = caller_frame.f_back
            
            return caller_frame.f_globals
        finally:
            del frame
    
    def _get_caller_info(self, depth: int = 3) -> Dict[str, str]:
        """
        呼び出し元の情報を取得（ファイル名、関数名など）
        
        Args:
            depth: 呼び出し元からのフレーム深度
            
        Returns:
            dict: 呼び出し元の情報（filename, function_name, line_number）
        """
        try:
            frame = inspect.currentframe()
            if frame is None:
                return {"filename": "<unknown>", "function_name": "<unknown>", "line_number": "0"}
            
            caller_frame = frame
            for _ in range(depth):
                if caller_frame.f_back is None:
                    return {"filename": "<unknown>", "function_name": "<unknown>", "line_number": "0"}
                caller_frame = caller_frame.f_back
            
            filename = caller_frame.f_code.co_filename
            function_name = caller_frame.f_code.co_name
            line_number = caller_frame.f_lineno
            
            # ファイル名を正規化（絶対パスから相対パスに変換）
            try:
                filename = str(Path(filename).relative_to(Path.cwd()))
            except ValueError:
                # 相対パスに変換できない場合はそのまま
                pass
            
            return {
                "filename": filename,
                "function_name": function_name,
                "line_number": str(line_number),
            }
        except Exception as e:
            logger.debug(f"Failed to get caller info: {e}")
            return {"filename": "<unknown>", "function_name": "<unknown>", "line_number": "0"}
        finally:
            if 'frame' in locals():
                del frame
    
    @property
    def is_initialized(self) -> bool:
        """SSMが初期化されているか"""
        return self.ssm_path.exists() and (self.ssm_path / self.CONFIG_FILE).exists()
    
    def init(self, force: bool = False) -> None:
        """
        .ssm ディレクトリを初期化
        
        Args:
            force: 既存の .ssm を上書きするか
        """
        if self.ssm_path.exists():
            if not force:
                message = i18n.translate("info.ssm_already_initialized", base_path=self.base_path)
                print(f"✓ {message}")
                return
            shutil.rmtree(self.ssm_path)
        
        # ディレクトリ構造を作成
        self.ssm_path.mkdir(parents=True)
        (self.ssm_path / self.OBJECTS_DIR).mkdir()
        (self.ssm_path / self.COMMITS_DIR).mkdir()
        (self.ssm_path / self.SNAPSHOTS_DIR).mkdir()
        (self.ssm_path / self.CONTINUOUS_DIR).mkdir()
        (self.ssm_path / self.BRANCHES_DIR).mkdir()
        (self.ssm_path / self.TAGS_DIR).mkdir()
        (self.ssm_path / self.REMOTES_DIR).mkdir()
        
        # 設定ファイルを作成
        config = {
            "version": 1,
            "created_at": datetime.now().isoformat(),
            "exclude": self._default_exclude,
            "language": i18n.get_language(),  # 現在の言語設定を保存
        }
        self._write_json(self.ssm_path / self.CONFIG_FILE, config)
        
        # HEADを初期化（空）
        (self.ssm_path / self.HEAD_FILE).write_text("")
        
        message = i18n.translate("info.ssm_initialized", base_path=self.base_path)
        print(f"✓ {message}")
    
    def _ensure_initialized(self) -> None:
        """初期化されていることを確認
        
        Raises:
            SSMNotInitializedError: SSMが初期化されていない場合
        """
        if not self.is_initialized:
            logger.error(f"SSM not initialized in {self.base_path}")
            raise SSMNotInitializedError(str(self.base_path))
        
        # 言語設定を読み込む
        try:
            config = self._read_json(self.ssm_path / self.CONFIG_FILE)
            if "language" in config:
                i18n.set_language(config["language"])
        except Exception:
            pass  # 設定ファイルの読み込みに失敗しても続行
    
    def _write_json(self, path: Path, data: Any) -> None:
        """
        JSONファイルを書き込む（ファイルロックとバックアップ付き）
        
        Args:
            path: ファイルパス
            data: 書き込むデータ
        """
        # ファイルロックを取得
        lock = self._get_file_lock(str(path))
        with lock:
            # バックアップを作成（既存ファイルがある場合）
            backup_path = path.with_suffix(path.suffix + '.bak')
            if path.exists():
                try:
                    shutil.copy2(path, backup_path)
                except Exception as e:
                    logger.warning(f"Failed to create backup for {path}: {e}")
            
            # 一時ファイルに書き込んでから移動（アトミックな書き込み）
            temp_path = path.with_suffix(path.suffix + '.tmp')
            try:
                with open(temp_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False, default=str)
                # アトミックに移動
                temp_path.replace(path)
            except Exception as e:
                # エラー時は一時ファイルを削除
                if temp_path.exists():
                    try:
                        temp_path.unlink()
                    except Exception:
                        pass
                # バックアップから復旧を試行
                if backup_path.exists() and not path.exists():
                    logger.warning(f"Failed to write {path}, attempting recovery from backup")
                    if self._recover_from_backup(path):
                        logger.info(f"Recovered {path} from backup")
                    else:
                        raise
                else:
                    raise
    
    def _read_json(self, path: Path) -> Any:
        """
        JSONファイルを読み込む（破損検出と復旧付き）
        
        Args:
            path: ファイルパス
            
        Returns:
            Any: 読み込んだデータ
        """
        # ファイルロックを取得
        lock = self._get_file_lock(str(path))
        with lock:
            # ファイルの整合性を確認
            if not self._verify_file_integrity(path):
                # 破損している場合はバックアップから復旧を試行
                logger.warning(f"File {path} is corrupted, attempting recovery from backup")
                if self._recover_from_backup(path):
                    logger.info(f"Recovered {path} from backup")
                else:
                    raise FileNotFoundError(f"File not found or corrupted: {path}")
            
            # ファイルを読み込む
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                # 読み込みエラー時はバックアップから復旧を試行
                logger.warning(f"Failed to read {path}: {e}, attempting recovery from backup")
                if self._recover_from_backup(path):
                    logger.info(f"Recovered {path} from backup")
                    with open(path, 'r', encoding='utf-8') as f:
                        return json.load(f)
                else:
                    raise
    
    def _hash_object(self, data: bytes) -> str:
        """オブジェクトのハッシュを計算"""
        return hashlib.sha256(data).hexdigest()[:16]
    
    def _store_object(self, data: bytes) -> str:
        """オブジェクトを保存してハッシュを返す"""
        obj_hash = self._hash_object(data)
        
        # 2文字のプレフィックスでディレクトリ分割
        prefix = obj_hash[:2]
        obj_dir = self.ssm_path / self.OBJECTS_DIR / prefix
        obj_dir.mkdir(exist_ok=True)
        
        obj_path = obj_dir / obj_hash[2:]
        
        # 圧縮して保存
        if not obj_path.exists():
            with gzip.open(obj_path, 'wb') as f:
                f.write(data)
        
        return obj_hash
    
    def _load_object(self, obj_hash: str) -> bytes:
        """オブジェクトを読み込む"""
        prefix = obj_hash[:2]
        obj_path = self.ssm_path / self.OBJECTS_DIR / prefix / obj_hash[2:]
        
        if not obj_path.exists():
            raise FileNotFoundError(f"Object not found: {obj_hash}")
        
        with gzip.open(obj_path, 'rb') as f:
            return f.read()
    
    def _get_saveable_vars(
        self, 
        globals_dict: Dict[str, Any],
        size_check: bool = True,
        verbose: bool = False,
        check_conflicts: bool = True,
    ) -> Dict[str, Any]:
        """
        保存可能な変数を取得
        
        Args:
            globals_dict: グローバル変数辞書
            size_check: サイズチェックを行うか
            verbose: 詳細ログを表示
            check_conflicts: 変数名の衝突をチェックするか（複数ファイル使用時）
            
        Returns:
            dict: 保存可能な変数
        """
        import types
        
        config = self._read_json(self.ssm_path / self.CONFIG_FILE)
        exclude = set(config.get("exclude", []))
        
        skip_types = (types.ModuleType, types.FunctionType, type)
        result = {}
        total_size = 0
        skipped_vars = []
        large_vars = []
        conflict_warnings = []
        
        # 変数名の衝突をチェック（最新のコミットと比較）
        if check_conflicts:
            try:
                head_file = self.ssm_path / self.HEAD_FILE
                current_commit_hash = head_file.read_text().strip()
                
                if current_commit_hash:
                    commit_path = self.ssm_path / self.COMMITS_DIR / f"{current_commit_hash}.json"
                    if commit_path.exists():
                        previous_commit = self._read_json(commit_path)
                        previous_caller = previous_commit.get("caller", {})
                        previous_filename = previous_caller.get("filename", "<unknown>")
                        
                        # 現在の呼び出し元の情報を取得
                        current_caller = self._get_caller_info(depth=4)
                        current_filename = current_caller.get("filename", "<unknown>")
                        
                        # 異なるファイルからの呼び出しの場合、警告を準備
                        if previous_filename != current_filename and previous_filename != "<unknown>":
                            previous_vars = set(previous_commit.get("variables", {}).keys())
                            conflict_warnings.append({
                                "previous_file": previous_filename,
                                "current_file": current_filename,
                                "previous_vars": previous_vars,
                            })
            except Exception as e:
                logger.debug(f"Failed to check conflicts: {e}")
        
        for name, value in globals_dict.items():
            # 特殊変数をスキップ
            if name.startswith("__") and name.endswith("__"):
                continue
            if name.startswith("_"):
                continue
            if name in exclude:
                continue
            if isinstance(value, skip_types):
                continue
            if is_jupyter_internal_var(name):
                continue
            
            # シリアライズ可能かチェック
            try:
                data = pickle.dumps(value)
                var_size = len(data)
                var_size_mb = var_size / (1024 * 1024)
                
                # サイズチェック
                if size_check:
                    if var_size_mb > self.MAX_VARIABLE_SIZE_MB:
                        skipped_vars.append((name, var_size_mb, "exceeds size limit"))
                        logger.warning(f"Skipped '{name}': {var_size_mb:.1f}MB exceeds limit of {self.MAX_VARIABLE_SIZE_MB}MB")
                        continue
                    
                    if var_size_mb > self.MAX_VARIABLE_SIZE_WARN_MB:
                        large_vars.append((name, var_size_mb))
                        logger.info(f"Large variable detected: '{name}' ({var_size_mb:.1f}MB)")
                    
                    # 総サイズチェック
                    if (total_size + var_size) / (1024 * 1024) > self.MAX_TOTAL_SIZE_MB:
                        skipped_vars.append((name, var_size_mb, "would exceed total size limit"))
                        logger.warning(f"Skipped '{name}': would exceed total size limit of {self.MAX_TOTAL_SIZE_MB}MB")
                        continue
                
                result[name] = value
                total_size += var_size
                
            except Exception as e:
                skipped_vars.append((name, 0, str(e)))
                logger.debug(f"Cannot serialize '{name}': {e}")
                continue
        
        # 警告を表示
        if large_vars and verbose:
            warnings.warn(
                f"Large variables detected: " +
                ", ".join(f"{n} ({s:.1f}MB)" for n, s in large_vars)
            )
        
        if skipped_vars and verbose:
            print(f"⚠ Skipped {len(skipped_vars)} variables (use ssm.log_skipped() for details)")
        
        # 変数名の衝突警告を表示
        if conflict_warnings and verbose:
            for conflict in conflict_warnings:
                current_vars = set(result.keys())
                common_vars = current_vars & conflict["previous_vars"]
                
                if common_vars:
                    warn_msg = i18n.translate(
                        "warn.variable_conflict",
                        previous_file=conflict["previous_file"],
                        current_file=conflict["current_file"],
                        var_count=len(common_vars),
                        vars=", ".join(sorted(common_vars)[:5])  # 最大5個まで表示
                    )
                    if len(common_vars) > 5:
                        warn_msg += f" ... (and {len(common_vars) - 5} more)"
                    warnings.warn(warn_msg, UserWarning)
                    print(f"⚠ {warn_msg}")
        
        # 統計情報を更新
        self._stats["total_saved_bytes"] = total_size
        
        return result
    
    def _serialize_with_retry(
        self,
        value: Any,
        max_attempts: int = None,
    ) -> bytes:
        """
        リトライ付きシリアライズ
        
        Args:
            value: シリアライズする値
            max_attempts: 最大リトライ回数
            
        Returns:
            bytes: シリアライズされたデータ
            
        Raises:
            SerializationError: シリアライズに失敗した場合
        """
        from .exceptions import SerializationError
        
        if max_attempts is None:
            max_attempts = self.MAX_RETRY_ATTEMPTS
        
        last_error = None
        
        for attempt in range(max_attempts):
            try:
                return pickle.dumps(value)
            except Exception as e:
                last_error = e
                if attempt < max_attempts - 1:
                    time.sleep(self.RETRY_DELAY_SECONDS)
                    logger.debug(f"Retry {attempt + 1}/{max_attempts} for serialization")
        
        raise SerializationError(f"Failed to serialize after {max_attempts} attempts: {last_error}")
    
    def commit(self, message: str = "", author: Optional[str] = None) -> str:
        """
        現在の状態をコミット
        
        Args:
            message: コミットメッセージ（最大500文字）
            author: 作成者名（最大100文字）
            
        Returns:
            str: コミットハッシュ
            
        Raises:
            SSMNotInitializedError: SSMが初期化されていない場合
            ValidationError: 入力バリデーションエラー
        """
        self._ensure_initialized()
        
        # 入力バリデーション
        if message and len(message) > 500:
            raise ValidationError("message", "Message must be 500 characters or less")
        if author and len(author) > 100:
            raise ValidationError("author", "Author name must be 100 characters or less")
        
        globals_dict = self._get_globals_dict(depth=3)
        variables = self._get_saveable_vars(globals_dict)
        
        if not variables:
            logger.warning("No variables to commit")
            warn_msg = i18n.translate("msg.no_variables")
            print(f"⚠ {warn_msg}")
            return ""
        
        # リソースチェック（ディスク容量、メモリ）
        if self._resource_manager:
            try:
                # 必要な容量を概算（変数の総サイズ）
                total_size_mb = sum(
                    len(pickle.dumps(v)) / (1024 * 1024) 
                    for v in variables.values()
                )
                self._resource_manager.check_disk_space(required_mb=total_size_mb, auto_cleanup=True)
                self._resource_manager.check_memory_usage(required_mb=total_size_mb, auto_gc=True)
            except Exception as e:
                logger.warning(f"Resource check failed: {e}")
        
        # 各変数をオブジェクトとして保存
        var_hashes: Dict[str, Dict[str, Any]] = {}
        failed_vars: List[str] = []
        
        for name, value in variables.items():
            try:
                data = pickle.dumps(value)
                obj_hash = self._store_object(data)
                var_hashes[name] = {
                    "hash": obj_hash,
                    "type": type(value).__name__,
                    "size": len(data),
                }
                logger.debug(f"Stored variable: {name} (hash: {obj_hash[:7]})")
            except Exception as e:
                failed_vars.append(name)
                logger.warning(f"Failed to serialize '{name}': {e}")
        
        if failed_vars:
            warnings.warn(f"Failed to serialize: {', '.join(failed_vars)}")
        
        # 親コミットを取得（現在のブランチから）
        current_branch = self.get_current_branch()
        if current_branch:
            branch_file = self.ssm_path / self.BRANCHES_DIR / current_branch
            if branch_file.exists():
                parent = branch_file.read_text().strip() or None
            else:
                head_file = self.ssm_path / self.HEAD_FILE
                parent = head_file.read_text().strip() or None
        else:
            head_file = self.ssm_path / self.HEAD_FILE
            parent = head_file.read_text().strip() or None
        
        # 呼び出し元の情報を取得（ファイル名、関数名など）
        caller_info = self._get_caller_info(depth=3)
        
        # コミット情報を作成
        commit_data = {
            "message": message or "Snapshot",
            "author": author or os.environ.get("USER", "unknown"),
            "timestamp": datetime.now().isoformat(),
            "parent": parent,
            "variables": var_hashes,
            "caller": caller_info,  # 呼び出し元の情報を追加
        }
        
        # コミットを保存
        commit_bytes = json.dumps(commit_data, indent=2).encode('utf-8')
        commit_hash = self._hash_object(commit_bytes)
        
        commit_path = self.ssm_path / self.COMMITS_DIR / f"{commit_hash}.json"
        self._write_json(commit_path, commit_data)
        
        # HEADを更新
        head_file = self.ssm_path / self.HEAD_FILE
        head_file.write_text(commit_hash)
        
        # 現在のブランチを更新
        if current_branch:
            branch_file = self.ssm_path / self.BRANCHES_DIR / current_branch
            branch_file.write_text(commit_hash)
        else:
            # デフォルトブランチがなければ作成
            config = self._read_json(self.ssm_path / self.CONFIG_FILE)
            default_branch = config.get("default_branch", "main")
            branch_file = self.ssm_path / self.BRANCHES_DIR / default_branch
            branch_file.write_text(commit_hash)
            config["current_branch"] = default_branch
            self._write_json(self.ssm_path / self.CONFIG_FILE, config)
        
        # 最新スナップショットも保存
        self._save_snapshot("latest", variables)
        
        var_count = len(variables)
        short_hash = commit_hash[:7]
        commit_msg = message or i18n.translate("msg.no_changes")
        info_msg = i18n.translate("info.commit_created", short_hash=short_hash, message=commit_msg, var_count=var_count)
        print(f"✓ {info_msg}")
        
        return commit_hash
    
    def _save_snapshot(self, name: str, variables: Dict[str, Any]) -> None:
        """スナップショットを保存"""
        snapshot_path = self.ssm_path / self.SNAPSHOTS_DIR / name
        with gzip.open(snapshot_path, 'wb') as f:
            pickle.dump(variables, f)
    
    def _load_snapshot(self, name: str) -> Dict[str, Any]:
        """スナップショットを読み込む"""
        snapshot_path = self.ssm_path / self.SNAPSHOTS_DIR / name
        if not snapshot_path.exists():
            raise FileNotFoundError(f"Snapshot not found: {name}")
        
        with gzip.open(snapshot_path, 'rb') as f:
            return pickle.load(f)
    
    def log(self, limit: int = 10, oneline: bool = False) -> List[Dict[str, Any]]:
        """
        コミット履歴を表示
        
        Args:
            limit: 表示するコミット数
            oneline: 1行形式で表示
            
        Returns:
            list: コミット情報のリスト
        """
        self._ensure_initialized()
        
        head_file = self.ssm_path / self.HEAD_FILE
        current = head_file.read_text().strip()
        
        if not current:
            print("No commits yet")
            return []
        
        commits = []
        count = 0
        
        while current and count < limit:
            commit_path = self.ssm_path / self.COMMITS_DIR / f"{current}.json"
            if not commit_path.exists():
                break
            
            commit_data = self._read_json(commit_path)
            commit_data["hash"] = current
            commits.append(commit_data)
            
            if oneline:
                var_count = len(commit_data.get("variables", {}))
                print(f"{current[:7]} {commit_data['message']} ({var_count} vars)")
            else:
                print(f"\ncommit {current}")
                print(f"Author: {commit_data['author']}")
                print(f"Date:   {commit_data['timestamp']}")
                
                # 呼び出し元の情報を表示（複数ファイル使用時の追跡）
                caller_info = commit_data.get("caller", {})
                if caller_info and caller_info.get("filename") != "<unknown>":
                    filename = caller_info.get("filename", "<unknown>")
                    print(f"File:   {filename}")
                
                print(f"\n    {commit_data['message']}")
                var_count = len(commit_data.get("variables", {}))
                print(f"    ({var_count} variables)")
            
            current = commit_data.get("parent")
            count += 1
        
        return commits
    
    def checkout(self, commit_hash: Optional[str] = None) -> None:
        """
        以前のコミット状態に復元
        
        Args:
            commit_hash: コミットハッシュ（短縮形可）
            
        Raises:
            SSMNotInitializedError: SSMが初期化されていない場合
            SSMNoCommitsError: コミットが存在しない場合
            SSMCommitNotFoundError: 指定されたコミットが見つからない場合
        """
        self._ensure_initialized()
        
        if commit_hash is None:
            # HEADのコミットを復元
            head_file = self.ssm_path / self.HEAD_FILE
            commit_hash = head_file.read_text().strip()
            if not commit_hash:
                logger.error("No commits to checkout")
                raise SSMNoCommitsError()
        
        # 短縮ハッシュを展開
        try:
            full_hash = self._resolve_hash(commit_hash)
        except ValueError:
            logger.error(f"Commit not found: {commit_hash}")
            raise SSMCommitNotFoundError(commit_hash)
        
        commit_path = self.ssm_path / self.COMMITS_DIR / f"{full_hash}.json"
        if not commit_path.exists():
            logger.error(f"Commit file not found: {commit_path}")
            raise SSMCommitNotFoundError(commit_hash)
        
        commit_data = self._read_json(commit_path)
        
        # 変数を復元
        globals_dict = self._get_globals_dict(depth=3)
        restored = 0
        failed = 0
        
        for name, var_info in commit_data.get("variables", {}).items():
            try:
                data = self._load_object(var_info["hash"])
                value = pickle.loads(data)
                globals_dict[name] = value
                restored += 1
                logger.debug(f"Restored variable: {name}")
            except Exception as e:
                failed += 1
                logger.warning(f"Failed to restore '{name}': {e}")
                warnings.warn(f"Failed to restore '{name}': {e}")
        
        logger.info(f"Restored {restored} variables from {full_hash[:7]}")
        info_msg = i18n.translate("info.variables_restored", restored=restored, short_hash=full_hash[:7])
        print(f"✓ {info_msg}")
        if failed > 0:
            warn_msg = i18n.translate("warn.partial_load", loaded=restored, total=restored + failed)
            print(f"  ⚠️ {warn_msg}")
    
    def _resolve_hash(self, short_hash: str) -> str:
        """短縮ハッシュを完全なハッシュに展開"""
        commits_dir = self.ssm_path / self.COMMITS_DIR
        
        matches = []
        for commit_file in commits_dir.glob("*.json"):
            full_hash = commit_file.stem
            if full_hash.startswith(short_hash):
                matches.append(full_hash)
        
        if len(matches) == 0:
            raise ValueError(f"No commit found matching: {short_hash}")
        elif len(matches) > 1:
            raise ValueError(f"Ambiguous hash: {short_hash} (matches: {matches})")
        
        return matches[0]
    
    def status(self) -> Dict[str, Any]:
        """
        現在の状態を表示
        """
        self._ensure_initialized()
        
        head_file = self.ssm_path / self.HEAD_FILE
        current = head_file.read_text().strip()
        
        globals_dict = self._get_globals_dict(depth=3)
        variables = self._get_saveable_vars(globals_dict)
        
        print(f"On commit: {current[:7] if current else '(none)'}")
        print(f"Variables: {len(variables)}")
        
        if self._continuous_enabled:
            print(f"Continuous: enabled")
        
        print("\nTracked variables:")
        for name, value in sorted(variables.items()):
            type_name = type(value).__name__
            print(f"  {name}: {type_name}")
        
        return {
            "head": current,
            "variables": list(variables.keys()),
            "continuous": self._continuous_enabled,
        }
    
    def diff(self, commit1: Optional[str] = None, commit2: Optional[str] = None) -> None:
        """
        コミット間の差分を表示
        """
        self._ensure_initialized()
        
        head_file = self.ssm_path / self.HEAD_FILE
        current = head_file.read_text().strip()
        
        if not current:
            print("No commits to compare")
            return
        
        # 現在の変数と最新コミットを比較
        globals_dict = self._get_globals_dict(depth=3)
        current_vars = set(self._get_saveable_vars(globals_dict).keys())
        
        commit_path = self.ssm_path / self.COMMITS_DIR / f"{current}.json"
        commit_data = self._read_json(commit_path)
        committed_vars = set(commit_data.get("variables", {}).keys())
        
        added = current_vars - committed_vars
        removed = committed_vars - current_vars
        
        if added:
            print("New variables:")
            for name in sorted(added):
                print(f"  + {name}")
        
        if removed:
            print("Removed variables:")
            for name in sorted(removed):
                print(f"  - {name}")
        
        if not added and not removed:
            print("No changes")
    
    def continuous(self, enable: bool = True, verbose: bool = False) -> None:
        """
        常時記録モードを有効化/無効化
        
        Args:
            enable: 有効化するか
            verbose: 詳細ログを表示するか
        """
        self._ensure_initialized()
        
        if not is_jupyter_environment():
            warn_msg = i18n.translate("warn.continuous_mode_unavailable")
            warnings.warn(warn_msg)
            return
        
        if enable:
            self._continuous_enabled = True
            self._continuous_verbose = verbose
            
            try:
                ip = get_ipython()  # type: ignore
                
                # 既存のフックを削除
                try:
                    ip.events.unregister('post_run_cell', self._continuous_callback)
                except Exception:
                    pass
                
                ip.events.register('post_run_cell', self._continuous_callback)
                print("✓ Continuous mode enabled")
            except Exception as e:
                warnings.warn(f"Failed to enable continuous mode: {e}")
                self._continuous_enabled = False
        else:
            self._continuous_enabled = False
            try:
                ip = get_ipython()  # type: ignore
                ip.events.unregister('post_run_cell', self._continuous_callback)
            except Exception:
                pass
            print("✓ Continuous mode disabled")
    
    def _continuous_callback(self, result=None) -> None:
        """セル実行後のコールバック"""
        if not self._continuous_enabled:
            return
        
        try:
            globals_dict = self._get_globals_dict(depth=4)
            variables = self._get_saveable_vars(globals_dict)
            
            if variables:
                # 常時記録用スナップショットを保存
                autosave_path = self.ssm_path / self.CONTINUOUS_DIR / "autosave"
                with gzip.open(autosave_path, 'wb') as f:
                    pickle.dump(variables, f)
                
                if self._continuous_verbose:
                    print(f"  ✓ Auto-saved {len(variables)} variables")
        except Exception as e:
            if self._continuous_verbose:
                warnings.warn(f"Auto-save failed: {e}")
    
    def recover(self) -> None:
        """
        常時記録から復元
        """
        self._ensure_initialized()
        
        autosave_path = self.ssm_path / self.CONTINUOUS_DIR / "autosave"
        if not autosave_path.exists():
            print("No autosave found")
            return
        
        try:
            with gzip.open(autosave_path, 'rb') as f:
                variables = pickle.load(f)
            
            globals_dict = self._get_globals_dict(depth=3)
            for name, value in variables.items():
                globals_dict[name] = value
            
            info_msg = i18n.translate("info.checkpoint_restored", restored_count=len(variables))
            print(f"✓ {info_msg}")
        except Exception as e:
            raise RuntimeError(f"Failed to recover: {e}")
    
    # ========== チェックポイント機能（長時間実行対応） ==========
    
    @contextmanager
    def checkpoint(
        self,
        interval: int = 300,
        max_checkpoints: int = 5,
        on_error: str = "warn",
        compress: bool = True,
        message: str = "Checkpoint",
    ):
        """
        チェックポイントコンテキストマネージャー（長時間実行対応）
        
        機械学習の学習ループなど、長時間実行されるタスクで使用します。
        指定された間隔で自動的にチェックポイントを保存し、
        中断時やエラー時にも状態を復元可能にします。
        
        Args:
            interval: チェックポイント間隔（秒）、デフォルト5分
            max_checkpoints: 保持するチェックポイント数
            on_error: エラー時の動作 ('ignore', 'warn', 'raise')
            compress: 圧縮するか
            message: チェックポイントメッセージ
            
        Yields:
            CheckpointContext: チェックポイントコンテキスト
            
        Example:
            >>> with ssm.checkpoint(interval=300) as cp:  # 5分ごと
            ...     for epoch in range(1000):
            ...         loss = train()
            ...         cp.step(loss=loss)  # 手動チェックポイント + メトリクス記録
            ...         
            ...         # 学習が長くなっても自動保存される
            
            >>> # 復元
            >>> ssm.restore_checkpoint()  # 最新から復元
        """
        self._ensure_initialized()
        
        ctx = CheckpointContext(
            ssm=self,
            interval=interval,
            max_checkpoints=max_checkpoints,
            on_error=on_error,
            compress=compress,
            message=message,
        )
        
        try:
            ctx.start()
            yield ctx
        except Exception as e:
            # 例外発生時は緊急チェックポイント
            ctx._save_checkpoint(f"Emergency: {type(e).__name__}")
            raise
        finally:
            ctx.stop()
    
    def restore_checkpoint(
        self,
        checkpoint: Optional[Union[str, Path]] = None,
    ) -> Dict[str, Any]:
        """
        チェックポイントから復元
        
        Args:
            checkpoint: チェックポイントファイル（Noneの場合は最新）
            
        Returns:
            dict: 復元されたメタ情報
        """
        self._ensure_initialized()
        
        checkpoint_dir = self.ssm_path / self.CHECKPOINTS_DIR
        
        if checkpoint is None:
            # 最新のチェックポイントを取得
            checkpoints = sorted(
                checkpoint_dir.glob("checkpoint_*.gz"),
                key=lambda p: p.stat().st_mtime,
                reverse=True
            )
            
            if not checkpoints:
                raise FileNotFoundError("No checkpoints found")
            
            checkpoint = checkpoints[0]
        
        checkpoint = Path(checkpoint)
        
        # 読み込み
        with gzip.open(checkpoint, 'rb') as f:
            data = pickle.load(f)
        
        # 変数を復元
        globals_dict = self._get_globals_dict(depth=3)
        restored_count = 0
        
        for name, value in data.get("variables", {}).items():
            globals_dict[name] = value
            restored_count += 1
        
        meta = {
            "file": str(checkpoint),
            "timestamp": data.get("timestamp"),
            "message": data.get("message"),
            "step_count": data.get("step_count"),
            "metrics": data.get("metrics", {}),
            "restored_count": restored_count,
        }
        
        info_msg = i18n.translate("info.checkpoint_restored", restored_count=restored_count)
        print(f"✓ {info_msg}")
        print(f"  Timestamp: {data.get('timestamp')}")
        print(f"  Message: {data.get('message')}")
        
        return meta
    
    def list_checkpoints(self) -> List[Dict[str, Any]]:
        """
        利用可能なチェックポイントを一覧表示
        
        Returns:
            list: チェックポイント情報のリスト
        """
        self._ensure_initialized()
        
        checkpoint_dir = self.ssm_path / self.CHECKPOINTS_DIR
        checkpoints = []
        
        if not checkpoint_dir.exists():
            return checkpoints
        
        for cp_file in sorted(
            checkpoint_dir.glob("checkpoint_*.gz"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        ):
            try:
                with gzip.open(cp_file, 'rb') as f:
                    data = pickle.load(f)
                
                checkpoints.append({
                    "file": str(cp_file.name),
                    "timestamp": data.get("timestamp"),
                    "message": data.get("message"),
                    "step_count": data.get("step_count"),
                    "variable_count": len(data.get("variables", {})),
                    "metrics": data.get("metrics", {}),
                })
            except Exception as e:
                logger.warning(f"Failed to read checkpoint {cp_file}: {e}")
        
        return checkpoints
    
    def clean_checkpoints(self, keep: int = 0) -> int:
        """
        古いチェックポイントを削除
        
        Args:
            keep: 保持するチェックポイント数（0ですべて削除）
            
        Returns:
            int: 削除したチェックポイント数
        """
        self._ensure_initialized()
        
        checkpoint_dir = self.ssm_path / self.CHECKPOINTS_DIR
        
        if not checkpoint_dir.exists():
            return 0
        
        checkpoints = sorted(
            checkpoint_dir.glob("checkpoint_*.gz"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )
        
        deleted = 0
        for old_cp in checkpoints[keep:]:
            try:
                old_cp.unlink()
                deleted += 1
            except Exception as e:
                logger.warning(f"Failed to delete checkpoint: {e}")
        
        if deleted > 0:
            print(f"✓ Deleted {deleted} checkpoint(s)")
        
        return deleted
    
    # ========== 形式互換性機能 ==========
    
    def export(
        self,
        output_path: Union[str, Path],
        commit_hash: Optional[str] = None,
        format: Optional[str] = None,
        compress: Union[bool, str] = False,
    ) -> Path:
        """
        コミットを従来形式（.pkl, .json など）でエクスポート
        
        Args:
            output_path: 出力ファイルパス
            commit_hash: エクスポートするコミット（Noneの場合はHEAD）
            format: 出力形式（None の場合は拡張子から自動検出）
            compress: 圧縮形式（True, 'gzip', 'bz2', または False）
            
        Returns:
            Path: 出力されたファイルのパス
            
        Example:
            >>> ssm.export("backup.pkl")  # HEADをpickleでエクスポート
            >>> ssm.export("data.json", commit_hash="abc123", format="json")
        """
        from .core import save_session
        from .formats import detect_format
        
        self._ensure_initialized()
        
        output_path = Path(output_path)
        
        # コミットを取得
        if commit_hash is None:
            head_file = self.ssm_path / self.HEAD_FILE
            commit_hash = head_file.read_text().strip()
            if not commit_hash:
                raise SSMNoCommitsError()
        
        full_hash = self._resolve_hash(commit_hash)
        commit_path = self.ssm_path / self.COMMITS_DIR / f"{full_hash}.json"
        
        if not commit_path.exists():
            raise SSMCommitNotFoundError(commit_hash)
        
        commit_data = self._read_json(commit_path)
        
        # 変数を復元
        variables = {}
        for name, var_info in commit_data.get("variables", {}).items():
            try:
                data = self._load_object(var_info["hash"])
                value = pickle.loads(data)
                variables[name] = value
            except Exception as e:
                logger.warning(f"Failed to load '{name}': {e}")
        
        # 形式を検出
        if format is None:
            format = detect_format(output_path)
        
        # 従来のsave_sessionを使用してエクスポート
        save_session(
            file_path=output_path,
            globals_dict=variables,
            compress=compress,
            format=format,
        )
        
        logger.info(f"Exported {len(variables)} variables to {output_path}")
        info_msg = i18n.translate("info.session_saved", file_path=output_path, size=0, format=format)
        print(f"✓ {info_msg}")
        print(f"  Format: {format}, Commit: {full_hash[:7]}")
        
        return output_path
    
    def import_session(
        self,
        input_path: Union[str, Path],
        message: Optional[str] = None,
        format: Optional[str] = None,
    ) -> str:
        """
        従来形式（.pkl, .json など）からインポートしてコミット
        
        Args:
            input_path: 入力ファイルパス
            message: コミットメッセージ（Noneの場合は自動生成）
            format: 入力形式（None の場合は拡張子から自動検出）
            
        Returns:
            str: 作成されたコミットのハッシュ
            
        Example:
            >>> ssm.import_session("old_session.pkl")
            >>> ssm.import_session("data.json", message="Import from JSON")
        """
        from .core import load_session
        from .formats import detect_format
        
        self._ensure_initialized()
        
        input_path = Path(input_path)
        
        if not input_path.exists():
            raise FileNotFoundError(f"File not found: {input_path}")
        
        # 形式を検出
        if format is None:
            format = detect_format(input_path)
        
        # 一時的な辞書に読み込み
        loaded_vars: Dict[str, Any] = {}
        load_session(
            file_path=input_path,
            globals_dict=loaded_vars,
            format=format,
        )
        
        if not loaded_vars:
            warn_msg = i18n.translate("msg.no_variables")
            print(f"⚠ {warn_msg}")
            return ""
        
        # 読み込んだ変数を使ってコミット
        original_globals = self.globals_dict
        self.globals_dict = loaded_vars
        
        try:
            if message is None:
                message = f"Import from {input_path.name}"
            
            commit_hash = self.commit(message)
            
            logger.info(f"Imported {len(loaded_vars)} variables from {input_path}")
            print(f"✓ Imported {len(loaded_vars)} variables from {input_path}")
            print(f"  Format: {format}, Commit: {commit_hash[:7] if commit_hash else 'none'}")
            
            return commit_hash
        finally:
            self.globals_dict = original_globals
    
    def convert(
        self,
        input_path: Union[str, Path],
        output_path: Union[str, Path],
        input_format: Optional[str] = None,
        output_format: Optional[str] = None,
        compress: Union[bool, str] = False,
    ) -> Path:
        """
        ファイル形式を変換（SSMを経由せずに直接変換）
        
        Args:
            input_path: 入力ファイルパス
            output_path: 出力ファイルパス
            input_format: 入力形式（Noneで自動検出）
            output_format: 出力形式（Noneで自動検出）
            compress: 圧縮形式
            
        Returns:
            Path: 出力されたファイルのパス
            
        Example:
            >>> ssm.convert("data.pkl", "data.json")
            >>> ssm.convert("old.json", "new.pkl", compress=True)
        """
        from .core import load_session, save_session
        from .formats import detect_format
        
        input_path = Path(input_path)
        output_path = Path(output_path)
        
        if not input_path.exists():
            raise FileNotFoundError(f"File not found: {input_path}")
        
        # 形式を検出
        if input_format is None:
            input_format = detect_format(input_path)
        if output_format is None:
            output_format = detect_format(output_path)
        
        # 読み込み
        loaded_vars: Dict[str, Any] = {}
        load_session(
            file_path=input_path,
            globals_dict=loaded_vars,
            format=input_format,
        )
        
        # 書き込み
        save_session(
            file_path=output_path,
            globals_dict=loaded_vars,
            format=output_format,
            compress=compress,
        )
        
        print(f"✓ Converted {len(loaded_vars)} variables")
        print(f"  {input_path} ({input_format}) → {output_path} ({output_format})")
        
        return output_path
    
    def config(self, key: Optional[str] = None, value: Optional[Any] = None) -> Any:
        """
        設定を取得/設定
        
        Args:
            key: 設定キー
            value: 設定値（Noneの場合は取得）
        """
        self._ensure_initialized()
        
        config_path = self.ssm_path / self.CONFIG_FILE
        config = self._read_json(config_path)
        
        if key is None:
            # 全設定を表示
            for k, v in config.items():
                print(f"{k}: {v}")
            return config
        
        if value is None:
            # 値を取得
            return config.get(key)
        
        # 値を設定
        config[key] = value
        self._write_json(config_path, config)
        # 言語設定の場合はグローバル設定も更新
        if key == "language":
            try:
                i18n.set_language(value)
            except Exception:
                pass
        info_msg = i18n.translate("msg.operation_completed")
        print(f"✓ {info_msg}: {key} = {value}")
        return value
    
    def exclude(self, *names: str) -> None:
        """
        除外リストに変数を追加
        
        Args:
            *names: 除外する変数名
        """
        self._ensure_initialized()
        
        config_path = self.ssm_path / self.CONFIG_FILE
        config = self._read_json(config_path)
        
        exclude_list = set(config.get("exclude", []))
        exclude_list.update(names)
        config["exclude"] = list(exclude_list)
        
        self._write_json(config_path, config)
        print(f"✓ Added to exclude: {', '.join(names)}")
    
    # ========== ブランチ機能 ==========
    
    def branch(self, branch_name: Optional[str] = None, create: bool = False) -> Union[str, List[str]]:
        """
        ブランチの作成、一覧表示、または現在のブランチを取得
        
        Args:
            branch_name: ブランチ名（Noneの場合は一覧表示または現在のブランチを取得）
            create: 新しいブランチを作成するか（デフォルト: False）
            
        Returns:
            str: ブランチ名（作成または取得時）
            list: ブランチ名のリスト（一覧表示時）
            
        Example:
            >>> ssm.branch()  # 現在のブランチを取得
            'main'
            >>> ssm.branch()  # すべてのブランチを一覧表示
            ['main', 'feature']
            >>> ssm.branch('feature', create=True)  # 新しいブランチを作成
            'feature'
        """
        self._ensure_initialized()
        
        branches_dir = self.ssm_path / self.BRANCHES_DIR
        
        if branch_name is None:
            # ブランチ一覧を返す
            if not branches_dir.exists():
                return []
            return sorted([f.name for f in branches_dir.iterdir() if f.is_file()])
        
        # ブランチ名の検証
        if not branch_name or not branch_name.replace("_", "").replace("-", "").isalnum():
            raise ValidationError("branch_name", "Branch name must be alphanumeric with underscores or hyphens")
        
        branch_file = branches_dir / branch_name
        
        if create:
            # 新しいブランチを作成
            if branch_file.exists():
                i18n = _get_i18n()
                error_msg = i18n.translate("error.branch_already_exists", branch_name=branch_name)
                raise SSMConfigError(error_msg)
            
            # 現在のHEADを取得
            head_file = self.ssm_path / self.HEAD_FILE
            current_commit = head_file.read_text().strip()
            
            if not current_commit:
                raise SSMNoCommitsError()
            
            # ブランチファイルを作成
            branch_file.write_text(current_commit)
            
            # デフォルトブランチがなければ設定
            config = self._read_json(self.ssm_path / self.CONFIG_FILE)
            if "default_branch" not in config:
                config["default_branch"] = "main"
                self._write_json(self.ssm_path / self.CONFIG_FILE, config)
            
            info_msg = i18n.translate("info.branch_created", branch_name=branch_name, commit=current_commit[:7])
            print(f"✓ {info_msg}")
            return branch_name
        else:
            # ブランチの存在確認
            if not branch_file.exists():
                raise SSMBranchNotFoundError(branch_name)
            return branch_name
    
    def checkout_branch(self, branch_name: str) -> None:
        """
        ブランチに切り替え
        
        Args:
            branch_name: 切り替えるブランチ名
            
        Raises:
            SSMNotInitializedError: SSMが初期化されていない場合
            SSMConfigError: ブランチが存在しない場合
        """
        self._ensure_initialized()
        
        branch_file = self.ssm_path / self.BRANCHES_DIR / branch_name
        if not branch_file.exists():
            raise SSMBranchNotFoundError(branch_name)
        
        # ブランチのコミットを取得
        commit_hash = branch_file.read_text().strip()
        
        # HEADを更新
        head_file = self.ssm_path / self.HEAD_FILE
        head_file.write_text(commit_hash)
        
        # 現在のブランチを設定ファイルに保存
        config = self._read_json(self.ssm_path / self.CONFIG_FILE)
        config["current_branch"] = branch_name
        self._write_json(self.ssm_path / self.CONFIG_FILE, config)
        
        # 変数を復元
        self.checkout(commit_hash)
        
        info_msg = i18n.translate("info.branch_checked_out", branch_name=branch_name)
        print(f"✓ {info_msg}")
    
    def get_current_branch(self) -> Optional[str]:
        """
        現在のブランチを取得
        
        Returns:
            str or None: 現在のブランチ名（ブランチにいない場合はNone）
        """
        self._ensure_initialized()
        
        config = self._read_json(self.ssm_path / self.CONFIG_FILE)
        return config.get("current_branch")
    
    # ========== マージ機能 ==========
    
    def merge(self, branch_name: str, message: Optional[str] = None) -> str:
        """
        ブランチを現在のブランチにマージ
        
        Args:
            branch_name: マージするブランチ名
            message: マージコミットメッセージ（Noneの場合は自動生成）
            
        Returns:
            str: マージコミットのハッシュ
            
        Raises:
            SSMNotInitializedError: SSMが初期化されていない場合
            SSMConfigError: ブランチが存在しない場合
        """
        self._ensure_initialized()
        
        # マージ元のブランチを取得
        branch_file = self.ssm_path / self.BRANCHES_DIR / branch_name
        if not branch_file.exists():
            raise SSMBranchNotFoundError(branch_name)
        
        merge_commit = branch_file.read_text().strip()
        
        # 現在のHEADを取得
        head_file = self.ssm_path / self.HEAD_FILE
        current_commit = head_file.read_text().strip()
        
        if not current_commit:
            raise SSMNoCommitsError()
        
        # 既にマージ済みかチェック
        if merge_commit == current_commit:
            info_msg = i18n.translate("info.already_merged", branch_name=branch_name)
            print(f"✓ {info_msg}")
            return current_commit
        
        # 2つのコミットの共通祖先を探す（簡易版：最初の共通コミット）
        common_ancestor = self._find_common_ancestor(current_commit, merge_commit)
        
        # マージコミットを作成（2つの親を持つ）
        globals_dict = self._get_globals_dict(depth=3)
        variables = self._get_saveable_vars(globals_dict)
        
        if not variables:
            raise SSMError("No variables to merge")
        
        # 変数を保存
        var_hashes: Dict[str, Dict[str, Any]] = {}
        for name, value in variables.items():
            try:
                data = pickle.dumps(value)
                obj_hash = self._store_object(data)
                var_hashes[name] = {
                    "hash": obj_hash,
                    "type": type(value).__name__,
                    "size": len(data),
                }
            except Exception as e:
                logger.warning(f"Failed to serialize '{name}': {e}")
        
        # マージコミット情報を作成
        if message is None:
            current_branch = self.get_current_branch() or "HEAD"
            message = i18n.translate("msg.merge_commit", branch_name=branch_name, current_branch=current_branch)
        
        commit_data = {
            "message": message,
            "author": os.environ.get("USER", "unknown"),
            "timestamp": datetime.now().isoformat(),
            "parent": current_commit,
            "merge_parent": merge_commit,
            "variables": var_hashes,
        }
        
        # マージコミットを保存
        commit_bytes = json.dumps(commit_data, indent=2).encode('utf-8')
        merge_hash = self._hash_object(commit_bytes)
        
        commit_path = self.ssm_path / self.COMMITS_DIR / f"{merge_hash}.json"
        self._write_json(commit_path, commit_data)
        
        # HEADを更新
        head_file.write_text(merge_hash)
        
        # ブランチを更新
        current_branch = self.get_current_branch()
        if current_branch:
            branch_file = self.ssm_path / self.BRANCHES_DIR / current_branch
            branch_file.write_text(merge_hash)
        
        info_msg = i18n.translate("info.merge_completed", branch_name=branch_name, commit=merge_hash[:7])
        print(f"✓ {info_msg}")
        
        return merge_hash
    
    def _find_common_ancestor(self, commit1: str, commit2: str) -> Optional[str]:
        """
        2つのコミットの共通祖先を探す（簡易版）
        
        Args:
            commit1: コミット1のハッシュ
            commit2: コミット2のハッシュ
            
        Returns:
            str or None: 共通祖先のハッシュ（見つからない場合はNone）
        """
        # コミット1の祖先を取得
        ancestors1 = set()
        current = commit1
        while current:
            ancestors1.add(current)
            commit_path = self.ssm_path / self.COMMITS_DIR / f"{current}.json"
            if not commit_path.exists():
                break
            commit_data = self._read_json(commit_path)
            current = commit_data.get("parent")
            if current in ancestors1:  # 循環参照を防ぐ
                break
        
        # コミット2の祖先を辿って共通祖先を探す
        current = commit2
        visited = set()
        while current:
            if current in ancestors1:
                return current
            if current in visited:  # 循環参照を防ぐ
                break
            visited.add(current)
            commit_path = self.ssm_path / self.COMMITS_DIR / f"{current}.json"
            if not commit_path.exists():
                break
            commit_data = self._read_json(commit_path)
            current = commit_data.get("parent")
        
        return None
    
    # ========== タグ機能 ==========
    
    def tag(self, tag_name: str, commit_hash: Optional[str] = None, message: Optional[str] = None) -> str:
        """
        コミットにタグを付ける
        
        Args:
            tag_name: タグ名
            commit_hash: タグを付けるコミット（Noneの場合はHEAD）
            message: タグメッセージ（オプション）
            
        Returns:
            str: タグ名
            
        Raises:
            SSMNotInitializedError: SSMが初期化されていない場合
            SSMCommitNotFoundError: コミットが見つからない場合
            ValidationError: タグ名が無効な場合
        """
        self._ensure_initialized()
        
        # タグ名の検証
        if not tag_name or not tag_name.replace("_", "").replace("-", "").replace(".", "").isalnum():
            raise ValidationError("tag_name", "Tag name must be alphanumeric with underscores, hyphens, or dots")
        
        # コミットハッシュを取得
        if commit_hash is None:
            head_file = self.ssm_path / self.HEAD_FILE
            commit_hash = head_file.read_text().strip()
            if not commit_hash:
                raise SSMNoCommitsError()
        else:
            # 短縮ハッシュを展開
            try:
                commit_hash = self._resolve_hash(commit_hash)
            except ValueError:
                raise SSMCommitNotFoundError(commit_hash)
        
        # タグファイルを作成
        tag_file = self.ssm_path / self.TAGS_DIR / tag_name
        if tag_file.exists():
            i18n = _get_i18n()
            error_msg = i18n.translate("error.tag_already_exists", tag_name=tag_name)
            raise SSMConfigError(error_msg)
        
        tag_data = {
            "commit": commit_hash,
            "message": message or f"Tag: {tag_name}",
            "timestamp": datetime.now().isoformat(),
        }
        
        self._write_json(tag_file, tag_data)
        
        info_msg = i18n.translate("info.tag_created", tag_name=tag_name, commit=commit_hash[:7])
        print(f"✓ {info_msg}")
        
        return tag_name
    
    def list_tags(self) -> List[Dict[str, Any]]:
        """
        すべてのタグを一覧表示
        
        Returns:
            list: タグ情報のリスト
        """
        self._ensure_initialized()
        
        tags_dir = self.ssm_path / self.TAGS_DIR
        if not tags_dir.exists():
            return []
        
        tags = []
        for tag_file in tags_dir.iterdir():
            if tag_file.is_file():
                tag_data = self._read_json(tag_file)
                tags.append({
                    "name": tag_file.name,
                    "commit": tag_data.get("commit"),
                    "message": tag_data.get("message"),
                    "timestamp": tag_data.get("timestamp"),
                })
        
        return sorted(tags, key=lambda x: x["timestamp"] or "", reverse=True)
    
    def checkout_tag(self, tag_name: str) -> None:
        """
        タグからチェックアウト
        
        Args:
            tag_name: タグ名
            
        Raises:
            SSMNotInitializedError: SSMが初期化されていない場合
            SSMConfigError: タグが存在しない場合
        """
        self._ensure_initialized()
        
        tag_file = self.ssm_path / self.TAGS_DIR / tag_name
        if not tag_file.exists():
            raise SSMTagNotFoundError(tag_name)
        
        tag_data = self._read_json(tag_file)
        commit_hash = tag_data.get("commit")
        
        if not commit_hash:
            i18n = _get_i18n()
            error_msg = i18n.translate("error.tag_no_commit", tag_name=tag_name)
            raise SSMConfigError(error_msg)
        
        # チェックアウト
        self.checkout(commit_hash)
        
        info_msg = i18n.translate("info.tag_checked_out", tag_name=tag_name, commit=commit_hash[:7])
        print(f"✓ {info_msg}")
    
    # ========== リモートリポジトリ機能 ==========
    
    def remote_add(self, name: str, url: str) -> None:
        """
        リモートリポジトリを追加
        
        Args:
            name: リモート名（例: 'origin'）
            url: リモートURL（ファイルパスまたはURL）
            
        Raises:
            SSMNotInitializedError: SSMが初期化されていない場合
            ValidationError: リモート名が無効な場合
        """
        self._ensure_initialized()
        
        # リモート名の検証
        if not name or not name.replace("_", "").replace("-", "").isalnum():
            raise ValidationError("remote_name", "Remote name must be alphanumeric with underscores or hyphens")
        
        remote_file = self.ssm_path / self.REMOTES_DIR / name
        if remote_file.exists():
            i18n = _get_i18n()
            error_msg = i18n.translate("error.remote_already_exists", remote_name=name)
            raise SSMConfigError(error_msg)
        
        remote_data = {
            "url": url,
            "created_at": datetime.now().isoformat(),
        }
        
        self._write_json(remote_file, remote_data)
        
        info_msg = i18n.translate("info.remote_added", name=name, url=url)
        print(f"✓ {info_msg}")
    
    def remote_list(self) -> Dict[str, str]:
        """
        リモートリポジトリの一覧を取得
        
        Returns:
            dict: リモート名とURLの辞書
        """
        self._ensure_initialized()
        
        remotes_dir = self.ssm_path / self.REMOTES_DIR
        if not remotes_dir.exists():
            return {}
        
        remotes = {}
        for remote_file in remotes_dir.iterdir():
            if remote_file.is_file():
                remote_data = self._read_json(remote_file)
                remotes[remote_file.name] = remote_data.get("url", "")
        
        return remotes
    
    def push(self, remote_name: str = "origin", branch_name: Optional[str] = None) -> None:
        """
        リモートリポジトリにプッシュ
        
        Args:
            remote_name: リモート名（デフォルト: 'origin'）
            branch_name: プッシュするブランチ（Noneの場合は現在のブランチ）
            
        Raises:
            SSMNotInitializedError: SSMが初期化されていない場合
            SSMConfigError: リモートが存在しない場合
        """
        self._ensure_initialized()
        
        remote_file = self.ssm_path / self.REMOTES_DIR / remote_name
        if not remote_file.exists():
            raise SSMRemoteNotFoundError(remote_name)
        
        remote_data = self._read_json(remote_file)
        remote_url = remote_data.get("url")
        
        if not remote_url:
            i18n = _get_i18n()
            error_msg = i18n.translate("error.remote_no_url", remote_name=remote_name)
            raise SSMConfigError(error_msg)
        
        # ブランチ名を取得
        if branch_name is None:
            branch_name = self.get_current_branch() or "main"
        
        # 現在のコミットを取得
        head_file = self.ssm_path / self.HEAD_FILE
        current_commit = head_file.read_text().strip()
        
        if not current_commit:
            raise SSMNoCommitsError()
        
        # リモートがファイルパスの場合
        if remote_url.startswith("/") or remote_url.startswith(".") or "://" not in remote_url:
            remote_path = Path(remote_url)
            if not remote_path.exists():
                # リモートリポジトリを初期化
                from .ssm import SSM
                remote_ssm = SSM(path=remote_path)
                remote_ssm.init()
            
            # リモートのブランチファイルを更新
            remote_ssm_path = remote_path / self.SSM_DIR
            remote_branch_file = remote_ssm_path / self.BRANCHES_DIR / branch_name
            remote_branch_file.parent.mkdir(parents=True, exist_ok=True)
            remote_branch_file.write_text(current_commit)
            
            # コミットとオブジェクトをコピー（簡易版：すべてコピー）
            self._copy_to_remote(remote_ssm_path)
            
            info_msg = i18n.translate("info.push_completed", remote=remote_name, branch=branch_name, commit=current_commit[:7])
            print(f"✓ {info_msg}")
        else:
            # URL形式のリモート（将来の拡張用）
            raise NotImplementedError("URL-based remotes are not yet implemented")
    
    def pull(self, remote_name: str = "origin", branch_name: Optional[str] = None) -> None:
        """
        リモートリポジトリからプル
        
        Args:
            remote_name: リモート名（デフォルト: 'origin'）
            branch_name: プルするブランチ（Noneの場合は現在のブランチ）
            
        Raises:
            SSMNotInitializedError: SSMが初期化されていない場合
            SSMRemoteNotFoundError: リモートが存在しない場合
        """
        self._ensure_initialized()
        
        remote_file = self.ssm_path / self.REMOTES_DIR / remote_name
        if not remote_file.exists():
            raise SSMRemoteNotFoundError(remote_name)
        
        remote_data = self._read_json(remote_file)
        remote_url = remote_data.get("url")
        
        if not remote_url:
            i18n = _get_i18n()
            error_msg = i18n.translate("error.remote_no_url", remote_name=remote_name)
            raise SSMConfigError(error_msg)
        
        # ブランチ名を取得
        if branch_name is None:
            branch_name = self.get_current_branch() or "main"
        
        # リモートがファイルパスの場合
        if remote_url.startswith("/") or remote_url.startswith(".") or "://" not in remote_url:
            remote_path = Path(remote_url)
            remote_ssm_path = remote_path / self.SSM_DIR
            
            if not remote_ssm_path.exists():
                i18n = _get_i18n()
                error_msg = i18n.translate("error.remote_repository_not_found", remote_url=remote_url)
                raise SSMConfigError(error_msg)
            
            # リモートのブランチからコミットを取得
            remote_branch_file = remote_ssm_path / self.BRANCHES_DIR / branch_name
            if not remote_branch_file.exists():
                raise SSMBranchNotFoundError(branch_name)
            
            remote_commit = remote_branch_file.read_text().strip()
            
            # コミットとオブジェクトをコピー
            self._copy_from_remote(remote_ssm_path)
            
            # 現在のブランチを更新
            current_branch = self.get_current_branch()
            if current_branch:
                branch_file = self.ssm_path / self.BRANCHES_DIR / current_branch
                branch_file.write_text(remote_commit)
            
            # HEADを更新
            head_file = self.ssm_path / self.HEAD_FILE
            head_file.write_text(remote_commit)
            
            # 変数を復元
            self.checkout(remote_commit)
            
            info_msg = i18n.translate("info.pull_completed", remote=remote_name, branch=branch_name, commit=remote_commit[:7])
            print(f"✓ {info_msg}")
        else:
            # URL形式のリモート（将来の拡張用）
            raise NotImplementedError("URL-based remotes are not yet implemented")
    
    def _copy_to_remote(self, remote_ssm_path: Path) -> None:
        """リモートにコミットとオブジェクトをコピー（簡易版）"""
        # コミットをコピー
        commits_dir = self.ssm_path / self.COMMITS_DIR
        remote_commits_dir = remote_ssm_path / self.COMMITS_DIR
        remote_commits_dir.mkdir(parents=True, exist_ok=True)
        
        for commit_file in commits_dir.glob("*.json"):
            remote_commit_file = remote_commits_dir / commit_file.name
            if not remote_commit_file.exists():
                shutil.copy2(commit_file, remote_commit_file)
        
        # オブジェクトをコピー
        objects_dir = self.ssm_path / self.OBJECTS_DIR
        remote_objects_dir = remote_ssm_path / self.OBJECTS_DIR
        remote_objects_dir.mkdir(parents=True, exist_ok=True)
        
        for obj_file in objects_dir.rglob("*"):
            if obj_file.is_file():
                relative_path = obj_file.relative_to(objects_dir)
                remote_obj_file = remote_objects_dir / relative_path
                remote_obj_file.parent.mkdir(parents=True, exist_ok=True)
                if not remote_obj_file.exists():
                    shutil.copy2(obj_file, remote_obj_file)
    
    def _copy_from_remote(self, remote_ssm_path: Path) -> None:
        """リモートからコミットとオブジェクトをコピー（簡易版）"""
        # コミットをコピー
        remote_commits_dir = remote_ssm_path / self.COMMITS_DIR
        commits_dir = self.ssm_path / self.COMMITS_DIR
        
        if remote_commits_dir.exists():
            for commit_file in remote_commits_dir.glob("*.json"):
                local_commit_file = commits_dir / commit_file.name
                if not local_commit_file.exists():
                    shutil.copy2(commit_file, local_commit_file)
        
        # オブジェクトをコピー
        remote_objects_dir = remote_ssm_path / self.OBJECTS_DIR
        objects_dir = self.ssm_path / self.OBJECTS_DIR
        
        if remote_objects_dir.exists():
            for obj_file in remote_objects_dir.rglob("*"):
                if obj_file.is_file():
                    relative_path = obj_file.relative_to(remote_objects_dir)
                    local_obj_file = objects_dir / relative_path
                    local_obj_file.parent.mkdir(parents=True, exist_ok=True)
                    if not local_obj_file.exists():
                        shutil.copy2(obj_file, local_obj_file)


# ========== グローバル関数 ==========

def _get_ssm() -> SSM:
    """グローバルSSMインスタンスを取得"""
    global _ssm_instance
    if _ssm_instance is None:
        _ssm_instance = SSM()
    return _ssm_instance


def init(path: Optional[Union[str, Path]] = None, force: bool = False) -> None:
    """SSMを初期化"""
    global _ssm_instance
    _ssm_instance = SSM(path)
    _ssm_instance.init(force=force)


def commit(message: str = "", author: Optional[str] = None) -> str:
    """現在の状態をコミット"""
    return _get_ssm().commit(message, author)


def log(limit: int = 10, oneline: bool = False) -> List[Dict[str, Any]]:
    """コミット履歴を表示"""
    return _get_ssm().log(limit, oneline)


def checkout(commit_hash: Optional[str] = None) -> None:
    """以前のコミット状態に復元"""
    _get_ssm().checkout(commit_hash)


def status() -> Dict[str, Any]:
    """現在の状態を表示"""
    return _get_ssm().status()


def diff(commit1: Optional[str] = None, commit2: Optional[str] = None) -> None:
    """コミット間の差分を表示"""
    _get_ssm().diff(commit1, commit2)


def continuous(enable: bool = True, verbose: bool = False) -> None:
    """常時記録モードを有効化/無効化"""
    _get_ssm().continuous(enable, verbose)


def recover() -> None:
    """常時記録から復元"""
    _get_ssm().recover()


def config(key: Optional[str] = None, value: Optional[Any] = None) -> Any:
    """設定を取得/設定"""
    return _get_ssm().config(key, value)


def exclude(*names: str) -> None:
    """除外リストに変数を追加"""
    _get_ssm().exclude(*names)


# ========== 言語設定関数（非推奨: トップレベルの set_language/get_language を使用) ==========

def set_language(lang: Union[str, Any]) -> None:
    """
    言語を設定（非推奨）
    
    .. deprecated:: 0.2.0
        この関数は非推奨です。トップレベルの `set_language()` を使用してください::
        
            from SessionSmith import set_language
            set_language('ja')
    
    Args:
        lang: 言語コード ('ja', 'en', 'auto') または Language 列挙型
    """
    import warnings
    warnings.warn(
        "ssm.set_language() is deprecated. Use set_language() from SessionSmith instead.",
        DeprecationWarning,
        stacklevel=2
    )
    i18n.set_language(lang, save_to_ssm=True)


def get_language() -> str:
    """
    現在の言語設定を取得（非推奨）
    
    .. deprecated:: 0.2.0
        この関数は非推奨です。トップレベルの `get_language()` を使用してください::
        
            from SessionSmith import get_language
            get_language()
    
    Returns:
        str: 現在の言語コード ('ja' または 'en')
    """
    import warnings
    warnings.warn(
        "ssm.get_language() is deprecated. Use get_language() from SessionSmith instead.",
        DeprecationWarning,
        stacklevel=2
    )
    return i18n.get_language()


# ========== チェックポイント関数 ==========

def checkpoint(
    interval: int = 300,
    max_checkpoints: int = 5,
    on_error: str = "warn",
    compress: bool = True,
    message: str = "Checkpoint",
):
    """
    チェックポイントコンテキストマネージャー（長時間実行対応）
    
    Args:
        interval: チェックポイント間隔（秒）、デフォルト5分
        max_checkpoints: 保持するチェックポイント数
        on_error: エラー時の動作 ('ignore', 'warn', 'raise')
        compress: 圧縮するか
        message: チェックポイントメッセージ
        
    Returns:
        CheckpointContext: チェックポイントコンテキスト
        
    Example:
        >>> with ssm.checkpoint(interval=300) as cp:
        ...     for epoch in range(1000):
        ...         loss = train()
        ...         cp.step(loss=loss)
    """
    return _get_ssm().checkpoint(
        interval=interval,
        max_checkpoints=max_checkpoints,
        on_error=on_error,
        compress=compress,
        message=message,
    )


def restore_checkpoint(checkpoint: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
    """
    チェックポイントから復元
    
    Args:
        checkpoint: チェックポイントファイル（Noneの場合は最新）
        
    Returns:
        dict: 復元されたメタ情報
    """
    return _get_ssm().restore_checkpoint(checkpoint)


def list_checkpoints() -> List[Dict[str, Any]]:
    """
    利用可能なチェックポイントを一覧表示
    
    Returns:
        list: チェックポイント情報のリスト
    """
    return _get_ssm().list_checkpoints()


def clean_checkpoints(keep: int = 0) -> int:
    """
    古いチェックポイントを削除
    
    Args:
        keep: 保持するチェックポイント数（0ですべて削除）
        
    Returns:
        int: 削除したチェックポイント数
    """
    return _get_ssm().clean_checkpoints(keep)


# ========== 形式互換性関数 ==========

def export(
    output_path: Union[str, Path],
    commit_hash: Optional[str] = None,
    format: Optional[str] = None,
    compress: Union[bool, str] = False,
) -> Path:
    """
    コミットを従来形式（.pkl, .json など）でエクスポート
    
    Args:
        output_path: 出力ファイルパス
        commit_hash: エクスポートするコミット（Noneの場合はHEAD）
        format: 出力形式（None の場合は拡張子から自動検出）
        compress: 圧縮形式
        
    Returns:
        Path: 出力されたファイルのパス
    """
    return _get_ssm().export(output_path, commit_hash, format, compress)


def import_session(
    input_path: Union[str, Path],
    message: Optional[str] = None,
    format: Optional[str] = None,
) -> str:
    """
    従来形式（.pkl, .json など）からインポートしてコミット
    
    Args:
        input_path: 入力ファイルパス
        message: コミットメッセージ
        format: 入力形式
        
    Returns:
        str: 作成されたコミットのハッシュ
    """
    return _get_ssm().import_session(input_path, message, format)


def convert(
    input_path: Union[str, Path],
    output_path: Union[str, Path],
    input_format: Optional[str] = None,
    output_format: Optional[str] = None,
    compress: Union[bool, str] = False,
) -> Path:
    """
    ファイル形式を変換（SSMを経由せずに直接変換）
    
    Args:
        input_path: 入力ファイルパス
        output_path: 出力ファイルパス
        input_format: 入力形式
        output_format: 出力形式
        compress: 圧縮形式
        
    Returns:
        Path: 出力されたファイルのパス
    """
    return _get_ssm().convert(input_path, output_path, input_format, output_format, compress)


# ========== ブランチ関数 ==========

def branch(branch_name: Optional[str] = None, create: bool = False) -> Union[str, List[str]]:
    """
    ブランチの作成、一覧表示、または現在のブランチを取得
    
    Args:
        branch_name: ブランチ名（Noneの場合は一覧表示）
        create: 新しいブランチを作成するか
        
    Returns:
        str or list: ブランチ名またはブランチ名のリスト
        
    Example:
        >>> from SessionSmith import ssm
        >>> ssm.branch()  # ブランチ一覧
        ['main', 'feature']
        >>> ssm.branch('feature', create=True)  # ブランチ作成
        'feature'
    """
    return _get_ssm().branch(branch_name, create)


def checkout_branch(branch_name: str) -> None:
    """
    ブランチに切り替え
    
    Args:
        branch_name: 切り替えるブランチ名
        
    Example:
        >>> from SessionSmith import ssm
        >>> ssm.checkout_branch('feature')
    """
    _get_ssm().checkout_branch(branch_name)


def get_current_branch() -> Optional[str]:
    """
    現在のブランチを取得
    
    Returns:
        str or None: 現在のブランチ名
        
    Example:
        >>> from SessionSmith import ssm
        >>> ssm.get_current_branch()
        'main'
    """
    return _get_ssm().get_current_branch()


# ========== マージ関数 ==========

def merge(branch_name: str, message: Optional[str] = None) -> str:
    """
    ブランチを現在のブランチにマージ
    
    Args:
        branch_name: マージするブランチ名
        message: マージコミットメッセージ
        
    Returns:
        str: マージコミットのハッシュ
        
    Example:
        >>> from SessionSmith import ssm
        >>> ssm.merge('feature')
        'abc1234...'
    """
    return _get_ssm().merge(branch_name, message)


# ========== タグ関数 ==========

def tag(tag_name: str, commit_hash: Optional[str] = None, message: Optional[str] = None) -> str:
    """
    コミットにタグを付ける
    
    Args:
        tag_name: タグ名
        commit_hash: タグを付けるコミット（Noneの場合はHEAD）
        message: タグメッセージ
        
    Returns:
        str: タグ名
        
    Example:
        >>> from SessionSmith import ssm
        >>> ssm.tag('v1.0.0')
        'v1.0.0'
    """
    return _get_ssm().tag(tag_name, commit_hash, message)


def list_tags() -> List[Dict[str, Any]]:
    """
    すべてのタグを一覧表示
    
    Returns:
        list: タグ情報のリスト
        
    Example:
        >>> from SessionSmith import ssm
        >>> ssm.list_tags()
        [{'name': 'v1.0.0', 'commit': 'abc1234...', ...}]
    """
    return _get_ssm().list_tags()


def checkout_tag(tag_name: str) -> None:
    """
    タグからチェックアウト
    
    Args:
        tag_name: タグ名
        
    Example:
        >>> from SessionSmith import ssm
        >>> ssm.checkout_tag('v1.0.0')
    """
    _get_ssm().checkout_tag(tag_name)


# ========== リモート関数 ==========

def remote_add(name: str, url: str) -> None:
    """
    リモートリポジトリを追加
    
    Args:
        name: リモート名（例: 'origin'）
        url: リモートURL（ファイルパスまたはURL）
        
    Example:
        >>> from SessionSmith import ssm
        >>> ssm.remote_add('origin', '/path/to/remote')
    """
    _get_ssm().remote_add(name, url)


def remote_list() -> Dict[str, str]:
    """
    リモートリポジトリの一覧を取得
    
    Returns:
        dict: リモート名とURLの辞書
        
    Example:
        >>> from SessionSmith import ssm
        >>> ssm.remote_list()
        {'origin': '/path/to/remote'}
    """
    return _get_ssm().remote_list()


def push(remote_name: str = "origin", branch_name: Optional[str] = None) -> None:
    """
    リモートリポジトリにプッシュ
    
    Args:
        remote_name: リモート名（デフォルト: 'origin'）
        branch_name: プッシュするブランチ（Noneの場合は現在のブランチ）
        
    Example:
        >>> from SessionSmith import ssm
        >>> ssm.push('origin', 'main')
    """
    _get_ssm().push(remote_name, branch_name)


def pull(remote_name: str = "origin", branch_name: Optional[str] = None) -> None:
    """
    リモートリポジトリからプル
    
    Args:
        remote_name: リモート名（デフォルト: 'origin'）
        branch_name: プルするブランチ（Noneの場合は現在のブランチ）
        
    Example:
        >>> from SessionSmith import ssm
        >>> ssm.pull('origin', 'main')
    """
    _get_ssm().pull(remote_name, branch_name)

