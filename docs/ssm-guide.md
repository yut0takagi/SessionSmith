# SSM - Git風セッション管理

SessionSmith Manager (SSM) は、Git と同様のディレクトリベースでセッションを管理する機能です。

## 概要

`.ssm/` ディレクトリを使用して、変数の状態をコミット履歴として管理します。

## クイックスタート

```python
from SessionSmith import ssm

ssm.init()
ssm.commit("Initial state")
ssm.log()
ssm.checkout("abc123")
```

## 基本コマンド

### 初期化

```python
ssm.init()
```

`.ssm/` ディレクトリが作成されます。

### コミット

```python
ssm.commit("Add training data")
ssm.commit("Fix bug", author="Alice")
```

### 履歴表示

```python
ssm.log()              # 詳細表示
ssm.log(oneline=True)  # 1行形式
ssm.log(limit=5)       # 最新5件
```

### 復元

```python
ssm.checkout("abc123")  # 特定のコミット
ssm.checkout()          # 最新（HEAD）
```

### 状態確認

```python
ssm.status()  # 現在の状態
ssm.diff()    # 差分表示
```

## 常時記録（Continuous Mode）

Jupyter Notebookのクラッシュ対策として、セル実行ごとに自動保存します。

```python
# 有効化
ssm.continuous()

# 無効化
ssm.continuous(enable=False)

# クラッシュ後の復元
ssm.recover()
```

## 設定

### 除外リスト

```python
ssm.exclude("large_data", "temp_var")
```

### 設定の確認・変更

```python
ssm.config()              # 全設定を表示
ssm.config("exclude")      # 特定の設定を取得
ssm.config("exclude", []) # 設定を変更
```

## チェックポイント（長時間学習対応）

機械学習の学習ループなど、長時間実行されるタスク向けの機能です。

```python
# 5分ごとに自動チェックポイント
with ssm.checkpoint(interval=300) as cp:
    for epoch in range(1000):
        loss = train()
        cp.step(loss=loss, epoch=epoch)

# 復元
ssm.restore_checkpoint()
```

詳細は [チェックポイントガイド](checkpoint-guide.md) を参照してください。

## 形式変換

### エクスポート

```python
ssm.export("backup.pkl")                    # HEADをエクスポート
ssm.export("data.json", commit_hash="abc") # 特定のコミット
ssm.export("backup.pkl", compress=True)     # 圧縮
```

### インポート

```python
ssm.import_session("old_session.pkl")
ssm.import_session("data.json", message="Import from backup")
```

### 変換

```python
ssm.convert("data.pkl", "data.json")
ssm.convert("data.json", "data.pkl", compress=True)
```

## ディレクトリ構造

```
.ssm/
├── config              # 設定ファイル
├── HEAD                # 現在のコミット
├── objects/            # オブジェクトストレージ（SHA-256ハッシュ）
├── commits/            # コミット情報
├── snapshots/          # スナップショット
├── continuous/         # 常時記録用
├── checkpoints/        # チェックポイント
├── branches/           # ブランチ管理
├── tags/               # タグ管理
└── remotes/            # リモート設定
```

## ベストプラクティス

1. **作業開始時に初期化**
   ```python
   ssm.init()
   ssm.continuous()  # クラッシュ対策
   ```

2. **重要なポイントでコミット**
   ```python
   data = load_data()
   ssm.commit("Load data")
   
   model = train(data)
   ssm.commit("Train model")
   ```

3. **大きな変数は除外**
   ```python
   ssm.exclude("raw_data", "cache")
   ```

## 関連ドキュメント

- [基本的な使い方](getting-started.md) - クイックスタート
- [バージョン管理機能](version-control.md) - ブランチ・マージ・タグ
- [チェックポイント](checkpoint-guide.md) - 長時間学習対応
- [API リファレンス](api-reference.md) - 詳細なAPI
