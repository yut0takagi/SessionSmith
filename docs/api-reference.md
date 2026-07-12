# APIリファレンス

SessionSmithの主要APIのリファレンスです。シグネチャは実装（v2.1.0）に準拠しています。

> オプション機能の依存: 暗号化は `pip install SessionSmith[crypto]`、S3 は `[s3]`、GCS は `[gcs]`、両方は `[cloud]`、すべては `[all]`。署名（HMAC）・構造化ロギング・i18n は追加依存なしで動作します。

## SSM（Git風セッション管理）

### 基本操作

#### `ssm.init()`

SSMを初期化します。

```python
ssm.init(path: Optional[Union[str, Path]] = None, force: bool = False) -> None
```

#### `ssm.commit()`

現在の状態をコミットします。`sign_key` が設定されている場合は HMAC 署名を付与します（[セキュリティ](#セキュリティ暗号化署名検証)参照）。

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

設定を取得/設定します。`key` のみ指定で取得、`key` と `value` で設定します。署名鍵は `ssm.config('sign_key', '<secret>')` で設定します（環境変数 `SESSIONSMITH_SIGN_KEY` でも可）。

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

#### `ssm.get_current_branch()`

現在のブランチ名を取得します（detached HEAD の場合は `None`）。

```python
ssm.get_current_branch() -> Optional[str]
```

#### `ssm.merge()`

指定したブランチを現在のブランチにマージします。共通祖先を検出し、2つの親（現在のHEADとマージ元）を持つマージコミットを作成します。

> ⚠️ 現状のマージは**履歴の統合のみ**で、変数値レベルのコンフリクト検出は行いません。同名変数が両ブランチで異なる場合、マージ時点でセッションに存在する値がそのまま記録されます（last-writer-wins）。`SSMMergeConflictError` は将来の値マージ実装のために予約された例外で、現状は送出されません。

```python
ssm.merge(branch_name: str, message: Optional[str] = None) -> str
```

**戻り値:** マージコミットのハッシュ

#### `ssm.tag()`

コミットにタグを付けます（`commit_hash` 省略時は現在の HEAD）。

```python
ssm.tag(tag_name: str, commit_hash: Optional[str] = None, message: Optional[str] = None) -> str
```

#### `ssm.list_tags()`

すべてのタグを一覧表示します。

```python
ssm.list_tags() -> List[Dict[str, Any]]
```

**戻り値:** 各タグの `name` / `commit` / `message` などを含む辞書のリスト

#### `ssm.checkout_tag()`

タグが指すコミットからチェックアウトします。

```python
ssm.checkout_tag(tag_name: str) -> None
```

### リモート（クラウド / URL 対応）

対応する URL スキーム（v2.1.0）:

| URL | バックエンド | 依存 (extras) | 対応操作 |
|-----|------------|--------------|---------|
| ローカルパス / `file://` | FileSystem | なし | push / pull |
| `s3://bucket/prefix` | Amazon S3（S3互換含む） | `boto3`（`[s3]`） | push / pull |
| `gs://bucket/prefix` | Google Cloud Storage | `google-cloud-storage`（`[gcs]`） | push / pull |
| `http://` / `https://` | HTTP | なし | **pull のみ（読み取り専用）** |

> push 時に `manifest.json` を生成し、一覧取得できないバックエンド（HTTP など）からの pull に対応します。依存が未インストールの場合、該当スキームの利用時にのみエラーになります。

#### `ssm.remote_add()`

リモートリポジトリを追加します。

```python
ssm.remote_add(name: str, url: str) -> None
```

#### `ssm.remote_list()`

登録済みリモートの一覧を取得します。

```python
ssm.remote_list() -> Dict[str, str]
```

**戻り値:** `{リモート名: URL}` の辞書

#### `ssm.push()`

リモートにプッシュします。`password` を指定するとリモート上のデータを暗号化します（要 `[crypto]`）。

```python
ssm.push(
    remote_name: str = "origin",
    branch_name: Optional[str] = None,
    *,
    password: Optional[str] = None,
) -> None
```

#### `ssm.pull()`

リモートからプルします。暗号化して push したデータは同じ `password` を指定して復号します。

```python
ssm.pull(
    remote_name: str = "origin",
    branch_name: Optional[str] = None,
    *,
    password: Optional[str] = None,
) -> None
```

### 形式変換

#### `ssm.export()`

コミットを従来形式（.pkl, .json など）でエクスポートします。`password` を指定すると認証付き暗号でエクスポートします（要 `[crypto]`）。

```python
ssm.export(
    output_path: Union[str, Path],
    commit_hash: Optional[str] = None,
    format: Optional[str] = None,
    compress: Union[bool, str] = False,
    *,
    password: Optional[str] = None,
) -> Path
```

#### `ssm.import_session()`

従来形式からインポートしてコミットを作成します。暗号化ファイルは同じ `password` を指定して復号します。

```python
ssm.import_session(
    input_path: Union[str, Path],
    message: Optional[str] = None,
    format: Optional[str] = None,
    *,
    password: Optional[str] = None,
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

## セキュリティ（暗号化・署名・検証）

v2.1.0 で追加。暗号化は `cryptography`（extras: `crypto`）が必要です。署名（HMAC）と検証は標準ライブラリのみで動作します。

### 署名と検証

`ssm.config('sign_key', ...)`（または環境変数 `SESSIONSMITH_SIGN_KEY`）で署名鍵を設定すると、以降の `ssm.commit()` に HMAC-SHA256 署名が付与されます。

#### `ssm.verify()`

コミットの整合性（オブジェクトの再ハッシュ）と署名を検証します。`commit_hash` 省略時は HEAD を検証します。

```python
ssm.verify(commit_hash: Optional[str] = None) -> Dict[str, Any]
```

**戻り値（辞書）:**

| キー | 型 | 説明 |
|------|----|------|
| `commit` | `str` | 検証対象のコミットハッシュ |
| `integrity_ok` | `bool` | 全オブジェクトの再ハッシュが一致したか |
| `signed` | `bool` | コミットに署名が付いているか |
| `signature_ok` | `Optional[bool]` | 署名検証の結果（未署名時は `None`、署名済みだが鍵未設定なら `False`） |
| `issues` | `List[str]` | 検出された問題のメッセージ一覧 |

```python
ssm.config('sign_key', 'team-secret')
ssm.commit('signed snapshot')
result = ssm.verify()
# {'commit': '...', 'integrity_ok': True, 'signed': True, 'signature_ok': True, 'issues': []}
```

### トップレベルの暗号化・署名関数

低レベルのバイト列操作用に、以下がトップレベルで公開されています。

```python
from SessionSmith import (
    encrypt_data, decrypt_data, sign_data, verify_signature,
    CryptoError, HAS_CRYPTOGRAPHY,
)
```

#### `encrypt_data()` / `decrypt_data()`

認証付き暗号（Fernet / AES-128-CBC + HMAC）。パスワードから PBKDF2-HMAC-SHA256 で鍵を導出します。要 `[crypto]`。

```python
encrypt_data(data: bytes, password: str, iterations: int = DEFAULT_ITERATIONS) -> bytes
decrypt_data(blob: bytes, password: str) -> bytes
```

#### `sign_data()` / `verify_signature()`

HMAC-SHA256 署名（標準ライブラリのみ）。検証はタイミング攻撃に耐性のある比較を使用します。

```python
sign_data(data: bytes, key: str) -> str
verify_signature(data: bytes, signature: str, key: str) -> bool
```

- `CryptoError`: 暗号化・復号の失敗時に送出される例外。
- `HAS_CRYPTOGRAPHY`: `cryptography` が利用可能かを示す真偽値。`False` の場合、暗号化系 API は `CryptoError` を送出します（署名系は影響を受けません）。

## 構造化ロギング

v2.1.0 で追加。ログレベル・ファイル出力（サイズベースのローテーション）・JSON 構造化ログに対応します。追加依存は不要です。

```python
from SessionSmith import setup_logging, set_log_level, get_log_level, enable_debug
```

#### `setup_logging()`

```python
setup_logging(
    level: Union[int, str] = "INFO",
    log_file: Optional[Union[str, Path]] = None,
    *,
    console: bool = True,
    json_format: bool = False,
    fmt: str = DEFAULT_FORMAT,
    max_bytes: int = 5 * 1024 * 1024,
    backup_count: int = 3,
) -> logging.Logger
```

#### `set_log_level()` / `get_log_level()` / `enable_debug()`

```python
set_log_level(level: Union[int, str]) -> None
get_log_level() -> str
enable_debug(log_file: Optional[Union[str, Path]] = None) -> logging.Logger
```

> 環境変数 `SESSIONSMITH_LOG_LEVEL` / `SESSIONSMITH_LOG_FILE` / `SESSIONSMITH_LOG_JSON` により import 時に自動設定されます。

## 国際化（i18n）

日本語・英語のエラー/情報メッセージに対応します。

```python
from SessionSmith import set_language, get_language, translate, t, Language
```

```python
set_language(lang: Union[str, Language], save_to_ssm: bool = True) -> None
get_language() -> str
translate(key: str, **kwargs: Any) -> str
t(key: str, **kwargs: Any) -> str   # translate のエイリアス
```

- `set_language('ja' | 'en' | 'auto')` で切り替え（`auto` はロケールから判定）。環境変数 `SESSIONSMITH_LANG` でも設定可能。
- `save_to_ssm=True`（既定）の場合、SSM 初期化済みなら `.ssm/config` に言語設定を保存します。
- `Language` は言語を表す Enum。

## 基本機能（後方互換性）

> ⚠️ 新規開発では `ssm` の使用を推奨します。

### `save_session()`

セッションを保存します（デフォルトで SSM に統合済み）。

```python
save_session(
    file_path: Union[str, Path],
    globals_dict: Optional[Dict[str, Any]] = None,
    exclude: Optional[List[str]] = None,
    use_ssm: bool = True,  # デフォルトでSSMに統合
) -> None
```

### `load_session()`

セッションを復元します（デフォルトで SSM から読み込み）。

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
| `SessionSmithError` | ライブラリ全体の基底例外 |
| `SSMError` | SSM関連の基底例外 |
| `SSMNotInitializedError` | SSMが初期化されていない |
| `SSMCommitNotFoundError` | コミットが見つからない |
| `SSMNoCommitsError` | コミットが存在しない |
| `SSMConfigError` | 設定関連のエラー |
| `SSMBranchNotFoundError` | ブランチが見つからない |
| `SSMTagNotFoundError` | タグが見つからない |
| `SSMRemoteNotFoundError` | リモートが見つからない |
| `SSMMergeConflictError` | マージコンフリクト（将来の値マージ用に予約。現状は未送出） |
| `SessionError` | セッション操作の基底例外 |
| `SessionSaveError` | 保存時のエラー |
| `SessionLoadError` | 読み込み時のエラー |
| `SessionCorruptedError` | セッションファイルの破損 |
| `CheckpointError` / `CheckpointSaveError` / `CheckpointRestoreError` | チェックポイント関連のエラー |
| `SerializationError` / `VariableSerializationError` | シリアライズ失敗 |
| `ValidationError` | 入力検証エラー |
| `ResourceError` / `MemoryLimitError` / `StorageLimitError` | リソース制限関連 |
| `CryptoError` | 暗号化・復号の失敗 |

すべての例外クラスは `to_dict()` を持ち、JSON 出力に対応します。詳細は各ドキュメントを参照してください。
