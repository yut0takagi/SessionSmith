# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.3.0] - 2026-08-30

Windows と macOS を CI のテストマトリクスに追加したことで見つかった、
プラットフォーム依存のバグを中心とした修正リリースです。

### ⚠️ 挙動の変更（アップグレード時の注意）

いずれも壊れていた挙動の修正ですが、これまでの動作に依存していた場合は影響します。

- **大文字小文字が違う参照名は解決されなくなります** (#51)
  macOS / Windows では `checkout_branch("FEATURE")` が `branches/feature` を
  指して成功していましたが、`SSMBranchNotFoundError` になります。正しい名前を指定してください。
- **大文字小文字だけが異なる参照は作成できなくなります** (#51)
  `feature` がある状態での `branch("Feature", create=True)` は `SSMConfigError` になります。
- **一部の参照名が使えなくなります** (#51)
  Windows の予約デバイス名（`CON` / `PRN` / `AUX` / `NUL` / `COM1`〜`COM9` / `LPT1`〜`LPT9`）と、
  末尾が `.` の名前は `ValidationError` になります。
- **`compare_sessions(detailed=True)` が `.ssm` にコミットを作らなくなります** (#57)
  従来は比較しただけでコミットが2つ増えていました。この副作用に依存していた場合は影響します。
- **`get_session_info()["compression"]` が実際の圧縮形式を返します** (#58)
  従来は常に `None` でした。

### Fixed

#### Windows / macOS 依存のバグ

- **Windows のコンソールで出力時にクラッシュする問題を修正**
  - `ssm.commit()` などが出力する `✓` や日本語メッセージが、Windows の既定コンソール
    （`cp1252` など）で `UnicodeEncodeError` になり処理全体が落ちていた
  - 端末が表現できない文字を置換して出力を継続する `SessionSmith/_console.py` の
    `safe_print()` を追加し、パッケージ内の `print()` 229箇所を置き換え
  - 回帰テスト: `tests/test_console.py`
- **Windows で `file://` リモートが意図しない場所を指す問題を修正**
  - `file://C:\data` は `urlparse` で `path` が空になるため、カレントディレクトリ配下の
    相対パス `.ssm` として扱われていた。`file:///C:/data` や `file://C:/data` も
    ドライブレターが失われていた
  - `file_url_to_path()` を追加し、`url2pathname()` 経由で3つの書き方すべてと
    UNC パス（`file://server/share`）に対応
  - 回帰テスト: `tests/test_remote_backends.py::TestFileUrlToPath`
- **参照名の解決が大文字小文字を区別していなかった問題を修正 (#51)**
  - ブランチ・タグ・リモートの存在確認を `Path.exists()` で行っていたため、
    macOS（APFS の既定）と Windows では `branches/feature` しか無いのに
    `FEATURE` が「存在する」と判定されていた
  - `checkout_branch("FEATURE")` が通り、`current_branch` に実在しない名前が入る。
    その状態で `push` するとリモートに別ブランチが作られ、1本だったブランチが2本に割れていた
  - 存在確認をディレクトリ列挙 + Python 側の厳密比較に変更（`_ref_exists()`）
  - 作成時は大文字小文字だけが異なる既存参照があれば拒否（`_find_case_conflicting_ref()`）。
    大文字小文字を区別しないFSでは同じファイルになり既存参照を壊すため
  - `validate_ref_name()` に Windows の予約デバイス名と末尾ドットの拒否を追加
  - 回帰テスト: `tests/test_ref_case_sensitivity.py`
- **ロケール依存のテキストファイル入出力を修正 (#48)**
  - `open()` / `Path.read_text()` / `Path.write_text()` の `encoding` 未指定を全廃し、
    パッケージ内のテキストI/Oをすべて `encoding="utf-8"` に統一
  - `_write_json()` は `ensure_ascii=False` で書くため、Windows（cp1252 / cp932）では
    日本語のコミットメッセージを含むファイルを読めなかった
  - 具体的な実害: `ResourceManager.cleanup_old_files(commits_days=...)` が
    `UnicodeDecodeError`（`ValueError` のサブクラス）を except 節で握りつぶし、
    日本語コミットのクリーンアップを黙ってスキップしていた
  - 回帰テスト: `tests/test_encoding.py`（ソースレベルのガード + 非ASCIIコミットの機能テスト）
- **Windows でコミットのクリーンアップが全く機能していなかった問題を修正 (#48)**
  - `ResourceManager.cleanup_old_files(commits_days=...)` が `unlink()` を
    `with open(...)` の内側で呼んでいたため、Windows では開いたままのファイルを
    削除できず `WinError 32` になっていた
  - `except OSError` に捕まるため例外にはならず、警告ログを出して黙ってスキップしていた
  - 読み込みの `with` ブロックを抜けてから `unlink()` するように修正
- **`init(force=True)` の `.ssm` 破棄を堅牢化 (#53)**
  - 破棄をリポジトリロックの内側で行い、他プロセスが操作の途中で消されないようにした
  - Windows の一時的な削除失敗（他プロセスが開いている `WinError 32`、読み取り専用属性）に対して、
    属性の解除と短いリトライを追加
  - 削除に失敗した場合は削除失敗として明示的に送出する。従来は `rmtree` が途中で失敗しても
    素通りし、直後の `mkdir()` が `FileExistsError`（「既に存在します」）になって
    本当の原因が伝わらなかった
- **Windows の `MAX_PATH` 制限を分かりやすいエラーにした (#54)**
  - 参照名は255文字まで許可されるため、`.ssm/branches/<name>` は長パス未有効の Windows の
    上限（260文字）を容易に超える。従来は原因の分からない `OSError` になっていた
  - `check_path_length()` を追加し、書き込みの集約点（`_write_text_atomic()` / `_write_json()`）で
    一時ファイル名も含めて検査する
  - 制限は Windows 固有のため既定では Windows 上でのみ検査する（テストからは強制可能）

#### 機能不全

- **`compare_sessions(detailed=True)` が変更を検出できず、副作用があった問題を修正 (#57)**
  - `load_session()` を既定の `use_ssm=True` で呼んでいたため、一時的な名前空間に
    何も読み込まれず `changed_variables` が常に空だった
  - さらに「ファイルを SSM にインポートしてコミットする」経路を通るため、
    **2つのファイルを比較しただけで `.ssm` にコミットが2つ増えていた**
  - `use_ssm=False` を指定して、渡した辞書に直接読み込むように修正
- **`get_session_info()` の `compression` が常に `None` だった問題を修正 (#58)**
  - `_load_session_file()` が `compression` を `None` で初期化したまま一度も代入していなかった
  - `utils.detect_compression()` でマジックナンバーから判定するように修正
- `SSM._signal_handler` が、元のシグナルハンドラが `SIG_IGN`（整数の 1）だった場合に
  `1(signum, frame)` を呼び出して `TypeError` になる問題を修正
  （真偽値ではなく `callable()` で確認するように変更。`SIG_DFL` は 0 のため従来も呼ばれなかった）

### Changed

#### 開発基盤

- **CI のテストマトリクスに `windows-latest` と `macos-latest`（ともに Python 3.12）を追加**
  - OS 依存の実装（`ProcessLock` / アトミック書き込み / パス検証 / ファイル名の大文字小文字）の
    動作確認が目的。このリリースの修正の大半はこれによって見つかった
  - 全ステップのシェルを bash に統一（Windows の既定 pwsh では `rm -rf` や
    `dist/*.whl` のグロブが動かないため）
- **mypy の CI ゲートを `SessionSmith/` 全モジュールに拡大 (#27 の残作業)**
  - `ssm` / `cli` / `formats` / `manager` / `remote_backends` の `ignore_errors` を削除し、
    既存の型エラー30件をすべて解消
  - `pyproject.toml` の overrides に残るのは、型スタブを提供していないサードパーティ依存の
    `ignore_missing_imports` のみ
  - 公開シグネチャ用に `SessionFormat`（`Literal["pickle", "json", "msgpack", "hdf5"]`）を
    `SessionSmith/formats.py` に追加
- **テストカバレッジを 35% → 50.0% に引き上げ、CI のしきい値を 30% → 45% に更新**
  - `utils` 7% → 76%、`compare` 8% → 79%、`info` 10% → 66%、`tracer` 9% → 57%
  - 追加したテストファイル: `test_console.py` / `test_encoding.py` /
    `test_ref_case_sensitivity.py` / `test_platform_robustness.py` /
    `test_utils.py` / `test_info_and_compare.py` / `test_tracer.py`
- **Homebrew Formula の自動更新が一度も実行されていなかった問題を修正**
  - `update-formula.yml` は `on: push: tags` で起動する設計だったが、`release.yml` が
    `GITHUB_TOKEN` でタグを push しているため（GITHUB_TOKEN が発生させたイベントは
    他のワークフローを起動しない仕様）一度も動かず、`sha256` が空のままだった
  - reusable workflow (`workflow_call`) 化して `release.yml` から明示的に呼び出す形に変更。
    手動実行用に `workflow_dispatch` も追加
- **リリースノートが CHANGELOG から抽出できていなかった問題を修正 (#60)**
  - `release.yml` の `awk "/^## \\[${VERSION}\\]/,/^## \\[/"` は、awk のレンジが
    開始行に対して終端パターンも評価するため常に1行しか取れず、続く `sed '$d'` で
    出力が空になっていた
  - その結果 v2.0.0 / v2.1.0 / v2.2.0 の GitHub Release 本文は、
    「See CHANGELOG.md for details」という定型文だけになっていた
  - 見出しをスキップして次のバージョン見出しで止める状態機械に変更
- **GitHub Actions を Node.js 24 対応のバージョンへ更新**
  - `actions/checkout` v4 → v7、`actions/setup-python` v5 → v7、
    `actions/upload-artifact` v4 → v7、`actions/setup-node` v4 → v7、
    `softprops/action-gh-release` v1 → v3
  - Node.js 20 は非推奨で、実行時は Node.js 24 に強制されたうえで警告が出ていた
    （`softprops/action-gh-release@v1` に至っては Node.js 16 のままだった）

## [2.2.0] - 2026-08-30

### Added

#### プロセス間ロックとアトミック書き込み (#29)
- ロックモジュール（`SessionSmith/locking.py`）を追加
- `.ssm/` リポジトリ単位のプロセス間ロック（`ProcessLock`、ロックファイル `.ssm/.lock`）
  - `commit` / `checkout` / `merge` / `checkpoint` など、リポジトリを書き換える操作を排他制御
  - 生存中の保持者からの横取りを防止し、死んだプロセスが残したスタールロックのみ回収
  - 同一プロセス内では再入可能（`checkout` → 内部の `commit` などでデッドロックしない）
  - 既定の取得タイムアウトは 10 秒（`SSM.LOCK_TIMEOUT_SECONDS`）。超過時は `SSMLockError`
- `HEAD` / ブランチ参照などの書き込みを `os.replace` によるアトミック書き込みに変更し、
  中断時のファイル破損を防止
- 例外 `SSMLockError` を追加

#### パス・参照名の入力検証 (#30)
- 検証モジュール（`SessionSmith/validation.py`）を追加
  - `validate_ref_name()` - ブランチ / タグ / リモート名の検証（制御文字・パス区切り・予約名の拒否）
  - `ensure_within()` - 対象パスが基準ディレクトリ配下に収まることを保証（パストラバーサル対策）
  - `validate_path_arg()` - パス引数の共通検証
- `validate_remote_url()` を追加し、`remote_add()` の時点で未対応スキームを早期に拒否
  （許可: ローカルパス / `file://` / `s3://` / `gs://`(`gcs://`) / `http(s)://`）
- VS Code 拡張機能側の検証ルールを Python 実装と統一

#### マージのコンフリクト検出とクリーンチェックアウト (#43)
- `ssm.merge(branch_name, message=None, on_conflict="warn")` - コンフリクト検出を追加
  - 両ブランチで同じ変数が異なる値に変更された場合を、マージコミット作成前に検出
  - `on_conflict`: `"warn"`（既定・警告した上でマージを続行）/ `"error"`（`SSMMergeConflictError`
    を送出しマージを中止）/ `"ignore"`（従来どおり検出しない）
  - マージ結果そのものは従来どおりライブな名前空間を記録する last-writer-wins のままで、
    値レベルの自動マージは行わない
- 例外 `SSMMergeConflictError` を追加
- `checkout()` / `checkout_branch()` / `checkout_tag()` に `clean=True` を追加
  - 対象コミットに含まれない変数を名前空間から削除し、リポジトリの状態を厳密に再現

#### ベンチマーク基盤 (#31)
- `benchmarks/bench_ssm.py` - `commit` / `checkout` / `diff` / `verify` / チェックポイントを
  変数数・ペイロード総サイズ・履歴長を変えながら計測（`--preset smoke/quick/heavy`）
- `benchmarks/compare.py` - 計測結果の比較
- `.github/workflows/benchmark.yml` - CI でのスモーク実行
- 計測結果と既知の性能上の懸念は `benchmarks/README.md` を参照

#### テスト
- プロセス間ロック（`tests/test_locking.py`）
- パス・入力検証（`tests/test_security.py`）
- マージコンフリクト / クリーンチェックアウト（`tests/test_merge_checkout_features.py`）
- 既知バグの回帰テスト（`tests/test_ssm_bugfixes.py`）
- branch / merge / tag / remote のE2E・異常系（`tests/test_ssm_e2e.py`、#28）

### Fixed

- `SSM._file_locks` がコミットごとに無制限に増加していたメモリリークを修正
  （上限 512 件の LRU キャッシュ化、#31）
- `SSM._resolve_hash()` に完全長ハッシュの高速パスを追加し、`commits/` 全走査による
  O(n) の解決を O(1) に改善
- 同一秒内に連続したチェックポイントが黙って上書きされる問題を修正
  （ファイル名にマイクロ秒と重複回避カウンタを付与）
- `core.py` の型不整合と `merge` のドキュメント齟齬を修正 (#41)

### Changed

- CI: `mypy` を公開API・コアモジュールで必須ゲート化 (#27)
  - グローバルな `ignore_missing_imports` を廃止し、実際に import している
    サードパーティモジュールのみを override で列挙
  - 既存の型エラーを抱えるモジュール（`ssm` / `cli` / `formats` / `manager` /
    `remote_backends`）は理由付きで一時除外（段階的に縮小予定）
- CI: `pytest-cov` によるカバレッジレポート生成と `--cov-fail-under=30` のしきい値を追加
  (#24 #25 #26)
- パッケージ設定を `pyproject.toml` に一本化し、`setup.py` を shim 化
- `docs/api-reference.md` を v2.1.0 の実装に合わせて更新 (#32)

### Note

- VS Code / Cursor 拡張機能 v0.3.0（Session Graph）は別タグ `ext-v0.3.0` として
  リリース済みです。変更内容は `extension/CHANGELOG.md` を参照してください。

## [2.1.0] - 2026-06-13

### Added

#### クラウド / URL リモート対応
- リモートバックエンド抽象化（`SessionSmith/remote_backends.py`）を追加
- `ssm.push()` / `ssm.pull()` が以下のリモートに対応:
  - `s3://bucket/prefix` （Amazon S3 / S3互換、要 `boto3`、extras: `s3`）
  - `gs://bucket/prefix` （Google Cloud Storage、要 `google-cloud-storage`、extras: `gcs`）
  - `http(s)://...` （読み取り専用 / pull のみ。`manifest.json` を利用）
  - `file://...` / ローカルパス（従来通り）
- push 時に `manifest.json` を生成し、一覧取得ができないバックエンドからの pull に対応

#### セッションの暗号化・改ざん検出
- 暗号化・署名モジュール（`SessionSmith/crypto.py`）を追加
- **暗号化**（認証付き暗号 Fernet / AES-128-CBC + HMAC、要 `cryptography`、extras: `crypto`）
  - `ssm.export(path, password=...)` / `ssm.import_session(path, password=...)`
  - `ssm.push(..., password=...)` / `ssm.pull(..., password=...)` でリモート上のデータを暗号化
  - パスワードから PBKDF2-HMAC-SHA256 で鍵を導出
- **改ざん検出（署名）**（HMAC-SHA256、標準ライブラリのみ・追加依存なし）
  - `ssm.config('sign_key', ...)` または環境変数 `SESSIONSMITH_SIGN_KEY` で署名鍵を設定すると、
    コミット時に HMAC 署名を付与
  - `ssm.verify()` で整合性（オブジェクトの再ハッシュ）と署名を検証
  - トップレベル API: `encrypt_data`, `decrypt_data`, `sign_data`, `verify_signature`

#### 構造化ロギング
- ロギング設定モジュール（`SessionSmith/logging_config.py`）を追加
- `setup_logging()`, `set_log_level()`, `get_log_level()`, `enable_debug()`
- JSON 形式の構造化ログ、ファイル出力（サイズベースのローテーション）に対応
- 環境変数 `SESSIONSMITH_LOG_LEVEL` / `SESSIONSMITH_LOG_FILE` / `SESSIONSMITH_LOG_JSON` で
  import 時に自動設定

#### テスト
- 新機能のテストを追加: `test_crypto.py`, `test_logging_config.py`,
  `test_remote_backends.py`（push/pull 統合テスト含む）, `test_verify.py`

### Fixed

- `branch()`, `tag()`, `push()`, `pull()`, `remote_add()` で、関数内のローカル変数 `i18n`
  がモジュールの `i18n` をシャドウし、特定の経路で `UnboundLocalError` が発生していた
  バグを修正（リモート新規追加・ローカル push/pull などが失敗していた）

### Dependencies

- オプショナル extras を追加: `crypto`（cryptography）, `s3`（boto3）, `gcs`
  （google-cloud-storage）, `cloud`（boto3 + google-cloud-storage）
- いずれも未インストールの環境では該当機能のみ無効化され、ライブラリ全体は動作します

---

## [2.0.0] - 2025-12-24

### 🎉 メジャーバージョンアップ

このバージョンでは、0.1.4以降の大幅な機能追加と改善が含まれています。

### Added

#### 高度なバージョン管理機能
- **ブランチ機能**
  - `ssm.branch()` - ブランチの作成・一覧表示
  - `ssm.checkout_branch()` - ブランチに切り替え
  - `ssm.get_current_branch()` - 現在のブランチを取得
- **マージ機能**
  - `ssm.merge()` - ブランチをマージ
  - 共通祖先の検出
  - マージコミットの作成（2つの親を持つ）
- **タグ機能**
  - `ssm.tag()` - コミットにタグを付ける
  - `ssm.list_tags()` - タグ一覧表示
  - `ssm.checkout_tag()` - タグからチェックアウト
- **リモートリポジトリとの同期**
  - `ssm.remote_add()` - リモートを追加
  - `ssm.remote_list()` - リモート一覧表示
  - `ssm.push()` - リモートにプッシュ
  - `ssm.pull()` - リモートからプル

#### チェックポイント機能（長時間実行対応）
- `ssm.checkpoint()` - コンテキストマネージャーで自動チェックポイント
- 定期的な自動保存（バックグラウンドスレッド）
- `cp.step()` - 手動チェックポイント + メトリクス記録
- シグナルハンドラー（SIGINT/SIGTERM）で中断時自動保存
- 例外発生時の緊急チェックポイント
- `ssm.restore_checkpoint()` - チェックポイントから復元
- `ssm.list_checkpoints()` - チェックポイント一覧
- `ssm.clean_checkpoints()` - 古いチェックポイントの削除
- メトリクス追跡（loss, accuracy など）

#### 国際化（i18n）
- 日本語・英語の翻訳辞書
- `set_language()` / `get_language()` - 言語設定
- 環境変数 `SESSIONSMITH_LANG` での設定
- システムロケールからの自動検出
- SSM設定ファイルへの自動保存
- すべての例外クラスの多言語対応
- 情報メッセージの多言語対応

#### 堅牢なエラーハンドリング
- `@retry` デコレータ - リトライ機能
- `error_context` コンテキストマネージャー - エラーコンテキスト管理
- `safe_execute()` - 安全な実行
- `ErrorHandler` クラス - エラーハンドリング設定
- 詳細なエラー情報の提供

#### リソース管理
- ディスク容量監視
- メモリ使用量監視
- 自動クリーンアップ機能
- リソース制限例外（`MemoryLimitError`, `StorageLimitError`）

#### ファイル操作の堅牢性
- ファイルロック機能
- アトミック書き込み
- ファイル破損検出・復旧機能
- バックアップ・リストア機能

#### 形式互換性機能
- `ssm.export()` - 従来形式（.pkl/.json）へエクスポート
- `ssm.import_session()` - 従来形式からインポート
- `ssm.convert()` - ファイル形式変換
- CLI: `ssm export-session`, `ssm import-session`, `ssm convert` コマンド

#### 複数ファイル使用時の対応
- コミット元ファイル情報の記録
- 変数名衝突の自動検出と警告
- コミット履歴にファイル情報を表示

#### CLI機能
- `ssm` コマンドラインツール
- `ssm init`, `ssm commit`, `ssm log`, `ssm checkout` など
- `ssm watch` - 監視モード
- `ssm stats` - 統計分析
- `ssm dashboard` - Webダッシュボード
- バージョン管理コマンド（`ssm branch`, `ssm merge`, `ssm tag` など）

#### Homebrew対応
- Homebrew Formula の追加
- GitHub Actions による自動更新

### Changed

#### 破壊的変更
- **`save_session()` / `load_session()` の動作変更**
  - デフォルトでSSMに統合（`use_ssm=True`）
  - `.ssm/` ディレクトリに保存されるようになりました
  - 従来の動作は `use_ssm=False` で利用可能

- **`ssm.set_language()` / `ssm.get_language()` の非推奨化**
  - トップレベルの `set_language()` / `get_language()` を使用してください

#### 改善
- 例外クラスに `to_dict()` メソッド追加（JSON出力対応）
- `_get_saveable_vars()` にサイズチェック機能追加
- 大規模データ対応（変数サイズチェック、警告、制限）
- スレッドセーフティの向上（RLockによる並行アクセス保護）
- ドキュメントの大幅な整理と改善

### Removed

- `SessionSmith/version_control.py` を削除（`ssm` モジュールに統合）

### Security

- セキュリティ警告の追加（pickle使用に関する注意喚起）
- セッションファイルの検証機能の強化

### Documentation

- ドキュメントの大幅な整理
- 各機能の詳細なガイドを追加
- 実践的な使用例を追加
- Homebrewインストール方法を追加

### Example Usage

```python
# 基本的な使い方
from SessionSmith import ssm

ssm.init()
ssm.commit("Initial state")
ssm.log()
ssm.checkout("abc123")

# バージョン管理
ssm.branch('feature', create=True)
ssm.checkout_branch('feature')
ssm.merge('feature')
ssm.tag('v1.0.0')

# チェックポイント（長時間学習）
with ssm.checkpoint(interval=300) as cp:
    for epoch in range(1000):
        loss = train()
        cp.step(loss=loss, epoch=epoch)

# 国際化
from SessionSmith import set_language
set_language('ja')  # 日本語に設定
```

---

## [0.1.4] - 2024-XX-XX

### Added
- 基本的なセッション保存・復元機能
- SSM（Git風セッション管理）の基本機能
- アルゴリズムトレーサー
- 可視化機能
