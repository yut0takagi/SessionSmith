# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.3] - 2025-12-21

### Fixed
- **`save_session`/`load_session` が変数を正しく保存・復元しない問題を修正**
  - `_get_globals_dict` 関数がユーザーのグローバル変数ではなく、`core.py` の内部変数（`typing` モジュールのインポートなど）を取得していた問題を修正
  - フレームスタックを正しく2階層遡るように修正（`_get_globals_dict` → `save/load_session` → ユーザーコード）
  - `SessionManager` クラスの `_get_globals_dict` メソッドも同様に修正

## [0.1.2] - 2025-12-20

### Added
- **バージョン管理機能（Git風）**: `SessionManager`に統合されたバージョン管理機能
  - `commit()`: セッションをコミット
  - `log()`: コミット履歴を表示
  - `checkout()`: 以前の状態に戻す
  - `diff()`: コミット間の差分を表示
  - `status()`: 現在の状態を確認
  - `tag()`: コミットにタグを追加
  - `show()`: コミットの詳細情報を表示
- `save()`メソッドに`auto_commit`と`commit_message`パラメータを追加
- 詳細なドキュメント（`docs/`ディレクトリ）
  - `docs/getting-started.md`: 基本的な使い方
  - `docs/version-control.md`: バージョン管理機能の詳細
  - `docs/algorithm-tracer.md`: アルゴリズムトレーサーの詳細
  - `docs/api-reference.md`: 全APIのリファレンス

### Changed
- **コードの細分化**: 大きなファイルを適切に分割
  - `manager.py`: 768行 → 533行（バージョン管理機能を`version_control.py`に分離）
  - `visualizer.py`: 489行 → 229行（配列可視化と一般可視化を分離）
  - `core.py`: 421行 → 369行（Jupyter関連ユーティリティを`jupyter_utils.py`に分離）
- エラーハンドリングの強化（より詳細なエラーメッセージ、例外チェーン）
- 型ヒントの改善（`Union[str, Path]`対応など）
- バリデーション関数の追加（入力値の検証を強化）

### Fixed
- 可視化機能の「No data」問題を修正
- ファイルパスの検証を改善
- スレッド安全性の改善（`SessionManager`の自動バックアップ）

## [0.1.1] - 2025-12-20

### Added
- 圧縮サポート（gzip/bz2）
- セッション情報表示機能（`get_session_info`, `print_session_info`, `list_session_variables`）
- セッション比較機能（`compare_sessions`, `print_comparison`）
- セッション検証機能（`verify_session`）
- メタデータ保存機能
- カスタムシリアライザー機能（`CustomSerializer`）
- 自動バックアップ機能（`SessionManager.auto_save`）
- Jupyter Notebook内部変数の自動除外機能
- `SessionManager.list_variables()` と `get_variable_info()` メソッド
- セレクティブロード機能（`include`/`exclude`パラメータ）
- 詳細ログ機能（`verbose`パラメータ）
- エラーハンドリングの改善（`on_error`パラメータ）
- pickleプロトコルバージョン指定機能

### Changed
- パッケージ構造を大規模開発向けにリファクタリング
- `dill`依存から標準ライブラリの`pickle`に変更
- `SessionManager`クラスの機能拡張

### Fixed
- Python 3.9との互換性問題（`bz2.BadBz2File`の処理）

## [0.1.0] - 2025-12-20

### Added
- 基本的なセッション保存・復元機能
- `dill`を使用した実装

