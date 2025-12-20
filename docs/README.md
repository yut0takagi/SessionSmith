# SessionSmith ドキュメント

SessionSmithの詳細なドキュメントです。

## ドキュメント一覧

### 📖 [基本的な使い方](getting-started.md)
保存・復元の基本的な使い方、圧縮、セレクティブロードなどの機能を説明します。

### 🔄 [バージョン管理](version-control.md)
Git風のバージョン管理機能の使い方を説明します。コミット、チェックアウト、履歴管理など。

### 📈 [アルゴリズム実行トレーサー](algorithm-tracer.md)
アルゴリズムの実行を1行ごとにトレースし、可視化する機能の使い方を説明します。

### 📚 [APIリファレンス](api-reference.md)
全APIの詳細なリファレンスです。パラメータ、戻り値、使用例を含みます。

## クイックリファレンス

### 基本的な保存・復元

```python
from SessionSmith import save_session, load_session

save_session("session.pkl")
load_session("session.pkl")
```

### SessionManager

```python
from SessionSmith import SessionManager

manager = SessionManager()
manager.save("session.pkl")
manager.load("session.pkl")
```

### バージョン管理

```python
manager = SessionManager(enable_version_control=True)
manager.save("session.pkl", commit_message="Initial state")
manager.log()
manager.checkout(message="Initial state")
```

### アルゴリズムトレーサー

```python
from SessionSmith import AlgorithmTracer, visualize_algorithm_trace

with AlgorithmTracer(target_variables=["arr"]) as tracer:
    bubble_sort(arr)

visualize_algorithm_trace(
    trace_data=tracer.get_trace_data(),
    output_file="animation.gif"
)
```

