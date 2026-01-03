# SSM CLI リファレンス

SessionSmith のコマンドラインインターフェース (CLI) です。

## インストール

### pip でインストール（推奨）

```bash
pip install SessionSmith
```

### Homebrew でインストール

```bash
# 現在のリポジトリから直接インストール
brew install yut0takagi/SessionSmith/sessionsmith

# または、ローカルファイルからインストール
brew install --build-from-source ./Formula/sessionsmith.rb
```

インストール後、`ssm` コマンドが利用可能になります。

## 基本コマンド

### `ssm init`

SSM を初期化します。

```bash
ssm init
ssm init --path /other/path
ssm init --force  # 既存の .ssm を上書き
```

### `ssm commit`

現在のスナップショットをコミットします。

```bash
ssm commit -m "Add training data"
ssm commit -m "Fix bug" -a "Alice"
```

**オプション:**
- `--message, -m`: コミットメッセージ
- `--author, -a`: 作成者名

### `ssm log`

コミット履歴を表示します。

```bash
ssm log
ssm log --oneline
ssm log -n 5  # 最新5件のみ
```

**オプション:**
- `--limit, -n`: 表示するコミット数
- `--oneline`: 1行形式で表示

### `ssm status`

現在の状態を表示します。

```bash
ssm status
ssm status -v  # 詳細表示
```

### `ssm checkout`

以前のコミットに復元します。

```bash
ssm checkout abc1234
ssm checkout abc  # 短縮ハッシュ
ssm checkout     # HEAD に復元
```

### `ssm diff`

スナップショットとコミットの差分を表示します。

```bash
ssm diff
```

## バージョン管理

### `ssm branch`

ブランチの作成・一覧表示。

```bash
ssm branch                    # ブランチ一覧
ssm branch feature -c         # ブランチ作成
```

### `ssm checkout-branch`

ブランチに切り替えます。

```bash
ssm checkout-branch feature
```

### `ssm merge`

ブランチをマージします。

```bash
ssm merge feature
```

### `ssm tag`

タグの作成・一覧表示。

```bash
ssm tag v1.0.0               # タグ作成
ssm tag --list               # タグ一覧
ssm checkout-tag v1.0.0      # タグからチェックアウト
```

### `ssm remote`

リモートリポジトリの管理。

```bash
ssm remote --add origin /path/to/remote  # リモート追加
ssm remote                   # リモート一覧
ssm push origin main         # プッシュ
ssm pull origin main          # プル
```

## 形式変換

### `ssm export-session`

コミットを従来形式でエクスポートします。

```bash
ssm export-session backup.pkl
ssm export-session data.json -c abc1234  # 特定のコミット
ssm export-session backup.pkl -z         # 圧縮
```

**オプション:**
- `--commit, -c`: エクスポートするコミット（デフォルト: HEAD）
- `--compress, -z`: 出力を圧縮

### `ssm import-session`

従来形式からインポートしてコミットを作成します。

```bash
ssm import-session old_session.pkl
ssm import-session data.json -m "Import from backup"
```

**オプション:**
- `--message, -m`: コミットメッセージ

### `ssm convert`

ファイル形式を直接変換します。

```bash
ssm convert data.pkl data.json
ssm convert old.json new.pkl -z  # 圧縮
```

**オプション:**
- `--compress, -z`: 出力を圧縮

## 監視機能

### `ssm watch`

定期的にスナップショットを取得します。

```bash
ssm watch
ssm watch --interval 5  # 5秒ごと
ssm watch -t /path/to/dir  # ターゲットディレクトリ
```

**オプション:**
- `--interval, -i`: スナップショット間隔（秒）
- `--target, -t`: 監視対象ディレクトリ

### `ssm stats`

監視データの統計を表示します。

```bash
ssm stats
ssm stats --graph  # ASCIIグラフを表示
```

### `ssm dashboard`

Web ベースのダッシュボードを起動します。

```bash
ssm dashboard
ssm dashboard --port 3000
```

**オプション:**
- `--port, -p`: ポート番号（デフォルト: 8080）

## 関連ドキュメント

- [基本的な使い方](getting-started.md) - クイックスタート
- [SSM ガイド](ssm-guide.md) - 詳細な機能説明
- [API リファレンス](api-reference.md) - Python API
