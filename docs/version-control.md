# バージョン管理機能

ブランチ、マージ、タグ、リモート機能を使った実践的な使用例です。

## 基本的な使い方

```python
from SessionSmith import ssm

ssm.init()

# ブランチ作成
ssm.branch('feature', create=True)
ssm.checkout_branch('feature')

# マージ
ssm.merge('feature')

# タグ
ssm.tag('v1.0.0')
ssm.checkout_tag('v1.0.0')

# リモート
ssm.remote_add('origin', '/path/to/remote')
ssm.push('origin', 'main')
ssm.pull('origin', 'main')
```

## 実践例: 機械学習実験の管理

### 1. 初期セットアップ

```python
from SessionSmith import ssm

ssm.init()
X, y = load_data()
ssm.commit("Initial data preparation")
```

### 2. ブランチで実験

```python
# 実験用ブランチを作成
ssm.branch('experiment-dropout', create=True)
ssm.checkout_branch('experiment-dropout')

# 実験を実行
model1 = create_model_with_dropout()
history1 = train(model1)
ssm.commit("Experiment: Add dropout layer")

# 別の実験
ssm.checkout_branch('main')
ssm.branch('experiment-batch-norm', create=True)
ssm.checkout_branch('experiment-batch-norm')

model2 = create_model_with_batch_norm()
history2 = train(model2)
ssm.commit("Experiment: Add batch normalization")
```

### 3. マージ

```python
# 最良の実験をマージ
ssm.checkout_branch('main')
ssm.merge('experiment-batch-norm')
```

### 4. タグ付け

```python
# リリース時にタグ
ssm.tag('v1.0.0', message="First release")
ssm.checkout_tag('v1.0.0')  # 後で復元可能
```

### 5. リモート同期

```python
# リモート追加
ssm.remote_add('origin', '/shared/experiments/ml-project')

# プッシュ
ssm.push('origin', 'main')

# 別のマシンでプル
ssm.pull('origin', 'main')
```

## CLI での操作

```bash
# ブランチ
ssm branch                    # 一覧
ssm branch feature -c         # 作成
ssm checkout-branch feature   # 切り替え

# マージ
ssm merge feature

# タグ
ssm tag v1.0.0               # 作成
ssm tag --list               # 一覧
ssm checkout-tag v1.0.0      # チェックアウト

# リモート
ssm remote --add origin /path/to/remote
ssm push origin main
ssm pull origin main
```

## 関連ドキュメント

- [SSM ガイド](ssm-guide.md) - 基本機能
- [API リファレンス](api-reference.md) - 詳細なAPI
