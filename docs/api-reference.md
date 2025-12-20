# APIリファレンス

SessionSmithの全APIの詳細なリファレンスです。

## 基本機能

### `save_session()`

セッションを保存します。

```python
save_session(
    file_path: Union[str, Path],
    globals_dict: Optional[Dict[str, Any]] = None,
    exclude: Optional[List[str]] = None,
    compress: Union[bool, str] = False,
    protocol: Optional[int] = None,
    metadata: bool = False,
    verbose: bool = False,
    on_error: str = "skip",
    serializer: Optional[Callable[[Any], Any]] = None,
    exclude_jupyter: bool = True,
) -> None
```

**パラメータ:**
- `file_path`: 保存するファイルパス
- `globals_dict`: 保存対象のグローバル変数辞書（通常は自動取得）
- `exclude`: 除外したい変数名のリスト
- `compress`: 圧縮形式（`True`=gzip, `"gzip"`, `"bz2"`, `False`）
- `protocol`: pickleプロトコルバージョン
- `metadata`: メタデータを保存するか
- `verbose`: 詳細なログを出力するか
- `on_error`: エラー時の動作（`"skip"`, `"warn"`, `"raise"`）
- `serializer`: カスタムシリアライザー関数
- `exclude_jupyter`: Jupyter内部変数を除外するか

### `load_session()`

セッションを復元します。

```python
load_session(
    file_path: Union[str, Path],
    globals_dict: Optional[Dict[str, Any]] = None,
    include: Optional[List[str]] = None,
    exclude: Optional[List[str]] = None,
    verbose: bool = False,
) -> Dict[str, Any]
```

**パラメータ:**
- `file_path`: ロードするファイルパス
- `globals_dict`: 復元先のグローバル変数辞書（通常は自動取得）
- `include`: ロードする変数名のリスト
- `exclude`: ロードから除外する変数名のリスト
- `verbose`: 詳細なログを出力するか

**戻り値:** ロードされた変数の辞書

## SessionManagerクラス

### `SessionManager`

セッション管理クラス。

```python
SessionManager(
    globals_dict: Optional[Dict[str, Any]] = None,
    enable_version_control: bool = False,
    vc_base_path: Optional[Union[str, Path]] = None
)
```

### メソッド

#### `save()`

セッションを保存します。

```python
save(
    file_path: Union[str, Path],
    exclude: Optional[List[str]] = None,
    compress: Union[bool, str] = False,
    protocol: Optional[int] = None,
    metadata: bool = False,
    verbose: bool = False,
    on_error: str = "skip",
    serializer: Optional[Callable[[Any], Any]] = None,
    exclude_jupyter: bool = True,
    auto_commit: Optional[bool] = None,
    commit_message: Optional[str] = None,
) -> None
```

#### `load()`

セッションをロードします。

```python
load(
    file_path: Union[str, Path],
    include: Optional[List[str]] = None,
    exclude: Optional[List[str]] = None,
    verbose: bool = False,
) -> Dict[str, Any]
```

#### `auto_save()`

自動バックアップを開始します。

```python
auto_save(
    interval: int = 300,
    file_path: Optional[Union[str, Path]] = None,
    exclude: Optional[List[str]] = None,
    compress: Union[bool, str] = False,
    metadata: bool = True,
) -> None
```

#### `stop_auto_save()`

自動バックアップを停止します。

```python
stop_auto_save() -> None
```

#### `is_auto_save_running()`

自動バックアップが実行中かどうかを返します。

```python
is_auto_save_running() -> bool
```

### バージョン管理メソッド

#### `commit()`

現在のセッションをコミットします。

```python
commit(
    message: str,
    file_path: Optional[Union[str, Path]] = None,
    author: Optional[str] = None,
    tags: Optional[List[str]] = None
) -> Optional[str]
```

**戻り値:** コミットハッシュ

#### `log()`

コミット履歴を表示します。

```python
log(
    limit: Optional[int] = None,
    oneline: bool = False
) -> List[Dict[str, Any]]
```

#### `checkout()`

以前のコミット状態に戻します。

```python
checkout(
    commit_hash: Optional[str] = None,
    message: Optional[str] = None,
    target_file: Optional[Union[str, Path]] = None
) -> None
```

#### `diff()`

2つのコミット間の差分を表示します。

```python
diff(
    commit1: Optional[str] = None,
    commit2: Optional[str] = None,
    detailed: bool = True
) -> Dict[str, Any]
```

#### `status()`

現在の状態を確認します。

```python
status() -> Dict[str, Any]
```

#### `tag()`

コミットにタグを追加します。

```python
tag(
    tag_name: str,
    commit_hash: Optional[str] = None
) -> None
```

#### `show()`

コミットの詳細情報を表示します。

```python
show(
    commit_hash: Optional[str] = None
) -> Dict[str, Any]
```

#### `enable_version_control()`

バージョン管理を有効化します。

```python
enable_version_control(
    base_path: Optional[Union[str, Path]] = None
) -> None
```

#### `disable_version_control()`

バージョン管理を無効化します。

```python
disable_version_control() -> None
```

## 情報表示機能

### `get_session_info()`

セッション情報を取得します。

```python
get_session_info(file_path: Union[str, Path]) -> Dict[str, Any]
```

### `print_session_info()`

セッション情報を整形して表示します。

```python
print_session_info(file_path: Union[str, Path]) -> None
```

### `list_session_variables()`

セッションファイルに含まれる変数名のリストを取得します。

```python
list_session_variables(file_path: Union[str, Path]) -> List[str]
```

## 比較機能

### `compare_sessions()`

2つのセッションファイルを比較します。

```python
compare_sessions(
    file_path1: Union[str, Path],
    file_path2: Union[str, Path],
    detailed: bool = False
) -> Dict[str, Any]
```

### `print_comparison()`

セッション比較結果を整形して表示します。

```python
print_comparison(
    file_path1: Union[str, Path],
    file_path2: Union[str, Path],
    detailed: bool = False
) -> None
```

## 検証機能

### `verify_session()`

セッションファイルの整合性を検証します。

```python
verify_session(file_path: Union[str, Path]) -> Tuple[bool, Optional[str]]
```

**戻り値:** `(is_valid, error_message)`

## カスタムシリアライザー

### `CustomSerializer`

カスタムシリアライザークラス。

```python
serializer = CustomSerializer()
serializer.register(MyClass, lambda obj: obj.to_dict())
```

## アルゴリズムトレーサー

### `AlgorithmTracer`

アルゴリズム実行トレーサークラス。

```python
AlgorithmTracer(
    target_variables: Optional[List[str]] = None,
    track_all: bool = True,
    max_depth: int = 10,
    exclude_types: Optional[List[type]] = None,
    max_array_size: int = 1000,
    max_string_length: int = 200,
)
```

### メソッド

#### `start()`

トレーシングを開始します。

```python
start() -> None
```

#### `stop()`

トレーシングを停止します。

```python
stop() -> None
```

#### `save()`

トレースデータを保存します。

```python
save(
    file_path: Union[str, Path],
    format: str = "json"
) -> None
```

#### `load()`

トレースデータを読み込みます。

```python
load(
    file_path: Union[str, Path],
    format: str = "json"
) -> None
```

#### `get_trace_data()`

トレースデータを取得します。

```python
get_trace_data() -> List[Dict[str, Any]]
```

#### `get_summary()`

トレースデータのサマリーを取得します。

```python
get_summary() -> Dict[str, Any]
```

#### `clear()`

トレースデータをクリアします。

```python
clear() -> None
```

## 可視化機能

### `visualize_algorithm_trace()`

アルゴリズムトレースを可視化します。

```python
visualize_algorithm_trace(
    trace_file: Optional[Union[str, Path]] = None,
    trace_data: Optional[List[Dict[str, Any]]] = None,
    output_file: Optional[Union[str, Path]] = None,
    target_variables: Optional[List[str]] = None,
    animation: bool = True,
    interval: int = 500,
    show: bool = True,
    debug: bool = False,
) -> None
```

### `print_trace_summary()`

トレースデータのサマリーを表示します。

```python
print_trace_summary(
    trace_file: Optional[Union[str, Path]] = None,
    trace_data: Optional[List[Dict[str, Any]]] = None
) -> None
```

