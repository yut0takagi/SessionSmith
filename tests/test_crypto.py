"""
crypto.py のテスト（暗号化・署名）
"""

import pytest

from SessionSmith import crypto

requires_crypto = pytest.mark.skipif(
    not crypto.HAS_CRYPTOGRAPHY,
    reason="cryptography package is not available",
)


class TestSigning:
    """HMAC 署名のテスト（標準ライブラリのみ・常に利用可能）"""

    def test_sign_and_verify(self):
        sig = crypto.sign_data(b"hello", "secret")
        assert isinstance(sig, str)
        assert crypto.verify_signature(b"hello", sig, "secret")

    def test_verify_fails_on_tampered_data(self):
        sig = crypto.sign_data(b"hello", "secret")
        assert not crypto.verify_signature(b"hello!", sig, "secret")

    def test_verify_fails_on_wrong_key(self):
        sig = crypto.sign_data(b"hello", "secret")
        assert not crypto.verify_signature(b"hello", sig, "other")

    def test_verify_empty_signature(self):
        assert not crypto.verify_signature(b"hello", "", "secret")

    def test_sign_requires_bytes(self):
        with pytest.raises(TypeError):
            crypto.sign_data("not bytes", "key")


class TestEncryptionUnavailable:
    """cryptography が無い場合の挙動"""

    def test_encrypt_raises_without_dependency(self):
        if crypto.HAS_CRYPTOGRAPHY:
            pytest.skip("cryptography is available")
        with pytest.raises(crypto.CryptoDependencyError):
            crypto.encrypt_data(b"data", "pw")


@requires_crypto
class TestEncryption:
    """Fernet 暗号化のテスト（cryptography が必要）"""

    def test_round_trip(self):
        blob = crypto.encrypt_data(b"secret data", "password")
        assert crypto.is_encrypted(blob)
        assert crypto.decrypt_data(blob, "password") == b"secret data"

    def test_wrong_password_fails(self):
        blob = crypto.encrypt_data(b"secret data", "password")
        with pytest.raises(crypto.CryptoError):
            crypto.decrypt_data(blob, "wrong")

    def test_tampered_ciphertext_fails(self):
        blob = bytearray(crypto.encrypt_data(b"secret data", "password"))
        blob[-1] ^= 0xFF  # 末尾を改ざん
        with pytest.raises(crypto.CryptoError):
            crypto.decrypt_data(bytes(blob), "password")

    def test_empty_password_rejected(self):
        with pytest.raises(crypto.CryptoError):
            crypto.encrypt_data(b"data", "")

    def test_is_encrypted_false_for_plaintext(self):
        assert not crypto.is_encrypted(b"plain text data")

    def test_maybe_decrypt_passthrough(self):
        assert crypto.maybe_decrypt(b"plain", None) == b"plain"

    def test_maybe_decrypt_encrypted(self):
        blob = crypto.encrypt_data(b"data", "pw")
        assert crypto.maybe_decrypt(blob, "pw") == b"data"

    def test_maybe_decrypt_encrypted_without_password(self):
        blob = crypto.encrypt_data(b"data", "pw")
        with pytest.raises(crypto.CryptoError):
            crypto.maybe_decrypt(blob, None)

    def test_decrypt_rejects_non_encrypted(self):
        with pytest.raises(crypto.CryptoError):
            crypto.decrypt_data(b"not encrypted", "pw")

    def test_unique_salt_per_encryption(self):
        a = crypto.encrypt_data(b"same", "pw")
        b = crypto.encrypt_data(b"same", "pw")
        assert a != b  # ソルト/IV が異なるため毎回異なる暗号文
