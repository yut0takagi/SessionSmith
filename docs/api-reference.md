# APIリファレンス

SessionSmithの主要APIのリファレンスです。

## SSM（Git風セッション管理）

### 基本操作

#### `ssm.init()`

SSMを初期化します。

```python
ssm.init(path: Optional[Union[str, Path]] = None, force: bool = False) -> None
```

#### `ssm.commit()`

現在の状態をコミットします。

```python
ssm.commit(message: str = "", author: Optional[str] = None) -> str
```

**戻り値:** コミットハッシュ

#### `ssm.log()`

コミット履歴を表示します。

```python
ssm.log(limit: int = 10, oneline: bool = False) -> List[Dict[str, Any]]
```

#### `ssm.checkout()`

以前のコミット状態に復元します。

```python
ssm.checkout(commit_hash: Optional[str] = None) -> None
```

#### `ssm.status()`

現在の状態を表示します。

```python
ssm.status() -> Dict[str, Any]
```

#### `ssm.diff()`

コミットとの差分を表示します。

```python
ssm.diff(commit1: Optional[str] = None, commit2: Optional[str] = None) -> None
```

### 常時記録

#### `ssm.continuous()`

常時記録モードを有効化/無効化します。

```python
ssm.continuous(enable: bool = True, verbose: bool = False) -> None
```

#### `ssm.recover()`

常時記録から復元します。

```python
ssm.recover() -> None
```

### 設定

#### `ssm.config()`

設定を取得/設定します。

```python
ssm.config(key: Optional[str] = None, value: Optional[Any] = None) -> Any
```

#### `ssm.exclude()`

除外リストに変数を追加します。

```python
ssm.exclude(*names: str) -> None
```

### チェックポイント

#### `ssm.checkpoint()`

チェックポイントコンテキストマネージャーを返します。

```python
ssm.checkpoint(
    interval: int = 300,
    max_checkpoints: int = 5,
    on_error: str = "warn",
    compress: bool = True,
    message: str = "Checkpoint",
) -> CheckpointContext
```

#### `ssm.restore_checkpoint()`

チェックポイントから変数を復元します。

```python
ssm.restore_checkpoint(checkpoint: Optional[Union[str, Path]] = None) -> Dict[str, Any]
```

#### `ssm.list_checkpoints()`

利用可能なチェックポイントを一覧表示します。

```python
ssm.list_checkpoints() -> List[Dict[str, Any]]
```

### バージョン管理

#### `ssm.branch()`

ブランチの作成、一覧表示、または現在のブランチを取得します。

```python
ssm.branch(branch_name: Optional[str] = None, create: bool = False) -> Union[str, List[str]]
```

#### `ssm.checkout_branch()`

ブランチに切り替えます。

```python
ssm.checkout_branch(branch_name: str) -> None
```

#### `ssm.merge()`

ブランチをマージします。

```python
ssm.merge(branch_name: str, message: Optional[str] = None) -> str
```

#### `ssm.tag()`

コミットにタグを付けます。

```python
ssm.tag(tag_name: str, commit_hash: Optional[str] = None, message: Optional[str] = None) -> str
```

#### `ssm.remote_add()`

リモートリポジトリを追加します。

```python
ssm.remote_add(name: str, url: str) -> None
```

#### `ssm.push()`

リモートにプッシュします。

```python
ssm.push(remote: str, branch: str) -> None
```

#### `ssm.pull()`

リモートからプルします。

```python
ssm.pull(remote: str, branch: str) -> None
```

### 形式変換

#### `ssm.export()`

コミットを従来形式でエクスポートします。

```python
ssm.export(
    output_path: Union[str, Path],
    commit_hash: Optional[str] = None,
    format: Optional[str] = None,
    compress: Union[bool, str] = False,
) -> Path
```

#### `ssm.import_session()`

従来形式からインポートしてコミットを作成します。

```python
ssm.import_session(
    input_path: Union[str, Path],
    message: Optional[str] = None,
    format: Optional[str] = None,
) -> str
```

#### `ssm.convert()`

ファイル形式を直接変換します。

```python
ssm.convert(
    input_path: Union[str, Path],
    output_path: Union[str, Path],
    input_format: Optional[str] = None,
    output_format: Optional[str] = None,
    compress: Union[bool, str] = False,
) -> Path
```

## 基本機能（後方互換性）

### `save_session()`

セッションを保存します（SSMに統合済み）。

```python
save_session(
    file_path: Union[str, Path],
    globals_dict: Optional[Dict[str, Any]] = None,
    exclude: Optional[List[str]] = None,
    use_ssm: bool = True,  # デフォルトでSSMに統合
) -> None
```

### `load_session()`

セッションを復元します（SSMに統合済み）。

```python
load_session(
    file_path: Optional[Union[str, Path]] = None,  # Noneの場合はSSMから読み込み
    globals_dict: Optional[Dict[str, Any]] = None,
    use_ssm: bool = True,  # デフォルトでSSMから読み込み
) -> Dict[str, Any]
```

## 例外クラス

| 例外クラス | 説明 |
|---------|------|
| `SSMError` | SSM関連の基底例外 |
| `SSMNotInitializedError` | SSMが初期化されていない |
| `SSMCommitNotFoundError` | コミットが見つからない |
| `SSMNoCommitsError` | コミットが存在しない |
| `SessionSaveError` | 保存時のエラー |
| `SessionLoadError` | 読み込み時のエラー |

詳細は各ドキュメントを参照してください。
