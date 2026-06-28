"""
暗号化・署名モジュール（セキュリティ機能）

このモジュールは2つの独立した機能を提供します:

1. **整合性・改ざん検出（署名）**: HMAC-SHA256 を使用。Python標準ライブラリ
   のみで動作し、追加の依存関係は不要です。コミットやエクスポートしたデータの
   改ざんを検出できます。

2. **暗号化**: 認証付き暗号（Fernet / AES-128-CBC + HMAC）を使用。`cryptography`
   パッケージが必要です（``pip install SessionSmith[crypto]``）。パスワードから
   PBKDF2-HMAC-SHA256 で鍵を導出します。

Note:
    暗号化はエクスポート／インポートやリモートとの同期など、データが SessionSmith
    の管理下を離れる「境界」での利用を想定しています。pickle ファイルを平文のまま
    共有・バックアップするリスクを軽減します。
"""

import base64
import hashlib
import hmac
import os
import struct
from typing import Optional

# 暗号化用のオプショナル依存
# ImportError だけでなく、ネイティブ拡張（cffi/rust）の読み込み失敗など
# 環境依存の例外も握りつぶし、暗号化機能を無効化して degrade させる。
try:
    from cryptography.fernet import Fernet, InvalidToken

    HAS_CRYPTOGRAPHY = True
except BaseException:  # noqa: BLE001  # pragma: no cover - 依存がない/壊れている環境向け
    # ImportError に加え、ネイティブ拡張（cffi/pyo3）の読み込み失敗による
    # PanicException（BaseException 派生）等もここで握りつぶし degrade させる。
    HAS_CRYPTOGRAPHY = False
    Fernet = None  # type: ignore
    InvalidToken = Exception  # type: ignore


# 暗号化済みデータを識別するためのマジックヘッダー
MAGIC = b"SSMENC01"
# 鍵導出のデフォルト反復回数（PBKDF2）
DEFAULT_ITERATIONS = 200_000
# ソルト長（バイト）
SALT_SIZE = 16


class CryptoError(Exception):
    """暗号化・復号・署名検証に関するエラー"""


class CryptoDependencyError(CryptoError):
    """暗号化に必要な依存パッケージが不足している場合のエラー"""

    def __init__(self) -> None:
        super().__init__(
            "Encryption requires the 'cryptography' package. "
            "Install it with: pip install SessionSmith[crypto]"
        )


# ========== 署名（HMAC-SHA256, 標準ライブラリのみ） ==========


def sign_data(data: bytes, key: str) -> str:
    """
    データに HMAC-SHA256 署名を付与します（改ざん検出用）。

    Args:
        data: 署名対象のバイト列
        key: 署名鍵（秘密鍵）

    Returns:
        str: 16進数の署名文字列
    """
    if not isinstance(data, bytes):
        raise TypeError("data must be bytes")
    return hmac.new(key.encode("utf-8"), data, hashlib.sha256).hexdigest()


def verify_signature(data: bytes, signature: str, key: str) -> bool:
    """
    HMAC-SHA256 署名を検証します（タイミング攻撃に耐性のある比較）。

    Args:
        data: 検証対象のバイト列
        signature: 期待される署名（16進数文字列）
        key: 署名鍵

    Returns:
        bool: 署名が一致すれば True
    """
    if not signature:
        return False
    expected = sign_data(data, key)
    return hmac.compare_digest(expected, signature)


# ========== 暗号化（Fernet, オプショナル） ==========


def _derive_fernet_key(password: str, salt: bytes, iterations: int = DEFAULT_ITERATIONS) -> bytes:
    """
    パスワードから Fernet 用の鍵（url-safe base64 でエンコードされた32バイト）を導出します。

    PBKDF2-HMAC-SHA256 を標準ライブラリで実行するため、cryptography の鍵導出機能には
    依存しません。
    """
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations, dklen=32)
    return base64.urlsafe_b64encode(dk)


def is_encrypted(blob: bytes) -> bool:
    """データが SessionSmith により暗号化されたものか判定します。"""
    return isinstance(blob, bytes) and blob[: len(MAGIC)] == MAGIC


def encrypt_data(data: bytes, password: str, iterations: int = DEFAULT_ITERATIONS) -> bytes:
    """
    データを暗号化します（認証付き暗号）。

    出力フォーマット::

        MAGIC(8) | iterations(uint32 BE) | salt(16) | Fernet token(...)

    Args:
        data: 平文のバイト列
        password: 暗号化パスワード
        iterations: PBKDF2 の反復回数

    Returns:
        bytes: 暗号化されたバイト列（``is_encrypted`` が True を返す形式）

    Raises:
        CryptoDependencyError: cryptography パッケージが無い場合
    """
    if not HAS_CRYPTOGRAPHY:
        raise CryptoDependencyError()
    if not password:
        raise CryptoError("Password must not be empty")
    if not isinstance(data, bytes):
        raise TypeError("data must be bytes")

    salt = os.urandom(SALT_SIZE)
    key = _derive_fernet_key(password, salt, iterations)
    token = Fernet(key).encrypt(data)
    header = MAGIC + struct.pack(">I", iterations) + salt
    return header + token


def decrypt_data(blob: bytes, password: str) -> bytes:
    """
    ``encrypt_data`` で暗号化されたデータを復号します。

    Args:
        blob: 暗号化されたバイト列
        password: 復号パスワード

    Returns:
        bytes: 復号された平文

    Raises:
        CryptoDependencyError: cryptography パッケージが無い場合
        CryptoError: フォーマット不正・パスワード誤り・改ざんを検出した場合
    """
    if not HAS_CRYPTOGRAPHY:
        raise CryptoDependencyError()
    if not is_encrypted(blob):
        raise CryptoError("Data is not in SessionSmith encrypted format")

    header_len = len(MAGIC) + 4 + SALT_SIZE
    if len(blob) < header_len:
        raise CryptoError("Encrypted data is truncated or corrupted")

    iterations = struct.unpack(">I", blob[len(MAGIC) : len(MAGIC) + 4])[0]
    salt = blob[len(MAGIC) + 4 : header_len]
    token = blob[header_len:]

    key = _derive_fernet_key(password, salt, iterations)
    try:
        return Fernet(key).decrypt(token)
    except InvalidToken as e:
        raise CryptoError(
            "Failed to decrypt: wrong password or the data has been tampered with"
        ) from e


def maybe_decrypt(blob: bytes, password: Optional[str]) -> bytes:
    """
    暗号化されていれば復号し、そうでなければそのまま返します。

    Args:
        blob: 読み込んだバイト列
        password: パスワード（None で暗号化されていない場合はそのまま）

    Returns:
        bytes: 平文のバイト列
    """
    if is_encrypted(blob):
        if not password:
            raise CryptoError("Data is encrypted but no password was provided")
        return decrypt_data(blob, password)
    return blob
