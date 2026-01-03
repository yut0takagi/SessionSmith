"""
SessionSmith 国際化（i18n）モジュール

多言語対応のための翻訳システムを提供します。
現在サポートしている言語: 日本語 (ja), 英語 (en)
"""

import os
import locale
from typing import Dict, Optional, Any, Union
from enum import Enum


class Language(Enum):
    """サポートされている言語"""
    JAPANESE = "ja"
    ENGLISH = "en"
    AUTO = "auto"  # システムのロケールから自動検出


# 翻訳辞書
_TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "ja": {
        # エラーメッセージ
        "error.ssm_not_initialized": "SSMが初期化されていません: '{path}'. 'ssm.init()' または 'ssm init' を先に実行してください。",
        "error.ssm_commit_not_found": "コミットが見つかりません: {commit_hash}",
        "error.ssm_no_commits": "コミットが存在しません。先に 'ssm.commit()' を実行してください。",
        "error.ssm_config": "設定エラー: {message}",
        "error.session_save": "セッションの保存に失敗しました: '{file_path}'. 理由: {reason}",
        "error.session_load": "セッションの読み込みに失敗しました: '{file_path}'. 理由: {reason}",
        "error.session_corrupted": "セッションファイルが破損しています: '{file_path}'",
        "error.session_corrupted_with_backup": "セッションファイルが破損しています: '{file_path}' (バックアップが利用可能: {backup_path})",
        "error.checkpoint_save": "チェックポイントの保存に失敗しました: {reason}",
        "error.checkpoint_restore": "チェックポイントの復元に失敗しました: '{checkpoint_path}'. 理由: {reason}",
        "error.serialization": "シリアライズに失敗しました: 変数 '{variable_name}' (型: {variable_type}). 理由: {reason}",
        "error.validation": "バリデーションエラー '{field}': {message}",
        "error.memory_limit": "メモリ制限を超過しました: {used_mb:.1f}MB > {limit_mb:.1f}MB",
        "error.memory_limit_variable": "変数 '{variable_name}' がメモリ制限を超過しました: {used_mb:.1f}MB > {limit_mb:.1f}MB",
        "error.storage_limit": "ストレージ制限を超過しました: {used_mb:.1f}MB > {limit_mb:.1f}MB",
        "error.storage_limit_path": "ストレージ制限を超過しました: {used_mb:.1f}MB > {limit_mb:.1f}MB (パス: {path})",
        "error.file_not_found": "ファイルが見つかりません: '{file_path}'",
        "error.permission_denied": "アクセス権限がありません: '{file_path}'",
        "error.disk_full": "ディスク容量が不足しています: '{path}'",
        "error.network_error": "ネットワークエラー: {reason}",
        "error.timeout": "タイムアウト: {operation} が {timeout}秒以内に完了しませんでした",
        "error.retry_exceeded": "リトライ回数の上限に達しました: {max_attempts}回試行しましたが失敗しました",
        "error.branch_not_found": "ブランチが見つかりません: '{branch_name}'",
        "error.branch_already_exists": "ブランチ '{branch_name}' は既に存在します",
        "error.tag_not_found": "タグが見つかりません: '{tag_name}'",
        "error.tag_already_exists": "タグ '{tag_name}' は既に存在します",
        "error.remote_not_found": "リモートが見つかりません: '{remote_name}'",
        "error.remote_already_exists": "リモート '{remote_name}' は既に存在します",
        "error.remote_no_url": "リモート '{remote_name}' にURLが設定されていません",
        "error.remote_repository_not_found": "リモートリポジトリが見つかりません: {remote_url}",
        "error.tag_no_commit": "タグ '{tag_name}' にコミットが設定されていません",
        "error.merge_conflict": "マージコンフリクトが発生しました: ブランチ '{branch_name}' で {count} 個のコンフリクト",
        
        # 警告メッセージ
        "warn.large_variable": "大きな変数が検出されました: '{name}' ({size_mb:.1f}MB)",
        "warn.skipped_variable": "変数 '{name}' をスキップしました: {reason}",
        "warn.partial_load": "セッションの一部のみ読み込みました: {loaded}/{total} 変数",
        "warn.checkpoint_failed": "チェックポイントの保存に失敗しました: {reason}",
        "warn.continuous_mode_unavailable": "常時記録モードはJupyter/IPython環境でのみ利用可能です",
        "warn.variable_conflict": "変数名の衝突が検出されました: ファイル '{previous_file}' と '{current_file}' で同じ変数名 ({vars}) が使用されています。複数のファイルから同じ変数名を使用する場合は注意してください。",
        
        # 情報メッセージ
        "info.session_saved": "セッションを保存しました: {file_path} ({size:,} bytes, 形式: {format})",
        "info.session_loaded": "{count} 個の変数を読み込みました",
        "info.commit_created": "[{short_hash}] {message} ({var_count} 変数)",
        "info.checkpoint_saved": "チェックポイントを保存しました: {filepath}",
        "info.checkpoint_restored": "{restored_count} 個の変数をチェックポイントから復元しました",
        "info.variables_restored": "{restored} 個の変数を {short_hash} から復元しました",
        "info.ssm_initialized": "SSMを初期化しました: {base_path}",
        "info.ssm_already_initialized": "SSMは既に初期化されています: {base_path}",
        "info.branch_created": "ブランチ '{branch_name}' を作成しました (コミット: {commit})",
        "info.branch_checked_out": "ブランチ '{branch_name}' に切り替えました",
        "info.merge_completed": "ブランチ '{branch_name}' をマージしました (コミット: {commit})",
        "info.already_merged": "ブランチ '{branch_name}' は既にマージ済みです",
        "info.tag_created": "タグ '{tag_name}' を作成しました (コミット: {commit})",
        "info.tag_checked_out": "タグ '{tag_name}' からチェックアウトしました (コミット: {commit})",
        "info.remote_added": "リモート '{name}' を追加しました: {url}",
        "info.push_completed": "リモート '{remote}' のブランチ '{branch}' にプッシュしました (コミット: {commit})",
        "info.pull_completed": "リモート '{remote}' のブランチ '{branch}' からプルしました (コミット: {commit})",
        
        # 一般的なメッセージ
        "msg.no_variables": "保存する変数がありません",
        "msg.no_changes": "変更がありません",
        "msg.operation_completed": "操作が完了しました",
        "msg.operation_failed": "操作に失敗しました",
        "msg.merge_commit": "マージ: '{branch_name}' を '{current_branch}' にマージ",
    },
    "en": {
        # Error messages
        "error.ssm_not_initialized": "SSM is not initialized in '{path}'. Run 'ssm.init()' or 'ssm init' first.",
        "error.ssm_commit_not_found": "Commit not found: {commit_hash}",
        "error.ssm_no_commits": "No commits yet. Run 'ssm.commit()' first.",
        "error.ssm_config": "Configuration error: {message}",
        "error.session_save": "Failed to save session to '{file_path}': {reason}",
        "error.session_load": "Failed to load session from '{file_path}': {reason}",
        "error.session_corrupted": "Session file is corrupted: '{file_path}'",
        "error.session_corrupted_with_backup": "Session file is corrupted: '{file_path}' (backup available: {backup_path})",
        "error.checkpoint_save": "Failed to save checkpoint: {reason}",
        "error.checkpoint_restore": "Failed to restore checkpoint from '{checkpoint_path}': {reason}",
        "error.serialization": "Failed to serialize variable '{variable_name}' (type: {variable_type}): {reason}",
        "error.validation": "Validation error for '{field}': {message}",
        "error.memory_limit": "Memory limit exceeded: {used_mb:.1f}MB > {limit_mb:.1f}MB",
        "error.memory_limit_variable": "Variable '{variable_name}' exceeds memory limit: {used_mb:.1f}MB > {limit_mb:.1f}MB",
        "error.storage_limit": "Storage limit exceeded: {used_mb:.1f}MB > {limit_mb:.1f}MB",
        "error.storage_limit_path": "Storage limit exceeded: {used_mb:.1f}MB > {limit_mb:.1f}MB (path: {path})",
        "error.file_not_found": "File not found: '{file_path}'",
        "error.permission_denied": "Permission denied: '{file_path}'",
        "error.disk_full": "Disk full: '{path}'",
        "error.network_error": "Network error: {reason}",
        "error.timeout": "Timeout: {operation} did not complete within {timeout} seconds",
        "error.retry_exceeded": "Maximum retry attempts exceeded: failed after {max_attempts} attempts",
        "error.branch_not_found": "Branch not found: '{branch_name}'",
        "error.branch_already_exists": "Branch '{branch_name}' already exists",
        "error.tag_not_found": "Tag not found: '{tag_name}'",
        "error.tag_already_exists": "Tag '{tag_name}' already exists",
        "error.remote_not_found": "Remote not found: '{remote_name}'",
        "error.remote_already_exists": "Remote '{remote_name}' already exists",
        "error.remote_no_url": "Remote '{remote_name}' has no URL",
        "error.remote_repository_not_found": "Remote repository not found: {remote_url}",
        "error.tag_no_commit": "Tag '{tag_name}' has no commit",
        "error.merge_conflict": "Merge conflict: {count} conflicts in branch '{branch_name}'",
        
        # Warning messages
        "warn.large_variable": "Large variable detected: '{name}' ({size_mb:.1f}MB)",
        "warn.skipped_variable": "Skipped variable '{name}': {reason}",
        "warn.partial_load": "Only partially loaded session: {loaded}/{total} variables",
        "warn.checkpoint_failed": "Checkpoint save failed: {reason}",
        "warn.continuous_mode_unavailable": "Continuous mode is only available in Jupyter/IPython environment",
        "warn.variable_conflict": "Variable name conflict detected: same variable names ({vars}) used in '{previous_file}' and '{current_file}'. Be careful when using the same variable names from multiple files.",
        "warn.disk_warning": "Disk space warning: {usage_percent:.1f}% used ({free_mb:.1f}MB free)",
        "warn.disk_critical": "Disk space critical: {usage_percent:.1f}% used ({free_mb:.1f}MB free)",
        "warn.memory_warning": "Memory usage warning: {usage_percent:.1f}% used ({used_mb:.1f}MB used, {available_mb:.1f}MB available)",
        "warn.memory_critical": "Memory usage critical: {usage_percent:.1f}% used ({used_mb:.1f}MB used, {available_mb:.1f}MB available)",
        "info.cleanup_completed": "Cleanup completed: freed {freed_mb:.1f}MB",
        "warn.disk_warning": "Disk space warning: {usage_percent:.1f}% used ({free_mb:.1f}MB free)",
        "warn.disk_critical": "Disk space critical: {usage_percent:.1f}% used ({free_mb:.1f}MB free)",
        "warn.memory_warning": "Memory usage warning: {usage_percent:.1f}% used ({used_mb:.1f}MB used, {available_mb:.1f}MB available)",
        "warn.memory_critical": "Memory usage critical: {usage_percent:.1f}% used ({used_mb:.1f}MB used, {available_mb:.1f}MB available)",
        "info.cleanup_completed": "Cleanup completed: freed {freed_mb:.1f}MB",
        
        # Info messages
        "info.session_saved": "Session saved to {file_path} ({size:,} bytes, format: {format})",
        "info.session_loaded": "Loaded {count} variables",
        "info.commit_created": "[{short_hash}] {message} ({var_count} variables)",
        "info.checkpoint_saved": "Checkpoint saved: {filepath}",
        "info.checkpoint_restored": "Restored {restored_count} variables from checkpoint",
        "info.variables_restored": "Restored {restored} variables from {short_hash}",
        "info.ssm_initialized": "Initialized SSM in {base_path}",
        "info.ssm_already_initialized": "SSM already initialized in {base_path}",
        "info.branch_created": "Created branch '{branch_name}' (commit: {commit})",
        "info.branch_checked_out": "Switched to branch '{branch_name}'",
        "info.merge_completed": "Merged branch '{branch_name}' (commit: {commit})",
        "info.already_merged": "Branch '{branch_name}' is already merged",
        "info.tag_created": "Created tag '{tag_name}' (commit: {commit})",
        "info.tag_checked_out": "Checked out tag '{tag_name}' (commit: {commit})",
        "info.remote_added": "Added remote '{name}': {url}",
        "info.push_completed": "Pushed to remote '{remote}' branch '{branch}' (commit: {commit})",
        "info.pull_completed": "Pulled from remote '{remote}' branch '{branch}' (commit: {commit})",
        
        # General messages
        "msg.no_variables": "No variables to save",
        "msg.no_changes": "No changes",
        "msg.operation_completed": "Operation completed",
        "msg.operation_failed": "Operation failed",
        "msg.merge_commit": "Merge: '{branch_name}' into '{current_branch}'",
    }
}


# グローバル言語設定
_current_language: Language = Language.AUTO


def detect_language() -> str:
    """
    システムのロケールから言語を自動検出
    
    Returns:
        str: 言語コード ('ja' または 'en')
    """
    try:
        # 環境変数をチェック
        lang_env = os.environ.get("SESSIONSMITH_LANG") or os.environ.get("LANG") or os.environ.get("LC_ALL")
        if lang_env:
            if "ja" in lang_env.lower() or "japanese" in lang_env.lower():
                return "ja"
            if "en" in lang_env.lower() or "english" in lang_env.lower():
                return "en"
        
        # システムロケールをチェック
        system_locale = locale.getdefaultlocale()[0]
        if system_locale:
            if "ja" in system_locale.lower():
                return "ja"
        
        # デフォルトは英語
        return "en"
    except Exception:
        return "en"


def get_language() -> str:
    """
    現在の言語設定を取得
    
    Returns:
        str: 現在の言語コード
    """
    global _current_language
    
    if _current_language == Language.AUTO:
        return detect_language()
    else:
        return _current_language.value


def set_language(lang: Union[str, Language], save_to_ssm: bool = True) -> None:
    """
    言語を設定
    
    Args:
        lang: 言語コード ('ja', 'en', 'auto') または Language 列挙型
        save_to_ssm: SSMが初期化されている場合、設定ファイルに保存するか（デフォルト: True）
        
    Example:
        >>> from SessionSmith import set_language
        >>> set_language('ja')  # 日本語に設定
        >>> set_language('en')  # 英語に設定
        >>> set_language('auto')  # 自動検出
    """
    global _current_language
    
    if isinstance(lang, str):
        if lang.lower() == "auto":
            _current_language = Language.AUTO
        elif lang.lower() in ("ja", "japanese"):
            _current_language = Language.JAPANESE
        elif lang.lower() in ("en", "english"):
            _current_language = Language.ENGLISH
        else:
            raise ValueError(f"Unsupported language: {lang}. Supported: 'ja', 'en', 'auto'")
    elif isinstance(lang, Language):
        _current_language = lang
    else:
        raise TypeError(f"lang must be str or Language, got {type(lang).__name__}")
    
    # SSMが初期化されている場合は設定ファイルにも保存
    if save_to_ssm:
        try:
            # 循環参照を避けるため、遅延インポート
            from . import ssm
            ssm_instance = ssm._get_ssm()
            if ssm_instance.is_initialized:
                lang_value = lang if isinstance(lang, str) else lang.value
                ssm_instance.config("language", lang_value)
        except Exception:
            pass  # SSMが初期化されていない、またはエラーが発生した場合は無視


def translate(key: str, **kwargs: Any) -> str:
    """
    翻訳キーからメッセージを取得し、パラメータを置換
    
    Args:
        key: 翻訳キー（例: "error.ssm_not_initialized"）
        **kwargs: メッセージ内のプレースホルダーを置換するパラメータ
        
    Returns:
        str: 翻訳されたメッセージ
        
    Raises:
        KeyError: 翻訳キーが見つからない場合
    """
    lang = get_language()
    translations = _TRANSLATIONS.get(lang, _TRANSLATIONS["en"])
    
    if key not in translations:
        # フォールバック: 英語版を試す
        if lang != "en" and key in _TRANSLATIONS["en"]:
            template = _TRANSLATIONS["en"][key]
        else:
            # キーが見つからない場合はキーをそのまま返す
            return key
    
    template = translations.get(key, _TRANSLATIONS["en"].get(key, key))
    
    try:
        return template.format(**kwargs)
    except KeyError as e:
        # パラメータが不足している場合は警告を出してテンプレートを返す
        import warnings
        warnings.warn(f"Missing parameter for translation key '{key}': {e}")
        return template


def t(key: str, **kwargs: Any) -> str:
    """
    translate() の短縮形
    
    Args:
        key: 翻訳キー
        **kwargs: パラメータ
        
    Returns:
        str: 翻訳されたメッセージ
    """
    return translate(key, **kwargs)


# 環境変数から初期言語を設定
if "SESSIONSMITH_LANG" in os.environ:
    try:
        set_language(os.environ["SESSIONSMITH_LANG"])
    except ValueError:
        pass  # 無効な値の場合はデフォルトを使用

