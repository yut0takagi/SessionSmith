"""
remote_backends.py のテストと、SSM の push/pull 統合テスト
"""

import pytest

from SessionSmith import crypto
from SessionSmith.remote_backends import (
    FileSystemBackend,
    HTTPBackend,
    RemoteBackendError,
    get_backend,
    is_url_remote,
)
from SessionSmith.ssm import SSM

requires_crypto = pytest.mark.skipif(
    not crypto.HAS_CRYPTOGRAPHY,
    reason="cryptography package is not available",
)


class TestFileSystemBackend:
    def test_write_read_exists(self, tmp_path):
        backend = FileSystemBackend(tmp_path / "remote")
        assert not backend.exists("a/b.txt")
        backend.write_bytes("a/b.txt", b"hello")
        assert backend.exists("a/b.txt")
        assert backend.read_bytes("a/b.txt") == b"hello"

    def test_text_helpers(self, tmp_path):
        backend = FileSystemBackend(tmp_path / "remote")
        backend.write_text("ref", "commit123")
        assert backend.read_text("ref") == "commit123"

    def test_list_files(self, tmp_path):
        backend = FileSystemBackend(tmp_path / "remote")
        backend.write_bytes("objects/aa/x", b"1")
        backend.write_bytes("commits/c.json", b"2")
        files = set(backend.list_files())
        assert "objects/aa/x" in files
        assert "commits/c.json" in files

    def test_list_files_with_prefix(self, tmp_path):
        backend = FileSystemBackend(tmp_path / "remote")
        backend.write_bytes("objects/aa/x", b"1")
        backend.write_bytes("commits/c.json", b"2")
        files = backend.list_files("objects")
        assert files == ["objects/aa/x"]


class TestGetBackend:
    def test_local_path(self, tmp_path):
        backend = get_backend(str(tmp_path))
        assert isinstance(backend, FileSystemBackend)

    def test_file_url(self, tmp_path):
        backend = get_backend(f"file://{tmp_path}")
        assert isinstance(backend, FileSystemBackend)

    def test_http_url(self):
        backend = get_backend("https://example.com/repo")
        assert isinstance(backend, HTTPBackend)
        assert not backend.writable

    def test_unsupported_scheme(self):
        with pytest.raises(RemoteBackendError):
            get_backend("ftp://example.com/repo")


class TestIsUrlRemote:
    @pytest.mark.parametrize(
        "url,expected",
        [
            ("s3://bucket/p", True),
            ("gs://bucket/p", True),
            ("http://x/y", True),
            ("https://x/y", True),
            ("/local/path", False),
            ("./rel/path", False),
            ("file:///abs", False),
        ],
    )
    def test_detection(self, url, expected):
        assert is_url_remote(url) is expected


class TestHTTPBackendReadOnly:
    def test_write_raises(self):
        backend = HTTPBackend("https://example.com/repo")
        with pytest.raises(RemoteBackendError):
            backend.write_bytes("x", b"1")


class TestPushPullIntegration:
    """SSM の push/pull を URL リモート（file://）経由で検証"""

    def _make_repo(self, path, variables, message="init"):
        ssm = SSM(path=path)
        ssm.init()
        ssm.globals_dict = dict(variables)
        ssm.commit(message)
        return ssm

    def test_push_pull_roundtrip(self, tmp_path):
        remote = tmp_path / "remote"
        local = self._make_repo(tmp_path / "local", {"x": [1, 2, 3], "y": {"a": 1}})
        local.remote_add("cloud", f"file://{remote}")
        local.push("cloud", "main")

        clone = SSM(path=tmp_path / "clone")
        clone.init()
        clone.remote_add("cloud", f"file://{remote}")
        clone.globals_dict = {}
        clone.pull("cloud", "main")

        assert clone.globals_dict["x"] == [1, 2, 3]
        assert clone.globals_dict["y"] == {"a": 1}

    def test_pull_unknown_branch(self, tmp_path):
        from SessionSmith.exceptions import SSMBranchNotFoundError

        remote = tmp_path / "remote"
        local = self._make_repo(tmp_path / "local", {"x": 1})
        local.remote_add("cloud", f"file://{remote}")
        local.push("cloud", "main")

        clone = SSM(path=tmp_path / "clone")
        clone.init()
        clone.remote_add("cloud", f"file://{remote}")
        with pytest.raises(SSMBranchNotFoundError):
            clone.pull("cloud", "does-not-exist")

    def test_manifest_written(self, tmp_path):
        import json

        remote = tmp_path / "remote"
        local = self._make_repo(tmp_path / "local", {"x": 1})
        local.remote_add("cloud", f"file://{remote}")
        local.push("cloud", "main")

        manifest_path = remote / ".ssm" / "manifest.json"
        assert manifest_path.exists()
        manifest = json.loads(manifest_path.read_text())
        assert manifest["branch"] == "main"
        assert manifest["encrypted"] is False

    @requires_crypto
    def test_encrypted_push_pull(self, tmp_path):
        remote = tmp_path / "remote"
        local = self._make_repo(tmp_path / "local", {"secret": [9, 9, 9]})
        local.remote_add("cloud", f"file://{remote}")
        local.push("cloud", "main", password="my-pass")

        # オブジェクトが暗号化されていることを確認
        objects_dir = remote / ".ssm" / "objects"
        obj_files = [p for p in objects_dir.rglob("*") if p.is_file()]
        assert obj_files
        assert crypto.is_encrypted(obj_files[0].read_bytes())

        clone = SSM(path=tmp_path / "clone")
        clone.init()
        clone.remote_add("cloud", f"file://{remote}")
        clone.globals_dict = {}
        clone.pull("cloud", "main", password="my-pass")
        assert clone.globals_dict["secret"] == [9, 9, 9]
