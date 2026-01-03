"""
SessionSmith - Git風セッション管理ライブラリ

.ssm/ ディレクトリベースでセッションを管理します。
Jupyter Notebook環境での使用に最適化されています。

基本的な使い方:
    >>> from SessionSmith import ssm
    >>> ssm.init()                    # 初期化
    >>> ssm.commit("Initial state")   # コミット
    >>> ssm.log()                     # 履歴表示
    >>> ssm.checkout("abc123")        # 復元
    >>> ssm.continuous()              # 常時記録モード

長時間実行（機械学習など）:
    >>> with ssm.checkpoint(interval=300) as cp:  # 5分ごとに自動保存
    ...     for epoch in range(1000):
    ...         loss = train()
    ...         cp.step(loss=loss)    # 手動チェックポイント + メトリクス
    >>> 
    >>> ssm.restore_checkpoint()      # 最新から復元
    >>> ssm.list_checkpoints()        # チェックポイント一覧

形式変換:
    >>> ssm.export("backup.pkl")      # .pkl/.json へエクスポート
    >>> ssm.import_session("old.pkl") # .pkl/.json からインポート
    >>> ssm.convert("a.pkl", "b.json") # 形式変換

Note:
    save_session/load_session および SessionManager は後方互換性のために
    残されていますが、新規開発では ssm モジュールの使用を推奨します。
"""

# 主要API（推奨）
from . import ssm

# ブランチ・マージ・タグ・リモート機能（ssmモジュールから直接インポート）
from .ssm import (
    branch,
    checkout_branch,
    get_current_branch,
    merge,
    tag,
    list_tags,
    checkout_tag,
    remote_add,
    remote_list,
    push,
    pull,
)

# 後方互換性のためのAPI（非推奨）
from .core import save_session, load_session
from .manager import SessionManager

# ユーティリティ
from .info import get_session_info, list_session_variables, print_session_info
from .compare import compare_sessions, print_comparison
from .utils import verify_session
from .serializers import CustomSerializer

# 国際化（i18n）
from . import i18n
from .i18n import set_language, get_language, translate, t, Language

# エラーハンドリング
from .error_handling import (
    retry,
    error_context,
    safe_execute,
    get_error_summary,
    format_error_message,
    ErrorHandler,
    set_default_error_handler,
    get_default_error_handler,
)

# アルゴリズムトレーサー
from .tracer import AlgorithmTracer
from .visualizer import visualize_algorithm_trace, print_trace_summary

# 例外クラス
from .exceptions import (
    SessionSmithError,
    SSMError,
    SSMNotInitializedError,
    SSMCommitNotFoundError,
    SSMNoCommitsError,
    SSMConfigError,
    SSMBranchNotFoundError,
    SSMTagNotFoundError,
    SSMRemoteNotFoundError,
    SSMMergeConflictError,
    SessionError,
    SessionSaveError,
    SessionLoadError,
    SessionCorruptedError,
    CheckpointError,
    CheckpointSaveError,
    CheckpointRestoreError,
    SerializationError,
    VariableSerializationError,
    ValidationError,
    ResourceError,
    MemoryLimitError,
    StorageLimitError,
)

__version__ = "2.0.0"

__all__ = [
    # 主要API（推奨）
    "ssm",
    
    # 後方互換性（非推奨: ssm を使用してください）
    "save_session",     # → ssm.export() または ssm.commit()
    "load_session",     # → ssm.checkout() または ssm.import_session()
    "SessionManager",   # → ssm モジュール
    
    # ユーティリティ
    "get_session_info",
    "list_session_variables",
    "print_session_info",
    "compare_sessions",
    "print_comparison",
    "verify_session",
    "CustomSerializer",
    
    # アルゴリズムトレーサー
    "AlgorithmTracer",
    "visualize_algorithm_trace",
    "print_trace_summary",
    
    # 国際化（i18n）
    "i18n",
    "set_language",
    "get_language",
    "translate",
    "t",
    "Language",
    
    # エラーハンドリング
    "retry",
    "error_context",
    "safe_execute",
    "get_error_summary",
    "format_error_message",
    "ErrorHandler",
    "set_default_error_handler",
    "get_default_error_handler",
    
    # ブランチ・マージ・タグ・リモート機能
    "branch",
    "checkout_branch",
    "get_current_branch",
    "merge",
    "tag",
    "list_tags",
    "checkout_tag",
    "remote_add",
    "remote_list",
    "push",
    "pull",
    
    # 例外クラス
    "SessionSmithError",
    "SSMError",
    "SSMNotInitializedError",
    "SSMCommitNotFoundError",
    "SSMNoCommitsError",
    "SSMConfigError",
    "SSMBranchNotFoundError",
    "SSMTagNotFoundError",
    "SSMRemoteNotFoundError",
    "SSMMergeConflictError",
    "SessionError",
    "SessionSaveError",
    "SessionLoadError",
    "SessionCorruptedError",
    "CheckpointError",
    "CheckpointSaveError",
    "CheckpointRestoreError",
    "SerializationError",
    "VariableSerializationError",
    "ValidationError",
    "ResourceError",
    "MemoryLimitError",
    "StorageLimitError",
]
