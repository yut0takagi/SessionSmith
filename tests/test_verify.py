"""
コミットの整合性・署名検証（ssm.verify）のテスト
"""

import gzip

import pytest

from SessionSmith.ssm import SSM


class TestVerify:
    def _repo(self, path, variables, sign_key=None):
        ssm = SSM(path=path)
        ssm.init()
        if sign_key:
            ssm.config("sign_key", sign_key)
        ssm.globals_dict = dict(variables)
        commit = ssm.commit("snapshot")
        return ssm, commit

    def test_unsigned_commit_integrity_ok(self, tmp_path):
        ssm, commit = self._repo(tmp_path, {"x": [1, 2, 3]})
        result = ssm.verify(commit)
        assert result["integrity_ok"] is True
        assert result["signed"] is False
        assert result["signature_ok"] is None
        assert result["issues"] == []

    def test_signed_commit_verifies(self, tmp_path):
        ssm, commit = self._repo(tmp_path, {"x": 42}, sign_key="topsecret")
        result = ssm.verify(commit)
        assert result["signed"] is True
        assert result["signature_ok"] is True
        assert result["integrity_ok"] is True

    def test_tampered_object_detected(self, tmp_path):
        ssm, commit = self._repo(tmp_path, {"x": [1, 2, 3]}, sign_key="k")
        # オブジェクトを破壊
        objects_dir = tmp_path / ".ssm" / "objects"
        for obj in objects_dir.rglob("*"):
            if obj.is_file():
                with gzip.open(obj, "wb") as f:
                    f.write(b"tampered")
        result = ssm.verify(commit)
        assert result["integrity_ok"] is False
        assert any("hash mismatch" in i for i in result["issues"])

    def test_wrong_key_signature_fails(self, tmp_path, monkeypatch):
        ssm, commit = self._repo(tmp_path, {"x": 1}, sign_key="right")
        # 環境変数で別の鍵を強制
        monkeypatch.setenv("SESSIONSMITH_SIGN_KEY", "wrong")
        result = ssm.verify(commit)
        assert result["signature_ok"] is False

    def test_verify_head_default(self, tmp_path):
        ssm, commit = self._repo(tmp_path, {"x": 1})
        result = ssm.verify()  # commit_hash=None → HEAD
        assert result["commit"] == commit

    def test_verify_unknown_commit(self, tmp_path):
        from SessionSmith.exceptions import SSMCommitNotFoundError

        ssm, _ = self._repo(tmp_path, {"x": 1})
        with pytest.raises(SSMCommitNotFoundError):
            ssm.verify("deadbeef")
