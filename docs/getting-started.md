# 基本的な使い方

SessionSmithの基本的な保存・復元機能の使い方を説明します。

## 基本的な保存・復元

### シンプルな保存・復元

```python
from SessionSmith import save_session, load_session

# セッション保存（pickle形式、デフォルト）
save_session("my_session.pkl")

# セッション復元
load_session("my_session.pkl")
```

### 複数形式のサポート

SessionSmithは複数の形式をサポートしています：

```python
# pickle形式（デフォルト、互換性重視）
save_session("session.pkl")
save_session("session.pkl", format="pickle")

# JSON形式（安全、可読性）
save_session("session.json")
save_session("session.json", format="json")

# MessagePack形式（安全、高速）
save_session("session.msgpack", format="msgpack")

# HDF5形式（科学計算データに最適）
save_session("session.h5", format="hdf5")
```

形式はファイル拡張子から自動検出されます。明示的に指定することも可能です。

### 特定の変数を除外して保存

```python
# 一時的な変数を除外
save_session("session.pkl", exclude=["temp", "cache", "debug_data"])
```

### 特定の変数のみ復元

```python
# 必要な変数のみロード
load_session("session.pkl", include=["data", "model", "scaler"])
```

### 特定の変数を除外して復元

```python
# 大きなデータを除外してロード
load_session("session.pkl", exclude=["large_array", "raw_data"])
```

## 圧縮サポート

大きなセッションを圧縮して保存することで、ディスク容量を節約できます。

```python
# gzip圧縮で保存（デフォルト）
save_session("session.pkl", compress=True)

# bzip2圧縮で保存（より高圧縮率）
save_session("session.pkl", compress="bz2")

# 圧縮なしで保存
save_session("session.pkl", compress=False)
```

圧縮されたファイルは自動的に検出されてロードされます。

## Jupyter Notebook環境での使用

Jupyter Notebook環境では、内部変数（`_ih`, `_oh`, `In`, `Out`など）は自動的に除外されます。

```python
# デフォルトでは内部変数は除外される
save_session("session.pkl")  # exclude_jupyter=True（デフォルト）

# 内部変数も含めて保存したい場合
save_session("session.pkl", exclude_jupyter=False)
```

## メタデータの保存

保存日時やバージョン情報を含めて保存できます。

```python
save_session("session.pkl", metadata=True)

# ロード時にメタデータが表示される
load_session("session.pkl", verbose=True)
```

## 詳細ログ

保存・復元の詳細を確認できます。

```python
# 保存時の詳細ログ
save_session("session.pkl", verbose=True)

# 復元時の詳細ログ
load_session("session.pkl", verbose=True)
```

## エラーハンドリング

エラー時の動作を指定できます。

```python
# エラーをスキップ（デフォルト）
save_session("session.pkl", on_error="skip")

# 警告を表示
save_session("session.pkl", on_error="warn")

# エラーで例外を発生
save_session("session.pkl", on_error="raise")
```

## セッション情報の確認

保存されたセッションの情報を確認できます。

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

## セッションの検証

セッションファイルの整合性を検証できます。

```python
from SessionSmith import verify_session

is_valid, error = verify_session("session.pkl")
if is_valid:
    print("Session file is valid")
else:
    print(f"Error: {error}")
```

## セッションの比較

2つのセッションファイルを比較できます。

```python
from SessionSmith import compare_sessions, print_comparison

# 基本的な比較
result = compare_sessions("session1.pkl", "session2.pkl")
print(result)

# 詳細な比較（値の変更も検出）
result = compare_sessions("session1.pkl", "session2.pkl", detailed=True)

# 整形して表示
print_comparison("session1.pkl", "session2.pkl", detailed=True)
```

