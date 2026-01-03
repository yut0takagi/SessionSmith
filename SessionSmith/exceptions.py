"""
SessionSmith カスタム例外クラス

堅牢なエラーハンドリングのための例外階層を定義します。

例外階層:
    SessionSmithError (基底)
    ├── SSMError (SSM操作関連)
    │   ├── SSMNotInitializedError
    │   ├── SSMCommitNotFoundError
    │   ├── SSMNoCommitsError
    │   └── SSMConfigError
    ├── SessionError (セッション操作関連)
    │   ├── SessionSaveError
    │   ├── SessionLoadError
    │   └── SessionCorruptedError
    ├── CheckpointError (チェックポイント関連)
    │   ├── CheckpointSaveError
    │   └── CheckpointRestoreError
    ├── SerializationError
    │   └── VariableSerializationError
    ├── ValidationError
    └── ResourceError
        ├── MemoryLimitError
        └── StorageLimitError
"""

from typing import Any, Optional

# i18nモジュールを遅延インポート（循環参照を避けるため）
_i18n_module = None


def _get_i18n():
    """i18nモジュールを遅延インポート"""
    global _i18n_module
    if _i18n_module is None:
        from . import i18n
        _i18n_module = i18n
    return _i18n_module


class SessionSmithError(Exception):
    """
    SessionSmith の基底例外クラス

    すべてのSessionSmith固有の例外はこのクラスを継承します。
    """

    def __init__(self, message: str = "", details: Optional[dict[str, Any]] = None):
        super().__init__(message)
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        """例外情報を辞書形式で返す"""
        return {
            "error_type": self.__class__.__name__,
            "message": str(self),
            "details": self.details,
        }


class SSMError(SessionSmithError):
    """SSM 関連の基底例外クラス"""
    pass


class SSMNotInitializedError(SSMError):
    """SSM が初期化されていない場合の例外"""

    def __init__(self, path: str = "."):
        self.path = path
        i18n = _get_i18n()
        message = i18n.translate("error.ssm_not_initialized", path=path)
        super().__init__(message, details={"path": path})


class SSMCommitNotFoundError(SSMError):
    """指定されたコミットが見つからない場合の例外"""

    def __init__(self, commit_hash: str):
        self.commit_hash = commit_hash
        i18n = _get_i18n()
        message = i18n.translate("error.ssm_commit_not_found", commit_hash=commit_hash)
        super().__init__(message, details={"commit_hash": commit_hash})


class SSMNoCommitsError(SSMError):
    """コミットが存在しない場合の例外"""

    def __init__(self):
        i18n = _get_i18n()
        message = i18n.translate("error.ssm_no_commits")
        super().__init__(message)


class SSMConfigError(SSMError):
    """設定エラーの例外"""

    def __init__(self, message: str, key: Optional[str] = None):
        self.key = key
        i18n = _get_i18n()
        error_message = i18n.translate("error.ssm_config", message=message)
        super().__init__(error_message, details={"key": key} if key else {})


class SSMBranchNotFoundError(SSMError):
    """ブランチが見つからない場合の例外"""

    def __init__(self, branch_name: str):
        self.branch_name = branch_name
        i18n = _get_i18n()
        message = i18n.translate("error.branch_not_found", branch_name=branch_name)
        super().__init__(message, details={"branch_name": branch_name})


class SSMTagNotFoundError(SSMError):
    """タグが見つからない場合の例外"""

    def __init__(self, tag_name: str):
        self.tag_name = tag_name
        i18n = _get_i18n()
        message = i18n.translate("error.tag_not_found", tag_name=tag_name)
        super().__init__(message, details={"tag_name": tag_name})


class SSMRemoteNotFoundError(SSMError):
    """リモートが見つからない場合の例外"""

    def __init__(self, remote_name: str):
        self.remote_name = remote_name
        i18n = _get_i18n()
        message = i18n.translate("error.remote_not_found", remote_name=remote_name)
        super().__init__(message, details={"remote_name": remote_name})


class SSMMergeConflictError(SSMError):
    """マージコンフリクトが発生した場合の例外"""

    def __init__(self, branch_name: str, conflicts: list[str]):
        self.branch_name = branch_name
        self.conflicts = conflicts
        i18n = _get_i18n()
        message = i18n.translate("error.merge_conflict", branch_name=branch_name, count=len(conflicts))
        super().__init__(message, details={"branch_name": branch_name, "conflicts": conflicts})


class SessionError(SessionSmithError):
    """セッション保存・読み込み関連の例外"""
    pass


class SessionSaveError(SessionError):
    """セッション保存時のエラー"""

    def __init__(self, file_path: str, reason: str, recoverable: bool = False):
        self.file_path = file_path
        self.reason = reason
        self.recoverable = recoverable
        i18n = _get_i18n()
        message = i18n.translate("error.session_save", file_path=file_path, reason=reason)
        super().__init__(
            message,
            details={"file_path": file_path, "reason": reason, "recoverable": recoverable}
        )


class SessionLoadError(SessionError):
    """セッション読み込み時のエラー"""

    def __init__(self, file_path: str, reason: str, partial_data: Optional[dict] = None):
        self.file_path = file_path
        self.reason = reason
        self.partial_data = partial_data  # 部分的に読み込めたデータ
        i18n = _get_i18n()
        message = i18n.translate("error.session_load", file_path=file_path, reason=reason)
        super().__init__(
            message,
            details={"file_path": file_path, "reason": reason}
        )


class SessionCorruptedError(SessionError):
    """セッションファイルが破損している場合の例外"""

    def __init__(self, file_path: str, backup_path: Optional[str] = None):
        self.file_path = file_path
        self.backup_path = backup_path
        i18n = _get_i18n()
        if backup_path:
            message = i18n.translate(
                "error.session_corrupted_with_backup",
                file_path=file_path,
                backup_path=backup_path
            )
        else:
            message = i18n.translate("error.session_corrupted", file_path=file_path)
        super().__init__(message, details={"file_path": file_path, "backup_path": backup_path})


class CheckpointError(SessionSmithError):
    """チェックポイント関連の例外"""
    pass


class CheckpointSaveError(CheckpointError):
    """チェックポイント保存時のエラー"""

    def __init__(self, reason: str, step: Optional[int] = None, retry_count: int = 0):
        self.reason = reason
        self.step = step
        self.retry_count = retry_count
        i18n = _get_i18n()
        message = i18n.translate("error.checkpoint_save", reason=reason)
        super().__init__(
            message,
            details={"reason": reason, "step": step, "retry_count": retry_count}
        )


class CheckpointRestoreError(CheckpointError):
    """チェックポイント復元時のエラー"""

    def __init__(self, checkpoint_path: str, reason: str, available_checkpoints: Optional[list] = None):
        self.checkpoint_path = checkpoint_path
        self.reason = reason
        self.available_checkpoints = available_checkpoints
        i18n = _get_i18n()
        message = i18n.translate(
            "error.checkpoint_restore",
            checkpoint_path=checkpoint_path,
            reason=reason
        )
        super().__init__(
            message,
            details={
                "checkpoint_path": checkpoint_path,
                "reason": reason,
                "available_checkpoints": available_checkpoints
            }
        )


class SerializationError(SessionSmithError):
    """シリアライズ関連のエラー"""
    pass


class VariableSerializationError(SerializationError):
    """変数のシリアライズに失敗した場合の例外"""

    def __init__(self, variable_name: str, variable_type: str, reason: str, size_bytes: Optional[int] = None):
        self.variable_name = variable_name
        self.variable_type = variable_type
        self.reason = reason
        self.size_bytes = size_bytes
        i18n = _get_i18n()
        message = i18n.translate(
            "error.serialization",
            variable_name=variable_name,
            variable_type=variable_type,
            reason=reason
        )
        super().__init__(
            message,
            details={
                "variable_name": variable_name,
                "variable_type": variable_type,
                "reason": reason,
                "size_bytes": size_bytes
            }
        )


class ValidationError(SessionSmithError):
    """入力バリデーションエラー"""

    def __init__(self, field: str, message: str, value: Any = None):
        self.field = field
        self.message = message
        self.value = value
        i18n = _get_i18n()
        error_message = i18n.translate("error.validation", field=field, message=message)
        super().__init__(
            error_message,
            details={"field": field, "message": message, "value": repr(value) if value else None}
        )


class ResourceError(SessionSmithError):
    """リソース制限に関するエラー"""
    pass


class MemoryLimitError(ResourceError):
    """メモリ制限超過のエラー"""

    def __init__(self, used_bytes: int, limit_bytes: int, variable_name: Optional[str] = None):
        self.used_bytes = used_bytes
        self.limit_bytes = limit_bytes
        self.variable_name = variable_name

        used_mb = used_bytes / (1024 * 1024)
        limit_mb = limit_bytes / (1024 * 1024)

        i18n = _get_i18n()
        if variable_name:
            message = i18n.translate(
                "error.memory_limit_variable",
                variable_name=variable_name,
                used_mb=used_mb,
                limit_mb=limit_mb
            )
        else:
            message = i18n.translate(
                "error.memory_limit",
                used_mb=used_mb,
                limit_mb=limit_mb
            )

        super().__init__(
            message,
            details={
                "used_bytes": used_bytes,
                "limit_bytes": limit_bytes,
                "variable_name": variable_name
            }
        )


class StorageLimitError(ResourceError):
    """ストレージ制限超過のエラー"""

    def __init__(self, used_bytes: int, limit_bytes: int, path: Optional[str] = None):
        self.used_bytes = used_bytes
        self.limit_bytes = limit_bytes
        self.path = path

        used_mb = used_bytes / (1024 * 1024)
        limit_mb = limit_bytes / (1024 * 1024)

        i18n = _get_i18n()
        if path:
            message = i18n.translate(
                "error.storage_limit_path",
                used_mb=used_mb,
                limit_mb=limit_mb,
                path=path
            )
        else:
            message = i18n.translate(
                "error.storage_limit",
                used_mb=used_mb,
                limit_mb=limit_mb
            )

        super().__init__(
            message,
            details={"used_bytes": used_bytes, "limit_bytes": limit_bytes, "path": path}
        )


# 便利なエラーチェック関数

def raise_if_not_initialized(is_initialized: bool, path: str = ".") -> None:
    """初期化されていなければ例外を投げる"""
    if not is_initialized:
        raise SSMNotInitializedError(path)


def raise_validation_error(field: str, message: str, value: Any = None) -> None:
    """バリデーションエラーを投げる"""
    raise ValidationError(field, message, value)

