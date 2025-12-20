# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

