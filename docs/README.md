# SessionSmith ドキュメント

SessionSmithの詳細なドキュメントです。

## ドキュメント一覧

### 📖 [基本的な使い方](getting-started.md)
クイックスタートと基本操作。複数ファイル使用時の注意事項。

### 🚀 [SSM - Git風セッション管理](ssm-guide.md)
`.ssm/` ディレクトリベースのセッション管理。基本コマンド、設定、チェックポイント。

### 🌿 [バージョン管理機能](version-control.md)
ブランチ、マージ、タグ、リモート機能の実践的な使用例。

### ⏱️ [チェックポイント - 長時間学習対応](checkpoint-guide.md)
機械学習の長時間学習に対応したチェックポイント機能。

### 💻 [CLI リファレンス](cli-reference.md)
コマンドラインツール `ssm` の使い方。

### 📚 [APIリファレンス](api-reference.md)
主要APIの詳細なリファレンス。

### 📈 [アルゴリズム実行トレーサー](algorithm-tracer.md)
アルゴリズムの実行を1行ごとにトレースし、可視化する機能。

### 🌐 [国際化（i18n）ガイド](i18n-guide.md)
多言語対応（日本語・英語）の設定方法。

## クイックリファレンス

### SSM（推奨）

```python
from SessionSmith import ssm

ssm.init()                    # 初期化
ssm.commit("Initial state")   # コミット
ssm.log()                     # 履歴表示
ssm.checkout("abc123")        # 復元
ssm.continuous()              # 常時記録
```

### チェックポイント

```python
with ssm.checkpoint(interval=300) as cp:
    for epoch in range(1000):
        loss = train()
        cp.step(loss=loss)
```

### バージョン管理

```python
ssm.branch('feature', create=True)
ssm.checkout_branch('feature')
ssm.merge('feature')
ssm.tag('v1.0.0')
```
