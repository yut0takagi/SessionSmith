"""
SessionSmith.locking (プロセス間ロック) のテスト

issue #29: 複数プロセス／複数スレッドが同じ `.ssm` リポジトリに
同時アクセスしても履歴が破損しないことを検証する。

- 複数プロセスから同時に commit() してもリポジトリが破損しないこと
- ロック取得がタイムアウトした際に、分かりやすいエラーになること
- stale なロックファイル（保持者プロセスが死んでいる／古すぎる）が
  ハングせずに回収されること
- 同一プロセス（同一スレッド）内でのネストしたロック取得が
  デッドロックしないこと（例: checkout_branch() が内部で checkout() を呼ぶ）
"""

from __future__ import annotations

import json
import multiprocessing
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from SessionSmith import locking
from SessionSmith.exceptions import SSMLockError
from SessionSmith.locking import LOCK_FILENAME, ProcessLock
from SessionSmith.ssm import SSM

# ========== 複数プロセスからの commit() 用ワーカー ==========
# multiprocessing の 'spawn' 開始方式でも pickle 可能なように、
# モジュールのトップレベルに定義する（picklable であるためにはクロージャや
# インスタンスメソッドではなく、モジュールレベル関数である必要がある）。


def _concurrent_commit_worker(base_path_str: str, worker_id: int, n_commits: int) -> None:
    """同じ .ssm リポジトリに対して、複数回 commit() を行うワーカープロセス"""
    ssm = SSM(path=base_path_str, globals_dict={})
    for step in range(n_commits):
        ssm.globals_dict = {
            "worker_id": worker_id,
            "step": step,
            "payload": list(range(worker_id, worker_id + 10)),
        }
        ssm.commit(f"worker={worker_id} step={step}")


def _assert_repo_consistent(base_path: Path, expected_commit_count: int) -> None:
    """
    リポジトリが破損していないことを検証する:

    - HEAD が実在する（かつ壊れていない）コミットを指している
    - ブランチ参照（main）が実在するコミットを指しており、HEADと一致する
    - commits/*.json がすべて壊れずに読み込める（JSONとして valid）
    - それらが単一の親子チェーンとして HEAD から辿れる
      （commit() 全体がリポジトリロックで直列化されている前提での、
      「フォークが発生していない」という強い一貫性チェック）
    """
    ssm_path = base_path / ".ssm"

    commit_files = list((ssm_path / "commits").glob("*.json"))
    assert len(commit_files) == expected_commit_count, (
        f"expected {expected_commit_count} commit files, found {len(commit_files)}"
    )

    all_hashes: set[str] = set()
    parent_map: dict[str, str | None] = {}

    for commit_file in commit_files:
        # 壊れて（truncateされて）いれば json.load がここで例外を出す
        with open(commit_file, encoding="utf-8") as f:
            data = json.load(f)

        assert "variables" in data and data["variables"], f"commit {commit_file} has no variables"

        commit_hash = commit_file.stem
        all_hashes.add(commit_hash)
        parent_map[commit_hash] = data.get("parent")

    head = (ssm_path / "HEAD").read_text().strip()
    assert head, "HEAD is empty"
    assert head in all_hashes, "HEAD points to a nonexistent commit"

    branch_file = ssm_path / "branches" / "main"
    assert branch_file.exists(), "default branch 'main' ref is missing"
    branch_head = branch_file.read_text().strip()
    assert branch_head in all_hashes, "branch ref points to a nonexistent commit"
    assert branch_head == head, "HEAD and branch ref disagree"

    # HEAD から親を辿ると、循環なしで、すべてのコミットをちょうど1回ずつ通ること
    chain: list[str] = []
    seen: set[str] = set()
    current: str | None = head
    while current:
        assert current not in seen, "cycle detected in commit history"
        seen.add(current)
        chain.append(current)
        current = parent_map.get(current)

    assert set(chain) == all_hashes, "commit history is not a single linear chain (possible fork/corruption)"


class TestConcurrentCommits:
    """複数プロセスからの同時 commit() がリポジトリを破損しないことのテスト"""

    NUM_WORKERS = 5
    COMMITS_PER_WORKER = 3

    @pytest.mark.timeout(60)
    def test_concurrent_commits_do_not_corrupt_repo(self, tmp_path):
        ssm = SSM(path=tmp_path)
        ssm.init()

        ctx = multiprocessing.get_context("spawn")
        procs = [
            ctx.Process(
                target=_concurrent_commit_worker,
                args=(str(tmp_path), worker_id, self.COMMITS_PER_WORKER),
            )
            for worker_id in range(self.NUM_WORKERS)
        ]

        for p in procs:
            p.start()
        for p in procs:
            p.join(timeout=50)

        for p in procs:
            assert not p.is_alive(), "worker process did not finish within the timeout"
            assert p.exitcode == 0, f"worker process exited with code {p.exitcode}"

        _assert_repo_consistent(
            tmp_path, expected_commit_count=self.NUM_WORKERS * self.COMMITS_PER_WORKER
        )


class TestLockTimeout:
    """ロック取得がタイムアウトした際に分かりやすいエラーになることのテスト"""

    @pytest.mark.timeout(15)
    def test_timeout_raises_clear_error_with_path_and_holder(self, tmp_path):
        ssm_dir = tmp_path / ".ssm"
        ssm_dir.mkdir()

        holder_ready = threading.Event()
        release_holder = threading.Event()

        def _hold_lock():
            with ProcessLock(ssm_dir, timeout=5.0):
                holder_ready.set()
                release_holder.wait(timeout=5.0)

        holder_thread = threading.Thread(target=_hold_lock, daemon=True)
        holder_thread.start()
        try:
            assert holder_ready.wait(timeout=5.0), "holder thread failed to acquire the lock in time"

            with pytest.raises(SSMLockError) as exc_info:
                with ProcessLock(ssm_dir, timeout=0.3):
                    pass  # pragma: no cover - should never be reached

            message = str(exc_info.value)
            # メッセージには対象の .ssm パスが含まれていること
            assert str(ssm_dir) in message
            # 保持者 PID についての言及があること（診断に使えること）
            assert "PID" in message
            assert exc_info.value.ssm_path == str(ssm_dir)
        finally:
            release_holder.set()
            holder_thread.join(timeout=5.0)

    @pytest.mark.timeout(15)
    def test_commit_raises_lock_error_when_repo_locked_by_other_thread(self, tmp_path):
        """SSM.commit() レベルでも SSMLockError が伝播することを確認する"""
        ssm = SSM(path=tmp_path, globals_dict={"a": 1})
        ssm.init()
        ssm.commit("initial")

        # テストを高速にするため、このインスタンスだけタイムアウトを短縮
        ssm.LOCK_TIMEOUT_SECONDS = 0.3

        holder_ready = threading.Event()
        release_holder = threading.Event()

        def _hold_lock():
            with ProcessLock(ssm.ssm_path, timeout=5.0):
                holder_ready.set()
                release_holder.wait(timeout=5.0)

        holder_thread = threading.Thread(target=_hold_lock, daemon=True)
        holder_thread.start()
        try:
            assert holder_ready.wait(timeout=5.0)
            ssm.globals_dict = {"a": 2}
            with pytest.raises(SSMLockError):
                ssm.commit("should time out")
        finally:
            release_holder.set()
            holder_thread.join(timeout=5.0)


class TestStaleLockRecovery:
    """クラッシュ等で残った stale ロックが、ハングせずに回収されることのテスト"""

    @pytest.mark.timeout(15)
    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="PID生存確認 (os.kill(pid, 0)) による stale 判定は POSIX 専用",
    )
    def test_stale_lock_with_dead_pid_is_reclaimed(self, tmp_path):
        ssm_dir = tmp_path / ".ssm"
        ssm_dir.mkdir()
        lock_path = ssm_dir / LOCK_FILENAME

        # 確実に「死んでいる」PIDを用意する: 子プロセスを起動して即終了させ、
        # wait() で reap することでそのPIDが再利用可能な状態にする
        proc = subprocess.Popen([sys.executable, "-c", "pass"])
        dead_pid = proc.pid
        proc.wait(timeout=5)

        lock_path.write_text(
            json.dumps({"pid": dead_pid, "started_at": time.time()}), encoding="utf-8"
        )

        start = time.monotonic()
        with ProcessLock(ssm_dir, timeout=5.0):
            pass
        elapsed = time.monotonic() - start

        # stale ロックはポーリング1回程度で即座に回収されるはず（タイムアウト
        # いっぱいまで待たされてはいけない = ハングしていないことの確認）
        assert elapsed < 3.0, f"stale lock was not reclaimed promptly (took {elapsed:.2f}s)"

    @pytest.mark.timeout(15)
    def test_stale_lock_by_age_is_reclaimed(self, tmp_path, monkeypatch):
        """
        PIDの生死が判定できない場合（Windows、または権限で確認できない場合）の
        フォールバックである「年齢ベースのヒューリスティック」を検証する。
        自分自身の（生きている）PIDを保持者として記録しつつ、ファイルの
        mtime だけを古くすることで、PID生死判定に依存せず stale と判定
        されることを確認する。
        """
        ssm_dir = tmp_path / ".ssm"
        ssm_dir.mkdir()
        lock_path = ssm_dir / LOCK_FILENAME

        monkeypatch.setattr(locking, "STALE_LOCK_MAX_AGE", 0.2)

        # 保持者は自分自身の PID（=生きている）だが、ファイルは十分古い
        lock_path.write_text(
            json.dumps({"pid": os.getpid(), "started_at": time.time()}), encoding="utf-8"
        )
        old_time = time.time() - 10
        os.utime(lock_path, (old_time, old_time))

        start = time.monotonic()
        with ProcessLock(ssm_dir, timeout=5.0):
            pass
        elapsed = time.monotonic() - start

        assert elapsed < 3.0, f"aged-out stale lock was not reclaimed promptly (took {elapsed:.2f}s)"


class TestReentrancy:
    """同一プロセス（同一スレッド）内でのネストしたロック取得がデッドロックしないことのテスト"""

    @pytest.mark.timeout(10)
    def test_processlock_is_reentrant_within_same_thread(self, tmp_path):
        ssm_dir = tmp_path / ".ssm"
        ssm_dir.mkdir()

        # 3重にネストしても、同一スレッドであれば即座に取得できる
        with ProcessLock(ssm_dir, timeout=2.0):
            with ProcessLock(ssm_dir, timeout=2.0):
                with ProcessLock(ssm_dir, timeout=2.0):
                    pass

    @pytest.mark.timeout(10)
    def test_checkout_branch_nested_lock_does_not_deadlock(self, tmp_path):
        """
        checkout_branch() は内部で checkout() を呼び出し、どちらも
        リポジトリロックを取得する（merge() 内から他の内部処理を呼ぶ、
        checkout_tag() や pull() が checkout() を呼ぶのと同じネスト経路）。
        ここでデッドロックすればテストが timeout で失敗する。
        """
        ssm = SSM(path=tmp_path, globals_dict={"a": 1})
        ssm.init()
        ssm.commit("initial")
        ssm.branch("feature", create=True)

        ssm.globals_dict = {"a": 2}
        ssm.commit("second")

        ssm.checkout_branch("feature")

        assert ssm.get_current_branch() == "feature"
        assert ssm.globals_dict["a"] == 1

    @pytest.mark.timeout(10)
    def test_pull_nested_lock_does_not_deadlock(self, tmp_path):
        """pull()（ファイルパスリモート）も内部で checkout() を呼ぶネスト経路"""
        remote_dir = tmp_path / "remote"
        local_dir = tmp_path / "local"

        remote = SSM(path=remote_dir, globals_dict={"a": 1})
        remote.init()
        remote.commit("initial")

        local = SSM(path=local_dir, globals_dict={})
        local.init()
        local.remote_add("origin", str(remote_dir))

        local.pull("origin", "main")

        assert local.globals_dict.get("a") == 1
