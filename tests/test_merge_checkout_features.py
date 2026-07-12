"""
``ssm.merge(on_conflict=...)`` と ``ssm.checkout(clean=...)`` の新機能のテスト。

- merge(): 現在のHEADコミットとマージ元コミットを比較し、共通祖先から見て
  「両側で」値が変更されている同名変数をコンフリクトとして検出する。
  検出結果の扱いは ``on_conflict`` で選べる（"ignore" / "warn"（デフォルト）/
  "error"）。マージ結果そのもの（マージ呼び出し時点でライブな
  globals_dict をマージコミットとして記録する、last-writer-wins）は
  ``on_conflict`` の値によらず変わらない。
- checkout(clean=...): デフォルト（False）では従来通り、対象コミットの
  変数で globals_dict を上書き・追加するだけ。``clean=True`` を指定した
  場合のみ、「離れる直前のコミット（呼び出し時点のHEAD）には存在したが、
  対象コミットには存在しない」変数を globals_dict から削除する。
"""

import json
import warnings

import pytest

from SessionSmith.exceptions import SSMMergeConflictError, ValidationError
from SessionSmith.ssm import SSM


def _read_commit(ssm: SSM, commit_hash: str) -> dict:
    """指定コミットの JSON をそのまま読み込むヘルパー"""
    commit_path = ssm.ssm_path / SSM.COMMITS_DIR / f"{commit_hash}.json"
    return json.loads(commit_path.read_text())


def _head(ssm: SSM) -> str:
    return (ssm.ssm_path / SSM.HEAD_FILE).read_text().strip()


def _all_commit_hashes(ssm: SSM) -> set:
    commits_dir = ssm.ssm_path / SSM.COMMITS_DIR
    return {p.stem for p in commits_dir.glob("*.json")}


def _make_diverged_repo(tmp_path):
    """
    base コミットの共通の変数 "shared" を、feature ブランチと main ブランチの
    双方で異なる値に変更した「真の分岐編集」状態を作る。
    （tests/test_ssm_e2e.py の
    test_divergent_edits_on_same_variable_do_not_raise_merge_conflict と
    同じシナリオ）
    """
    g = {"shared": "base"}
    ssm = SSM(path=tmp_path, globals_dict=g)
    ssm.init()
    ssm.commit("base commit")

    ssm.branch("feature", create=True)
    ssm.checkout_branch("feature")
    g["shared"] = "feature-value"
    ssm.commit("feature diverges")

    ssm.checkout_branch("main")
    assert g["shared"] == "base"
    g["shared"] = "main-value"
    ssm.commit("main diverges")

    return ssm, g


class TestMergeConflictDetection:
    """merge(on_conflict=...) のテスト"""

    @pytest.mark.timeout(10)
    def test_default_warn_emits_warning_and_still_creates_merge_commit(self, tmp_path):
        ssm, g = _make_diverged_repo(tmp_path)

        with pytest.warns(UserWarning, match="shared"):
            merge_hash = ssm.merge("feature")

        # マージコミットは作成され、結果は従来通り last-writer-wins
        assert merge_hash
        merge_commit = _read_commit(ssm, merge_hash)
        assert merge_commit["parent"] and merge_commit["merge_parent"]
        merged_var_hash = merge_commit["variables"]["shared"]["hash"]
        import pickle

        assert pickle.loads(ssm._load_object(merged_var_hash)) == "main-value"
        assert g["shared"] == "main-value"
        assert _head(ssm) == merge_hash

    @pytest.mark.timeout(10)
    def test_on_conflict_error_raises_and_creates_no_merge_commit(self, tmp_path):
        ssm, g = _make_diverged_repo(tmp_path)

        head_before = _head(ssm)
        commits_before = _all_commit_hashes(ssm)

        with pytest.raises(SSMMergeConflictError) as exc_info:
            ssm.merge("feature", on_conflict="error")

        # コンフリクトした変数名が例外メッセージに含まれる
        assert "shared" in str(exc_info.value)
        assert "shared" in exc_info.value.conflicts

        # マージコミットは作成されず、HEADも一切変更されない
        assert _head(ssm) == head_before
        assert _all_commit_hashes(ssm) == commits_before

    @pytest.mark.timeout(10)
    def test_on_conflict_ignore_emits_no_warning(self, tmp_path):
        ssm, g = _make_diverged_repo(tmp_path)

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            merge_hash = ssm.merge("feature", on_conflict="ignore")

        assert merge_hash
        merge_warnings = [w for w in caught if "conflict" in str(w.message).lower()]
        assert merge_warnings == []

    @pytest.mark.timeout(10)
    def test_no_conflict_when_branches_touch_different_variables(self, tmp_path):
        """同一変数名を編集していなければ、コンフリクトは検出されない"""
        g = {"a": 1}
        ssm = SSM(path=tmp_path, globals_dict=g)
        ssm.init()
        ssm.commit("base commit")

        ssm.branch("feature", create=True)
        ssm.checkout_branch("feature")
        g["feature_only"] = "from feature"
        ssm.commit("feature adds its own var")

        ssm.checkout_branch("main")
        g["main_only"] = "from main"
        ssm.commit("main adds its own var")

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            merge_hash = ssm.merge("feature")

        assert merge_hash
        merge_warnings = [w for w in caught if "conflict" in str(w.message).lower()]
        assert merge_warnings == []

    @pytest.mark.timeout(10)
    def test_invalid_on_conflict_value_raises_validation_error(self, tmp_path):
        g = {"a": 1}
        ssm = SSM(path=tmp_path, globals_dict=g)
        ssm.init()
        ssm.commit("base commit")
        ssm.branch("feature", create=True)

        with pytest.raises(ValidationError):
            ssm.merge("feature", on_conflict="bogus-mode")


class TestCheckoutClean:
    """checkout(clean=...) のテスト"""

    @pytest.mark.timeout(10)
    def test_clean_true_removes_variable_absent_from_target_commit(self, tmp_path):
        g = {"a": 1}
        ssm = SSM(path=tmp_path, globals_dict=g)
        ssm.init()
        h1 = ssm.commit("only a")

        g["b"] = "added later"
        ssm.commit("added b")

        ssm.checkout(h1, clean=True)

        assert g["a"] == 1
        assert "b" not in g

    @pytest.mark.timeout(10)
    def test_clean_false_default_keeps_variable_absent_from_target_commit(self, tmp_path):
        g = {"a": 1}
        ssm = SSM(path=tmp_path, globals_dict=g)
        ssm.init()
        h1 = ssm.commit("only a")

        g["b"] = "added later"
        ssm.commit("added b")

        # clean を明示しない = 従来通りの挙動
        ssm.checkout(h1)

        assert g["a"] == 1
        assert g["b"] == "added later"

    @pytest.mark.timeout(10)
    def test_clean_true_does_not_remove_never_committed_user_global(self, tmp_path):
        g = {"a": 1}
        ssm = SSM(path=tmp_path, globals_dict=g)
        ssm.init()
        h1 = ssm.commit("only a")

        g["b"] = "added later"
        ssm.commit("added b")

        # 一度もコミットされていない変数（現HEADのコミットにも含まれない）
        g["untracked"] = "never committed"

        ssm.checkout(h1, clean=True)

        assert g["a"] == 1
        assert "b" not in g
        # SSM が追跡していなかった変数は削除対象にならない
        assert g["untracked"] == "never committed"

    @pytest.mark.timeout(10)
    def test_clean_true_via_checkout_branch(self, tmp_path):
        """checkout_branch(clean=True) も checkout() と同じ削除ロジックを適用する"""
        g = {"a": 1}
        ssm = SSM(path=tmp_path, globals_dict=g)
        ssm.init()
        ssm.commit("main: a only")

        ssm.branch("feature", create=True)
        ssm.checkout_branch("feature")
        g["feature_only"] = "extra"
        ssm.commit("feature: a + feature_only")

        ssm.checkout_branch("main", clean=True)

        assert g["a"] == 1
        assert "feature_only" not in g
