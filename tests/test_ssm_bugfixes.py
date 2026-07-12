"""
監査で発見された3件のバグに対する回帰テスト

1. `SSM._file_locks` の無制限増加（メモリリーク）
2. `SSM._resolve_hash()` の commits/ ディレクトリ全走査による O(n) 劣化
3. チェックポイントファイル名の秒解像度による衝突（サイレント上書き）
"""

import gzip
import pickle
from pathlib import Path

import pytest

from SessionSmith.ssm import SSM


class TestFileLocksBounded:
    """Bug1: _file_locks が無制限に増え続けないことを確認"""

    @pytest.mark.timeout(10)
    def test_direct_calls_keep_cache_within_cap(self, tmp_path):
        """多数の異なるパスで _get_file_lock を呼んでもキャッシュが上限を超えない"""
        ssm = SSM(path=tmp_path)
        ssm.init()

        # 上限（_FILE_LOCK_CACHE_MAX）を大きく超える数のユニークなパスで
        # ロックを取得する。commits/<hash>.json のように、コミットごとに
        # 一意なパスが増え続けるワークロードを模している
        n_paths = SSM._FILE_LOCK_CACHE_MAX + 200
        for i in range(n_paths):
            ssm._get_file_lock(f"/fake/commits/{i:06d}.json")

        assert len(ssm._file_locks) <= SSM._FILE_LOCK_CACHE_MAX

    @pytest.mark.timeout(10)
    def test_hot_path_returns_same_lock_object(self, tmp_path):
        """直近で使ったパスに対しては同一のロックオブジェクトが返る（LRUのホット状態）"""
        ssm = SSM(path=tmp_path)
        ssm.init()

        lock_a = ssm._get_file_lock("/fake/commits/hot.json")
        lock_a_again = ssm._get_file_lock("/fake/commits/hot.json")

        assert lock_a is lock_a_again

        # ホットな状態を保ったまま他のパスを大量に追加しても、
        # 直近アクセスされたパスは（LRU なので）キャッシュに残り続ける
        for i in range(SSM._FILE_LOCK_CACHE_MAX + 50):
            ssm._get_file_lock(f"/fake/commits/other_{i:06d}.json")
            if i % 100 == 0:
                # 定期的にホットパスへ触れて「最近使った」状態を維持する
                ssm._get_file_lock("/fake/commits/hot.json")

        assert ssm._get_file_lock("/fake/commits/hot.json") is lock_a
        assert len(ssm._file_locks) <= SSM._FILE_LOCK_CACHE_MAX

    @pytest.mark.timeout(30)
    def test_many_real_commits_keep_cache_within_cap(self, tmp_path):
        """実際に多数コミットしても _file_locks が上限内に収まる（実運用に近い経路）"""
        globals_dict = {"counter": 0}
        ssm = SSM(path=tmp_path, globals_dict=globals_dict)
        ssm.init()

        for i in range(35):
            globals_dict["counter"] = i
            ssm.commit(f"commit {i}")

        # commits/<hash>.json は毎回ユニークなパスになるため、
        # 修正前は len(ssm._file_locks) がコミット数に比例して増え続けていた
        assert len(ssm._file_locks) <= SSM._FILE_LOCK_CACHE_MAX
        # 実際にコミットは失われていない（キャッシュの縮小が正しさに影響しない）
        assert len(ssm.log(limit=100)) == 35


class TestResolveHashFastPath:
    """Bug2: _resolve_hash() の完全ハッシュ高速パスのテスト"""

    @pytest.mark.timeout(10)
    def test_full_hash_resolves_correctly(self, tmp_path):
        globals_dict = {"a": 1}
        ssm = SSM(path=tmp_path, globals_dict=globals_dict)
        ssm.init()

        hashes = []
        for i in range(5):
            globals_dict["a"] = i
            hashes.append(ssm.commit(f"commit {i}"))

        for full_hash in hashes:
            assert ssm._resolve_hash(full_hash) == full_hash

    @pytest.mark.timeout(10)
    def test_valid_short_prefix_still_resolves(self, tmp_path):
        globals_dict = {"a": 1}
        ssm = SSM(path=tmp_path, globals_dict=globals_dict)
        ssm.init()

        full_hash = ssm.commit("only commit")
        short_hash = full_hash[:7]

        assert ssm._resolve_hash(short_hash) == full_hash

    @pytest.mark.timeout(10)
    def test_unknown_full_length_hash_raises_value_error(self, tmp_path):
        ssm = SSM(path=tmp_path, globals_dict={"a": 1})
        ssm.init()
        ssm.commit("init")

        with pytest.raises(ValueError, match="No commit found matching"):
            ssm._resolve_hash("deadbeefdeadbeef")  # 16文字・16進数だが存在しない

    @pytest.mark.timeout(10)
    def test_unknown_short_hash_raises_value_error(self, tmp_path):
        ssm = SSM(path=tmp_path, globals_dict={"a": 1})
        ssm.init()
        ssm.commit("init")

        with pytest.raises(ValueError, match="No commit found matching"):
            ssm._resolve_hash("zzzzzzz")  # 短く、かつ16進数でもない

    @pytest.mark.timeout(10)
    def test_ambiguous_short_hash_raises_value_error(self, tmp_path):
        """
        確率に頼らず決定論的にプレフィックス衝突を再現するため、
        commits/ に共通プレフィックスを持つダミーコミットを直接2つ書き込む
        （tests/test_ssm_e2e.py の同種テストと同じ手法）
        """
        import json

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

        with pytest.raises(ValueError, match="Ambiguous hash"):
            ssm._resolve_hash("ffaaaaaaaaaaaaa")

    @pytest.mark.timeout(10)
    def test_full_hash_hit_does_not_scan_commits_directory(self, tmp_path, monkeypatch):
        """
        完全長ハッシュがヒットする場合、commits/ ディレクトリの glob 走査
        （O(n)）が発生しないことを確認する（高速パスの直接的な証拠）
        """
        globals_dict = {"a": 1}
        ssm = SSM(path=tmp_path, globals_dict=globals_dict)
        ssm.init()

        for i in range(5):
            globals_dict["a"] = i
            full_hash = ssm.commit(f"commit {i}")

        glob_calls = []
        original_glob = Path.glob

        def spy_glob(self_path, pattern, *args, **kwargs):
            glob_calls.append((self_path, pattern))
            return original_glob(self_path, pattern, *args, **kwargs)

        monkeypatch.setattr(Path, "glob", spy_glob)

        resolved = ssm._resolve_hash(full_hash)

        assert resolved == full_hash
        assert glob_calls == []


class TestCheckpointFilenameCollision:
    """Bug3: 同一秒内に連続保存したチェックポイントが上書きされないことを確認"""

    @pytest.mark.timeout(10)
    def test_rapid_successive_forced_checkpoints_do_not_overwrite(self, tmp_path):
        globals_dict = {"x": 0}
        ssm = SSM(path=tmp_path, globals_dict=globals_dict)
        ssm.init()

        # interval を非常に長くし、バックグラウンドの自動保存が割り込まない
        # 状態で、force=True の手動チェックポイントを同一ウォールクロック秒内に
        # 連続して2回呼び出す（修正前は checkpoint_%Y%m%d_%H%M%S.gz が衝突し、
        # 2回目の書き込みが1回目を静かに上書きしていた）
        with ssm.checkpoint(interval=9999, max_checkpoints=10) as cp:
            globals_dict["x"] = 1
            assert cp.step(force=True) is True
            globals_dict["x"] = 2
            assert cp.step(force=True) is True

        checkpoint_dir = tmp_path / ".ssm" / "checkpoints"
        files = sorted(checkpoint_dir.glob("checkpoint_*.gz"))

        # 2回の明示的な force チェックポイント（+ 終了時の final checkpoint）が
        # すべて別ファイルとして残っていること
        assert len(files) >= 2

        step_counts = []
        for f in files:
            with gzip.open(f, "rb") as fh:
                data = pickle.load(fh)
            step_counts.append(data["step_count"])

        # 1回目・2回目の両方の step_count が残っている
        # （衝突していれば、どちらか一方が失われ片方の step_count しか残らない）
        assert 1 in step_counts
        assert 2 in step_counts

        # list_checkpoints() API からも両方参照できること
        listed = ssm.list_checkpoints()
        listed_step_counts = [c["step_count"] for c in listed]
        assert 1 in listed_step_counts
        assert 2 in listed_step_counts

    @pytest.mark.timeout(10)
    def test_direct_unsafe_saves_in_same_second_produce_distinct_files(self, tmp_path):
        """CheckpointContext._save_checkpoint_unsafe を直接連続呼び出しした場合も衝突しない"""
        from SessionSmith.ssm import CheckpointContext

        globals_dict = {"y": 0}
        ssm = SSM(path=tmp_path, globals_dict=globals_dict)
        ssm.init()

        ctx = CheckpointContext(ssm=ssm, interval=9999, max_checkpoints=10)
        ctx.checkpoint_dir.mkdir(parents=True, exist_ok=True)

        for i in range(5):
            globals_dict["y"] = i
            assert ctx._save_checkpoint_unsafe(f"step {i}") is True

        files = list(ctx.checkpoint_dir.glob("checkpoint_*.gz"))
        # 5回すべてが別ファイルとして保存されている（同一秒内でも上書きなし）
        assert len(files) == 5
