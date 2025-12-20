# バージョン管理機能

SessionSmithのバージョン管理機能は、Git風の操作でセッションの履歴を管理できます。

## 概要

`SessionManager`にバージョン管理機能が統合されています。通常の保存機能とGit風のバージョン管理を両方使用できます。

## 基本的な使い方

### バージョン管理を有効化

```python
from SessionSmith import SessionManager

# バージョン管理を有効化してマネージャーを作成
manager = SessionManager(enable_version_control=True)

# または後から有効化
manager = SessionManager()
manager.enable_version_control()
```

### 保存とコミット

```python
# 保存時に自動的にコミット（デフォルト）
manager.save("session.pkl", commit_message="Initial state")

# コミットしないで保存（長期中断用）
manager.save("session.pkl", auto_commit=False)

# 明示的にコミット
manager.commit("After training", tags=["ml", "v1"])
```

### コミット履歴の確認

```python
# 全履歴を表示
manager.log()

# 最新10件のみ表示
manager.log(limit=10)

# 1行形式で表示
manager.log(oneline=True)
```

### 以前の状態に戻す

```python
# コミットハッシュで戻す
manager.checkout(commit_hash="abc123def456")

# コミットメッセージで検索して戻す
manager.checkout(message="Initial state")

# 別のファイルに復元
manager.checkout(message="After training", target_file="restored.pkl")
```

### コミット間の差分を確認

```python
# 2つのコミット間の差分
diff = manager.diff(commit1="abc123", commit2="def456", detailed=True)

# HEADと前のコミットの差分
diff = manager.diff(commit1=None, commit2="abc123")
```

### 現在の状態を確認

```python
status = manager.status()
print(status)
# {
#   "version_control": True,
#   "total_commits": 5,
#   "current_commit": "def456",
#   "head": "def456",
#   "latest_commit": {...}
# }
```

### タグの追加

```python
# コミットにタグを追加
manager.tag("production", commit_hash="def456")

# HEADにタグを追加
manager.tag("v1.0")
```

### コミットの詳細情報

```python
# コミットの詳細情報を取得
commit_info = manager.show(commit_hash="abc123")
print(commit_info)
```

## 使用シナリオ

### 実験の管理

```python
manager = SessionManager(enable_version_control=True)

# 実験の各ステップをコミット
manager.save("experiment.pkl", commit_message="Initial data")
manager.save("experiment.pkl", commit_message="After preprocessing")
manager.save("experiment.pkl", commit_message="After training", tags=["ml"])

# 履歴を確認
manager.log()

# 前のステップに戻る
manager.checkout(message="After preprocessing")
```

### 長期中断時の保存

```python
# バージョン管理中でも、通常の保存が可能
manager.save("session.pkl", auto_commit=False)  # コミットしない

# 後でコミット
manager.commit("Before long break", file_path="session.pkl")
```

### バージョン管理なしでの使用

```python
# バージョン管理なしでも通常の保存は可能
manager = SessionManager()  # バージョン管理なし
manager.save("session.pkl")  # 通常の保存のみ

# 後からバージョン管理を有効化
manager.enable_version_control()
manager.save("session.pkl", commit_message="First commit")
```

## バージョン管理の無効化

```python
# バージョン管理を無効化
manager.disable_version_control()

# これ以降は通常の保存のみ
manager.save("session.pkl")  # コミットされない
```

## 内部構造

バージョン管理情報は`.sessionvc/`ディレクトリに保存されます：

```
project/
├── session.pkl
└── .sessionvc/
    ├── metadata.json      # コミット履歴
    └── commits/
        ├── abc123.pkl     # コミット1
        ├── def456.pkl     # コミット2
        └── ...
```

`.sessionvc/`ディレクトリは通常の`.gitignore`に追加することをお勧めします。

