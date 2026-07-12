"""
benchmarks/compare.py - SessionSmith ベンチマーク結果の比較ツール

2つの `bench_ssm.py --out result.json` の出力を比較し、
同じ (operation, sweep, n_vars, total_bytes, n_history) の組み合わせについて
実行時間 (seconds) の劣化（回帰）を検出します。

Usage (standalone):
    python benchmarks/compare.py baseline.json current.json --threshold 20

`bench_ssm.py --baseline baseline.json` からも呼び出されます。
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any

# 比較のキーにする項目（この組み合わせが同じレコード同士を比較する）
GROUP_KEYS = ("operation", "sweep", "n_vars", "total_bytes", "n_history")


def load_results(path: str | Path) -> dict[str, Any]:
    """結果JSONファイルを読み込む。トップレベルが {"meta":..., "results":[...]} 形式。"""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if "results" not in data:
        raise ValueError(f"{path}: 'results' キーが見つかりません（bench_ssm.py の出力形式ではない可能性）")
    return data


def _group_key(record: dict[str, Any]) -> tuple:
    return tuple(record.get(k) for k in GROUP_KEYS)


def aggregate(results: list[dict[str, Any]]) -> dict[tuple, dict[str, float]]:
    """同一キーのレコードを集約する（seconds は中央値、peak_mem_bytes は平均）。

    中央値を使うのは、単発の遅い外れ値（GCやOSスケジューラのジッタ）に
    引きずられて偽の回帰を報告しないようにするため。
    """
    groups: dict[tuple, list[dict[str, Any]]] = {}
    for r in results:
        groups.setdefault(_group_key(r), []).append(r)

    aggregated: dict[tuple, dict[str, float]] = {}
    for key, records in groups.items():
        seconds = [r["seconds"] for r in records if r.get("seconds") is not None]
        peaks = [r["peak_mem_bytes"] for r in records if r.get("peak_mem_bytes") is not None]
        aggregated[key] = {
            "mean_seconds": statistics.median(seconds) if seconds else float("nan"),
            "mean_peak_mem_bytes": statistics.mean(peaks) if peaks else float("nan"),
            "n": len(records),
        }
    return aggregated


# ミリ秒未満の操作は、プロセス間のGC/OSスケジューラのジッタだけで
# 数十%の見かけ上の変化が生じうるため、絶対時間の差がこの値未満なら
# 閾値(%)を超えていても回帰として扱わない（ノイズ対策のフロア）。
DEFAULT_MIN_DELTA_SECONDS = 0.003


def compare_results(
    baseline: dict[str, Any],
    current: dict[str, Any],
    threshold_pct: float = 20.0,
    mem_threshold_pct: float | None = None,
    min_delta_seconds: float = DEFAULT_MIN_DELTA_SECONDS,
) -> dict[str, Any]:
    """
    baseline と current の結果を比較し、閾値を超える回帰を検出する。

    回帰として報告する条件は「相対悪化率 > threshold_pct」かつ
    「絶対時間差 > min_delta_seconds」の両方を満たすこと。後者のフロアが
    ないと、数ミリ秒未満の操作ではプロセス間ノイズだけで閾値を超えてしまい
    smoke プリセットのような高速な操作で常に「回帰」を誤検知してしまう。

    Returns:
        dict: {"regressions": [...], "improvements": [...], "matched": int, "unmatched": int}
        各要素は {key fields..., baseline_seconds, current_seconds, pct_change, kind}
    """
    base_agg = aggregate(baseline.get("results", []))
    cur_agg = aggregate(current.get("results", []))

    regressions: list[dict[str, Any]] = []
    improvements: list[dict[str, Any]] = []
    matched = 0
    unmatched = 0

    for key, cur_stats in cur_agg.items():
        if key not in base_agg:
            unmatched += 1
            continue
        matched += 1
        base_stats = base_agg[key]
        base_s = base_stats["mean_seconds"]
        cur_s = cur_stats["mean_seconds"]
        delta_s = cur_s - base_s

        record = dict(zip(GROUP_KEYS, key))
        record["baseline_seconds"] = base_s
        record["current_seconds"] = cur_s

        if base_s and base_s > 0:
            pct_change = delta_s / base_s * 100.0
        else:
            pct_change = 0.0
        record["pct_change"] = pct_change

        # メモリの変化も参考情報として付与
        base_m = base_stats["mean_peak_mem_bytes"]
        cur_m = cur_stats["mean_peak_mem_bytes"]
        if base_m and base_m > 0:
            record["mem_pct_change"] = (cur_m - base_m) / base_m * 100.0
        else:
            record["mem_pct_change"] = 0.0

        is_time_regression = pct_change > threshold_pct and delta_s > min_delta_seconds
        is_mem_regression = (
            mem_threshold_pct is not None and record["mem_pct_change"] > mem_threshold_pct
        )

        if is_time_regression:
            record["kind"] = "time_regression"
            regressions.append(record)
        elif is_mem_regression:
            record["kind"] = "mem_regression"
            regressions.append(record)
        elif pct_change < -threshold_pct and abs(delta_s) > min_delta_seconds:
            record["kind"] = "time_improvement"
            improvements.append(record)

    regressions.sort(key=lambda r: r["pct_change"], reverse=True)
    improvements.sort(key=lambda r: r["pct_change"])

    return {
        "regressions": regressions,
        "improvements": improvements,
        "matched": matched,
        "unmatched": unmatched,
        "threshold_pct": threshold_pct,
        "min_delta_seconds": min_delta_seconds,
    }


def format_report(comparison: dict[str, Any]) -> str:
    lines = []
    threshold = comparison["threshold_pct"]
    regressions = comparison["regressions"]
    improvements = comparison["improvements"]

    lines.append(
        f"比較結果: {comparison['matched']} 件マッチ, {comparison['unmatched']} 件は比較対象なし "
        f"(閾値: +{threshold:.1f}%)"
    )

    if regressions:
        lines.append(f"\n⚠ 回帰の可能性がある項目 ({len(regressions)} 件):")
        for r in regressions:
            kind_label = "mem" if r["kind"] == "mem_regression" else "time"
            lines.append(
                f"  [{kind_label}] {r['operation']:<10} sweep={r['sweep']:<12} "
                f"n_vars={r['n_vars']:<6} total_bytes={r['total_bytes']:<10} n_history={r['n_history']:<5} "
                f"{r['baseline_seconds']:.4f}s -> {r['current_seconds']:.4f}s "
                f"({r['pct_change']:+.1f}%, mem {r['mem_pct_change']:+.1f}%)"
            )
    else:
        lines.append("\n✓ 回帰は検出されませんでした")

    if improvements:
        lines.append(f"\n✓ 改善した項目 ({len(improvements)} 件):")
        for r in improvements:
            lines.append(
                f"  {r['operation']:<10} sweep={r['sweep']:<12} "
                f"n_vars={r['n_vars']:<6} total_bytes={r['total_bytes']:<10} n_history={r['n_history']:<5} "
                f"{r['baseline_seconds']:.4f}s -> {r['current_seconds']:.4f}s ({r['pct_change']:+.1f}%)"
            )

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SessionSmith ベンチマーク結果の比較")
    parser.add_argument("baseline", help="ベースライン結果JSONファイル")
    parser.add_argument("current", help="現在の結果JSONファイル")
    parser.add_argument(
        "--threshold", type=float, default=20.0,
        help="回帰とみなす実行時間の悪化率（%%）。デフォルト: 20.0",
    )
    parser.add_argument(
        "--min-delta-seconds", type=float, default=DEFAULT_MIN_DELTA_SECONDS,
        help=(
            "回帰と判定するために必要な絶対時間差（秒）の下限。"
            f"ミリ秒未満の操作でのノイズ誤検知を防ぐ。デフォルト: {DEFAULT_MIN_DELTA_SECONDS}"
        ),
    )
    parser.add_argument(
        "--fail-on-regression", action="store_true",
        help="回帰が検出された場合、終了コード1を返す（CIのゲートに使用可能）",
    )
    args = parser.parse_args(argv)

    baseline = load_results(args.baseline)
    current = load_results(args.current)
    comparison = compare_results(
        baseline, current, threshold_pct=args.threshold, min_delta_seconds=args.min_delta_seconds
    )
    print(format_report(comparison))

    if args.fail_on_regression and comparison["regressions"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
