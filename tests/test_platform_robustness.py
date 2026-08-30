"""プラットフォーム依存の堅牢性に関するテスト（issue #53, #54）

- `init(force=True)` の `.ssm` 破棄が、削除失敗時に原因の分かるエラーになること
- Windows の `MAX_PATH` 制限に掛かるパスが、原因の分かるエラーになること
"""

import os
from pathlib import Path

import pytest

from SessionSmith.exceptions import SSMConfigError, ValidationError
from SessionSmith.ssm import SSM
from SessionSmith.validation import WINDOWS_MAX_PATH, check_path_length


class TestInitForceRemoval:
    def test_force_recreates_the_repository(self, tmp_path):
        ssm = SSM(path=tmp_path, globals_dict={"x": 1})
        ssm.init()
        ssm.commit("c1")
        assert list((tmp_path / ".ssm" / "commits").glob("*.json"))

        ssm.init(force=True)

        assert (tmp_path / ".ssm").exists()
        assert not list((tmp_path / ".ssm" / "commits").glob("*.json"))

    def test_removal_failure_reports_the_real_cause(self, tmp_path, monkeypatch):
        """削除に失敗したら、削除失敗として報告されること

        修正前は rmtree が途中で失敗しても素通りし、直後の mkdir() が
        FileExistsError（「既に存在します」）になっていた。本当の原因
        （削除に失敗した）が利用者に伝わらない。
        """
        ssm = SSM(path=tmp_path, globals_dict={"x": 1})
        ssm.init()

        def _always_busy(_path):
            raise OSError(32, "The process cannot access the file")

        monkeypatch.setattr("SessionSmith.ssm.shutil.rmtree", _always_busy)

        with pytest.raises(SSMConfigError) as excinfo:
            ssm.init(force=True)

        message = str(excinfo.value)
        assert ".ssm" in message
        # FileExistsError に化けていないこと
        assert "exist" not in message.lower() or "remove" in message.lower()

    def test_removal_is_retried(self, tmp_path, monkeypatch):
        """一時的な失敗はリトライで回復すること"""
        ssm = SSM(path=tmp_path, globals_dict={"x": 1})
        ssm.init()

        real_rmtree = __import__("shutil").rmtree
        calls = {"n": 0}

        def _busy_once(path):
            calls["n"] += 1
            if calls["n"] == 1:
                raise OSError(32, "The process cannot access the file")
            real_rmtree(path)

        monkeypatch.setattr("SessionSmith.ssm.shutil.rmtree", _busy_once)

        ssm.init(force=True)

        assert calls["n"] == 2
        assert (tmp_path / ".ssm").exists()

    def test_removal_takes_the_repository_lock(self, tmp_path, monkeypatch):
        """破棄はリポジトリロックの内側で行われること

        他プロセスが commit() の途中でも構わず消してしまうのを防ぐ。
        """
        ssm = SSM(path=tmp_path, globals_dict={"x": 1})
        ssm.init()

        locked_during_removal = []
        real_remove = SSM._remove_repo_tree

        def _spy(path, *args, **kwargs):
            locked_during_removal.append((path / ".lock").exists())
            return real_remove(path, *args, **kwargs)

        monkeypatch.setattr(SSM, "_remove_repo_tree", staticmethod(_spy))

        ssm.init(force=True)

        assert locked_during_removal == [True], "削除時にロックが保持されていない"


class TestPathLengthValidation:
    """Windows の MAX_PATH 制限（issue #54）"""

    def test_short_path_passes(self):
        assert check_path_length("short.txt", enforce=True) == Path("short.txt")

    def test_long_path_is_rejected_with_a_clear_message(self, tmp_path):
        long_path = tmp_path / ("a" * 300)

        with pytest.raises(ValidationError) as excinfo:
            check_path_length(long_path, enforce=True)

        message = str(excinfo.value)
        assert "too long" in message
        assert str(WINDOWS_MAX_PATH) in message

    def test_not_enforced_on_posix_by_default(self, tmp_path):
        """Windows 以外では既定で検査しないこと

        プラットフォーム非依存の一律制限にすると、Linux で作れる名前が
        不必要に狭くなるため。
        """
        long_path = tmp_path / ("a" * 300)

        if os.name == "nt":
            pytest.skip("Windows では既定で検査される")

        assert check_path_length(long_path) == long_path

    def test_relative_path_is_resolved_before_measuring(self, tmp_path, monkeypatch):
        """相対パスは絶対パスに直してから測ること"""
        monkeypatch.chdir(tmp_path)

        # 相対表記は短いが、絶対パスにすると長い
        name = "b" * 240
        with pytest.raises(ValidationError):
            check_path_length(name, enforce=True)

    def test_write_path_is_checked_on_windows(self, tmp_path):
        """長い参照名が、書き込み時点で分かりやすいエラーになること"""
        ssm = SSM(path=tmp_path, globals_dict={"x": 1})
        ssm.init()
        ssm.commit("c1")

        long_name = "b" * 250
        if os.name != "nt":
            pytest.skip("MAX_PATH は Windows 固有の制限")

        with pytest.raises(ValidationError, match="too long"):
            ssm.branch(long_name, create=True)
