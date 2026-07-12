"""
ssm.py の E2E ワークフローおよびブランチ / マージ / タグ / リモートの異常系テスト

(Issue #28) init → commit → branch → checkout_branch → merge → tag → checkout の
一連の流れが正しい履歴構造を作り、checkout が実際の変数値を復元することを検証する。
また、ブランチ・タグ・リモートが存在しない場合や、短縮ハッシュが曖昧・未知の場合の
エラーハンドリングを検証する。

これらのテストは実装の「実際の」挙動をアサートする（希望的な仕様ではない）。
特に以下は実装を読んだ上での確認事項:

- ``merge()`` は 2 つのブランチの変数を値レベルでマージしない。単に「現在ライブな
  globals_dict の中身」をマージコミットとして記録し、parent / merge_parent の 2 つの
  親を持たせるだけ。``SSMMergeConflictError``（exceptions.py に定義済み）は
  ``ssm.py`` のどこからも送出されない（`grep -n SSMMergeConflictError ssm.py` で確認済み）。
  そのため、同一変数名を両ブランチで異なる値に編集しても例外は発生しない。
- ``checkout()`` / ``checkout_branch()`` / ``checkout_tag()`` は対象コミットに含まれる
  変数を globals_dict に上書きするだけで、対象コミットに存在しないキーを削除はしない。
  そのため、後から追加した変数はブランチを切り替えても居残る。
"""

import importlib.util
import json

import pytest

from SessionSmith.exceptions import (
    SSMBranchNotFoundError,
    SSMCommitNotFoundError,
    SSMConfigError,
    SSMRemoteNotFoundError,
    SSMTagNotFoundError,
)
from SessionSmith.remote_backends import RemoteBackendError
from SessionSmith.ssm import SSM

def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        # 親パッケージ自体が存在しない場合、find_spec は ModuleNotFoundError を送出しうる
        return False


_HAS_BOTO3 = _module_available("boto3")
_HAS_GCS = _module_available("google.cloud.storage")


def _read_commit(ssm: SSM, commit_hash: str) -> dict:
    """指定コミットの JSON をそのまま読み込むヘルパー"""
    commit_path = ssm.ssm_path / SSM.COMMITS_DIR / f"{commit_hash}.json"
    return json.loads(commit_path.read_text())


class TestE2EBranchMergeTagWorkflow:
    """init → commit → branch → checkout_branch → merge → tag → checkout の E2E テスト"""

    @pytest.mark.timeout(15)
    def test_full_workflow_history_structure_and_checkout_restores_values(self, tmp_path):
        """
        分岐した履歴を作り、コミットの親子関係（履歴構造）と、
        checkout / checkout_branch / checkout_tag が実際の変数値を復元することを検証する。
        """
        g = {"x": 1, "label": "start"}
        ssm = SSM(path=tmp_path, globals_dict=g)
        ssm.init()

        # 1) 最初のコミット（main ブランチが暗黙に作られる）
        h_main0 = ssm.commit("initial commit")
        assert ssm.get_current_branch() == "main"
        assert ssm.branch() == ["main"]

        # 2) feature ブランチを作成して切り替え
        assert ssm.branch("feature", create=True) == "feature"
        assert ssm.branch() == ["feature", "main"]

        ssm.checkout_branch("feature")
        assert ssm.get_current_branch() == "feature"
        # feature はまだ main0 の内容そのまま
        assert g["x"] == 1

        # 3) feature ブランチでコミット
        g["x"] = 100
        g["feature_only"] = [1, 2, 3]
        h_feature = ssm.commit("feature commit")
        feature_commit = _read_commit(ssm, h_feature)
        assert feature_commit["parent"] == h_main0

        # 4) main に戻ってさらにコミット（main と feature が分岐）
        ssm.checkout_branch("main")
        assert ssm.get_current_branch() == "main"
        # main の h_main0 が持っていた x=1 に復元されている
        assert g["x"] == 1

        g["x"] = 2
        g["main_only"] = {"nested": True}
        h_main1 = ssm.commit("second main commit")
        main1_commit = _read_commit(ssm, h_main1)
        assert main1_commit["parent"] == h_main0

        # 5) feature を main にマージ
        merge_hash = ssm.merge("feature")
        merge_commit = _read_commit(ssm, merge_hash)
        # マージコミットは main1 と feature の両方を親として記録する（履歴構造）
        assert merge_commit["parent"] == h_main1
        assert merge_commit["merge_parent"] == h_feature
        # マージ後、main ブランチの参照がマージコミットを指す
        branch_file = tmp_path / ".ssm" / "branches" / "main"
        assert branch_file.read_text().strip() == merge_hash

        # 6) マージコミットにタグを付ける
        ssm.tag("v1.0", message="first release")
        tags = ssm.list_tags()
        assert len(tags) == 1
        assert tags[0]["name"] == "v1.0"
        assert tags[0]["commit"] == merge_hash

        # 7) 別の値に変更してからタグへ checkout（実際の値が復元されることを確認）
        g["x"] = 999
        ssm.checkout_tag("v1.0")
        # マージコミット時点で記録された x の値（=main の生きた値だった 2）に戻る
        assert g["x"] == 2

        # 8) 過去のコミット（h_main0）に checkout し、実際の値が復元されることを確認
        ssm.checkout(h_main0)
        assert g["x"] == 1
        assert g["label"] == "start"

    @pytest.mark.timeout(15)
    def test_checkout_restores_actual_container_values_across_branchy_history(self, tmp_path):
        """
        checkout がコンテナ型（list/dict/tuple/set）を含む変数について
        「エラーが出ないこと」だけでなく実際の値・型を正しく復元することを検証する。
        """
        g = {
            "n": 1,
            "items": [1, 2, 3],
            "meta": {"a": 1, "b": [4, 5]},
            "pair": (10, 20),
            "tags": {"x", "y"},
        }
        ssm = SSM(path=tmp_path, globals_dict=g)
        ssm.init()
        h1 = ssm.commit("v1")

        # 分岐用ブランチを作り、値を大きく変える
        ssm.branch("dev", create=True)
        ssm.checkout_branch("dev")
        g["n"] = 2
        g["items"] = [9, 9, 9]
        g["meta"] = {"a": 2, "b": [7]}
        g["pair"] = (30, 40)
        g["tags"] = {"z"}
        ssm.commit("v2 on dev")

        # h1 に戻す
        ssm.checkout(h1)

        assert g["n"] == 1
        assert g["items"] == [1, 2, 3] and isinstance(g["items"], list)
        assert g["meta"] == {"a": 1, "b": [4, 5]} and isinstance(g["meta"], dict)
        assert g["pair"] == (10, 20) and isinstance(g["pair"], tuple)
        assert g["tags"] == {"x", "y"} and isinstance(g["tags"], set)

    @pytest.mark.timeout(10)
    def test_checkout_does_not_remove_variables_added_after_target_commit(self, tmp_path):
        """
        実装上、checkout() はコミットに記録された変数を上書きするだけで、
        「そのコミット時点に存在しなかった変数」を globals から削除しない。
        これは checkout() 実装（ssm.py 内の該当メソッド）を読んで確認した実際の挙動であり、
        本テストはその実挙動を明示的に記録するもの。
        """
        g = {"a": 1}
        ssm = SSM(path=tmp_path, globals_dict=g)
        ssm.init()
        h1 = ssm.commit("only a")

        g["b"] = "added later"
        ssm.commit("added b")

        ssm.checkout(h1)

        # a は h1 の値に復元される
        assert g["a"] == 1
        # だが b は削除されず居残る（実装の実際の挙動）
        assert g["b"] == "added later"


class TestBranchTagEdgeCases:
    """ブランチ・タグの異常系テスト"""

    @pytest.mark.timeout(10)
    def test_checkout_branch_nonexistent_raises(self, tmp_path):
        ssm = SSM(path=tmp_path, globals_dict={"a": 1})
        ssm.init()
        ssm.commit("init")

        with pytest.raises(SSMBranchNotFoundError) as exc_info:
            ssm.checkout_branch("does-not-exist")
        assert exc_info.value.branch_name == "does-not-exist"

    @pytest.mark.timeout(10)
    def test_merge_nonexistent_branch_raises(self, tmp_path):
        ssm = SSM(path=tmp_path, globals_dict={"a": 1})
        ssm.init()
        ssm.commit("init")

        with pytest.raises(SSMBranchNotFoundError) as exc_info:
            ssm.merge("does-not-exist")
        assert exc_info.value.branch_name == "does-not-exist"

    @pytest.mark.timeout(10)
    def test_checkout_tag_nonexistent_raises(self, tmp_path):
        ssm = SSM(path=tmp_path, globals_dict={"a": 1})
        ssm.init()
        ssm.commit("init")

        with pytest.raises(SSMTagNotFoundError) as exc_info:
            ssm.checkout_tag("does-not-exist")
        assert exc_info.value.tag_name == "does-not-exist"

    @pytest.mark.timeout(10)
    def test_tag_overwrite_raises_config_error(self, tmp_path):
        """
        既に存在するタグ名で再度 tag() を呼ぶと、実装は上書きせず
        SSMConfigError（"already exists"）を送出する。git のタグ -f のような
        上書きオプションは存在しない。
        """
        ssm = SSM(path=tmp_path, globals_dict={"a": 1})
        ssm.init()
        ssm.commit("init")
        ssm.tag("v1.0")

        with pytest.raises(SSMConfigError) as exc_info:
            ssm.tag("v1.0")
        assert "v1.0" in str(exc_info.value)

        # 上書きされていないこと（タグは1つのまま、元のコミットを指す）
        tags = ssm.list_tags()
        assert len(tags) == 1

    @pytest.mark.timeout(10)
    def test_branch_create_duplicate_raises_config_error(self, tmp_path):
        """ブランチ名の重複作成も同様に SSMConfigError を送出する（実際の挙動）"""
        ssm = SSM(path=tmp_path, globals_dict={"a": 1})
        ssm.init()
        ssm.commit("init")
        ssm.branch("feature", create=True)

        with pytest.raises(SSMConfigError):
            ssm.branch("feature", create=True)


class TestMergeConflictBehavior:
    """
    マージコンフリクトに関するテスト。

    ``SSMMergeConflictError`` は exceptions.py に定義されているが、``ssm.py`` の
    ``merge()`` 実装はどこからもこの例外を送出しない（コード全体を grep して確認）。
    ``merge()`` は 2 ブランチの内容を値レベルで比較・マージするのではなく、
    マージを呼び出した時点で「ライブな」globals_dict の中身をそのままマージコミットの
    内容として記録するだけである。そのため、同一変数名を両ブランチで異なる値に
    編集しても例外は発生せず、マージ時点で globals_dict に入っている値がそのまま
    採用される（"ours" 戦略的な振る舞いだが、コンフリクト検出自体が行われない）。

    これは実装のギャップと考えられるが、Issue #28 の指示に従い、実装を変更せず
    「実際の挙動」をここに記録する。
    """

    @pytest.mark.timeout(10)
    def test_divergent_edits_on_same_variable_do_not_raise_merge_conflict(self, tmp_path):
        g = {"shared": "base"}
        ssm = SSM(path=tmp_path, globals_dict=g)
        ssm.init()
        ssm.commit("base commit")

        ssm.branch("feature", create=True)
        ssm.checkout_branch("feature")
        g["shared"] = "feature-value"
        ssm.commit("feature diverges")

        ssm.checkout_branch("main")
        # main のコミット時点の値に復元されている（"base"）ことを確認してから
        # main 側でも同じ変数を別の値に変更 = 真の分岐編集
        assert g["shared"] == "base"
        g["shared"] = "main-value"
        ssm.commit("main diverges")

        # 実際の挙動: 例外は発生しない
        merge_hash = ssm.merge("feature")
        assert merge_hash

        merge_commit = _read_commit(ssm, merge_hash)
        # マージコミットに記録される値は、マージ呼び出し時点でライブだった main 側の値
        merged_var_hash = merge_commit["variables"]["shared"]["hash"]
        obj_data = ssm._load_object(merged_var_hash)
        import pickle

        assert pickle.loads(obj_data) == "main-value"
        # globals_dict 自体もマージ呼び出しで書き換えられない
        assert g["shared"] == "main-value"


class TestShortHashResolution:
    """短縮ハッシュによる checkout の解決テスト"""

    @pytest.mark.timeout(10)
    def test_valid_short_prefix_checks_out_correct_commit_in_branchy_history(self, tmp_path):
        g = {"v": 1}
        ssm = SSM(path=tmp_path, globals_dict=g)
        ssm.init()
        h1 = ssm.commit("c1")

        ssm.branch("other", create=True)
        ssm.checkout_branch("other")
        g["v"] = 2
        ssm.commit("c2 on other branch")

        short = h1[:8]
        ssm.checkout(short)
        assert g["v"] == 1

    @pytest.mark.timeout(10)
    def test_unknown_hash_raises_commit_not_found(self, tmp_path):
        ssm = SSM(path=tmp_path, globals_dict={"a": 1})
        ssm.init()
        ssm.commit("init")

        with pytest.raises(SSMCommitNotFoundError) as exc_info:
            ssm.checkout("deadbeefdeadbeef")
        assert exc_info.value.commit_hash == "deadbeefdeadbeef"

    @pytest.mark.timeout(10)
    def test_ambiguous_short_hash_raises_commit_not_found(self, tmp_path):
        """
        実際に短縮ハッシュが衝突するケースを確率に頼らず決定論的に再現するため、
        commits ディレクトリに共通プレフィックスを持つダミーのコミット JSON を
        2つ直接書き込み、_resolve_hash() の曖昧一致（ValueError）が checkout() で
        SSMCommitNotFoundError に変換されることを確認する。
        """
        ssm = SSM(path=tmp_path, globals_dict={"a": 1})
        ssm.init()
        ssm.commit("init")

        commits_dir = ssm.ssm_path / SSM.COMMITS_DIR
        fake_commit = {
            "message": "fake",
            "author": "tester",
            "timestamp": "2024-01-01T00:00:00",
            "parent": None,
            "variables": {},
        }
        (commits_dir / "ffaaaaaaaaaaaaa1.json").write_text(json.dumps(fake_commit))
        (commits_dir / "ffaaaaaaaaaaaaa2.json").write_text(json.dumps(fake_commit))

        with pytest.raises(SSMCommitNotFoundError):
            ssm.checkout("ffaaaaaaaaaaaaa")


class TestRemoteEdgeCases:
    """リモート（push/pull）の異常系テスト"""

    def _init_with_commit(self, tmp_path, variables=None):
        ssm = SSM(path=tmp_path, globals_dict=dict(variables or {"a": 1}))
        ssm.init()
        ssm.commit("init")
        return ssm

    @pytest.mark.timeout(10)
    def test_push_to_nonexistent_remote_raises(self, tmp_path):
        ssm = self._init_with_commit(tmp_path)
        with pytest.raises(SSMRemoteNotFoundError) as exc_info:
            ssm.push("nosuchremote")
        assert exc_info.value.remote_name == "nosuchremote"

    @pytest.mark.timeout(10)
    def test_pull_from_nonexistent_remote_raises(self, tmp_path):
        ssm = self._init_with_commit(tmp_path)
        with pytest.raises(SSMRemoteNotFoundError) as exc_info:
            ssm.pull("nosuchremote")
        assert exc_info.value.remote_name == "nosuchremote"

    @pytest.mark.timeout(10)
    def test_pull_from_directory_without_ssm_raises_config_error(self, tmp_path):
        """リモート先が .ssm を持たない（未初期化・破損扱いの）ディレクトリの場合"""
        ssm = self._init_with_commit(tmp_path / "local")
        empty_remote = tmp_path / "empty_remote"
        empty_remote.mkdir()
        ssm.remote_add("badremote", str(empty_remote))

        with pytest.raises(SSMConfigError):
            ssm.pull("badremote")

    @pytest.mark.timeout(10)
    def test_pull_from_freshly_initialized_empty_remote_raises_branch_not_found(self, tmp_path):
        """
        リモート先に .ssm はあるが該当ブランチへ何も push されていない（空）場合、
        SSMBranchNotFoundError になる（test_remote_backends.py の
        test_pull_unknown_branch と同種の経路だが、ここでは「一度も push していない
        まっさらなリモート」という切り口で確認する）。
        """
        ssm = self._init_with_commit(tmp_path / "local")
        remote_dir = tmp_path / "remote"
        remote_ssm = SSM(path=remote_dir)
        remote_ssm.init()  # .ssm はあるが branches/main は存在しない

        ssm.remote_add("freshremote", str(remote_dir))

        with pytest.raises(SSMBranchNotFoundError):
            ssm.pull("freshremote")

    @pytest.mark.timeout(10)
    def test_push_s3_without_boto3_raises_documented_error(self, tmp_path):
        """
        boto3 未インストール環境で s3:// リモートに push すると、
        remote_backends.S3Backend が RemoteBackendError
        ("S3 remotes require 'boto3'...") を送出する。
        boto3 がインストールされている環境ではこの経路を再現できないためスキップする。
        """
        if _HAS_BOTO3:
            pytest.skip("boto3 is installed; missing-dependency path is not exercised")

        ssm = self._init_with_commit(tmp_path)
        ssm.remote_add("s3remote", "s3://mybucket/prefix")

        with pytest.raises(RemoteBackendError, match="boto3"):
            ssm.push("s3remote")

    @pytest.mark.timeout(10)
    def test_pull_s3_without_boto3_raises_documented_error(self, tmp_path):
        if _HAS_BOTO3:
            pytest.skip("boto3 is installed; missing-dependency path is not exercised")

        ssm = self._init_with_commit(tmp_path)
        ssm.remote_add("s3remote", "s3://mybucket/prefix")

        with pytest.raises(RemoteBackendError, match="boto3"):
            ssm.pull("s3remote")

    @pytest.mark.timeout(10)
    def test_push_gcs_without_dependency_raises_documented_error(self, tmp_path):
        """
        google-cloud-storage 未インストール環境で gs:// リモートに push すると、
        remote_backends.GCSBackend が RemoteBackendError
        ("GCS remotes require 'google-cloud-storage'...") を送出する。
        """
        if _HAS_GCS:
            pytest.skip("google-cloud-storage is installed; missing-dependency path is not exercised")

        ssm = self._init_with_commit(tmp_path)
        ssm.remote_add("gsremote", "gs://mybucket/prefix")

        with pytest.raises(RemoteBackendError, match="google-cloud-storage"):
            ssm.push("gsremote")
