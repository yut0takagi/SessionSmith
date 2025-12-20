# GitHub Actions ワークフロー

## ワークフロー概要

### 1. test.yml
- **トリガー**: `main`または`develop`ブランチへのpush、PR
- **目的**: 複数のPythonバージョンでパッケージのビルドとインポートをテスト
- **Pythonバージョン**: 3.9, 3.10, 3.11, 3.12, 3.13, 3.14

### 2. release.yml
- **トリガー**: `main`ブランチへのpush
- **目的**: 自動リリースとPyPI公開
- **処理内容**:
  1. バージョンを`SessionSmith/__init__.py`から取得
  2. タグが存在しない場合のみ処理を続行
  3. リリースブランチ（`release/v{version}`）を作成
  4. Gitタグ（`v{version}`）を作成してプッシュ
  5. パッケージをビルド
  6. PyPIに公開
  7. GitHub Releaseを作成

## セットアップ手順

### 1. PyPI API Tokenの取得

1. [PyPI](https://pypi.org)にログイン
2. Account settings → API tokens に移動
3. "Add API token"をクリック
4. Token名を入力（例: `SessionSmith-release`）
5. Scopeを"Entire account"に設定
6. Tokenをコピー（一度しか表示されません）

### 2. GitHub Secretsの設定

1. GitHubリポジトリの Settings → Secrets and variables → Actions に移動
2. "New repository secret"をクリック
3. 以下のシークレットを追加:
   - **Name**: `PYPI_API_TOKEN`
   - **Value**: 上記で取得したPyPI API Token

### 3. リリース手順

1. `develop`ブランチで作業
2. `SessionSmith/__init__.py`の`__version__`を更新
3. `CHANGELOG.md`を更新
4. `develop`から`main`にマージ（または`main`に直接push）
5. GitHub Actionsが自動的に以下を実行:
   - リリースブランチの作成
   - タグの作成
   - PyPIへの公開
   - GitHub Releaseの作成

## 注意事項

- 同じバージョンで複数回リリースしようとすると、タグが既に存在するためスキップされます
- `main`ブランチへのpushのみがリリースをトリガーします
- PyPI API Tokenは必ずGitHub Secretsに保存してください（コードに直接書かないでください）

