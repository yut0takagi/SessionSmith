"""`SessionSmith.utils` のテスト（verify_session / get_file_size / detect_compression）"""

import bz2
import gzip
import pickle

import pytest

from SessionSmith.utils import detect_compression, get_file_size, verify_session


@pytest.fixture
def pickle_session(tmp_path):
    path = tmp_path / "session.pkl"
    with open(path, "wb") as f:
        pickle.dump({"a": 1, "b": [1, 2, 3]}, f)
    return path


class TestVerifySession:
    def test_valid_pickle_session(self, pickle_session):
        assert verify_session(pickle_session) == (True, None)

    def test_accepts_str_path(self, pickle_session):
        is_valid, error = verify_session(str(pickle_session))
        assert is_valid and error is None

    def test_missing_file(self, tmp_path):
        is_valid, error = verify_session(tmp_path / "nope.pkl")
        assert not is_valid
        assert "not found" in error.lower()

    def test_directory_is_not_a_file(self, tmp_path):
        is_valid, error = verify_session(tmp_path)
        assert not is_valid
        assert "not a file" in error.lower()

    def test_corrupted_file(self, tmp_path):
        path = tmp_path / "broken.pkl"
        path.write_bytes(b"this is not a pickle")

        is_valid, error = verify_session(path)
        assert not is_valid
        assert "failed to load" in error.lower()

    def test_session_that_is_not_a_dict(self, tmp_path):
        path = tmp_path / "list.pkl"
        with open(path, "wb") as f:
            pickle.dump([1, 2, 3], f)

        is_valid, error = verify_session(path)
        assert not is_valid
        assert "not a dictionary" in error.lower()

    def test_metadata_must_be_a_dict(self, tmp_path):
        path = tmp_path / "bad_meta.pkl"
        with open(path, "wb") as f:
            pickle.dump({"a": 1, "__metadata__": "not a dict"}, f)

        is_valid, error = verify_session(path)
        assert not is_valid
        assert "metadata" in error.lower()

    def test_valid_metadata_is_accepted(self, tmp_path):
        path = tmp_path / "meta.pkl"
        with open(path, "wb") as f:
            pickle.dump({"a": 1, "__metadata__": {"saved_at": "2026-01-01"}}, f)

        assert verify_session(path) == (True, None)

    def test_gzip_compressed_session(self, tmp_path):
        path = tmp_path / "session.pkl.gz"
        with gzip.open(path, "wb") as f:
            pickle.dump({"a": 1}, f)

        assert verify_session(path) == (True, None)


class TestGetFileSize:
    def test_returns_size_in_bytes(self, tmp_path):
        path = tmp_path / "data.bin"
        path.write_bytes(b"0123456789")

        assert get_file_size(path) == 10

    def test_empty_file(self, tmp_path):
        path = tmp_path / "empty.bin"
        path.write_bytes(b"")

        assert get_file_size(path) == 0

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="File not found"):
            get_file_size(tmp_path / "nope.bin")


class TestDetectCompression:
    def test_gzip(self, tmp_path):
        path = tmp_path / "a.gz"
        with gzip.open(path, "wb") as f:
            f.write(b"hello")

        assert detect_compression(path) == "gzip"

    def test_bz2(self, tmp_path):
        path = tmp_path / "a.bz2"
        with bz2.open(path, "wb") as f:
            f.write(b"hello")

        assert detect_compression(path) == "bz2"

    def test_uncompressed(self, tmp_path):
        path = tmp_path / "a.bin"
        path.write_bytes(b"plain content")

        assert detect_compression(path) is None

    def test_file_shorter_than_the_magic_number(self, tmp_path):
        """2バイト未満のファイルはマジックナンバーを判定できない"""
        path = tmp_path / "tiny.bin"
        path.write_bytes(b"\x1f")

        assert detect_compression(path) is None

    def test_empty_file(self, tmp_path):
        path = tmp_path / "empty.bin"
        path.write_bytes(b"")

        assert detect_compression(path) is None

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="File not found"):
            detect_compression(tmp_path / "nope.bin")
