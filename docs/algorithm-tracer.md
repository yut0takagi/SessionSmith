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

### トレースデータの保存

```python
# JSON形式で保存
tracer.save("trace.json", format="json")

# Pickle形式で保存
tracer.save("trace.pkl", format="pickle")
```

### トレースデータの読み込み

```python
tracer = AlgorithmTracer()
tracer.load("trace.json", format="json")
trace_data = tracer.get_trace_data()
```

## 可視化

### 基本的な可視化

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

### デバッグモード

```python
# デバッグ情報を表示
visualize_algorithm_trace(
    trace_data=tracer.get_trace_data(),
    output_file="animation.gif",
    target_variables=["arr"],
    debug=True  # デバッグ情報を表示
)
```

### アニメーションなしで表示

```python
# 最後のステップのみ表示
visualize_algorithm_trace(
    trace_data=tracer.get_trace_data(),
    output_file="final_state.png",
    target_variables=["arr"],
    animation=False
)
```

## トレーサーのオプション

### 追跡する変数を指定

```python
# 特定の変数のみ追跡
tracer = AlgorithmTracer(
    target_variables=["arr", "i", "j"],
    track_all=False  # 指定した変数のみ追跡
)

# 全ての変数を追跡
tracer = AlgorithmTracer(track_all=True)
```

### 配列サイズの制限

```python
# 大きな配列はサンプルのみ記録
tracer = AlgorithmTracer(
    max_array_size=1000,  # 1000要素を超える場合はサンプル
    max_string_length=200  # 文字列の最大長
)
```

### 除外する型を指定

```python
from types import FunctionType, ModuleType

tracer = AlgorithmTracer(
    exclude_types=[FunctionType, ModuleType, type]
)
```

## サマリーの表示

```python
from SessionSmith import print_trace_summary

# トレースデータのサマリーを表示
print_trace_summary(trace_data=tracer.get_trace_data())

# ファイルから読み込んで表示
print_trace_summary(trace_file="trace.json")
```

### サマリー情報の取得

```python
summary = tracer.get_summary()
print(f"総ステップ数: {summary['total_steps']}")
print(f"追跡された変数: {summary['variables_tracked']}")
print(f"行番号範囲: {summary['line_range']}")
print(f"実行された関数: {summary['functions_called']}")
```

## 使用例

### バブルソートの可視化

```python
from SessionSmith import AlgorithmTracer, visualize_algorithm_trace

def bubble_sort(arr):
    n = len(arr)
    for i in range(n):
        for j in range(0, n - i - 1):
            if arr[j] > arr[j + 1]:
                arr[j], arr[j + 1] = arr[j + 1], arr[j]

arr = [64, 34, 25, 12, 22, 11, 90]
with AlgorithmTracer(target_variables=["arr"]) as tracer:
    bubble_sort(arr)

visualize_algorithm_trace(
    trace_data=tracer.get_trace_data(),
    output_file="bubble_sort.gif",
    target_variables=["arr"],
    animation=True
)
```

### ヒープソートの可視化

```python
def heap_sort(arr):
    n = len(arr)
    for i in range(n // 2 - 1, -1, -1):
        heapify(arr, n, i)
    for i in range(n - 1, 0, -1):
        arr[i], arr[0] = arr[0], arr[i]
        heapify(arr, i, 0)

def heapify(arr, n, i):
    largest = i
    left = 2 * i + 1
    right = 2 * i + 2
    if left < n and arr[left] > arr[largest]:
        largest = left
    if right < n and arr[right] > arr[largest]:
        largest = right
    if largest != i:
        arr[i], arr[largest] = arr[largest], arr[i]
        heapify(arr, n, largest)

arr = [12, 11, 13, 5, 6, 7]
with AlgorithmTracer(target_variables=["arr", "n", "i", "largest"]) as tracer:
    heap_sort(arr)

visualize_algorithm_trace(
    trace_data=tracer.get_trace_data(),
    output_file="heap_sort.gif",
    target_variables=["arr"],
    animation=True
)
```

## 注意事項

- トレーサーは`sys.settrace`を使用するため、パフォーマンスに影響を与える可能性があります
- 大きな配列は自動的にサンプリングされます（`max_array_size`で制御）
- 可視化機能を使用するには`matplotlib`が必要です

