# チェックポイント機能 - 長時間学習対応

機械学習の学習ループなど、長時間実行されるタスクのためのチェックポイント機能です。

## 概要

- ⏱️ **長時間学習の中断対策**: 学習が途中で中断しても、最後のチェックポイントから再開可能
- 💥 **クラッシュ対策**: システムクラッシュ時でも状態を復元可能
- 📊 **メトリクス追跡**: loss、accuracy などの学習指標を記録
- 🔄 **自動保存**: 指定間隔で自動的にチェックポイントを作成

## 基本的な使い方

```python
from SessionSmith import ssm

ssm.init()

# 5分ごとに自動チェックポイント
with ssm.checkpoint(interval=300) as cp:
    for epoch in range(1000):
        loss = train_one_epoch()
        acc = validate()
        
        # 手動チェックポイント + メトリクス記録
        cp.step(loss=loss, accuracy=acc, epoch=epoch)
```

## パラメータ

| パラメータ | 型 | デフォルト | 説明 |
|-----------|-----|-----------|------|
| `interval` | int | 300 | チェックポイント間隔（秒） |
| `max_checkpoints` | int | 5 | 保持するチェックポイント数 |
| `on_error` | str | "warn" | エラー時の動作（"ignore", "warn", "raise"） |
| `compress` | bool | True | 圧縮するか |
| `message` | str | "Checkpoint" | チェックポイントメッセージ |

## 自動チェックポイントの動作

チェックポイントは以下のタイミングで自動的に作成されます：

1. **定期的**: `interval` 秒ごとにバックグラウンドスレッドが自動保存
2. **中断時**: Ctrl+C（SIGINT）やSIGTERM 受信時
3. **例外発生時**: 例外が発生した場合、緊急チェックポイントを作成
4. **終了時**: `with` ブロックを抜ける際

## メトリクス追跡

```python
with ssm.checkpoint(interval=300) as cp:
    for epoch in range(100):
        train_loss = train()
        val_loss, val_acc = validate()
        
        # メトリクスを記録
        cp.step(
            train_loss=train_loss,
            val_loss=val_loss,
            val_accuracy=val_acc,
            epoch=epoch,
        )
    
    # サマリーを取得
    summary = cp.summary()
    print(f"Steps: {summary['step_count']}")
    print(f"Metrics: {summary['metrics']}")
```

## チェックポイントからの復元

### 最新のチェックポイントから復元

```python
ssm.init()

# 最新のチェックポイントから復元
meta = ssm.restore_checkpoint()

print(f"Restored: {meta['restored_count']} variables")
print(f"Timestamp: {meta['timestamp']}")
print(f"Metrics: {meta['metrics']}")
```

### 特定のチェックポイントから復元

```python
# チェックポイント一覧を取得
checkpoints = ssm.list_checkpoints()

# 特定のチェックポイントを指定
ssm.restore_checkpoint(".ssm/checkpoints/checkpoint_20251224_103000.gz")
```

## チェックポイントの管理

```python
# 一覧表示
checkpoints = ssm.list_checkpoints()

# 最新3つを残して削除
ssm.clean_checkpoints(keep=3)

# すべて削除
ssm.clean_checkpoints(keep=0)
```

## 実践例

### PyTorch での学習

```python
import torch
from SessionSmith import ssm

ssm.init()

model = create_model()
optimizer = torch.optim.Adam(model.parameters())

# 10分ごとにチェックポイント
with ssm.checkpoint(interval=600, max_checkpoints=3) as cp:
    for epoch in range(100):
        loss = train_step(model)
        val_loss, val_acc = validate(model)
        
        cp.step(
            epoch=epoch,
            train_loss=loss.item(),
            val_loss=val_loss,
            val_accuracy=val_acc,
        )

# 学習完了後にコミット
ssm.commit("Training complete")
```

### 中断からの再開

```python
ssm.init()

# 前回の状態を復元
try:
    meta = ssm.restore_checkpoint()
    start_epoch = epoch + 1
except FileNotFoundError:
    start_epoch = 0
    model = create_model()

# 学習を再開/開始
with ssm.checkpoint(interval=300) as cp:
    for epoch in range(start_epoch, 100):
        train()
        cp.step(epoch=epoch)
```

## 制限事項

- チェックポイントは `.ssm/checkpoints/` ディレクトリに保存されます
- 変数サイズが大きい場合（100MB以上）、警告が表示されます
- 500MB を超える変数はスキップされます
- 総サイズが 2GB を超える場合、一部の変数がスキップされます

## トラブルシューティング

### チェックポイントが作成されない

```python
with ssm.checkpoint(interval=60, on_error="raise") as cp:
    # on_error="raise" でエラーを表示
    ...
```

### 復元に時間がかかる

不要な変数を除外リストに追加してください：

```python
ssm.exclude("large_tensor", "temporary_data")
```

## 関連ドキュメント

- [SSM ガイド](ssm-guide.md) - Git風セッション管理
- [API リファレンス](api-reference.md) - 詳細なAPI
