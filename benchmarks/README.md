# SessionSmith ベンチマーク（issue #31）

大規模セッション・チェックポイント・メモリ挙動を継続的に計測するためのベンチマーク基盤です。
`SessionSmith.ssm.SSM` の実物（一時ディレクトリ上に作成した実際の `.ssm/`）に対して
`commit` / `checkout` / `diff` / `verify` / チェックポイント保存を実行し、
壁時計時間 (`time.perf_counter`) とメモリ (`tracemalloc`、可能なら `psutil`/`resource` の RSS) を計測します。

外部依存は追加していません。標準ライブラリ (`time`, `tracemalloc`, `gc`, `resource`) のみを使用し、
`psutil` がインストールされていれば追加でRSSの精度が上がりますが、無くても動作します。

## ファイル構成

| ファイル | 役割 |
|---|---|
| `benchmarks/bench_ssm.py` | メインのベンチマークハーネス（commit/checkout/diff/verify、チェックポイント、リーク兆候チェックすべてを含む） |
| `benchmarks/compare.py` | 2つの結果JSONを比較し、回帰（悪化）を検出するツール（単体実行も、`bench_ssm.py --baseline` からの内部利用も可能） |
| `benchmarks/README.md` | このファイル |

## クイックスタート

```bash
# 開発依存込みでインストール（既存の venv/dev環境を使う場合は不要）
pip install -e ".[dev]"

# CI向けの極小プリセット（数百ms〜数秒で完了）
python benchmarks/bench_ssm.py --smoke --out /tmp/smoke.json

# 通常の開発時チェック（十数秒〜数十秒）
python benchmarks/bench_ssm.py --preset quick --out results/quick.json

# 大規模データでの詳細な計測（数分。マシンによってはより長くかかる場合あり）
python benchmarks/bench_ssm.py --preset heavy --out results/heavy.json

# 前回の結果との回帰比較
python benchmarks/bench_ssm.py --preset quick --baseline results/quick_baseline.json
# または
python benchmarks/compare.py results/quick_baseline.json results/quick_new.json --threshold 20
```

## プリセット

| プリセット | 用途 | n_vars sweep | total_bytes sweep | n_history sweep | 目安時間 |
|---|---|---|---|---|---|
| `smoke` (`--smoke`) | CIスモークテスト。実行できること・数値が出ることの確認のみ | 1, 10 | 1KB, 20KB | 0, 5 | <1秒（プロセス起動込みで数秒） |
| `quick`（既定） | 日常の開発時チェック | 10, 100, 500 | 10KB, 500KB, 5MB | 0, 20, 100 | 約20秒（開発機実測） |
| `heavy` | リリース前などの詳細計測 | 100, 1000, 5000 | 1MB, 20MB, 100MB | 0, 100, 500 | 数分〜（マシン依存） |

`--n-vars-sweep`, `--total-bytes-sweep`, `--n-history-sweep` にカンマ区切りの整数リストを渡すと、
プリセットの該当スイープだけを上書きできます（例: `--total-bytes-sweep 1000,1000000`）。

各プリセットは3種類の「掃引 (sweep)」を独立に実行します（全組み合わせの直積ではありません。計算量爆発を避けるため、
1軸を動かす間は他の軸をプリセットの基準値に固定します）:

- `n_vars` sweep: `total_bytes` と `n_history` を基準値に固定し、変数の**個数**を変える
- `total_bytes` sweep: `n_vars` と `n_history` を基準値に固定し、**ペイロード総サイズ**を変える
- `n_history` sweep: `n_vars` と `total_bytes` を基準値に固定し、**事前コミット数（履歴の長さ）**を変える

さらに:
- チェックポイント保存コスト（`benchmarks/bench_ssm.py` 内 `run_checkpoint_bench`）: ペイロードサイズを変えながら
  `CheckpointContext.step(force=True)` を繰り返し呼び、1回あたりの保存コストを計測
- メモリリーク兆候チェック（`run_leak_check`）: `commit → checkout` を繰り返し、`tracemalloc` で
  「解放されずに残り続けているメモリ (current)」の推移を記録

## 実測の設計上の注意（なぜこの実装なのか）

- **`ssm.commit()` などモジュールレベル関数は使っていません。** これらは呼び出し元フレームの
  `globals()` を `inspect` で自動探索するため、ベンチマークスクリプトから呼ぶと「どの変数集合が
  対象になるか」が非決定的になります。代わりに `SSM(path=tmpdir, globals_dict=my_dict)` で
  インスタンスを明示的に作成し、`my_dict` を直接操作することで計測対象の変数集合を厳密に制御しています
  （`SSM.__init__` の `globals_dict` パラメータを利用。`ssm.py` 内 `_get_globals_dict()` は
  `self.globals_dict is not None` の場合、フレーム探索をスキップしてそれをそのまま返します）。
- **各操作の後に必ず結果を検証しています。** `commit()` がハッシュを返すこと、`checkout()` が
  期待した変数数を実際に復元すること、`verify()` が `integrity_ok=True` を返すことをアサーションで確認し、
  失敗時はベンチマーク自体を異常終了させます（静かに壊れた計測を出さないため）。
- **ペイロードは非圧縮性の疑似乱数バイト列** (`random.Random(seed).randbytes(n)`) を使っています。
  オブジェクトストレージは常に `gzip` (compresslevel はデフォルトの9) で保存するため、
  全ゼロなど圧縮が効きすぎるデータだと圧縮コストを過小評価してしまいます。
- **メモリは `tracemalloc` の `current`/`peak`** を主指標にしています。これはPythonレベルの
  アロケータ経由のメモリのみを追跡するため、`zlib`/`gzip` 内部でCレベルに直接確保される
  バッファなどは捕捉しきれない場合があります。`psutil` がインストールされていれば
  プロセスRSS (`rss_bytes`) も参考値として記録し、無ければ `resource.getrusage().ru_maxrss`
  （Unix限定・ピーク値であり瞬間値ではない点に注意）にフォールバックします。

## 出力フォーマット（JSON）

```json
{
  "meta": {
    "preset": "smoke",
    "timestamp": "2026-07-12T09:46:35.012846+00:00",
    "python_version": "3.14.4 ...",
    "platform": "macOS-...",
    "sessionsmith_version": "2.1.0",
    "seed": 42,
    "label": null,
    "has_psutil": false,
    "leak_check_summary": { "...": "..." }
  },
  "results": [
    {
      "operation": "commit",
      "sweep": "n_vars",
      "n_vars": 1,
      "total_bytes": 5000,
      "n_history": 0,
      "seconds": 0.0045668340171687305,
      "peak_mem_bytes": 984423,
      "current_mem_bytes": 14105,
      "rss_bytes": 35127296,
      "repeat": 0,
      "preset": "smoke",
      "label": null,
      "timestamp": "2026-07-12T09:46:34.815727+00:00"
    }
  ]
}
```

`operation` は `commit` / `checkout` / `diff` / `verify` / `checkpoint` / `leak_cycle` のいずれかです。
`checkpoint` は `n_history=0` 固定、`leak_cycle` は `n_history` フィールドをサイクル番号として流用しています
（同一の (operation, sweep, n_vars, total_bytes, n_history) タプルでグルーピングして2つの実行結果を比較できるようにするため）。

## 回帰検出（`compare.py`）

`(operation, sweep, n_vars, total_bytes, n_history)` が一致するレコード同士を突き合わせ、
**実行時間の中央値**を比較します（外れ値1発で誤検知しないよう平均ではなく中央値を採用）。

回帰と判定する条件は次の**両方**を満たす場合です:
1. 相対悪化率が `--threshold`（既定20%）を超える
2. 絶対時間差が `--min-delta-seconds`（既定3ms）を超える

条件2のフロアがないと、smokeプリセットのようにミリ秒未満で終わる操作は、
プロセス起動ごとのGC/OSスケジューラのジッタだけで簡単に20%を超えてしまい、
常に「回帰」と誤報してしまいます（実際に開発中に発生し、このフロアを導入することで解消しました）。
quick/heavyプリセットのように操作あたりの時間が長くなるほど、このフロアの影響は小さくなります。

```bash
python benchmarks/compare.py baseline.json current.json --threshold 20 --fail-on-regression
# または bench_ssm.py 実行と同時に:
python benchmarks/bench_ssm.py --preset quick --baseline baseline.json --out current.json
```

`--fail-on-regression` を付けると回帰検出時に終了コード1を返すので、CIのゲートに使えます
（ただし本リポジトリのCIワークフローでは、閾値ベースの判定はデフォルトで有効にしていません。
下記「CIでの位置づけ」を参照）。

## CIでの位置づけ

`.github/workflows/benchmark.yml` は `--smoke` プリセットを push/PR で実行し、
ハーネスがエンドツーエンドで動くこと・JSONが正しい形で出力されることだけを確認します。
**厳密な性能しきい値によるゲートは行いません**（CI環境はランナーごとに性能が大きく揺れるため、
固定しきい値は容易にフレーキーになります）。結果JSONはartifactとしてアップロードされ、
必要であれば手元で `compare.py` を使って過去の実行と比較できます。

## 観測結果と示唆（このハーネスで実測した範囲）

以下は開発機（macOS, Python 3.14, `quick` プリセット）での実測値の要約です。
**絶対値はマシン・Pythonバージョン・ディスクに強く依存するため、目安として読んでください。**
自分の環境・自分のデータサイズで `--preset quick` または `--preset heavy` を実行し、
その結果をベースラインとして保存することを推奨します。

### 変数の個数 vs ペイロード総サイズの影響

`total_bytes` を1MB固定で `n_vars` を10→500に増やすと、`commit` は約61ms→253msへと
**variable数にほぼ比例して増加**しました。一方 `n_vars` を50固定で `total_bytes` を
10KB→5MBに増やした場合も `commit` は25ms→279msへ増加しています。
つまり **「同じ総バイト数でも、少数の大きな変数より多数の小さな変数の方がコストが高い」**
傾向が明確に見えました（変数ごとに個別の pickle 化・ハッシュ計算・オブジェクトファイルI/Oが
発生するため）。可能であれば、大量の小さな変数を個別に持つより、まとめて1つのコンテナ
（list/dict等）に格納してからコミットする方が高速です。

### commit は checkout / verify よりも大幅に高コスト

同じ5MBペイロードで比較すると、`commit` 約279ms に対し `checkout` は約11ms、`verify` は約13ms でした。
書き込み（圧縮）と読み込み（伸長）のコスト差を考慮しても差が大きいため、コードを確認したところ
`SSM.commit()` は **同じ変数値を最大3回 `pickle.dumps()` している**ことがわかりました
（`_get_saveable_vars()` でのサイズチェック1回、`ResourceManager` が有効な場合の合計サイズ計算1回、
実際のオブジェクト保存ループでの本番シリアライズ1回）。詳細は「発見した性能上の懸念」を参照してください。

### 履歴の長さ (n_history) は checkout / verify にのみ影響し、commit / diff には影響しない

`n_history` を0→100に増やすと、`checkout` の中央値は約9.9ms→11.7ms、`verify` は約9.0ms→11.1ms へと
緩やかに増加しました。一方 `commit` と `diff` はほぼ横ばいでした（`commit`: 69ms→66ms、`diff`: 2.9ms→3.0ms）。
これはコード上の理由と整合しています: `checkout()`/`verify()`/`export()` は `_resolve_hash()` を経由し、
これは **`.ssm/commits/` 配下の全JSONファイルを毎回globして線形探索**しています（完全なハッシュを
渡した場合でも同様で、直接のファイル存在チェックにはショートカットしていません）。`commit()` と `diff()` は
`_resolve_hash()` を呼ばないため、履歴が伸びても時間は変わりません。`quick` プリセット（最大100コミット）
では影響は緩やかですが、数千〜数万コミットに達する長期利用では無視できないオーバーヘッドになり得ます。

### チェックポイント保存コストとペイロードサイズの関係

`CheckpointContext.step(force=True)` の1回あたりのコストは、10KB→500KB→2MBで
約1.2ms→13.8ms→53.2msと、概ねペイロードサイズに比例して増加しました
（およそ **25〜30ms/MB** のスループット。gzip圧縮とpickle化が支配的）。

### メモリリーク兆候チェック

`quick` プリセット（20サイクルの commit→checkout）では、`tracemalloc` の "current"（保持され続けている
メモリ）は約985KB→1003KB（+1.8%）とほぼ横ばいで、増加傾向は「明確な増加傾向なし」と判定されました。

ただし、ベンチマーク開発中に**別の場所で実際の無制限増加を確認しました**（下記「発見した性能上の懸念」参照）。
`current_mem` の増分自体は非常に小さいため、`tracemalloc` ベースの自動判定（20%以上かつ8サイクル以上）
には引っかかりませんでしたが、`SSM._file_locks` 辞書がコミットのたびに1エントリずつ増え続けることを
直接確認しています。長時間・大量コミットのワークロードではこの積み重ねが無視できなくなる可能性があります。

## 発見した性能上の懸念（ソースは変更していません。issue化を推奨）

このベンチマークを作成する過程で、`SessionSmith/ssm.py` に以下の実装上の懸念を発見しました。
**本タスクの方針に従い、ソースコードは変更していません。** 別issueとして報告することを推奨します。

1. **`commit()` が各変数の値を最大3回 `pickle.dumps()` している**
   - `_get_saveable_vars()`（サイズチェック用）→ `ResourceManager` 有効時の合計サイズ計算用の
     `sum(len(pickle.dumps(v)) ...)` → 実際の保存ループでの `pickle.dumps(value)`、と3箇所で
     同じオブジェクトを再シリアライズしています（`ssm.py` の `_get_saveable_vars()` 内 および
     `commit()` 内 `total_size_mb = sum(...)` の行、`commit()` 内保存ループの `data = pickle.dumps(value)` の行）。
   - 一度シリアライズした結果（バイト列とサイズ）を使い回せば、単純計算で最大3分の1程度まで
     commit のシリアライズコストを削減できる可能性があります。

2. **`_resolve_hash()` が毎回 `.ssm/commits/` 全体をglobして線形探索している**
   - `checkout()` / `verify()` / `export()` はすべて `_resolve_hash(commit_hash)` を経由しますが、
     この実装は完全な40文字ハッシュ（あるいは今回のような16文字ハッシュ）が渡された場合でも、
     `commits_dir.glob("*.json")` で全コミットファイルを毎回列挙してprefix一致を確認しています。
   - 完全一致するファイルパスが最初から分かっている場合（短縮形でない場合）は
     `(commits_dir / f"{commit_hash}.json").exists()` によるO(1)チェックを先に試みることで、
     履歴が長いリポジトリでの `checkout`/`verify` コストを大幅に削減できる可能性があります。
   - 本ベンチマークの `n_history` sweep でも、`checkout`/`verify` のみ履歴長に応じて緩やかに
     時間が増加し、`_resolve_hash()` を呼ばない `commit`/`diff` は横ばいという、この仮説と
     整合する結果が観測されています。

3. **`SSM._file_locks` が無制限に増加する（実質的なメモリリーク）**
   - `_get_file_lock(file_path)` は `file_path` ごとに新しい `threading.Lock()` を
     `self._file_locks` にキャッシュしますが、エントリが削除されることは一切ありません。
   - `commit()` はコミットのたびに一意なパス（`{commit_hash}.json`）に対して `_write_json()` を
     呼ぶため、**1コミットにつき `_file_locks` に1エントリが永続的に追加され続けます**。
     50回連続でコミットするテストスクリプトで実際に `len(ssm._file_locks)` が
     1（初期状態）→51（コンフィグ用ロック + コミット50件分）へと確認済みです。
   - 個々の `Lock` オブジェクトのサイズは小さいものの、`ssm.checkpoint()` による長時間の
     機械学習トレーニングループなど、同一の `SSM`/グローバルインスタンスで
     数千〜数百万回のコミット/チェックポイントを行うworkloadでは、無視できない量の
     メモリが解放されずに残り続ける可能性があります。ファイルパスごとではなく、
     一定数を超えたら古いロックを破棄する、あるいは軽量なロック分割戦略（例:
     パスのハッシュ値を固定個数のロックにマッピングする）に変更することを推奨します。

4. **チェックポイントのファイル名がタイムスタンプの秒単位でしか一意でない**
   - `CheckpointContext._save_checkpoint_unsafe()` はファイル名を
     `f"checkpoint_{datetime.now().strftime('%Y%m%d_%H%M%S')}.gz"` として生成しており、
     秒未満の解像度がありません。同一秒内に複数回 `step(force=True)` を呼ぶと
     （本ベンチマークの `run_checkpoint_bench` のように高頻度の強制チェックポイントを行うと）、
     後続の保存が同名ファイルを上書きし、それより前のチェックポイントが失われます。
     マイクロ秒やシーケンス番号をファイル名に含めることを推奨します。

## 推奨チェックポイント間隔（ガイドライン）

`docs/checkpoint-guide.md` のデフォルト値 `interval=300`（5分）は妥当な既定値です。
実測（約25〜30ms/MB、gzip level 9 込み）から、チェックポイントのオーバーヘッドを
インターバル時間の1%未満に抑えたい場合の目安は次の通りです:

```
必要な最小interval(秒) ≈ (ペイロードサイズ[MB] × 0.028) / 目標オーバーヘッド率
```

例:
- セッションサイズ 10MB 程度 → 1回あたり約0.28秒 → 1%未満に抑えるには interval ≥ 28秒
  （既定の300秒であれば実測ベースでオーバーヘッドは0.1%未満）
- セッションサイズ 100MB 程度 → 1回あたり約2.8秒 → 1%未満に抑えるには interval ≥ 280秒
  （既定の300秒はほぼこのラインちょうど。大きなセッションではより長いintervalを検討してください）
- セッションサイズが数百MB〜GB級になる場合は、`interval` を伸ばすか、
  `ssm.checkpoint(compress=...)` の圧縮設定や変数の間引き（不要な巨大変数を `ssm.exclude()` で除外）を
  検討してください。

**注意点・限界:**
- 上記の係数はランダムな非圧縮性バイト列に対する実測値です。実際のPythonオブジェクト
  （numpy配列、モデル重みなど）は圧縮率・pickle化コストが大きく異なるため、
  自分のワークロードで `benchmarks/bench_ssm.py --preset heavy` を実行し、
  実際のペイロードサイズに近い条件で再計測することを強く推奨します。
- 上記の懸念4（ファイル名の秒解像度）により、`interval` を極端に短く（1秒未満相当の
  高頻度 `step(force=True)`）設定するとチェックポイントが失われる場合があります。

## クリーンアップ

このハーネスは `tempfile.mkdtemp()` で作成した一時ディレクトリのみを使用し、
各シナリオの終了時に `shutil.rmtree()` で必ず削除します。リポジトリ内に `.ssm/` や
ビルド成果物を残しません。
