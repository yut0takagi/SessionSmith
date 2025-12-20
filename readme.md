# SessionSmith

**SessionSmith** は、Jupyter Notebook や Python 実行時のセッション（変数・オブジェクト）を簡単に保存・復元できる軽量ライブラリです。

## ⚠️ セキュリティ警告

**重要**: このライブラリは`pickle`を使用しています。信頼できないソースからのセッションファイルをロードしないでください。悪意のあるpickleファイルは任意のコードを実行する可能性があります。

- ✅ 信頼できるソースからのファイルのみをロードしてください
- ✅ 不審なファイルをロードする前に、`verify_session()`で検証してください
- ✅ 本番環境では、セッションファイルの保存場所へのアクセスを制限してください

## 特徴

- `pickle` を使ってシームレスにセッション保存
- たった2行で保存＆復元
- 簡単＆高速
- 圧縮サポート（gzip/bz2）
- セッション情報表示・比較機能
- 自動バックアップ機能
- カスタムシリアライザー対応
- **アルゴリズム実行トレーサー**（1行ごとの変数状態記録・可視化）

## インストール

```bash
pip install SessionSmith
```

## 基本的な使い方

```python
from SessionSmith import save_session, load_session

# セッション保存
save_session("my_session.pkl")

# セッション復元
load_session("my_session.pkl")
```

## 主な機能

### 1. 基本的な保存・復元

```python
from SessionSmith import save_session, load_session

# 保存
save_session("session.pkl")

# 特定の変数を除外して保存
save_session("session.pkl", exclude=["temp", "cache"])

# 復元
load_session("session.pkl")

# 特定の変数のみ復元
load_session("session.pkl", include=["data", "model"])
```

**注意**: Jupyter Notebook環境では、`_ih`, `_oh`, `In`, `Out`などの内部変数は自動的に除外されます（`exclude_jupyter=True`がデフォルト）。これらを含めたい場合は`exclude_jupyter=False`を指定してください。

### 2. 圧縮サポート

```python
# gzip圧縮で保存
save_session("session.pkl", compress=True)

# bzip2圧縮で保存
save_session("session.pkl", compress="bz2")
```

### 3. セッション情報表示

```python
from SessionSmith import get_session_info, print_session_info, list_session_variables

# 詳細情報を取得
info = get_session_info("session.pkl")
print(info)

# 整形して表示
print_session_info("session.pkl")

# 変数名のリストを取得
variables = list_session_variables("session.pkl")
print(variables)
```

### 4. セッション比較

```python
from SessionSmith import compare_sessions, print_comparison

# 2つのセッションを比較
result = compare_sessions("session1.pkl", "session2.pkl")
print(result)

# 詳細な比較（値の変更も検出）
result = compare_sessions("session1.pkl", "session2.pkl", detailed=True)

# 整形して表示
print_comparison("session1.pkl", "session2.pkl", detailed=True)
```

### 5. SessionManagerクラス

```python
from SessionSmith import SessionManager

# マネージャーを作成
manager = SessionManager()

# 保存
manager.save("session.pkl")

# ロード
manager.load("session.pkl")

# 自動バックアップ（5分ごと）
manager.auto_save(interval=300, file_path="autosave.pkl")

# 自動バックアップを停止
manager.stop_auto_save()
```

### 6. セッション検証

```python
from SessionSmith import verify_session

# セッションファイルの整合性を検証
is_valid, error = verify_session("session.pkl")
if is_valid:
    print("Session file is valid")
else:
    print(f"Error: {error}")
```

### 7. メタデータ保存

```python
# メタデータ（保存日時、バージョンなど）を含めて保存
save_session("session.pkl", metadata=True)
```

### 8. カスタムシリアライザー

```python
from SessionSmith import CustomSerializer

# シリアライザーを作成
serializer = CustomSerializer()

# 特定の型に対するシリアライザーを登録
def my_serializer(obj):
    return obj.to_dict()

serializer.register(MyClass, my_serializer)

# カスタムシリアライザーを使って保存
save_session("session.pkl", serializer=serializer)
```

### 9. 詳細オプション

```python
# 詳細ログを出力
save_session("session.pkl", verbose=True)

# エラー時の動作を指定
save_session("session.pkl", on_error="warn")  # 'skip', 'warn', 'raise'

# pickleプロトコルバージョンを指定
save_session("session.pkl", protocol=4)
```

### 10. アルゴリズム実行トレーサー（新機能）

アルゴリズムの実行を1行ごとにトレースし、変数の状態を記録・可視化する機能です。ヒープソートやバブルソートなどのアルゴリズムの動作を理解するのに最適です。

```python
from SessionSmith import AlgorithmTracer, visualize_algorithm_trace, print_trace_summary

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

# トレースデータを保存
tracer.save("bubble_sort_trace.json", format="json")

# サマリーを表示
print_trace_summary(trace_data=tracer.get_trace_data())

# 可視化（matplotlibが必要）
# pip install matplotlib または pip install SessionSmith[visualization]
visualize_algorithm_trace(
    trace_data=tracer.get_trace_data(),
    output_file="bubble_sort_animation.gif",
    target_variables=["arr"],
    animation=True
)
```

**特徴:**
- チェックポイント不要：`sys.settrace`で自動的に1行ごとに記録
- 柔軟な追跡：特定の変数のみ、または全ての変数を追跡可能
- 可視化対応：配列の変化をアニメーション（GIF/HTML）で表示
- 複数形式対応：JSON/Pickleで保存

**可視化機能を使うには:**
```bash
pip install SessionSmith[visualization]
# または
pip install matplotlib
```

## ライセンス

MIT
