# アルゴリズム実行トレーサー

アルゴリズムの実行を1行ごとにトレースし、変数の状態を記録・可視化する機能です。

## 概要

`AlgorithmTracer`を使用すると、アルゴリズムの実行中に変数の状態を自動的に記録できます。バブルソートやヒープソートなどのアルゴリズムの動作を理解するのに最適です。

## 基本的な使い方

### トレーサーの使用

```python
from SessionSmith import AlgorithmTracer

def bubble_sort(arr):
    n = len(arr)
    for i in range(n):
        for j in range(0, n - i - 1):
            if arr[j] > arr[j + 1]:
                arr[j], arr[j + 1] = arr[j + 1], arr[j]

# トレーサーを使用して実行
arr = [64, 34, 25, 12, 22, 11, 90]
with AlgorithmTracer(target_variables=["arr", "i", "j"]) as tracer:
    bubble_sort(arr)

# トレースデータを取得
trace_data = tracer.get_trace_data()
print(f"記録されたステップ数: {len(trace_data)}")
```

### トレースデータの保存・読み込み

```python
# 保存
tracer.save("trace.json", format="json")

# 読み込み
tracer = AlgorithmTracer()
tracer.load("trace.json", format="json")
trace_data = tracer.get_trace_data()
```

## 可視化

```python
from SessionSmith import visualize_algorithm_trace

# トレースデータを可視化
visualize_algorithm_trace(
    trace_data=tracer.get_trace_data(),
    output_file="animation.gif",
    target_variables=["arr"],
    animation=True
)
```

## トレーサーのオプション

```python
# 特定の変数のみ追跡
tracer = AlgorithmTracer(
    target_variables=["arr", "i", "j"],
    track_all=False
)

# すべての変数を追跡
tracer = AlgorithmTracer(track_all=True)
```

## 関連ドキュメント

- [API リファレンス](api-reference.md) - 詳細なAPI
