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

4. **stale ロックの回収**: ロックファイルが残っていても、それが
   「もう有効でない残骸」と判断できる場合のみ回収（削除して取得し直し）
   します。判定は保持者 PID の生存状態を3値（dead / alive / unknown）で
   見て行います（詳細は ``_reclaim_if_stale`` を参照）:

   - **自プロセスの PID** の残骸 → 回収（前回 release の unlink 失敗や
     PID 再利用による残骸。自己ロックアウトの回避）。
   - **死亡が確認できた保持者**（POSIX: ``os.kill(pid, 0)`` が
     `ProcessLookupError`）→ 回収。
   - **生存が確認できた保持者** → **決して回収しない**。mtime が古くても、
     大きな pull/merge/checkpoint 等で長時間ロックを保持している正当な
     保持者を横取りして `.ssm` を破損させないため、待機／タイムアウトする。
   - **生死が判定できない場合**（PID 不明、Windows で ``os.kill`` を生存
     判定に使わない方針、権限不足 等）→ ``STALE_LOCK_MAX_AGE`` 秒より
     古いロックファイルを stale とみなす **年齢ベースのフォールバック**を
     適用する。この age ベースの回収は「生死判定不能」な場合に **限る**。

   Windows では `os.kill(pid, 0)` が本来の「シグナル 0 での生存確認」
   としては使えない（`TerminateProcess` に化けてしまう危険がある）ため、
   PID の生死判定は POSIX でのみ行い、Windows は上記の unknown 経路
   （age フォールバック）を使います。

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

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Optional, Union

from .exceptions import SSMLockError

logger = logging.getLogger("SessionSmith.locking")
logger.addHandler(logging.NullHandler())

# ロック取得のデフォルトタイムアウト（秒）
DEFAULT_TIMEOUT = 10.0

# stale ロックとみなす最大経過時間（秒）。
# 【重要】これは「保持者の生死が判定できない場合のみ」のフォールバック。
# 生存が確認できた保持者のロックは、どれだけ古くても age では奪わない
# （正当な長時間保持者の横取り＝.ssm 破損を防ぐため）。
STALE_LOCK_MAX_AGE = 120.0

# 取得できなかった場合の再試行間隔（秒）
_POLL_INTERVAL = 0.05

# ロックファイル削除のリトライ回数と基準バックオフ（秒）
_UNLINK_RETRIES = 3
_UNLINK_BACKOFF = 0.01

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


def _pid_liveness(pid: Optional[int]) -> str:
    """
    PID の生存状態を3値で返す: ``"dead"`` / ``"alive"`` / ``"unknown"``。

    - ``"dead"``  : プロセスが存在しないと**確認できた**（安全に回収してよい）
    - ``"alive"`` : プロセスが存在すると**確認できた**（正当な保持者。回収禁止）
    - ``"unknown"``: 生死を**判定できない**（回収可否は age フォールバックで判断）

    POSIX でのみ ``os.kill(pid, 0)`` による生存確認を行う。Windows では
    `os.kill` がシグナル配送ではなく `TerminateProcess` にマップされて
    おり、シグナル 0 を安全に「生存確認のみ」に使えないため、判定せず
    ``"unknown"`` を返す（呼び出し側が age ベースにフォールバックする）。
    PID が None・0・負値の場合も、安全のため生死判定に使わず ``"unknown"``。
    """
    if pid is None or os.name == "nt":
        return "unknown"
    if pid <= 0:
        # os.kill(0/-1, sig) はプロセスグループへの送信になり危険なので触らない
        return "unknown"
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return "dead"
    except PermissionError:
        # プロセスは存在するが、こちらにシグナルを送る権限がない → 生存確認できた
        return "alive"
    except OSError:
        # その他の理由で判定できない
        return "unknown"
    else:
        return "alive"


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
        incremented = False

        # __enter__ 全体を BaseException で保護する。KeyboardInterrupt や
        # SystemExit（ssm.py の signal handler 経由で commit 中などに発生し得る）
        # が取得の途中で飛んでも、__exit__ は呼ばれない。ここで確保済みの
        # RLock / OS ロック / reentry カウントを確実に巻き戻し、部分取得状態を
        # 残さないことで、その .ssm パスへの以降のアクセスが永久に詰まる
        # （RLock リーク）のを防ぐ。
        try:
            remaining = max(0.0, deadline - time.monotonic())
            acquired = self._rlock.acquire(timeout=remaining)
            if not acquired:
                # 同一プロセス内の別スレッドがロックを保持している。
                # ロックファイルが読めない場合の保持者は「不明(None)」とする
                # （待機側自身の PID を既定にすると誤解を招くため）。
                holder = self._read_holder_info()
                raise SSMLockError(
                    str(self.ssm_path),
                    holder_pid=holder.get("pid") if holder else None,
                    timeout=self.timeout,
                )
            self._rlock_acquired = True

            with _registry_guard:
                count = _reentry_counts.get(self._key, 0)

            if count == 0:
                # このスレッドにとって最も外側の取得 → OS レベルのロックファイルを取る
                self._acquire_os_lock(deadline)
                self._holds_os_lock = True

            with _registry_guard:
                _reentry_counts[self._key] = _reentry_counts.get(self._key, 0) + 1
            incremented = True

            return self
        except BaseException:
            # 途中まで確保したものを、取得と逆順に巻き戻す
            if incremented:
                with _registry_guard:
                    _reentry_counts[self._key] = max(
                        0, _reentry_counts.get(self._key, 1) - 1
                    )
            if self._holds_os_lock:
                self._release_os_lock()
                self._holds_os_lock = False
            if self._rlock_acquired:
                self._rlock_acquired = False
                self._rlock.release()
            raise

    def __exit__(self, exc_type, exc, tb) -> None:
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
        return None

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
        # 一時的な unlink 失敗（AV/バックアップによる一時ロック等）を数回リトライ。
        # 全 OSError を黙って捨てると、自PIDのロックファイルが残った際に
        # 生存判定が alive を返してしまい、次回取得が age 期限まで待たされる
        # （自己ロックアウト）。取得側は own-PID 残骸を回収できるようにして
        # あるが、それでも最終失敗時は必ず warning を出す。
        last_err: Optional[OSError] = None
        for attempt in range(_UNLINK_RETRIES):
            try:
                os.unlink(self.lock_path)
                return
            except FileNotFoundError:
                return
            except OSError as e:
                last_err = e
                time.sleep(_UNLINK_BACKOFF * (attempt + 1))
        logger.warning(
            "Failed to remove lock file %s after %d attempts: %s. "
            "A stale lock file may remain; it will be reclaimed on the next "
            "acquisition (as an own-PID remnant, once the holder is confirmed "
            "dead, or after STALE_LOCK_MAX_AGE).",
            self.lock_path,
            _UNLINK_RETRIES,
            last_err,
        )

    def _read_holder_info(self) -> Optional[dict]:
        try:
            raw = self.lock_path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except (OSError, ValueError):
            return None
        return data if isinstance(data, dict) else None

    def _reclaim_if_stale(self) -> bool:
        """
        ロックファイルが stale（もう有効でない残骸）と判断できれば削除して
        True を返す。有効な保持者のロックは決して奪わない。

        判定順（重要）:

        1. **保持者 PID == 自プロセスの PID** → 残骸として回収。
           この関数が呼ばれる時点で、呼び出しスレッドは当該 .ssm パスの
           RLock を保持しており（`__enter__` 参照）、かつ reentry カウントが
           0（＝このプロセス内でまだ OS ロックを持っていない）。したがって
           同一プロセス内の他スレッドが正当に OS ロックを保持していることは
           あり得ず、自PIDのロックファイルは「前回 release の unlink 失敗で
           残った残骸」か「その PID を再利用した＝元の保持者は死んでいる」の
           いずれか。どちらも安全に回収できる（自己ロックアウトの回避）。

        2. **生存が確認できた保持者（liveness == "alive"）** → 回収しない。
           mtime がどれだけ古くても、正当な長時間保持者（大きな
           pull/merge/checkpoint）を横取りして .ssm を破損させてはならない。
           呼び出し側は待機し、必要ならタイムアウトして SSMLockError になる。

        3. **死んでいると確認できた保持者（liveness == "dead"）** → 回収。

        4. **生死を判定できない（liveness == "unknown"）** → age フォールバック。
           mtime が STALE_LOCK_MAX_AGE より古ければ回収する。この age ベースの
           判定は、生存が判定不能な場合（PID不明・Windows・権限不足 等）に
           **限って**適用される。
        """
        info = self._read_holder_info()
        pid = info.get("pid") if info else None

        # 1. 自プロセスの残骸ロック（自己ロックアウトの回避）
        if pid is not None and pid == os.getpid():
            return self._force_remove()

        liveness = _pid_liveness(pid)

        # 3. 死亡確認済み → 回収
        if liveness == "dead":
            return self._force_remove()

        # 2. 生存確認済み → 決して age で奪わない
        if liveness == "alive":
            return False

        # 4. 生死判定不能な場合のみ age フォールバック
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
