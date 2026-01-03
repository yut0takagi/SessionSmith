# 基本的な使い方

SessionSmith の基本的な使い方を説明します。

## クイックスタート

```python
from SessionSmith import ssm

# 初期化
ssm.init()

# 変数を作成してコミット
a = 1
b = [1, 2, 3]
ssm.commit("Initial state")

# 履歴表示
ssm.log()

# 復元
ssm.checkout("abc123")
```

## 基本操作

### 初期化

```python
ssm.init()  # カレントディレクトリに .ssm/ を作成
```

### コミット

```python
ssm.commit("Add training data")
ssm.commit("Fix bug", author="Alice")
```

### 履歴表示

```python
ssm.log()           # 詳細表示
ssm.log(oneline=True)  # 1行形式
ssm.log(limit=5)    # 最新5件
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

## 常時記録（クラッシュ対策）

```python
# 有効化（Jupyter環境で推奨）
ssm.continuous()

# クラッシュ後の復元
ssm.recover()
```

## 形式変換

```python
# SSM → 従来形式
ssm.export("backup.pkl")

# 従来形式 → SSM
ssm.import_session("old_session.pkl")

# 形式変換
ssm.convert("data.pkl", "data.json")
```

## ⚠️ 複数ファイル使用時の注意事項

複数のnotebookファイルから同じ`.ssm/`ディレクトリを使用する場合、変数名の衝突に注意してください。

### 推奨される使用方法

1. **ファイルごとに異なる変数名を使用**
   ```python
   # notebook1.ipynb
   raw_data = load_data()
   
   # notebook2.ipynb
   processed_data = process_data()
   ```

2. **ファイル名をプレフィックスとして使用**
   ```python
   # notebook1.ipynb
   notebook1_data = load_data()
   
   # notebook2.ipynb
   notebook2_data = process_data()
   ```

3. **コミットメッセージにファイル名を含める**
   ```python
   ssm.commit("Load data (notebook1.ipynb)")
   ```

### 自動検出機能

SSMは異なるファイルからのコミットを自動的に検出し、変数名の衝突を警告します：

```python
# notebook1.ipynb
ssm.commit("Initial state")

# notebook2.ipynb（同じ変数名を使用）
ssm.commit("Process data")
# ⚠️ 変数名の衝突が検出されました: ファイル 'notebook1.ipynb' と 'notebook2.ipynb' で同じ変数名 (data) が使用されています。
```

## 次のステップ

- [SSM ガイド](ssm-guide.md) - 詳細な機能説明
- [バージョン管理機能](version-control.md) - ブランチ・マージ・タグ
- [チェックポイント](checkpoint-guide.md) - 長時間学習対応
- [CLI リファレンス](cli-reference.md) - コマンドラインツール
