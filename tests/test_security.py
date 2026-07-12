"""
入力検証・パストラバーサル対策のリグレッションテスト（Issue #30）

ブランチ名/タグ名/リモート名/リモート URL に対する検証が正しく機能し、
`.ssm/branches`, `.ssm/tags`, `.ssm/remotes` の外側にファイルを作成・削除
できないことを確認する。
"""

import pytest

from SessionSmith.exceptions import ValidationError
from SessionSmith.remote_backends import validate_remote_url
from SessionSmith.ssm import SSM
from SessionSmith.validation import ensure_within, validate_path_arg, validate_ref_name

# パストラバーサル・不正な参照名として拒否されるべき入力
BAD_REF_NAMES = [
    "..",
    ".",
    "...",
    "a/b",
    "a\\b",
    "../evil",
    "../../evil",
    "",
    "a\x00b",
    "a\nb",
    "/etc/passwd",
    "-leading-hyphen",
]

# 既存機能・ドキュメントで使われている、引き続き有効であるべき通常の名前
GOOD_REF_NAMES = ["main", "v1.0.0", "feature-1", "exp_2", "feature", "experiment", "cloud", "origin"]


class TestValidateRefName:
    """validate_ref_name() 単体のテスト"""

    @pytest.mark.parametrize("name", BAD_REF_NAMES)
    def test_rejects_bad_names(self, name):
        with pytest.raises(ValidationError):
            validate_ref_name(name, "branch_name")

    @pytest.mark.parametrize("name", GOOD_REF_NAMES)
    def test_accepts_good_names(self, name):
        assert validate_ref_name(name, "branch_name") == name

    def test_rejects_too_long_name(self):
        with pytest.raises(ValidationError):
            validate_ref_name("a" * 256, "branch_name")

    def test_accepts_max_length_name(self):
        name = "a" * 255
        assert validate_ref_name(name, "branch_name") == name

    def test_rejects_non_string(self):
        with pytest.raises(ValidationError):
            validate_ref_name(None, "branch_name")  # type: ignore[arg-type]


class TestEnsureWithin:
    """ensure_within() 単体のテスト"""

    def test_raises_on_escape(self, tmp_path):
        base = tmp_path / "branches"
        base.mkdir()
        outside = tmp_path / "evil"
        with pytest.raises(ValidationError):
            ensure_within(base, outside)

    def test_raises_on_traversal(self, tmp_path):
        base = tmp_path / "branches"
        base.mkdir()
        traversal = base / ".." / "evil"
        with pytest.raises(ValidationError):
            ensure_within(base, traversal)

    def test_allows_within(self, tmp_path):
        base = tmp_path / "branches"
        base.mkdir()
        target = base / "main"
        assert ensure_within(base, target) == target


class TestValidatePathArg:
    """validate_path_arg()（export/import 用）単体のテスト"""

    def test_rejects_empty(self):
        with pytest.raises(ValidationError):
            validate_path_arg("", "output_path")

    def test_rejects_control_chars(self):
        with pytest.raises(ValidationError):
            validate_path_arg("a\x00b.pkl", "output_path")

    def test_allows_traversal_in_user_chosen_paths(self, tmp_path):
        # export/import の保存先はユーザーが自由に選ぶため .. 自体は許可する
        target = tmp_path / ".." / "backup.pkl"
        result = validate_path_arg(target, "output_path")
        assert result == target


class TestValidateRemoteUrl:
    """validate_remote_url() 単体のテスト"""

    @pytest.mark.parametrize(
        "url",
        [
            "https://example.com/repo",
            "http://example.com/repo",
            "s3://bucket/prefix",
            "gs://bucket/prefix",
            "file:///tmp/remote",
            "/local/path",
            "./relative/path",
        ],
    )
    def test_accepts_supported_schemes(self, url):
        assert validate_remote_url(url) == url

    @pytest.mark.parametrize(
        "url",
        ["ftp://example.com/repo", "javascript:alert(1)", "ssh://example.com/repo", ""],
    )
    def test_rejects_unsupported_or_empty(self, url):
        with pytest.raises(ValidationError):
            validate_remote_url(url)


def _make_repo(tmp_path):
    ssm = SSM(path=tmp_path)
    ssm.init()
    ssm.globals_dict = {"x": 1}
    commit_hash = ssm.commit("init")
    return ssm, commit_hash


class TestBranchSecurity:
    @pytest.mark.parametrize("name", BAD_REF_NAMES)
    def test_branch_create_rejects_bad_names(self, tmp_path, name):
        ssm, _ = _make_repo(tmp_path)
        with pytest.raises(ValidationError):
            ssm.branch(name, create=True)

    def test_branch_create_and_lookup_accept_normal_names(self, tmp_path):
        ssm, _ = _make_repo(tmp_path)
        for name in ["feature-1", "exp_2", "experiment"]:
            assert ssm.branch(name, create=True) == name
            assert ssm.branch(name) == name

    def test_branch_traversal_cannot_escape_ssm_dir(self, tmp_path):
        ssm, _ = _make_repo(tmp_path)
        outside_marker = tmp_path.parent / "evil-branch-marker"
        assert not outside_marker.exists()

        with pytest.raises(ValidationError):
            ssm.branch("../evil-branch-marker", create=True)

        # トラバーサル名でファイルが作成されていないことを確認
        assert not outside_marker.exists()
        assert not (ssm.ssm_path / ".." / "evil-branch-marker").resolve().exists()

    def test_checkout_branch_rejects_bad_names(self, tmp_path):
        ssm, _ = _make_repo(tmp_path)
        with pytest.raises(ValidationError):
            ssm.checkout_branch("../evil")

    def test_merge_rejects_bad_branch_names(self, tmp_path):
        ssm, _ = _make_repo(tmp_path)
        with pytest.raises(ValidationError):
            ssm.merge("../evil")


class TestTagSecurity:
    @pytest.mark.parametrize("name", BAD_REF_NAMES)
    def test_tag_create_rejects_bad_names(self, tmp_path, name):
        ssm, commit_hash = _make_repo(tmp_path)
        with pytest.raises(ValidationError):
            ssm.tag(name, commit_hash=commit_hash)

    def test_tag_create_accepts_normal_names(self, tmp_path):
        ssm, commit_hash = _make_repo(tmp_path)
        assert ssm.tag("v1.0.0", commit_hash=commit_hash) == "v1.0.0"

    @pytest.mark.parametrize("name", BAD_REF_NAMES)
    def test_checkout_tag_rejects_bad_names(self, tmp_path, name):
        ssm, _ = _make_repo(tmp_path)
        with pytest.raises(ValidationError):
            ssm.checkout_tag(name)

    def test_tag_traversal_cannot_create_file_outside_ssm_dir(self, tmp_path):
        ssm, commit_hash = _make_repo(tmp_path)
        outside_marker = tmp_path / "evil-tag-marker"
        assert not outside_marker.exists()

        with pytest.raises(ValidationError):
            ssm.tag("../evil-tag-marker", commit_hash=commit_hash)

        assert not outside_marker.exists()


class TestRemoteSecurity:
    @pytest.mark.parametrize("name", BAD_REF_NAMES)
    def test_remote_add_rejects_bad_names(self, tmp_path, name):
        ssm, _ = _make_repo(tmp_path)
        with pytest.raises(ValidationError):
            ssm.remote_add(name, "https://example.com/repo")

    def test_remote_add_accepts_normal_name(self, tmp_path):
        ssm, _ = _make_repo(tmp_path)
        ssm.remote_add("origin", "https://example.com/repo")
        assert "origin" in ssm.remote_list()

    @pytest.mark.parametrize(
        "bad_url", ["ftp://example.com/repo", "javascript:alert(1)", "ssh://example.com/repo"]
    )
    def test_remote_add_rejects_unsupported_scheme(self, tmp_path, bad_url):
        ssm, _ = _make_repo(tmp_path)
        with pytest.raises(ValidationError):
            ssm.remote_add("origin", bad_url)

    def test_remote_traversal_cannot_escape_ssm_dir(self, tmp_path):
        ssm, _ = _make_repo(tmp_path)
        outside_marker = tmp_path / "evil-remote-marker"
        assert not outside_marker.exists()

        with pytest.raises(ValidationError):
            ssm.remote_add("../evil-remote-marker", "https://example.com/repo")

        assert not outside_marker.exists()

    def test_push_pull_reject_bad_names(self, tmp_path):
        ssm, _ = _make_repo(tmp_path)
        ssm.remote_add("origin", f"file://{tmp_path / 'remote'}")

        with pytest.raises(ValidationError):
            ssm.push(remote_name="../evil")

        with pytest.raises(ValidationError):
            ssm.push(remote_name="origin", branch_name="../evil")

        with pytest.raises(ValidationError):
            ssm.pull(remote_name="../evil")
