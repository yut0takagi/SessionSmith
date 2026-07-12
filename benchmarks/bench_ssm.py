#!/usr/bin/env python3
"""
benchmarks/bench_ssm.py - SessionSmith 大規模セッション/チェックポイント/メモリのベンチマーク

GitHub issue #31 向けのベンチマーク基盤。

計測対象:
    - commit / checkout / diff / verify の壁時計時間とメモリ使用量
        - 変数の数 (n_vars) を変えたときの挙動
        - ペイロード総サイズ (total_bytes) を変えたときの挙動
        - 履歴の長さ (n_history, 事前コミット数) を変えたときの挙動
    - チェックポイント保存コスト（ペイロードサイズごとの1回あたりのコスト）
    - 繰り返しの commit/checkout サイクルによるメモリ増加傾向（リーク兆候）

計測は実際の `SessionSmith.ssm.SSM` API を、一時ディレクトリに作成した
実物の `.ssm/` に対して実行します（モックなし）。`SSM(globals_dict=...)` を
明示的に渡すことで、呼び出し元フレームの探索に頼らず、計測対象の変数集合を
厳密に制御しています（`ssm.commit()` 等のモジュールレベル関数は呼び出し元の
globals() を自動探索するため、ベンチマークスクリプトからは非決定的になり
使えません）。

Usage:
    python benchmarks/bench_ssm.py --smoke --out /tmp/smoke.json
    python benchmarks/bench_ssm.py --preset quick --out results.json
    python benchmarks/bench_ssm.py --preset heavy --out heavy.json
    python benchmarks/bench_ssm.py --smoke --baseline /tmp/smoke.json
"""

from __future__ import annotations

import argparse
import contextlib
import copy
import gc
import io
import json
import os
import platform
import random
import shutil
import sys
import tempfile
import time
import tracemalloc
import warnings
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# benchmarks/ を sys.path に追加して compare.py をインポート可能にする
_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

import compare as compare_mod  # noqa: E402

# リポジトリの SessionSmith を import できるようにする（editable install 前提だが保険で追加）
_REPO_ROOT = _THIS_DIR.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from SessionSmith import __version__ as SESSIONSMITH_VERSION  # noqa: E402
from SessionSmith.ssm import SSM, CheckpointContext  # noqa: E402

# psutil はオプショナル（未インストールでも動く。stdlib の tracemalloc/resource にフォールバック）
try:
    import psutil

    HAS_PSUTIL = True
except ImportError:
    psutil = None
    HAS_PSUTIL = False

try:
    import resource as _resource_mod

    HAS_RESOURCE = True
except ImportError:  # pragma: no cover - Windows
    _resource_mod = None
    HAS_RESOURCE = False


# ============================================================
# プリセット定義
# ============================================================

@dataclass
class Preset:
    name: str
    n_vars_sweep: list[int]
    total_bytes_sweep: list[int]
    n_history_sweep: list[int]
    base_n_vars: int
    base_total_bytes: int
    base_n_history: int
    repeats: int
    leak_cycles: int
    checkpoint_sizes: list[int]
    checkpoint_repeats: int
    checkpoint_n_vars: int = 10


PRESETS: dict[str, Preset] = {
    "smoke": Preset(
        name="smoke",
        n_vars_sweep=[1, 10],
        total_bytes_sweep=[1_000, 20_000],
        n_history_sweep=[0, 5],
        base_n_vars=5,
        base_total_bytes=5_000,
        base_n_history=0,
        repeats=1,
        leak_cycles=4,
        checkpoint_sizes=[1_000, 10_000],
        checkpoint_repeats=2,
        checkpoint_n_vars=3,
    ),
    "quick": Preset(
        name="quick",
        n_vars_sweep=[10, 100, 500],
        total_bytes_sweep=[10_000, 500_000, 5_000_000],
        n_history_sweep=[0, 20, 100],
        base_n_vars=50,
        base_total_bytes=1_000_000,
        base_n_history=0,
        repeats=2,
        leak_cycles=20,
        checkpoint_sizes=[10_000, 500_000, 2_000_000],
        checkpoint_repeats=8,
        checkpoint_n_vars=10,
    ),
    "heavy": Preset(
        name="heavy",
        n_vars_sweep=[100, 1_000, 5_000],
        total_bytes_sweep=[1_000_000, 20_000_000, 100_000_000],
        n_history_sweep=[0, 100, 500],
        base_n_vars=500,
        base_total_bytes=20_000_000,
        base_n_history=0,
        repeats=3,
        leak_cycles=50,
        checkpoint_sizes=[1_000_000, 20_000_000, 50_000_000],
        checkpoint_repeats=15,
        checkpoint_n_vars=20,
    ),
}


# ============================================================
# データ生成
# ============================================================

def make_variables(n_vars: int, total_bytes: int, seed: int) -> dict[str, bytes]:
    """
    n_vars 個の変数から成る dict を生成する。合計の pickle 前バイト数がおよそ
    total_bytes になるように、疑似乱数バイト列 (非圧縮性) を均等割りする。

    非圧縮性のランダムバイト列を使うことで、gzip 圧縮を「作業させる」実際の
    ワークロードに近い計測になる（全てゼロ埋めなどだと圧縮コストを過小評価する）。
    """
    if n_vars <= 0:
        return {}
    rng = random.Random(seed)
    base_size = max(total_bytes // n_vars, 0)
    remainder = max(total_bytes - base_size * n_vars, 0)

    variables: dict[str, bytes] = {}
    for i in range(n_vars):
        size = base_size + (remainder if i == n_vars - 1 else 0)
        variables[f"var_{i:06d}"] = rng.randbytes(size)
    return variables


# ============================================================
# メモリ計測ヘルパー
# ============================================================

def _current_rss_bytes() -> int | None:
    """可能であれば現在のプロセスRSS（常駐メモリ）をバイト単位で取得する。

    psutil が使えればそれを使い、なければ stdlib の resource モジュール
    (Unix系のみ、ru_maxrss は「これまでのピーク」であり瞬間値ではない点に注意) にフォールバックする。
    どちらも使えない場合は None を返す。
    """
    if HAS_PSUTIL:
        try:
            return psutil.Process(os.getpid()).memory_info().rss
        except Exception:
            return None
    if HAS_RESOURCE:
        try:
            usage = _resource_mod.getrusage(_resource_mod.RUSAGE_SELF).ru_maxrss
            # Linuxはkibibytes、macOS/BSDはbytes単位で返す
            if platform.system() == "Linux":
                return usage * 1024
            return usage
        except Exception:
            return None
    return None


@dataclass
class Measurement:
    seconds: float
    peak_mem_bytes: int
    current_mem_bytes: int
    rss_bytes: int | None


@contextlib.contextmanager
def _quiet():
    """計測対象のSSM呼び出しがstdoutに出す進捗メッセージ・warningsを抑制する。"""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), warnings.catch_warnings():
        warnings.simplefilter("ignore")
        yield


def measure(fn, *args, **kwargs) -> tuple[Any, Measurement]:
    """fn(*args, **kwargs) を1回実行し、壁時計時間とtracemallocメモリを計測する。"""
    gc.collect()
    tracemalloc.start()
    t0 = time.perf_counter()
    with _quiet():
        result = fn(*args, **kwargs)
    t1 = time.perf_counter()
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    rss = _current_rss_bytes()
    return result, Measurement(
        seconds=t1 - t0,
        peak_mem_bytes=peak,
        current_mem_bytes=current,
        rss_bytes=rss,
    )


# ============================================================
# 結果レコード
# ============================================================

@dataclass
class Record:
    operation: str
    sweep: str
    n_vars: int
    total_bytes: int
    n_history: int
    seconds: float
    peak_mem_bytes: int
    current_mem_bytes: int
    rss_bytes: int | None
    repeat: int
    preset: str
    label: str | None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation": self.operation,
            "sweep": self.sweep,
            "n_vars": self.n_vars,
            "total_bytes": self.total_bytes,
            "n_history": self.n_history,
            "seconds": self.seconds,
            "peak_mem_bytes": self.peak_mem_bytes,
            "current_mem_bytes": self.current_mem_bytes,
            "rss_bytes": self.rss_bytes,
            "repeat": self.repeat,
            "preset": self.preset,
            "label": self.label,
            "timestamp": self.timestamp,
        }


# ============================================================
# シナリオ計測（commit / checkout / diff / verify）
# ============================================================

@contextlib.contextmanager
def _temp_ssm_repo():
    """一時ディレクトリに実物の .ssm/ を初期化し、SSM インスタンスを渡す。終了後に必ず削除する。"""
    tmpdir = tempfile.mkdtemp(prefix="ssm_bench_")
    try:
        ssm_instance = SSM(path=tmpdir, globals_dict={})
        with _quiet():
            ssm_instance.init()
        yield ssm_instance
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def run_scenario(
    n_vars: int,
    total_bytes: int,
    n_history: int,
    seed: int,
    sweep: str,
    repeat: int,
    preset_name: str,
    label: str | None,
) -> list[Record]:
    """
    1つの (n_vars, total_bytes, n_history) シナリオについて、commit/checkout/diff/verify
    を実測し、各操作が実際に正しく動作したことをアサーションで確認する。
    """
    records: list[Record] = []

    with _temp_ssm_repo() as ssm_instance:
        # --- 履歴を積む（n_history 件の事前コミット） ---
        for i in range(n_history):
            filler = make_variables(n_vars, total_bytes, seed=seed * 100_003 + i)
            ssm_instance.globals_dict = filler
            with _quiet():
                h = ssm_instance.commit(f"filler {i}")
            if not h:
                raise RuntimeError("filler commit failed to return a hash")

        # --- 計測対象の変数を用意 ---
        variables = make_variables(n_vars, total_bytes, seed=seed)
        ssm_instance.globals_dict = dict(variables)

        # --- commit ---
        commit_hash, m = measure(ssm_instance.commit, "bench commit")
        if n_vars > 0 and not commit_hash:
            raise RuntimeError("commit() did not return a commit hash")
        records.append(Record(
            operation="commit", sweep=sweep, n_vars=n_vars, total_bytes=total_bytes,
            n_history=n_history, seconds=m.seconds, peak_mem_bytes=m.peak_mem_bytes,
            current_mem_bytes=m.current_mem_bytes, rss_bytes=m.rss_bytes,
            repeat=repeat, preset=preset_name, label=label,
        ))

        if n_vars == 0:
            # 変数がない場合は checkout/diff/verify は無意味（コミットが作られない）ためスキップ
            return records

        # --- checkout（globals_dictを空にしてから復元し、本当に復元されるか確認） ---
        ssm_instance.globals_dict = {}
        _, m = measure(ssm_instance.checkout, commit_hash)
        if len(ssm_instance.globals_dict) != n_vars:
            raise RuntimeError(
                f"checkout() restored {len(ssm_instance.globals_dict)} vars, expected {n_vars}"
            )
        records.append(Record(
            operation="checkout", sweep=sweep, n_vars=n_vars, total_bytes=total_bytes,
            n_history=n_history, seconds=m.seconds, peak_mem_bytes=m.peak_mem_bytes,
            current_mem_bytes=m.current_mem_bytes, rss_bytes=m.rss_bytes,
            repeat=repeat, preset=preset_name, label=label,
        ))

        # --- diff（HEADに対して現在の変数集合を比較。ここでは無変更なので "No changes" 経路） ---
        _, m = measure(ssm_instance.diff)
        records.append(Record(
            operation="diff", sweep=sweep, n_vars=n_vars, total_bytes=total_bytes,
            n_history=n_history, seconds=m.seconds, peak_mem_bytes=m.peak_mem_bytes,
            current_mem_bytes=m.current_mem_bytes, rss_bytes=m.rss_bytes,
            repeat=repeat, preset=preset_name, label=label,
        ))

        # --- verify ---
        result, m = measure(ssm_instance.verify, commit_hash)
        if not result.get("integrity_ok"):
            raise RuntimeError(f"verify() reported integrity_ok=False: {result}")
        records.append(Record(
            operation="verify", sweep=sweep, n_vars=n_vars, total_bytes=total_bytes,
            n_history=n_history, seconds=m.seconds, peak_mem_bytes=m.peak_mem_bytes,
            current_mem_bytes=m.current_mem_bytes, rss_bytes=m.rss_bytes,
            repeat=repeat, preset=preset_name, label=label,
        ))

    return records


def run_sweeps(preset: Preset, seed: int, label: str | None) -> list[Record]:
    records: list[Record] = []

    for n_vars in preset.n_vars_sweep:
        for r in range(preset.repeats):
            records.extend(run_scenario(
                n_vars=n_vars, total_bytes=preset.base_total_bytes, n_history=preset.base_n_history,
                seed=seed, sweep="n_vars", repeat=r, preset_name=preset.name, label=label,
            ))

    for total_bytes in preset.total_bytes_sweep:
        for r in range(preset.repeats):
            records.extend(run_scenario(
                n_vars=preset.base_n_vars, total_bytes=total_bytes, n_history=preset.base_n_history,
                seed=seed, sweep="total_bytes", repeat=r, preset_name=preset.name, label=label,
            ))

    for n_history in preset.n_history_sweep:
        for r in range(preset.repeats):
            records.extend(run_scenario(
                n_vars=preset.base_n_vars, total_bytes=preset.base_total_bytes, n_history=n_history,
                seed=seed, sweep="n_history", repeat=r, preset_name=preset.name, label=label,
            ))

    return records


# ============================================================
# チェックポイント・コスト計測
# ============================================================

def run_checkpoint_bench(preset: Preset, seed: int, label: str | None) -> list[Record]:
    """
    ペイロードサイズごとに `cp.step(force=True)` の1回あたりのコストを計測する。
    バックグラウンドスレッドやシグナルハンドラは使わず（計測ノイズになるため）、
    CheckpointContext の保存ロジックを直接、force=True で都度呼び出す。
    """
    records: list[Record] = []

    for total_bytes in preset.checkpoint_sizes:
        with _temp_ssm_repo() as ssm_instance:
            variables = make_variables(preset.checkpoint_n_vars, total_bytes, seed=seed)
            ssm_instance.globals_dict = dict(variables)

            ctx = CheckpointContext(
                ssm=ssm_instance,
                interval=10**9,  # バックグラウンドの自動保存が計測中に発火しないよう極端に長くする
                max_checkpoints=preset.checkpoint_repeats + 1,
            )
            # start() はバックグラウンドスレッド・シグナルハンドラ・atexitを登録するため
            # 計測ノイズを避けて、必要なディレクトリ作成だけ行う
            ctx.checkpoint_dir.mkdir(parents=True, exist_ok=True)

            for r in range(preset.checkpoint_repeats):
                _, m = measure(ctx.step, force=True)
                records.append(Record(
                    operation="checkpoint", sweep="checkpoint", n_vars=preset.checkpoint_n_vars,
                    total_bytes=total_bytes, n_history=0, seconds=m.seconds,
                    peak_mem_bytes=m.peak_mem_bytes, current_mem_bytes=m.current_mem_bytes,
                    rss_bytes=m.rss_bytes, repeat=r, preset=preset.name, label=label,
                ))

            saved = list(ctx.checkpoint_dir.glob("checkpoint_*.gz"))
            if not saved:
                raise RuntimeError("checkpoint bench: no checkpoint files were written")

    return records


# ============================================================
# メモリリーク兆候チェック
# ============================================================

def run_leak_check(preset: Preset, seed: int, label: str | None) -> list[Record]:
    """
    commit -> checkout を繰り返し、tracemallocで「保持され続けているメモリ」の
    推移を記録する。単調増加していればリークの兆候（false positiveもあり得るため、
    絶対的な証明ではなく "signal" として扱うこと。README参照。
    """
    records: list[Record] = []

    with _temp_ssm_repo() as ssm_instance:
        variables = make_variables(preset.base_n_vars, preset.base_total_bytes, seed=seed)

        gc.collect()
        tracemalloc.start()

        for cycle in range(preset.leak_cycles):
            ssm_instance.globals_dict = dict(variables)
            with _quiet():
                h = ssm_instance.commit(f"leak-check cycle {cycle}")
                if not h:
                    raise RuntimeError("leak check: commit() failed to return a hash")
                ssm_instance.globals_dict = {}
                ssm_instance.checkout(h)
            if len(ssm_instance.globals_dict) != preset.base_n_vars:
                raise RuntimeError("leak check: checkout() did not restore expected variable count")

            gc.collect()
            current, peak = tracemalloc.get_traced_memory()
            records.append(Record(
                operation="leak_cycle", sweep="leak", n_vars=preset.base_n_vars,
                total_bytes=preset.base_total_bytes, n_history=cycle, seconds=0.0,
                peak_mem_bytes=peak, current_mem_bytes=current, rss_bytes=_current_rss_bytes(),
                repeat=cycle, preset=preset.name, label=label,
            ))

        tracemalloc.stop()

    return records


MIN_LEAK_CYCLES_FOR_VERDICT = 8
MIN_LEAK_GROWTH_BYTES_FOR_VERDICT = 50_000  # 絶対的な下限。小さすぎるベースでの%ノイズを弾く


def summarize_leak_check(records: list[Record]) -> dict[str, Any]:
    """leak_cycle レコードから増加傾向を要約する。

    サイクル数が少ない場合（--smoke など）は統計的ノイズだけで「増加傾向あり」と
    誤判定しやすいため、判定に必要な最低サイクル数・最低増加量を設けている。
    それに満たない場合は verdict="insufficient_cycles_for_verdict" とし、
    観測値は出すが断定はしない。
    """
    cycles = [r for r in records if r.operation == "leak_cycle"]
    if len(cycles) < 2:
        return {"n_cycles": len(cycles), "verdict": "insufficient_data"}

    first, last = cycles[0], cycles[-1]
    growth_bytes = last.current_mem_bytes - first.current_mem_bytes
    growth_pct = (growth_bytes / first.current_mem_bytes * 100.0) if first.current_mem_bytes else 0.0

    # 単純な単調性チェック（ノイズに強くするため、増加している比率で判定）
    increases = sum(
        1 for a, b in zip(cycles, cycles[1:]) if b.current_mem_bytes > a.current_mem_bytes
    )
    monotonic_ratio = increases / (len(cycles) - 1)

    if len(cycles) < MIN_LEAK_CYCLES_FOR_VERDICT:
        verdict = "insufficient_cycles_for_verdict"
    elif (
        growth_pct > 20.0
        and monotonic_ratio > 0.7
        and growth_bytes > MIN_LEAK_GROWTH_BYTES_FOR_VERDICT
    ):
        verdict = "possible_leak_signal"
    else:
        verdict = "no_obvious_growth"

    return {
        "n_cycles": len(cycles),
        "first_current_mem_bytes": first.current_mem_bytes,
        "last_current_mem_bytes": last.current_mem_bytes,
        "growth_bytes": growth_bytes,
        "growth_pct": growth_pct,
        "monotonic_increase_ratio": monotonic_ratio,
        "peak_mem_bytes_max": max(r.peak_mem_bytes for r in cycles),
        "verdict": verdict,
    }


# ============================================================
# 表示・出力
# ============================================================

def _human_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if abs(n) < 1024.0:
            return f"{n:.1f}{unit}"
        n /= 1024.0
    return f"{n:.1f}TB"


def print_table(records: list[Record]) -> None:
    if not records:
        print("(no records)")
        return

    header = (
        f"{'operation':<10} {'sweep':<12} {'n_vars':>7} {'total_bytes':>12} "
        f"{'n_history':>9} {'rep':>3}  {'seconds':>10}  {'peak_mem':>10}  {'rss':>10}"
    )
    print(header)
    print("-" * len(header))
    for r in records:
        rss_str = _human_bytes(r.rss_bytes) if r.rss_bytes is not None else "n/a"
        print(
            f"{r.operation:<10} {r.sweep:<12} {r.n_vars:>7} {_human_bytes(r.total_bytes):>12} "
            f"{r.n_history:>9} {r.repeat:>3}  {r.seconds:>10.4f}  "
            f"{_human_bytes(r.peak_mem_bytes):>10}  {rss_str:>10}"
        )


def print_leak_summary(summary: dict[str, Any]) -> None:
    print("\n--- メモリリーク兆候チェック ---")
    if summary.get("verdict") == "insufficient_data":
        print("  データ不足（cycle数が少なすぎます）")
        return
    print(f"  cycles: {summary['n_cycles']}")
    print(f"  current_mem: {_human_bytes(summary['first_current_mem_bytes'])} -> "
          f"{_human_bytes(summary['last_current_mem_bytes'])} "
          f"({summary['growth_pct']:+.1f}%)")
    print(f"  peak_mem (max over cycles): {_human_bytes(summary['peak_mem_bytes_max'])}")
    print(f"  monotonic increase ratio: {summary['monotonic_increase_ratio']:.2f}")
    verdict_label = {
        "possible_leak_signal": "⚠ 増加傾向あり（リークの可能性 - 要調査）",
        "no_obvious_growth": "✓ 明確な増加傾向なし",
        "insufficient_cycles_for_verdict": (
            f"(参考値のみ: サイクル数 < {MIN_LEAK_CYCLES_FOR_VERDICT} のため断定しない。"
            " quick/heavy プリセットで再確認してください)"
        ),
    }.get(summary["verdict"], summary["verdict"])
    print(f"  verdict: {verdict_label}")


def build_output(
    records: list[Record],
    preset: Preset,
    args: argparse.Namespace,
    leak_summary: dict[str, Any],
) -> dict[str, Any]:
    return {
        "meta": {
            "preset": preset.name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "python_version": sys.version,
            "platform": platform.platform(),
            "sessionsmith_version": SESSIONSMITH_VERSION,
            "seed": args.seed,
            "label": args.label,
            "has_psutil": HAS_PSUTIL,
            "leak_check_summary": leak_summary,
        },
        "results": [r.to_dict() for r in records],
    }


# ============================================================
# CLI
# ============================================================

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="SessionSmith 大規模セッション/チェックポイント/メモリのベンチマーク"
    )
    parser.add_argument(
        "--preset", choices=sorted(PRESETS.keys()), default="quick",
        help="使用するプリセット（既定: quick）",
    )
    parser.add_argument(
        "--smoke", action="store_true",
        help="CI向けの極小プリセットで実行する（--preset smoke と同じ）",
    )
    parser.add_argument("--seed", type=int, default=42, help="乱数シード（既定: 42）")
    parser.add_argument("--label", type=str, default=None, help="結果に付与する任意ラベル")
    parser.add_argument("--out", type=str, default=None, help="結果を書き込むJSONファイルパス")
    parser.add_argument(
        "--baseline", type=str, default=None,
        help="このJSONファイルと比較し、回帰を検出する（compare.py と同等の処理）",
    )
    parser.add_argument(
        "--threshold", type=float, default=20.0,
        help="--baseline 使用時、回帰とみなす実行時間の悪化率（%%）。既定: 20.0",
    )
    parser.add_argument(
        "--skip-checkpoint", action="store_true", help="チェックポイントベンチマークをスキップする",
    )
    parser.add_argument(
        "--skip-leak-check", action="store_true", help="メモリリーク兆候チェックをスキップする",
    )
    # 個別スイープの上書き（カンマ区切りの整数リスト）
    parser.add_argument("--n-vars-sweep", type=str, default=None, help="例: 10,100,1000")
    parser.add_argument("--total-bytes-sweep", type=str, default=None, help="例: 10000,1000000")
    parser.add_argument("--n-history-sweep", type=str, default=None, help="例: 0,10,50")

    return parser.parse_args(argv)


def _parse_int_list(s: str | None) -> list[int] | None:
    if s is None:
        return None
    return [int(x.strip()) for x in s.split(",") if x.strip()]


def resolve_preset(args: argparse.Namespace) -> Preset:
    name = "smoke" if args.smoke else args.preset
    preset = copy.deepcopy(PRESETS[name])

    n_vars_override = _parse_int_list(args.n_vars_sweep)
    total_bytes_override = _parse_int_list(args.total_bytes_sweep)
    n_history_override = _parse_int_list(args.n_history_sweep)

    if n_vars_override is not None:
        preset.n_vars_sweep = n_vars_override
    if total_bytes_override is not None:
        preset.total_bytes_sweep = total_bytes_override
    if n_history_override is not None:
        preset.n_history_sweep = n_history_override

    return preset


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    preset = resolve_preset(args)

    print(f"=== SessionSmith benchmark (preset={preset.name}) ===")
    if not HAS_PSUTIL:
        print("(注意: psutil未検出。rss列は resource モジュールへフォールバックします)")

    t_start = time.perf_counter()

    records = run_sweeps(preset, seed=args.seed, label=args.label)

    if not args.skip_checkpoint:
        records.extend(run_checkpoint_bench(preset, seed=args.seed, label=args.label))

    leak_summary: dict[str, Any] = {"verdict": "skipped"}
    if not args.skip_leak_check:
        leak_records = run_leak_check(preset, seed=args.seed, label=args.label)
        records.extend(leak_records)
        leak_summary = summarize_leak_check(leak_records)

    t_total = time.perf_counter() - t_start

    print()
    print_table(records)
    if not args.skip_leak_check:
        print_leak_summary(leak_summary)
    print(f"\n合計実行時間: {t_total:.2f}s / レコード数: {len(records)}")

    output = build_output(records, preset, args, leak_summary)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        print(f"\n結果を書き込みました: {out_path}")

    exit_code = 0
    if args.baseline:
        baseline_data = compare_mod.load_results(args.baseline)
        comparison = compare_mod.compare_results(baseline_data, output, threshold_pct=args.threshold)
        print()
        print(compare_mod.format_report(comparison))
        if comparison["regressions"]:
            exit_code = 1

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
