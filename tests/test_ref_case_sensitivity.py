"""参照名（ブランチ/タグ/リモート）の大文字小文字の扱いに関するテスト（issue #51）

参照は `.ssm/branches/<name>` のように1名前1ファイルで保持しているが、
macOS（APFS の既定）と Windows のファイルシステムは大文字小文字を区別しない。
`Path.exists()` に存在確認を任せると、`feature` しか無いのに `FEATURE` が
「存在する」と判定され、リポジトリの状態が不整合になる。

これらのテストは、大文字小文字を区別するFS（Linux）でも区別しないFS
（macOS / Windows）でも同じ結果になることを保証する。
"""

import pytest

from SessionSmith.exceptions import (
    SSMBranchNotFoundError,
    SSMConfigError,
    SSMTagNotFoundError,
    ValidationError,
)
from SessionSmith.ssm import SSM


@pytest.fixture
def repo(tmp_path):
    ssm = SSM(path=tmp_path, globals_dict={"x": 1})
    ssm.init()
    ssm.commit("c1")
    return ssm


class TestBranchCaseSensitivity:
    def test_checkout_wrong_case_branch_is_rejected(self, repo):
        """大文字小文字が違うブランチ名は解決されないこと

        修正前は macOS / Windows で成功し、`current_branch` に実在しない
        名前が入ってリポジトリが壊れていた。
        """
        repo.branch("feature", create=True)

        with pytest.raises(SSMBranchNotFoundError):
            repo.checkout_branch("FEATURE")

        # 状態が汚れていないこと
        assert repo.get_current_branch() != "FEATURE"

    def test_creating_case_conflicting_branch_is_rejected(self, repo):
        """大文字小文字だけ違うブランチは作成できないこと

        大文字小文字を区別しないFSでは同じファイルになり既存のブランチを
        壊すため、区別するFSでも一貫して拒否する。
        """
        repo.branch("feature", create=True)

        with pytest.raises(SSMConfigError, match="differs only in case"):
            repo.branch("Feature", create=True)

        assert sorted(repo.branch()) == ["feature", "main"]

    def test_exact_case_still_works(self, repo):
        repo.branch("feature", create=True)
        repo.checkout_branch("feature")
        assert repo.get_current_branch() == "feature"

    def test_merge_with_wrong_case_is_rejected(self, repo):
        repo.branch("feature", create=True)

        with pytest.raises(SSMBranchNotFoundError):
            repo.merge("FEATURE")

    def test_current_branch_is_always_listed(self, repo):
        """current_branch は必ず branch() の一覧に含まれること"""
        repo.branch("feature", create=True)
        repo.checkout_branch("feature")

        assert repo.get_current_branch() in repo.branch()


class TestTagCaseSensitivity:
    def test_checkout_wrong_case_tag_is_rejected(self, repo):
        repo.tag("v1", message="one")

        with pytest.raises(SSMTagNotFoundError):
            repo.checkout_tag("V1")

    def test_creating_case_conflicting_tag_is_rejected(self, repo):
        repo.tag("v1", message="one")

        with pytest.raises(SSMConfigError, match="differs only in case"):
            repo.tag("V1", message="two")

        assert [t["name"] for t in repo.list_tags()] == ["v1"]


class TestRemoteCaseSensitivity:
    def test_creating_case_conflicting_remote_is_rejected(self, repo, tmp_path):
        repo.remote_add("origin", str(tmp_path / "remote"))

        with pytest.raises(SSMConfigError, match="differs only in case"):
            repo.remote_add("Origin", str(tmp_path / "remote2"))

    def test_push_with_wrong_case_remote_is_rejected(self, repo, tmp_path):
        from SessionSmith.exceptions import SSMRemoteNotFoundError

        repo.remote_add("origin", f"file://{tmp_path / 'remote'}")

        with pytest.raises(SSMRemoteNotFoundError):
            repo.push("ORIGIN", "main")


class TestPushDoesNotForkBranch:
    def test_push_uses_the_real_branch_name(self, repo, tmp_path):
        """存在しない大文字名で push してブランチが割れないこと

        修正前は checkout_branch('FEATURE') が通ってしまい、その状態で
        push するとリモートに 'FEATURE' が作られ、ローカルの 'feature' と
        合わせてブランチが2本に割れていた。
        """
        remote = tmp_path / "remote"
        repo.branch("feature", create=True)
        repo.remote_add("r", f"file://{remote}")

        with pytest.raises(SSMBranchNotFoundError):
            repo.checkout_branch("FEATURE")

        repo.checkout_branch("feature")
        repo.push("r", "feature")

        remote_branches = sorted(p.name for p in (remote / ".ssm" / "branches").iterdir())
        assert remote_branches == ["feature"]


class TestWindowsUnsafeRefNames:
    """Windows のファイル名規則で壊れる参照名を拒否すること"""

    @pytest.mark.parametrize(
        "name", ["NUL", "nul", "CON", "prn", "AUX", "COM1", "LPT9", "NUL.txt"]
    )
    def test_reserved_device_names_are_rejected(self, repo, name):
        """予約デバイス名はディレクトリ配下でもデバイスとして解決される"""
        with pytest.raises(ValidationError, match="reserved device name"):
            repo.branch(name, create=True)

    @pytest.mark.parametrize("name", ["v2.", "release."])
    def test_trailing_dot_is_rejected(self, repo, name):
        """Windows は末尾のドットを削除するため 'v2.' と 'v2' が衝突する"""
        with pytest.raises(ValidationError, match="must not end with"):
            repo.branch(name, create=True)

    @pytest.mark.parametrize("name", ["feature", "v1.0.0", "exp_2", "a.b-c"])
    def test_valid_names_still_accepted(self, repo, name):
        assert repo.branch(name, create=True) == name
