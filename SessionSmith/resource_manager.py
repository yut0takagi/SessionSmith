"""
リソース管理モジュール

ディスク容量、メモリ使用量の監視と管理を行います。
"""

import os
import shutil
import gc
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta

# psutilはオプショナル
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False
    psutil = None

from .exceptions import StorageLimitError, MemoryLimitError
from . import i18n

logger = logging.getLogger("SessionSmith.resource_manager")
logger.addHandler(logging.NullHandler())


class ResourceManager:
    """
    リソース管理クラス
    
    ディスク容量、メモリ使用量の監視と管理を行います。
    """
    
    # デフォルトの警告閾値
    DISK_WARNING_THRESHOLD_PERCENT = 85  # ディスク使用率85%で警告
    DISK_CRITICAL_THRESHOLD_PERCENT = 95  # ディスク使用率95%でクリティカル
    MEMORY_WARNING_THRESHOLD_PERCENT = 80  # メモリ使用率80%で警告
    MEMORY_CRITICAL_THRESHOLD_PERCENT = 90  # メモリ使用率90%でクリティカル
    
    # クリーンアップ設定
    CLEANUP_OLD_CHECKPOINTS_DAYS = 30  # 30日以上古いチェックポイントを削除
    CLEANUP_OLD_COMMITS_DAYS = 90  # 90日以上古いコミットを削除（デフォルト）
    MIN_FREE_SPACE_MB = 100  # 最低限必要な空き容量（MB）
    
    def __init__(self, ssm_path: Path):
        """
        Args:
            ssm_path: SSMディレクトリのパス
        """
        self.ssm_path = Path(ssm_path)
        self._last_disk_check: Optional[datetime] = None
        self._last_memory_check: Optional[datetime] = None
        self._disk_check_interval = timedelta(seconds=60)  # 1分ごとにチェック
        self._memory_check_interval = timedelta(seconds=30)  # 30秒ごとにチェック
    
    def check_disk_space(self, required_mb: float = 0, auto_cleanup: bool = True) -> Dict[str, Any]:
        """
        ディスク容量をチェック
        
        Args:
            required_mb: 必要な容量（MB）
            auto_cleanup: 自動クリーンアップを実行するか
            
        Returns:
            dict: ディスク容量情報
            
        Raises:
            StorageLimitError: ディスク容量が不足している場合
        """
        # キャッシュされた結果を使用（短時間内の再チェックを避ける）
        now = datetime.now()
        if (self._last_disk_check and 
            (now - self._last_disk_check) < self._disk_check_interval):
            # キャッシュされた結果を返す（簡易版）
            pass
        
        self._last_disk_check = now
        
        try:
            # ディスク容量を取得
            disk_usage = shutil.disk_usage(self.ssm_path)
            total_bytes = disk_usage.total
            used_bytes = disk_usage.used
            free_bytes = disk_usage.free
            
            total_mb = total_bytes / (1024 * 1024)
            used_mb = used_bytes / (1024 * 1024)
            free_mb = free_bytes / (1024 * 1024)
            usage_percent = (used_bytes / total_bytes) * 100
            
            # 必要な容量があるかチェック
            if free_mb < (required_mb + self.MIN_FREE_SPACE_MB):
                # 自動クリーンアップを試行
                if auto_cleanup:
                    freed_mb = self.cleanup_old_files()
                    free_mb += freed_mb
                    
                    # それでも不足している場合
                    if free_mb < (required_mb + self.MIN_FREE_SPACE_MB):
                        raise StorageLimitError(
                            used_bytes=used_bytes,
                            limit_bytes=total_bytes,
                            path=str(self.ssm_path)
                        )
                else:
                    raise StorageLimitError(
                        used_bytes=used_bytes,
                        limit_bytes=total_bytes,
                        path=str(self.ssm_path)
                    )
            
            # 警告を表示
            if usage_percent >= self.DISK_CRITICAL_THRESHOLD_PERCENT:
                warn_msg = i18n.translate(
                    "warn.disk_critical",
                    usage_percent=usage_percent,
                    free_mb=free_mb
                )
                logger.critical(warn_msg)
                print(f"⚠️ {warn_msg}")
            elif usage_percent >= self.DISK_WARNING_THRESHOLD_PERCENT:
                warn_msg = i18n.translate(
                    "warn.disk_warning",
                    usage_percent=usage_percent,
                    free_mb=free_mb
                )
                logger.warning(warn_msg)
                print(f"⚠️ {warn_msg}")
            
            return {
                "total_mb": total_mb,
                "used_mb": used_mb,
                "free_mb": free_mb,
                "usage_percent": usage_percent,
                "path": str(self.ssm_path),
            }
        except OSError as e:
            logger.error(f"Failed to check disk space: {e}")
            # ディスク容量が取得できない場合は警告のみ
            return {
                "total_mb": None,
                "used_mb": None,
                "free_mb": None,
                "usage_percent": None,
                "path": str(self.ssm_path),
                "error": str(e),
            }
    
    def check_memory_usage(self, required_mb: float = 0, auto_gc: bool = True) -> Dict[str, Any]:
        """
        メモリ使用量をチェック
        
        Args:
            required_mb: 必要なメモリ（MB）
            auto_gc: 自動ガベージコレクションを実行するか
            
        Returns:
            dict: メモリ使用量情報
            
        Raises:
            MemoryLimitError: メモリが不足している場合
        """
        # キャッシュされた結果を使用（短時間内の再チェックを避ける）
        now = datetime.now()
        if (self._last_memory_check and 
            (now - self._last_memory_check) < self._memory_check_interval):
            # キャッシュされた結果を返す（簡易版）
            pass
        
        self._last_memory_check = now
        
        if not HAS_PSUTIL:
            logger.warning("psutil is not available, memory checking is disabled")
            return {
                "total_mb": None,
                "used_mb": None,
                "available_mb": None,
                "usage_percent": None,
                "error": "psutil not available",
            }
        
        try:
            # メモリ使用量を取得
            process = psutil.Process(os.getpid())
            memory_info = process.memory_info()
            used_bytes = memory_info.rss  # 実メモリ使用量
            
            # システム全体のメモリ情報
            system_memory = psutil.virtual_memory()
            total_bytes = system_memory.total
            available_bytes = system_memory.available
            
            used_mb = used_bytes / (1024 * 1024)
            total_mb = total_bytes / (1024 * 1024)
            available_mb = available_bytes / (1024 * 1024)
            usage_percent = (used_bytes / total_bytes) * 100 if total_bytes > 0 else 0
            
            # 必要なメモリがあるかチェック
            if available_mb < (required_mb + 100):  # 100MBの余裕を持たせる
                # 自動ガベージコレクションを試行
                if auto_gc:
                    gc.collect()
                    # 再チェック
                    system_memory = psutil.virtual_memory()
                    available_bytes = system_memory.available
                    available_mb = available_bytes / (1024 * 1024)
                    
                    # それでも不足している場合
                    if available_mb < (required_mb + 100):
                        raise MemoryLimitError(
                            used_bytes=used_bytes,
                            limit_bytes=total_bytes
                        )
                else:
                    raise MemoryLimitError(
                        used_bytes=used_bytes,
                        limit_bytes=total_bytes
                    )
            
            # 警告を表示
            if usage_percent >= self.MEMORY_CRITICAL_THRESHOLD_PERCENT:
                warn_msg = i18n.translate(
                    "warn.memory_critical",
                    usage_percent=usage_percent,
                    used_mb=used_mb,
                    available_mb=available_mb
                )
                logger.critical(warn_msg)
                print(f"⚠️ {warn_msg}")
            elif usage_percent >= self.MEMORY_WARNING_THRESHOLD_PERCENT:
                warn_msg = i18n.translate(
                    "warn.memory_warning",
                    usage_percent=usage_percent,
                    used_mb=used_mb,
                    available_mb=available_mb
                )
                logger.warning(warn_msg)
                print(f"⚠️ {warn_msg}")
            
            return {
                "total_mb": total_mb,
                "used_mb": used_mb,
                "available_mb": available_mb,
                "usage_percent": usage_percent,
            }
        except Exception as e:
            logger.warning(f"Failed to check memory usage: {e}")
            # psutilが利用できない場合は警告のみ
            return {
                "total_mb": None,
                "used_mb": None,
                "available_mb": None,
                "usage_percent": None,
                "error": str(e),
            }
    
    def cleanup_old_files(self, checkpoints_days: Optional[int] = None, commits_days: Optional[int] = None) -> float:
        """
        古いファイルをクリーンアップ
        
        Args:
            checkpoints_days: チェックポイントの保持期間（日数、Noneの場合はデフォルト値を使用）
            commits_days: コミットの保持期間（日数、Noneの場合はデフォルト値を使用）
            
        Returns:
            float: 解放された容量（MB）
        """
        freed_bytes = 0
        
        # チェックポイントのクリーンアップ
        checkpoints_dir = self.ssm_path / "checkpoints"
        if checkpoints_dir.exists():
            days = checkpoints_days or self.CLEANUP_OLD_CHECKPOINTS_DAYS
            cutoff_time = datetime.now() - timedelta(days=days)
            
            for checkpoint_file in checkpoints_dir.glob("*.pkl*"):
                try:
                    mtime = datetime.fromtimestamp(checkpoint_file.stat().st_mtime)
                    if mtime < cutoff_time:
                        size = checkpoint_file.stat().st_size
                        checkpoint_file.unlink()
                        freed_bytes += size
                        logger.info(f"Cleaned up old checkpoint: {checkpoint_file.name}")
                except OSError as e:
                    logger.warning(f"Failed to delete checkpoint {checkpoint_file}: {e}")
        
        # コミットのクリーンアップ（オプション、デフォルトでは無効）
        if commits_days is not None:
            commits_dir = self.ssm_path / "commits"
            if commits_dir.exists():
                cutoff_time = datetime.now() - timedelta(days=commits_days)
                
                for commit_file in commits_dir.glob("*.json"):
                    try:
                        # コミットファイルからタイムスタンプを読み取る
                        import json
                        with open(commit_file, 'r') as f:
                            commit_data = json.load(f)
                            timestamp_str = commit_data.get("timestamp")
                            if timestamp_str:
                                commit_time = datetime.fromisoformat(timestamp_str)
                                if commit_time < cutoff_time:
                                    size = commit_file.stat().st_size
                                    commit_file.unlink()
                                    freed_bytes += size
                                    logger.info(f"Cleaned up old commit: {commit_file.name}")
                    except (OSError, json.JSONDecodeError, KeyError, ValueError) as e:
                        logger.warning(f"Failed to delete commit {commit_file}: {e}")
        
        freed_mb = freed_bytes / (1024 * 1024)
        if freed_mb > 0:
            info_msg = i18n.translate("info.cleanup_completed", freed_mb=freed_mb)
            logger.info(info_msg)
            print(f"✓ {info_msg}")
        
        return freed_mb
    
    def get_resource_summary(self) -> Dict[str, Any]:
        """
        リソース使用状況のサマリーを取得
        
        Returns:
            dict: リソース使用状況
        """
        disk_info = self.check_disk_space(auto_cleanup=False)
        memory_info = self.check_memory_usage(auto_gc=False)
        
        return {
            "disk": disk_info,
            "memory": memory_info,
            "timestamp": datetime.now().isoformat(),
        }

