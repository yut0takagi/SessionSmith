# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0] - 2025-12-24

### 🎉 メジャーバージョンアップ

このバージョンでは、0.1.4以降の大幅な機能追加と改善が含まれています。

### Added

#### 高度なバージョン管理機能
- **ブランチ機能**
  - `ssm.branch()` - ブランチの作成・一覧表示
  - `ssm.checkout_branch()` - ブランチに切り替え
  - `ssm.get_current_branch()` - 現在のブランチを取得
- **マージ機能**
  - `ssm.merge()` - ブランチをマージ
  - 共通祖先の検出
  - マージコミットの作成（2つの親を持つ）
- **タグ機能**
  - `ssm.tag()` - コミットにタグを付ける
  - `ssm.list_tags()` - タグ一覧表示
  - `ssm.checkout_tag()` - タグからチェックアウト
- **リモートリポジトリとの同期**
  - `ssm.remote_add()` - リモートを追加
  - `ssm.remote_list()` - リモート一覧表示
  - `ssm.push()` - リモートにプッシュ
  - `ssm.pull()` - リモートからプル

#### チェックポイント機能（長時間実行対応）
- `ssm.checkpoint()` - コンテキストマネージャーで自動チェックポイント
- 定期的な自動保存（バックグラウンドスレッド）
- `cp.step()` - 手動チェックポイント + メトリクス記録
- シグナルハンドラー（SIGINT/SIGTERM）で中断時自動保存
- 例外発生時の緊急チェックポイント
- `ssm.restore_checkpoint()` - チェックポイントから復元
- `ssm.list_checkpoints()` - チェックポイント一覧
- `ssm.clean_checkpoints()` - 古いチェックポイントの削除
- メトリクス追跡（loss, accuracy など）

#### 国際化（i18n）
- 日本語・英語の翻訳辞書
- `set_language()` / `get_language()` - 言語設定
- 環境変数 `SESSIONSMITH_LANG` での設定
- システムロケールからの自動検出
- SSM設定ファイルへの自動保存
- すべての例外クラスの多言語対応
- 情報メッセージの多言語対応

#### 堅牢なエラーハンドリング
- `@retry` デコレータ - リトライ機能
- `error_context` コンテキストマネージャー - エラーコンテキスト管理
- `safe_execute()` - 安全な実行
- `ErrorHandler` クラス - エラーハンドリング設定
- 詳細なエラー情報の提供

#### リソース管理
- ディスク容量監視
- メモリ使用量監視
- 自動クリーンアップ機能
- リソース制限例外（`MemoryLimitError`, `StorageLimitError`）

#### ファイル操作の堅牢性
- ファイルロック機能
- アトミック書き込み
- ファイル破損検出・復旧機能
- バックアップ・リストア機能

#### 形式互換性機能
- `ssm.export()` - 従来形式（.pkl/.json）へエクスポート
- `ssm.import_session()` - 従来形式からインポート
- `ssm.convert()` - ファイル形式変換
- CLI: `ssm export-session`, `ssm import-session`, `ssm convert` コマンド

#### 複数ファイル使用時の対応
- コミット元ファイル情報の記録
- 変数名衝突の自動検出と警告
- コミット履歴にファイル情報を表示

#### CLI機能
- `ssm` コマンドラインツール
- `ssm init`, `ssm commit`, `ssm log`, `ssm checkout` など
- `ssm watch` - 監視モード
- `ssm stats` - 統計分析
- `ssm dashboard` - Webダッシュボード
- バージョン管理コマンド（`ssm branch`, `ssm merge`, `ssm tag` など）

#### Homebrew対応
- Homebrew Formula の追加
- GitHub Actions による自動更新

### Changed

#### 破壊的変更
- **`save_session()` / `load_session()` の動作変更**
  - デフォルトでSSMに統合（`use_ssm=True`）
  - `.ssm/` ディレクトリに保存されるようになりました
  - 従来の動作は `use_ssm=False` で利用可能

- **`ssm.set_language()` / `ssm.get_language()` の非推奨化**
  - トップレベルの `set_language()` / `get_language()` を使用してください

#### 改善
- 例外クラスに `to_dict()` メソッド追加（JSON出力対応）
- `_get_saveable_vars()` にサイズチェック機能追加
- 大規模データ対応（変数サイズチェック、警告、制限）
- スレッドセーフティの向上（RLockによる並行アクセス保護）
- ドキュメントの大幅な整理と改善

### Removed

- `SessionSmith/version_control.py` を削除（`ssm` モジュールに統合）

### Security

- セキュリティ警告の追加（pickle使用に関する注意喚起）
- セッションファイルの検証機能の強化

### Documentation

- ドキュメントの大幅な整理
- 各機能の詳細なガイドを追加
- 実践的な使用例を追加
- Homebrewインストール方法を追加

### Example Usage

```python
# 基本的な使い方
from SessionSmith import ssm

ssm.init()
ssm.commit("Initial state")
ssm.log()
ssm.checkout("abc123")

# バージョン管理
ssm.branch('feature', create=True)
ssm.checkout_branch('feature')
ssm.merge('feature')
ssm.tag('v1.0.0')

# チェックポイント（長時間学習）
with ssm.checkpoint(interval=300) as cp:
    for epoch in range(1000):
        loss = train()
        cp.step(loss=loss, epoch=epoch)

# 国際化
from SessionSmith import set_language
set_language('ja')  # 日本語に設定
```

---

## [0.1.4] - 2024-XX-XX

### Added
- 基本的なセッション保存・復元機能
- SSM（Git風セッション管理）の基本機能
- アルゴリズムトレーサー
- 可視化機能
