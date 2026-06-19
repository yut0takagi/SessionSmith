"""
リモートストレージバックエンド

SessionSmith のリモート（push/pull 先）を抽象化します。ローカルディレクトリに
加えて、クラウドストレージ（S3, GCS）や HTTP 越しの読み取りに対応します。

各バックエンドは「リポジトリルート（objects/ や commits/ などを含む）」を基準とした
相対パスに対するシンプルなキー・バリュー操作を提供します:

    - exists(rel_path) -> bool
    - read_bytes(rel_path) -> bytes
    - write_bytes(rel_path, data) -> None
    - list_files(prefix="") -> list[str]

URL スキームによってバックエンドが選択されます:

    /path or ./path or file://   FileSystemBackend
    s3://bucket/prefix           S3Backend       （要 boto3 / extras: s3）
    gs://bucket/prefix           GCSBackend      （要 google-cloud-storage / extras: gcs）
    http:// , https://           HTTPBackend     （読み取り専用、pull のみ）

クラウド用の依存（boto3, google-cloud-storage）はオプショナルで、対応する
リモートを使用するときにのみ必要です。
"""

import logging
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger("SessionSmith.remote")

# 全ファイル一覧を保持するマニフェスト（HTTP のような一覧不可のバックエンド用）
MANIFEST_NAME = "manifest.json"


class RemoteBackendError(Exception):
    """リモートバックエンドに関するエラー"""


class RemoteBackend(ABC):
    """リモートストレージバックエンドの抽象基底クラス"""

    #: 書き込み可能か（HTTP は読み取り専用）
    writable: bool = True

    @abstractmethod
    def exists(self, rel_path: str) -> bool:
        """指定パスのオブジェクトが存在するか"""

    @abstractmethod
    def read_bytes(self, rel_path: str) -> bytes:
        """指定パスのオブジェクトを読み込む"""

    @abstractmethod
    def write_bytes(self, rel_path: str, data: bytes) -> None:
        """指定パスにオブジェクトを書き込む"""

    @abstractmethod
    def list_files(self, prefix: str = "") -> list[str]:
        """prefix 以下の全ファイルの相対パスを列挙する"""

    # 便利メソッド
    def read_text(self, rel_path: str) -> str:
        return self.read_bytes(rel_path).decode("utf-8")

    def write_text(self, rel_path: str, text: str) -> None:
        self.write_bytes(rel_path, text.encode("utf-8"))


class FileSystemBackend(RemoteBackend):
    """ローカル（またはマウントされた）ファイルシステム上のリモート"""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _full(self, rel_path: str) -> Path:
        return self.root / rel_path

    def exists(self, rel_path: str) -> bool:
        return self._full(rel_path).exists()

    def read_bytes(self, rel_path: str) -> bytes:
        return self._full(rel_path).read_bytes()

    def write_bytes(self, rel_path: str, data: bytes) -> None:
        full = self._full(rel_path)
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_bytes(data)

    def list_files(self, prefix: str = "") -> list[str]:
        base = self._full(prefix) if prefix else self.root
        if not base.exists():
            return []
        files = []
        for p in base.rglob("*"):
            if p.is_file():
                files.append(p.relative_to(self.root).as_posix())
        return files


class S3Backend(RemoteBackend):
    """Amazon S3（または S3 互換）ストレージ上のリモート"""

    def __init__(self, bucket: str, prefix: str = ""):
        try:
            import boto3
            from botocore.exceptions import ClientError
        except ImportError as e:  # pragma: no cover - 依存がない環境向け
            raise RemoteBackendError(
                "S3 remotes require 'boto3'. Install it with: pip install SessionSmith[s3]"
            ) from e
        self._client = boto3.client("s3")
        self._ClientError = ClientError
        self.bucket = bucket
        self.prefix = prefix.strip("/")

    def _key(self, rel_path: str) -> str:
        if self.prefix:
            return f"{self.prefix}/{rel_path}"
        return rel_path

    def exists(self, rel_path: str) -> bool:
        try:
            self._client.head_object(Bucket=self.bucket, Key=self._key(rel_path))
            return True
        except self._ClientError:
            return False

    def read_bytes(self, rel_path: str) -> bytes:
        obj = self._client.get_object(Bucket=self.bucket, Key=self._key(rel_path))
        return obj["Body"].read()

    def write_bytes(self, rel_path: str, data: bytes) -> None:
        self._client.put_object(Bucket=self.bucket, Key=self._key(rel_path), Body=data)

    def list_files(self, prefix: str = "") -> list[str]:
        full_prefix = self._key(prefix) if prefix else self.prefix
        paginator = self._client.get_paginator("list_objects_v2")
        base = (self.prefix + "/") if self.prefix else ""
        files = []
        for page in paginator.paginate(Bucket=self.bucket, Prefix=full_prefix):
            for item in page.get("Contents", []):
                key = item["Key"]
                rel = key[len(base):] if base and key.startswith(base) else key
                files.append(rel)
        return files


class GCSBackend(RemoteBackend):
    """Google Cloud Storage 上のリモート"""

    def __init__(self, bucket: str, prefix: str = ""):
        try:
            from google.cloud import storage
        except ImportError as e:  # pragma: no cover - 依存がない環境向け
            raise RemoteBackendError(
                "GCS remotes require 'google-cloud-storage'. "
                "Install it with: pip install SessionSmith[gcs]"
            ) from e
        self._client = storage.Client()
        self._bucket = self._client.bucket(bucket)
        self.prefix = prefix.strip("/")

    def _key(self, rel_path: str) -> str:
        if self.prefix:
            return f"{self.prefix}/{rel_path}"
        return rel_path

    def exists(self, rel_path: str) -> bool:
        return self._bucket.blob(self._key(rel_path)).exists()

    def read_bytes(self, rel_path: str) -> bytes:
        return self._bucket.blob(self._key(rel_path)).download_as_bytes()

    def write_bytes(self, rel_path: str, data: bytes) -> None:
        self._bucket.blob(self._key(rel_path)).upload_from_string(data)

    def list_files(self, prefix: str = "") -> list[str]:
        full_prefix = self._key(prefix) if prefix else self.prefix
        base = (self.prefix + "/") if self.prefix else ""
        files = []
        for blob in self._client.list_blobs(self._bucket, prefix=full_prefix):
            name = blob.name
            rel = name[len(base):] if base and name.startswith(base) else name
            files.append(rel)
        return files


class HTTPBackend(RemoteBackend):
    """HTTP(S) 越しの読み取り専用リモート（pull のみ対応）

    ファイル一覧の取得には、push 時に生成される ``manifest.json`` を使用します。
    """

    writable = False

    def __init__(self, base_url: str, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _url(self, rel_path: str) -> str:
        return f"{self.base_url}/{rel_path.lstrip('/')}"

    def exists(self, rel_path: str) -> bool:
        req = urllib.request.Request(self._url(rel_path), method="HEAD")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return 200 <= resp.status < 300
        except urllib.error.URLError:
            return False

    def read_bytes(self, rel_path: str) -> bytes:
        try:
            with urllib.request.urlopen(self._url(rel_path), timeout=self.timeout) as resp:
                return resp.read()
        except urllib.error.URLError as e:
            raise RemoteBackendError(f"Failed to fetch {rel_path}: {e}") from e

    def write_bytes(self, rel_path: str, data: bytes) -> None:
        raise RemoteBackendError("HTTP remotes are read-only; push is not supported")

    def list_files(self, prefix: str = "") -> list[str]:
        import json

        try:
            manifest = json.loads(self.read_text(MANIFEST_NAME))
        except Exception as e:
            raise RemoteBackendError(
                f"HTTP remote requires a {MANIFEST_NAME} (generated by push): {e}"
            ) from e
        files = manifest.get("files", [])
        if prefix:
            files = [f for f in files if f.startswith(prefix)]
        return files


def get_backend(url: str, *, local_ssm_dirname: str = ".ssm") -> RemoteBackend:
    """
    URL からリモートバックエンドを生成します。

    Args:
        url: リモート URL（ファイルパス, s3://, gs://, http(s)://）
        local_ssm_dirname: ローカルパスの場合に付与するリポジトリディレクトリ名

    Returns:
        RemoteBackend: 対応するバックエンドのインスタンス

    Raises:
        RemoteBackendError: 未対応のスキームの場合
    """
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()

    if scheme == "s3":
        return S3Backend(bucket=parsed.netloc, prefix=parsed.path.lstrip("/"))
    if scheme in ("gs", "gcs"):
        return GCSBackend(bucket=parsed.netloc, prefix=parsed.path.lstrip("/"))
    if scheme in ("http", "https"):
        return HTTPBackend(base_url=url)
    if scheme == "file":
        return FileSystemBackend(Path(parsed.path) / local_ssm_dirname)
    # スキームなし = ローカルパス
    if scheme == "" or len(scheme) == 1:  # Windows ドライブレター(C:) も考慮
        return FileSystemBackend(Path(url) / local_ssm_dirname)

    raise RemoteBackendError(f"Unsupported remote scheme: {scheme}://")


def is_url_remote(url: str) -> bool:
    """URL がクラウド/HTTP など、バックエンド経由が必要なリモートか判定します。"""
    parsed = urlparse(url)
    return parsed.scheme.lower() in ("s3", "gs", "gcs", "http", "https")
