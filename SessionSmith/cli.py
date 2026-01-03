#!/usr/bin/env python3
"""
SessionSmith CLI - Git風セッション管理コマンドラインツール

使用例:
    ssm init                    # 初期化
    ssm commit -m "message"     # コミット
    ssm log                     # 履歴表示
    ssm checkout abc123         # 復元
    ssm status                  # 状態表示
    ssm watch --interval 10     # 監視モード
    ssm stats                   # 分析
    ssm dashboard               # ダッシュボード
"""

import argparse
import sys
import os
import json
import time
import signal
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any

# SSMモジュールをインポート
from .ssm import SSM


def get_ssm(path: Optional[str] = None) -> SSM:
    """SSMインスタンスを取得"""
    return SSM(path=path)


def cmd_init(args):
    """ssm init - 初期化"""
    ssm = get_ssm(args.path)
    ssm.init(force=args.force)


def cmd_commit(args):
    """ssm commit - コミット"""
    ssm = get_ssm()
    
    if not ssm.is_initialized:
        print("Error: SSM not initialized. Run 'ssm init' first.", file=sys.stderr)
        sys.exit(1)
    
    # CLIからはグローバル変数を取得できないので、
    # 最新のスナップショットまたは監視データを使用
    snapshot_path = ssm.ssm_path / "snapshots" / "latest"
    
    if not snapshot_path.exists():
        print("Error: No snapshot found. Run 'ssm watch' first to capture variables.", file=sys.stderr)
        sys.exit(1)
    
    # スナップショットを読み込んでコミット
    import gzip
    import pickle
    
    with gzip.open(snapshot_path, 'rb') as f:
        variables = pickle.load(f)
    
    # 各変数をオブジェクトとして保存
    var_hashes: Dict[str, Dict[str, Any]] = {}
    for name, value in variables.items():
        data = pickle.dumps(value)
        obj_hash = ssm._store_object(data)
        var_hashes[name] = {
            "hash": obj_hash,
            "type": type(value).__name__,
            "size": len(data),
        }
    
    # 親コミットを取得
    head_file = ssm.ssm_path / "HEAD"
    parent = head_file.read_text().strip() or None
    
    # コミット情報を作成
    commit_data = {
        "message": args.message or "CLI commit",
        "author": args.author or os.environ.get("USER", "unknown"),
        "timestamp": datetime.now().isoformat(),
        "parent": parent,
        "variables": var_hashes,
    }
    
    # コミットを保存
    commit_bytes = json.dumps(commit_data, indent=2).encode('utf-8')
    commit_hash = ssm._hash_object(commit_bytes)
    
    commit_path = ssm.ssm_path / "commits" / f"{commit_hash}.json"
    ssm._write_json(commit_path, commit_data)
    
    # HEADを更新
    head_file.write_text(commit_hash)
    
    var_count = len(variables)
    short_hash = commit_hash[:7]
    print(f"✓ [{short_hash}] {args.message or 'CLI commit'} ({var_count} variables)")


def cmd_log(args):
    """ssm log - 履歴表示"""
    ssm = get_ssm()
    
    if not ssm.is_initialized:
        print("Error: SSM not initialized. Run 'ssm init' first.", file=sys.stderr)
        sys.exit(1)
    
    head_file = ssm.ssm_path / "HEAD"
    current = head_file.read_text().strip()
    
    if not current:
        print("No commits yet")
        return
    
    count = 0
    limit = args.limit or 10
    
    while current and count < limit:
        commit_path = ssm.ssm_path / "commits" / f"{current}.json"
        if not commit_path.exists():
            break
        
        commit_data = ssm._read_json(commit_path)
        var_count = len(commit_data.get("variables", {}))
        
        if args.oneline:
            print(f"{current[:7]} {commit_data['message']} ({var_count} vars)")
        else:
            print(f"\n\033[33mcommit {current}\033[0m")
            print(f"Author: {commit_data['author']}")
            print(f"Date:   {commit_data['timestamp']}")
            print(f"\n    {commit_data['message']}")
            print(f"    ({var_count} variables)")
        
        current = commit_data.get("parent")
        count += 1


def cmd_status(args):
    """ssm status - 状態表示"""
    ssm = get_ssm()
    
    if not ssm.is_initialized:
        print("Error: SSM not initialized. Run 'ssm init' first.", file=sys.stderr)
        sys.exit(1)
    
    head_file = ssm.ssm_path / "HEAD"
    current = head_file.read_text().strip()
    
    print(f"On commit: {current[:7] if current else '(none)'}")
    
    # 最新スナップショットの情報
    snapshot_path = ssm.ssm_path / "snapshots" / "latest"
    if snapshot_path.exists():
        import gzip
        import pickle
        
        with gzip.open(snapshot_path, 'rb') as f:
            variables = pickle.load(f)
        
        mtime = datetime.fromtimestamp(snapshot_path.stat().st_mtime)
        print(f"Last snapshot: {mtime.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Variables: {len(variables)}")
        
        if args.verbose:
            print("\nTracked variables:")
            for name, value in sorted(variables.items()):
                type_name = type(value).__name__
                print(f"  {name}: {type_name}")
    else:
        print("No snapshot yet")
    
    # 監視状態
    watch_pid_file = ssm.ssm_path / "watch.pid"
    if watch_pid_file.exists():
        pid = watch_pid_file.read_text().strip()
        print(f"Watch process: PID {pid}")


def cmd_checkout(args):
    """ssm checkout - 復元"""
    ssm = get_ssm()
    
    if not ssm.is_initialized:
        print("Error: SSM not initialized. Run 'ssm init' first.", file=sys.stderr)
        sys.exit(1)
    
    commit_hash = args.commit
    
    if not commit_hash:
        # HEADを使用
        head_file = ssm.ssm_path / "HEAD"
        commit_hash = head_file.read_text().strip()
        if not commit_hash:
            print("Error: No commits to checkout", file=sys.stderr)
            sys.exit(1)
    
    # 短縮ハッシュを展開
    full_hash = ssm._resolve_hash(commit_hash)
    
    commit_path = ssm.ssm_path / "commits" / f"{full_hash}.json"
    if not commit_path.exists():
        print(f"Error: Commit not found: {commit_hash}", file=sys.stderr)
        sys.exit(1)
    
    commit_data = ssm._read_json(commit_path)
    
    # 変数を復元してスナップショットに保存
    import gzip
    import pickle
    
    variables = {}
    for name, var_info in commit_data.get("variables", {}).items():
        try:
            data = ssm._load_object(var_info["hash"])
            value = pickle.loads(data)
            variables[name] = value
        except Exception as e:
            print(f"Warning: Failed to restore '{name}': {e}", file=sys.stderr)
    
    # スナップショットに保存
    snapshot_path = ssm.ssm_path / "snapshots" / "latest"
    with gzip.open(snapshot_path, 'wb') as f:
        pickle.dump(variables, f)
    
    print(f"✓ Restored {len(variables)} variables from {full_hash[:7]}")
    print(f"  Snapshot saved to: {snapshot_path}")


def cmd_diff(args):
    """ssm diff - 差分表示"""
    ssm = get_ssm()
    
    if not ssm.is_initialized:
        print("Error: SSM not initialized. Run 'ssm init' first.", file=sys.stderr)
        sys.exit(1)
    
    head_file = ssm.ssm_path / "HEAD"
    current = head_file.read_text().strip()
    
    if not current:
        print("No commits to compare")
        return
    
    # 最新スナップショットとコミットを比較
    snapshot_path = ssm.ssm_path / "snapshots" / "latest"
    if not snapshot_path.exists():
        print("No snapshot to compare")
        return
    
    import gzip
    import pickle
    
    with gzip.open(snapshot_path, 'rb') as f:
        snapshot_vars = pickle.load(f)
    
    commit_path = ssm.ssm_path / "commits" / f"{current}.json"
    commit_data = ssm._read_json(commit_path)
    committed_vars = set(commit_data.get("variables", {}).keys())
    current_vars = set(snapshot_vars.keys())
    
    added = current_vars - committed_vars
    removed = committed_vars - current_vars
    
    if added:
        print("\033[32mNew variables:\033[0m")
        for name in sorted(added):
            print(f"  + {name}")
    
    if removed:
        print("\033[31mRemoved variables:\033[0m")
        for name in sorted(removed):
            print(f"  - {name}")
    
    if not added and not removed:
        print("No changes")


def cmd_watch(args):
    """ssm watch - 監視モード"""
    ssm = get_ssm()
    
    if not ssm.is_initialized:
        print("Error: SSM not initialized. Run 'ssm init' first.", file=sys.stderr)
        sys.exit(1)
    
    interval = args.interval
    target = args.target or "."
    
    print(f"Watching: {target}")
    print(f"Interval: {interval} seconds")
    print("Press Ctrl+C to stop\n")
    
    # PIDファイルを作成
    watch_pid_file = ssm.ssm_path / "watch.pid"
    watch_pid_file.write_text(str(os.getpid()))
    
    # 監視履歴ファイル
    watch_log = ssm.ssm_path / "watch.log"
    
    def cleanup(signum=None, frame=None):
        if watch_pid_file.exists():
            watch_pid_file.unlink()
        print("\n✓ Watch stopped")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)
    
    snapshot_count = 0
    
    try:
        while True:
            timestamp = datetime.now()
            
            # Pythonファイルを検索して実行中のプロセスの変数を取得
            # （ここでは簡易的にスナップショットのタイムスタンプを記録）
            
            snapshot_path = ssm.ssm_path / "snapshots" / "latest"
            continuous_path = ssm.ssm_path / "continuous" / "autosave"
            
            # 監視ログに記録
            log_entry = {
                "timestamp": timestamp.isoformat(),
                "snapshot_exists": snapshot_path.exists(),
                "continuous_exists": continuous_path.exists(),
            }
            
            if snapshot_path.exists():
                import gzip
                import pickle
                
                try:
                    with gzip.open(snapshot_path, 'rb') as f:
                        variables = pickle.load(f)
                    
                    log_entry["variable_count"] = len(variables)
                    log_entry["variables"] = {
                        name: {
                            "type": type(value).__name__,
                            "size": len(pickle.dumps(value)),
                        }
                        for name, value in variables.items()
                    }
                except Exception as e:
                    log_entry["error"] = str(e)
            
            # ログに追記
            with open(watch_log, 'a') as f:
                f.write(json.dumps(log_entry) + "\n")
            
            snapshot_count += 1
            var_count = log_entry.get("variable_count", 0)
            print(f"[{timestamp.strftime('%H:%M:%S')}] Snapshot #{snapshot_count}: {var_count} variables")
            
            time.sleep(interval)
    
    finally:
        cleanup()


def cmd_stats(args):
    """ssm stats - 分析"""
    ssm = get_ssm()
    
    if not ssm.is_initialized:
        print("Error: SSM not initialized. Run 'ssm init' first.", file=sys.stderr)
        sys.exit(1)
    
    watch_log = ssm.ssm_path / "watch.log"
    
    if not watch_log.exists():
        print("No watch data found. Run 'ssm watch' first.", file=sys.stderr)
        sys.exit(1)
    
    # ログを読み込み
    entries = []
    with open(watch_log, 'r') as f:
        for line in f:
            try:
                entries.append(json.loads(line.strip()))
            except json.JSONDecodeError:
                continue
    
    if not entries:
        print("No data in watch log")
        return
    
    print(f"Watch Log Analysis")
    print(f"=" * 50)
    print(f"Total snapshots: {len(entries)}")
    
    if entries:
        first = datetime.fromisoformat(entries[0]["timestamp"])
        last = datetime.fromisoformat(entries[-1]["timestamp"])
        duration = last - first
        print(f"Duration: {duration}")
        print(f"First: {first.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Last:  {last.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 変数の統計
    all_vars: Dict[str, List[Dict]] = {}
    
    for entry in entries:
        if "variables" in entry:
            timestamp = entry["timestamp"]
            for name, info in entry["variables"].items():
                if name not in all_vars:
                    all_vars[name] = []
                all_vars[name].append({
                    "timestamp": timestamp,
                    **info
                })
    
    if all_vars:
        print(f"\nVariables tracked: {len(all_vars)}")
        print(f"\n{'Variable':<20} {'Type':<15} {'Appearances':<12} {'Avg Size':<12}")
        print("-" * 60)
        
        for name, records in sorted(all_vars.items()):
            var_type = records[-1]["type"]
            appearances = len(records)
            avg_size = sum(r["size"] for r in records) / len(records)
            print(f"{name:<20} {var_type:<15} {appearances:<12} {avg_size:,.0f} bytes")
    
    # グラフ表示（簡易ASCII）
    if args.graph and entries:
        print(f"\nVariable Count Over Time")
        print("-" * 50)
        
        counts = [e.get("variable_count", 0) for e in entries]
        max_count = max(counts) if counts else 0
        
        if max_count > 0:
            for i, count in enumerate(counts[-20:]):  # 最新20件
                bar_len = int(count / max_count * 30)
                bar = "█" * bar_len
                print(f"{count:3d} |{bar}")


def cmd_dashboard(args):
    """ssm dashboard - ダッシュボード"""
    ssm = get_ssm()
    
    if not ssm.is_initialized:
        print("Error: SSM not initialized. Run 'ssm init' first.", file=sys.stderr)
        sys.exit(1)
    
    port = args.port
    
    print(f"Starting dashboard on http://localhost:{port}")
    print("Press Ctrl+C to stop\n")
    
    # 簡易HTTPサーバー
    from http.server import HTTPServer, BaseHTTPRequestHandler
    import json
    
    class DashboardHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/":
                self.send_response(200)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                self.wfile.write(self._get_dashboard_html().encode())
            elif self.path == "/api/status":
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(self._get_status()).encode())
            elif self.path == "/api/log":
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(self._get_watch_log()).encode())
            else:
                self.send_response(404)
                self.end_headers()
        
        def log_message(self, format, *args):
            pass  # 静かに
        
        def _get_status(self):
            head_file = ssm.ssm_path / "HEAD"
            current = head_file.read_text().strip() if head_file.exists() else None
            
            snapshot_path = ssm.ssm_path / "snapshots" / "latest"
            variables = {}
            
            if snapshot_path.exists():
                import gzip
                import pickle
                try:
                    with gzip.open(snapshot_path, 'rb') as f:
                        data = pickle.load(f)
                    variables = {
                        name: {"type": type(value).__name__}
                        for name, value in data.items()
                    }
                except Exception:
                    pass
            
            return {
                "head": current,
                "variable_count": len(variables),
                "variables": variables,
                "timestamp": datetime.now().isoformat(),
            }
        
        def _get_watch_log(self):
            watch_log = ssm.ssm_path / "watch.log"
            entries = []
            
            if watch_log.exists():
                with open(watch_log, 'r') as f:
                    for line in f:
                        try:
                            entries.append(json.loads(line.strip()))
                        except json.JSONDecodeError:
                            continue
            
            return entries[-100:]  # 最新100件
        
        def _get_dashboard_html(self):
            return '''<!DOCTYPE html>
<html>
<head>
    <title>SSM Dashboard</title>
    <meta charset="utf-8">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0d1117; 
            color: #c9d1d9; 
            padding: 20px;
        }
        h1 { color: #58a6ff; margin-bottom: 20px; }
        .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
        .card { 
            background: #161b22; 
            border: 1px solid #30363d; 
            border-radius: 6px; 
            padding: 16px;
        }
        .card h2 { color: #8b949e; font-size: 14px; margin-bottom: 12px; }
        .stat { font-size: 32px; font-weight: bold; color: #58a6ff; }
        .var-list { max-height: 300px; overflow-y: auto; }
        .var-item { 
            padding: 8px; 
            border-bottom: 1px solid #30363d;
            display: flex;
            justify-content: space-between;
        }
        .var-name { color: #f0883e; }
        .var-type { color: #8b949e; }
        .chart { height: 200px; display: flex; align-items: flex-end; gap: 2px; }
        .bar { background: #238636; min-width: 10px; }
        .refresh { color: #8b949e; font-size: 12px; margin-top: 10px; }
    </style>
</head>
<body>
    <h1>🔧 SSM Dashboard</h1>
    <div class="grid">
        <div class="card">
            <h2>STATUS</h2>
            <div class="stat" id="var-count">-</div>
            <div>variables tracked</div>
            <div class="refresh" id="last-update">-</div>
        </div>
        <div class="card">
            <h2>HEAD</h2>
            <div class="stat" id="head" style="font-size: 20px;">-</div>
        </div>
        <div class="card">
            <h2>VARIABLES</h2>
            <div class="var-list" id="var-list"></div>
        </div>
        <div class="card">
            <h2>HISTORY</h2>
            <div class="chart" id="chart"></div>
        </div>
    </div>
    <script>
        async function refresh() {
            try {
                const status = await (await fetch('/api/status')).json();
                document.getElementById('var-count').textContent = status.variable_count;
                document.getElementById('head').textContent = status.head ? status.head.slice(0, 7) : '(none)';
                document.getElementById('last-update').textContent = 'Updated: ' + new Date().toLocaleTimeString();
                
                const varList = document.getElementById('var-list');
                varList.innerHTML = Object.entries(status.variables)
                    .map(([name, info]) => `<div class="var-item"><span class="var-name">${name}</span><span class="var-type">${info.type}</span></div>`)
                    .join('');
                
                const log = await (await fetch('/api/log')).json();
                const chart = document.getElementById('chart');
                const maxCount = Math.max(...log.map(e => e.variable_count || 0), 1);
                chart.innerHTML = log.slice(-50).map(e => {
                    const height = ((e.variable_count || 0) / maxCount) * 180;
                    return `<div class="bar" style="height: ${height}px" title="${e.variable_count} vars"></div>`;
                }).join('');
            } catch (e) {
                console.error(e);
            }
        }
        refresh();
        setInterval(refresh, 2000);
    </script>
</body>
</html>'''
    
    try:
        server = HTTPServer(("localhost", port), DashboardHandler)
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n✓ Dashboard stopped")


def cmd_export(args):
    """ssm export - エクスポート"""
    ssm = get_ssm()
    
    if not ssm.is_initialized:
        print("Error: SSM not initialized. Run 'ssm init' first.", file=sys.stderr)
        sys.exit(1)
    
    output = args.output
    format_type = args.format
    
    watch_log = ssm.ssm_path / "watch.log"
    
    if not watch_log.exists():
        print("No watch data to export", file=sys.stderr)
        sys.exit(1)
    
    entries = []
    with open(watch_log, 'r') as f:
        for line in f:
            try:
                entries.append(json.loads(line.strip()))
            except json.JSONDecodeError:
                continue
    
    if format_type == "json":
        with open(output, 'w') as f:
            json.dump(entries, f, indent=2)
    elif format_type == "csv":
        import csv
        with open(output, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "variable_count"])
            for entry in entries:
                writer.writerow([entry["timestamp"], entry.get("variable_count", 0)])
    
    print(f"✓ Exported to {output}")


def cmd_export_session(args):
    """ssm export-session - コミットを従来形式でエクスポート"""
    ssm = get_ssm()
    
    if not ssm.is_initialized:
        print("Error: SSM not initialized. Run 'ssm init' first.", file=sys.stderr)
        sys.exit(1)
    
    try:
        ssm.export(
            output_path=args.output,
            commit_hash=args.commit,
            compress=args.compress,
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_import_session(args):
    """ssm import-session - 従来形式からインポート"""
    ssm = get_ssm()
    
    if not ssm.is_initialized:
        print("Error: SSM not initialized. Run 'ssm init' first.", file=sys.stderr)
        sys.exit(1)
    
    try:
        ssm.import_session(
            input_path=args.input,
            message=args.message,
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_convert(args):
    """ssm convert - ファイル形式を変換"""
    ssm = get_ssm()
    ssm.init()  # 変換のみなので初期化が必要
    
    try:
        ssm.convert(
            input_path=args.input,
            output_path=args.output,
            compress=args.compress,
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_branch(args):
    """ssm branch - ブランチの作成・一覧表示"""
    ssm = get_ssm()
    
    if not ssm.is_initialized:
        print("Error: SSM not initialized. Run 'ssm init' first.", file=sys.stderr)
        sys.exit(1)
    
    if args.create:
        if not args.name:
            print("Error: Branch name required when creating a branch.", file=sys.stderr)
            sys.exit(1)
        try:
            ssm.branch(args.name, create=True)
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
    elif args.name:
        # ブランチの存在確認
        branches = ssm.branch()
        if args.name in branches:
            print(f"Branch '{args.name}' exists")
        else:
            print(f"Branch '{args.name}' does not exist", file=sys.stderr)
            sys.exit(1)
    else:
        # ブランチ一覧表示
        branches = ssm.branch()
        current = ssm.get_current_branch()
        
        if not branches:
            print("No branches")
        else:
            for branch_name in branches:
                marker = "* " if branch_name == current else "  "
                print(f"{marker}{branch_name}")


def cmd_checkout_branch(args):
    """ssm checkout-branch - ブランチに切り替え"""
    ssm = get_ssm()
    
    if not ssm.is_initialized:
        print("Error: SSM not initialized. Run 'ssm init' first.", file=sys.stderr)
        sys.exit(1)
    
    try:
        ssm.checkout_branch(args.branch)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_merge(args):
    """ssm merge - ブランチをマージ"""
    ssm = get_ssm()
    
    if not ssm.is_initialized:
        print("Error: SSM not initialized. Run 'ssm init' first.", file=sys.stderr)
        sys.exit(1)
    
    try:
        ssm.merge(args.branch, message=args.message)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_tag(args):
    """ssm tag - タグの作成・一覧表示"""
    ssm = get_ssm()
    
    if not ssm.is_initialized:
        print("Error: SSM not initialized. Run 'ssm init' first.", file=sys.stderr)
        sys.exit(1)
    
    if args.list:
        # タグ一覧表示
        tags = ssm.list_tags()
        if not tags:
            print("No tags")
        else:
            for tag_info in tags:
                print(f"{tag_info['name']} -> {tag_info['commit'][:7]} ({tag_info['message']})")
    elif args.name:
        # タグ作成
        try:
            ssm.tag(args.name, commit_hash=args.commit, message=args.message)
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        print("Error: Tag name required or use --list to list tags.", file=sys.stderr)
        sys.exit(1)


def cmd_checkout_tag(args):
    """ssm checkout-tag - タグからチェックアウト"""
    ssm = get_ssm()
    
    if not ssm.is_initialized:
        print("Error: SSM not initialized. Run 'ssm init' first.", file=sys.stderr)
        sys.exit(1)
    
    try:
        ssm.checkout_tag(args.tag)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_remote(args):
    """ssm remote - リモートの追加・一覧表示"""
    ssm = get_ssm()
    
    if not ssm.is_initialized:
        print("Error: SSM not initialized. Run 'ssm init' first.", file=sys.stderr)
        sys.exit(1)
    
    if args.add:
        if not args.name or not args.url:
            print("Error: Remote name and URL required when adding a remote.", file=sys.stderr)
            sys.exit(1)
        try:
            ssm.remote_add(args.name, args.url)
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        # リモート一覧表示
        remotes = ssm.remote_list()
        if not remotes:
            print("No remotes")
        else:
            for name, url in remotes.items():
                print(f"{name}\t{url}")


def cmd_push(args):
    """ssm push - リモートにプッシュ"""
    ssm = get_ssm()
    
    if not ssm.is_initialized:
        print("Error: SSM not initialized. Run 'ssm init' first.", file=sys.stderr)
        sys.exit(1)
    
    try:
        ssm.push(remote_name=args.remote, branch_name=args.branch)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_pull(args):
    """ssm pull - リモートからプル"""
    ssm = get_ssm()
    
    if not ssm.is_initialized:
        print("Error: SSM not initialized. Run 'ssm init' first.", file=sys.stderr)
        sys.exit(1)
    
    try:
        ssm.pull(remote_name=args.remote, branch_name=args.branch)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    from . import __version__
    
    parser = argparse.ArgumentParser(
        prog="ssm",
        description="SessionSmith - Git-style session management"
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # init
    init_parser = subparsers.add_parser("init", help="Initialize SSM")
    init_parser.add_argument("--path", "-p", help="Directory path")
    init_parser.add_argument("--force", "-f", action="store_true", help="Force re-initialization")
    
    # commit
    commit_parser = subparsers.add_parser("commit", help="Commit current state")
    commit_parser.add_argument("--message", "-m", help="Commit message")
    commit_parser.add_argument("--author", "-a", help="Author name")
    
    # log
    log_parser = subparsers.add_parser("log", help="Show commit history")
    log_parser.add_argument("--limit", "-n", type=int, help="Limit number of commits")
    log_parser.add_argument("--oneline", action="store_true", help="One line format")
    
    # status
    status_parser = subparsers.add_parser("status", help="Show current status")
    status_parser.add_argument("--verbose", "-v", action="store_true", help="Show details")
    
    # checkout
    checkout_parser = subparsers.add_parser("checkout", help="Restore to a commit")
    checkout_parser.add_argument("commit", nargs="?", help="Commit hash")
    
    # diff
    diff_parser = subparsers.add_parser("diff", help="Show differences")
    
    # watch
    watch_parser = subparsers.add_parser("watch", help="Watch mode")
    watch_parser.add_argument("--interval", "-i", type=int, default=10, help="Interval in seconds")
    watch_parser.add_argument("--target", "-t", help="Target directory")
    
    # stats
    stats_parser = subparsers.add_parser("stats", help="Show statistics")
    stats_parser.add_argument("--graph", "-g", action="store_true", help="Show graph")
    
    # dashboard
    dashboard_parser = subparsers.add_parser("dashboard", help="Start dashboard")
    dashboard_parser.add_argument("--port", "-p", type=int, default=8080, help="Port number")
    
    # export (watch log)
    export_parser = subparsers.add_parser("export", help="Export watch log data")
    export_parser.add_argument("output", help="Output file")
    export_parser.add_argument("--format", "-f", choices=["json", "csv"], default="json", help="Format")
    
    # export-session
    export_session_parser = subparsers.add_parser("export-session", help="Export commit to .pkl/.json")
    export_session_parser.add_argument("output", help="Output file (e.g., backup.pkl)")
    export_session_parser.add_argument("--commit", "-c", help="Commit hash (default: HEAD)")
    export_session_parser.add_argument("--compress", "-z", action="store_true", help="Compress output")
    
    # import-session
    import_session_parser = subparsers.add_parser("import-session", help="Import from .pkl/.json")
    import_session_parser.add_argument("input", help="Input file (e.g., old_session.pkl)")
    import_session_parser.add_argument("--message", "-m", help="Commit message")
    
    # convert
    convert_parser = subparsers.add_parser("convert", help="Convert file format")
    convert_parser.add_argument("input", help="Input file")
    convert_parser.add_argument("output", help="Output file")
    convert_parser.add_argument("--compress", "-z", action="store_true", help="Compress output")
    
    # branch
    branch_parser = subparsers.add_parser("branch", help="List or create branches")
    branch_parser.add_argument("name", nargs="?", help="Branch name")
    branch_parser.add_argument("--create", "-c", action="store_true", help="Create a new branch")
    
    # checkout-branch
    checkout_branch_parser = subparsers.add_parser("checkout-branch", help="Switch to a branch")
    checkout_branch_parser.add_argument("branch", help="Branch name")
    
    # merge
    merge_parser = subparsers.add_parser("merge", help="Merge a branch")
    merge_parser.add_argument("branch", help="Branch to merge")
    merge_parser.add_argument("--message", "-m", help="Merge commit message")
    
    # tag
    tag_parser = subparsers.add_parser("tag", help="Create or list tags")
    tag_parser.add_argument("name", nargs="?", help="Tag name")
    tag_parser.add_argument("--commit", "-c", help="Commit hash (default: HEAD)")
    tag_parser.add_argument("--message", "-m", help="Tag message")
    tag_parser.add_argument("--list", "-l", action="store_true", help="List all tags")
    
    # checkout-tag
    checkout_tag_parser = subparsers.add_parser("checkout-tag", help="Checkout from a tag")
    checkout_tag_parser.add_argument("tag", help="Tag name")
    
    # remote
    remote_parser = subparsers.add_parser("remote", help="Manage remotes")
    remote_parser.add_argument("--add", action="store_true", help="Add a remote")
    remote_parser.add_argument("--name", "-n", help="Remote name")
    remote_parser.add_argument("--url", "-u", help="Remote URL")
    
    # push
    push_parser = subparsers.add_parser("push", help="Push to remote")
    push_parser.add_argument("--remote", "-r", default="origin", help="Remote name")
    push_parser.add_argument("--branch", "-b", help="Branch name")
    
    # pull
    pull_parser = subparsers.add_parser("pull", help="Pull from remote")
    pull_parser.add_argument("--remote", "-r", default="origin", help="Remote name")
    pull_parser.add_argument("--branch", "-b", help="Branch name")
    
    args = parser.parse_args()
    
    if args.command is None:
        parser.print_help()
        sys.exit(1)
    
    commands = {
        "init": cmd_init,
        "commit": cmd_commit,
        "log": cmd_log,
        "status": cmd_status,
        "checkout": cmd_checkout,
        "diff": cmd_diff,
        "watch": cmd_watch,
        "stats": cmd_stats,
        "dashboard": cmd_dashboard,
        "export": cmd_export,
        "export-session": cmd_export_session,
        "import-session": cmd_import_session,
        "convert": cmd_convert,
        "branch": cmd_branch,
        "checkout-branch": cmd_checkout_branch,
        "merge": cmd_merge,
        "tag": cmd_tag,
        "checkout-tag": cmd_checkout_tag,
        "remote": cmd_remote,
        "push": cmd_push,
        "pull": cmd_pull,
    }
    
    commands[args.command](args)


if __name__ == "__main__":
    main()

