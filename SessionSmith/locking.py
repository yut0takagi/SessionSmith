"""
SessionSmith プロセス間ロック (.ssm リポジトリ単位)

複数のプロセス（および同一プロセス内の複数スレッド）が同じ `.ssm`
リポジトリに同時にアクセスしても、履歴（HEAD / ブランチ参照 / コミット /
オブジェクト）が破損しないようにするための排他ロックを提供します。

設計方針
--------
1. **クロスプラットフォーム**: POSIX / Windows のどちらでも同じ意味で
   動作する標準ライブラリのプリミティブのみを使用します。
   ``os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)`` は、対象パスに
   ファイルが存在しない場合に限りアトミックに新規作成する、という保証が
   POSIX と Windows の両方の `open()`/`CreateFile()` 実装で成り立つため、
   これをロック取得のプリミティブとして採用しています
   （`fcntl`/`msvcrt` のようなOS別APIを避けられる）。

2. **ロックファイル**: `<ssm_path>/.lock` に、保持者の PID と取得時刻を
   JSON で書き込みます。診断（誰が保持しているか）と stale ロックの
   判定に使います。

3. **タイムアウト**: 取得できない場合はポーリング（デフォルト 50ms間隔）
   で再試行し、`timeout` 秒（デフォルト 10 秒）を超えると
   `SSMLockError` を送出します。メッセージには対象の `.ssm` パスと、
   分かる場合は現在の保持者 PID を含めます。

4. **stale ロックの回収**: ロックファイルが存在していても、
   記録された PID が生きていなければ（POSIX: ``os.kill(pid, 0)`` が
   `ProcessLookupError` を返す）、そのロックはクラッシュ等で解放され
   なかった残骸とみなし、強制的に削除して取得し直します。
   Windows では `os.kill(pid, 0)` が本来の「シグナル 0 での生存確認」
   としては使えない（`TerminateProcess` に化けてしまう危険がある）ため、
   PID の生死判定は POSIX でのみ行い、そうでない場合は
   ``STALE_LOCK_MAX_AGE`` 秒より古いロックファイルを stale とみなす
   年齢ベースのヒューリスティックにフォールバックします。

5. **再入可能性（同一プロセス内）**: `.ssm` パスごとに 1 つの
   `threading.RLock` をモジュールレベルのレジストリで保持します。
   ある公開メソッド（例: `checkout_branch`）がロックを保持したまま、
   内部で別の公開メソッド（例: `checkout`）を呼び出しても、
   **同じスレッド**であれば `RLock` の再入性によって即座に
   ロックを取得でき、デッドロックしません。
   一方、**別スレッド**（例: バックグラウンドのチェックポイントスレッド）
   が同時に取得しようとした場合は、`RLock` がそのスレッド間できちんと
   排他するため、待機（またはタイムアウト）します。

   実際の OS レベルのロックファイルは、その `RLock` の
   「そのスレッドにとって最も外側の取得」（再入カウントが 0→1）の
   タイミングでのみ作成し、「最も外側の解放」（1→0）のタイミングでのみ
   削除します。つまり:

   - プロセス内の複数スレッド間の排他 → `threading.RLock`
   - プロセス間の排他 → `.lock` ファイル（RLock がスレッドを1つに
     絞り込んだ後、そのスレッドだけが `.lock` ファイルを操作する）

   この二層構造により、"file lock は常に1スレッドしか触らない" ことが
   保証され、OS レベルロックの操作自体をスレッドセーフにする追加の
   ロックは不要です。
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Optional, Union

from .exceptions import SSMLockError

# ロック取得のデフォルトタイムアウト（秒）
DEFAULT_TIMEOUT = 10.0

# stale ロックとみなす最大経過時間（秒）。
# PID の生死が確認できない環境（Windows 等）でのフォールバックに使う。
STALE_LOCK_MAX_AGE = 120.0

# 取得できなかった場合の再試行間隔（秒）
_POLL_INTERVAL = 0.05

LOCK_FILENAME = ".lock"

# .ssm パス（正規化済み文字列）ごとの threading.RLock レジストリ。
# 複数の ProcessLock インスタンス（毎回 `with self._lock():` で新規生成
# される）が、同じ .ssm パスに対しては必ず同じ RLock を共有するための
# もの。レジストリ自体への同時書き込みは _registry_guard で保護する。
_registry_guard = threading.Lock()
_thread_rlocks: dict[str, threading.RLock] = {}
_reentry_counts: dict[str, int] = {}


def _get_rlock(key: str) -> threading.RLock:
    """指定キーに対応する（プロセス内で共有される）RLock を取得する"""
    with _registry_guard:
        rlock = _thread_rlocks.get(key)
        if rlock is None:
            rlock = threading.RLock()
            _thread_rlocks[key] = rlock
        return rlock


def _pid_is_dead(pid: Optional[int]) -> bool:
    """
    PID が既に死んでいる（プロセスが存在しない）と確認できる場合に True。

    POSIX でのみ ``os.kill(pid, 0)`` による生存確認を行う。Windows では
    `os.kill` がシグナル配送ではなく `TerminateProcess` にマップされて
    おり、シグナル 0 を安全に「生存確認のみ」に使えないため、確認せず
    False（＝死んでいるとは断定しない）を返す。呼び出し側は年齢ベースの
    ヒューリスティックにフォールバックする。
    """
    if pid is None or os.name == "nt":
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except (PermissionError, OSError):
        # プロセスは存在するが shutil できない、等 → 生きているとみなす
        return False
    else:
        return False


class ProcessLock:
    """
    `.ssm` リポジトリ単位のプロセス間・スレッド間排他ロック。

    使い方::

        with ProcessLock(ssm_path, timeout=10.0):
            ... HEAD / branches / commits / objects を読み書き ...

    Args:
        ssm_path: `.ssm` ディレクトリのパス
        timeout: 取得を待つ最大秒数（デフォルト 10 秒）
        poll_interval: リトライ間隔（秒）
    """

    def __init__(
        self,
        ssm_path: Union[str, Path],
        timeout: float = DEFAULT_TIMEOUT,
        poll_interval: float = _POLL_INTERVAL,
    ):
        self.ssm_path = Path(ssm_path)
        self.lock_path = self.ssm_path / LOCK_FILENAME
        self.timeout = timeout
        self.poll_interval = poll_interval
        # シンボリックリンクや相対/絶対パスの違いを吸収し、同じ物理ディレクトリが
        # 常に同じキーにマップされるようにする（存在しなくても resolve() は失敗しない）
        self._key = str(self.ssm_path.resolve())
        self._rlock = _get_rlock(self._key)
        self._rlock_acquired = False
        self._holds_os_lock = False

    def __enter__(self) -> "ProcessLock":
        deadline = time.monotonic() + self.timeout

        remaining = max(0.0, deadline - time.monotonic())
        acquired = self._rlock.acquire(timeout=remaining)
        if not acquired:
            # 同一プロセス内の別スレッドがロックを保持している
            holder = self._read_holder_info()
            raise SSMLockError(
                str(self.ssm_path),
                holder_pid=holder.get("pid") if holder else os.getpid(),
                timeout=self.timeout,
            )
        self._rlock_acquired = True

        with _registry_guard:
            count = _reentry_counts.get(self._key, 0)

        if count == 0:
            # このスレッドにとって最も外側の取得 → OS レベルのロックファイルを取る
            try:
                self._acquire_os_lock(deadline)
            except BaseException:
                self._rlock.release()
                self._rlock_acquired = False
                raise
            self._holds_os_lock = True

        with _registry_guard:
            _reentry_counts[self._key] = _reentry_counts.get(self._key, 0) + 1

        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        try:
            with _registry_guard:
                count = max(0, _reentry_counts.get(self._key, 1) - 1)
                _reentry_counts[self._key] = count

            if count == 0 and self._holds_os_lock:
                self._release_os_lock()
                self._holds_os_lock = False
        finally:
            if self._rlock_acquired:
                self._rlock_acquired = False
                self._rlock.release()
        return False

    # ------------------------------------------------------------------
    # OS レベルのロックファイル操作（この時点で呼び出しスレッドは、
    # このプロセス内で当該 .ssm パスに対する唯一の候補者であることが
    # RLock によって保証されている）
    # ------------------------------------------------------------------

    def _acquire_os_lock(self, deadline: float) -> None:
        while True:
            try:
                fd = os.open(str(self.lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                try:
                    payload = json.dumps(
                        {"pid": os.getpid(), "started_at": time.time()}
                    ).encode("utf-8")
                    os.write(fd, payload)
                finally:
                    os.close(fd)
                return
            except FileExistsError:
                if self._reclaim_if_stale():
                    # stale ロックを消せたので即座に取得し直す
                    continue
                if time.monotonic() >= deadline:
                    holder = self._read_holder_info()
                    raise SSMLockError(
                        str(self.ssm_path),
                        holder_pid=holder.get("pid") if holder else None,
                        timeout=self.timeout,
                    )
                time.sleep(min(self.poll_interval, max(0.0, deadline - time.monotonic())) or self.poll_interval)

    def _release_os_lock(self) -> None:
        try:
            os.unlink(self.lock_path)
        except OSError:
            pass

    def _read_holder_info(self) -> Optional[dict]:
        try:
            raw = self.lock_path.read_text(encoding="utf-8")
            return json.loads(raw)
        except (OSError, ValueError):
            return None

    def _reclaim_if_stale(self) -> bool:
        """
        ロックファイルが stale（保持者プロセスが既に死んでいる、または
        十分に古い）と判断できれば削除して True を返す。
        """
        info = self._read_holder_info()
        pid = info.get("pid") if info else None

        if _pid_is_dead(pid):
            return self._force_remove()

        try:
            age = time.time() - self.lock_path.stat().st_mtime
        except OSError:
            # 既に他プロセスが削除済み
            return True

        if age > STALE_LOCK_MAX_AGE:
            return self._force_remove()

        return False

    def _force_remove(self) -> bool:
        try:
            os.unlink(self.lock_path)
            return True
        except FileNotFoundError:
            return True
        except OSError:
            return False
