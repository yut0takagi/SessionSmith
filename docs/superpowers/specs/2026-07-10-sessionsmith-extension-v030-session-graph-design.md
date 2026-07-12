# SessionSmith VSCode拡張 v0.3.0 — Session Graph 全面刷新 設計書

- **日付**: 2026-07-10
- **対象**: `extension/`（VSCode/Cursor 拡張機能）
- **現行バージョン**: 0.2.0 → **目標: 0.3.0**
- **位置づけ**: SessionSmith v3.0 ロードマップの最初のマイルストーン（「Webビューア = 拡張のグラフGUI」を先行して仕上げる）

---

## 1. 背景と狙い

拡張 v0.2.0 は `.ssm/` のコミット履歴を gitgraph 風に可視化し、コミット詳細（変数一覧・型・サイズ・署名状態）の表示と、GUI からの `Checkout / Branch / Tag / Commit` を提供する。堅実だが以下の伸びしろがある。

- グラフ操作が素朴（ズーム/パン・検索・フィルタが無い）
- `merge` / `branch・tag の削除・リネーム` が GUI から行えない
- 詳細ペイン幅が固定（340px）、空状態がエラー文のみ
- webview が単一の手書きバニラJS（`media/graph.js`）で、拡張しづらい

**本マイルストーンの狙い**: Session Graph を「見て終わり」から「実際に手を動かす道具」へ。**実用的なグラフ操作**と**全面的な見た目/UX刷新**を、依存を最小に保ったまま実現する。

### 採用アプローチ

**洗練バニラ + esbuild**（検討した3案から選定）。

- 現行の手書きSVG/バニラJS路線を維持しつつ、webview を TypeScript 化して `esbuild` で単一ファイルにバンドルし、レンダラを責務ごとにモジュール分割する。
- 却下: 軽量フレームワーク（Preact/Lit）はビルド複雑化・バンドル増で今回スコープには過剰（YAGNI）。将来 diff/metrics/値インスペクションの3画面が乗って UI 状態が本当に膨らんだ段階で再検討する。
- 却下: 既存グラフライブラリ（@gitgraph/js, d3）は保守性/テーマ整合/CSP の面で旨みが薄く、操作系は結局自前実装が必要。

---

## 2. スコープ

### 2.1 やること（In scope）

**グラフ操作の強化**
- ズーム / パン（ホイール・ドラッグ・キーボード）、`Fit` / `Reset` / `HEADへ移動`
- 横断検索（コミットメッセージ / ハッシュ / author / ブランチ・タグ名 / 変数名）とハイライト、次/前マッチへジャンプ
- `merge`（Python 経由）
- `branch` / `tag` の **削除・リネーム**（`.ssm/` の参照ファイルを直接操作、Python 不要）
- リサイズ可能な詳細ペイン（幅を永続化）・折りたたみ
- キーボードナビゲーション（選択移動・操作ショートカット）

**見た目 / UX の全面刷新**
- 洗練3ゾーンレイアウト（上ツールバー / 左グラフ・右詳細（リサイズ可）/ 下ステータス）
- ノード・エッジ・ref バッジのビジュアル改善、テーマ整合の徹底（ダーク/ライト/ハイコントラスト）
- 空状態・オンボーディングの刷新
- 遷移アニメーション / マイクロインタラクション（`prefers-reduced-motion` 尊重）、トースト通知

**基盤**
- webview の TypeScript 化 + esbuild バンドル、レンダラのモジュール分割
- extension ↔ webview のメッセージ型を共有（型安全）
- `node:test` による純ロジックのユニットテスト
- **拡張アイコン `icon.png` の登録**

### 2.2 やらないこと（Out of scope — 後続フェーズ）

- コミット間 **diff ビュー**（変数の追加/変更/削除の可視化）
- **値インスペクション**（DataFrame/ndarray/dict の中身プレビュー）
- **メトリクス可視化**（checkpoint の loss/accuracy チャート）
- **remote push/pull** の GUI 操作
- 複数 `.ssm/` リポジトリの高度な切り替え
- ESLint/Prettier の本格導入（必要なら別途、最小限に留める）

### 2.3 成功基準

- 100+ コミットのグラフでもズーム/パン/検索がスムーズに動く
- GUI だけで `commit / checkout / branch / tag / merge / 削除 / リネーム` が完結する
- ダーク / ライト / ハイコントラストのいずれでも表示が破綻しない
- **SessionSmith 未インストールでも、閲覧および branch/tag の削除・リネームが可能**（現行思想を維持）
- `npm run compile` とパッケージング（`vsce package`）が通り、拡張が起動する
- 純ロジックのユニットテストが CI で green

---

## 3. アーキテクチャ

### 3.1 責務分担（設計の背骨）

| 種別 | 対象操作 | 実行先 | 理由 |
|---|---|---|---|
| 閲覧・参照操作（Python不要） | グラフ読み取り、branch/tag の削除・リネーム | ファイルシステム（`ssmReader` / `ssmRefs`） | `.ssm/` の参照は単なるファイル。SessionSmith 未インストールでも動く |
| ライブセッション操作（Python必須） | commit / checkout / merge / branch作成 / tag作成 | Python（`runner` 経由で Notebook kernel かターミナル） | ライブの Python セッション変数、または既存ライブラリ API に依存 |
| 表示のみ | 検索 / ズーム / パン / 選択 / レイアウト | webview | 表示状態のみ、副作用なし |

この分担により「閲覧・整理は Python なしで完結、実行操作のみ Python に送る」という v0.2.0 の思想を保つ。

### 3.2 モジュール構成

**extension 側（`extension/src/`）**

| ファイル | 役割 | 変更 |
|---|---|---|
| `extension.ts` | activation・コマンド登録・ツリー/グラフ配線（薄く保つ） | 改修 |
| `graphPanel.ts` | webview ライフサイクル・メッセージ仲介・新規操作のハンドラ | 改修 |
| `ssmReader.ts` | `.ssm/` 読み取り（コミット/ブランチ/タグ/HEAD） | 改修（検索用フィールド整理） |
| `ssmRefs.ts` | **新規**: branch/tag の削除・リネーム（`.bak` 退避・バリデーション・`config.current_branch` 追従） | 新規 |
| `runner.ts` | Python 実行（Notebook/ターミナル） | 現状維持 |
| `treeView.ts` | アクティビティバーのツリー | 改修（インラインアクション追加は任意） |
| `messages.ts` | **新規**: extension ↔ webview のメッセージ型（discriminated union） | 新規 |

**webview 側（`extension/webview/` 新設、esbuild で `media/graph.js` へバンドル）**

| ファイル | 役割 |
|---|---|
| `main.ts` | エントリ、イベント配線、`acquireVsCodeApi()` |
| `state.ts` | アプリ状態（selectedHash / filter / zoom / pan / paneWidth）と永続化（`getState`/`setState`） |
| `layout.ts` | レーン割り当て（既存 `layout()` を整理移設） |
| `render.ts` | SVG 描画（ノード / エッジ / ラベル / バッジ / 行背景） |
| `interaction.ts` | ズーム / パン / 検索 / キーボード / スプリッター |
| `detail.ts` | 詳細ペインの描画とアクション配線 |
| `format.ts` / `dom.ts` | ユーティリティ（既存 `truncate`/`formatDate`/`formatBytes`/`escapeHtml` を移設） |

### 3.3 ビルド

- `esbuild`（devDependency 追加）で `webview/main.ts` → `extension/media/graph.js`（IIFE・minify・sourcemap）。
- extension 本体は `tsc`（`src` → `out`）を継続。
- npm scripts:
  - `compile`: `tsc -p ./ && node esbuild.js`（または esbuild CLI）
  - `watch`: tsc watch と esbuild watch を並行
  - `package`: `vsce package`
- `.vscodeignore` に `webview/**` と `esbuild.js` を追加（ソースは同梱せず、バンドル後の `media/graph.js` のみ配布）。CSP/nonce は現行の方式を踏襲（`script-src 'nonce-...'`）。

### 3.4 メッセージ契約（`messages.ts`）

型付き discriminated union で extension ↔ webview を型安全に接続する。

- **extension → webview**: `graph`（GraphData）/ `error`（message）/ `loading`（bool）
- **webview → extension**: `ready` / `refresh` / `checkout`(hash) / `createBranch`(hash) / `createTag`(hash) / `commit` / `merge`(branch?) / `deleteRef`(kind, name) / `renameRef`(kind, name) / `copyHash`(hash)

---

## 4. 機能詳細

### 4.1 ズーム / パン
- SVG を `viewBox` ベースでズーム/パン。ホイール=ズーム、ドラッグ=パン。
- ツールバー: `Fit`（全体表示）/ `Reset`（等倍・原点）/ `HEADへ移動`、`＋`/`－` ズーム。
- キーボード: `+` `-` `0`（リセット）、矢印キーでパン。
- ズーム率をステータスバーに表示。

### 4.2 検索 / フィルタ
- ツールバーの検索ボックスで横断検索: メッセージ / ハッシュ / author / ブランチ・タグ名 / 変数名。
- マッチしたコミットをハイライト、非マッチを淡色化（dim）。
- `Enter` / `Shift+Enter` で次 / 前のマッチへスクロール＆選択。`/` で検索フォーカス、`Esc` で解除。
- （拡張余地・任意）`branch:` `var:` `signed:` などのフィルタ接頭辞。最小要件はフリーテキスト横断検索。

### 4.3 参照操作（branch / tag）
- **削除**: バッジまたは詳細ペインから発火 → 確認モーダル → `ssmRefs.deleteRef()` が `.ssm/branches/<name>` または `.ssm/tags/<name>` を削除（削除前に `.bak` 退避）。
  - ガード: 現在ブランチの削除、および唯一のブランチの削除は不可（警告表示）。
- **リネーム**: 入力ボックス → 検証（`^[A-Za-z0-9_.-]+$`・既存名との重複不可）→ 参照ファイルを rename。対象が現在ブランチなら `config`（`current_branch`）を追従更新。
- どちらも Python 不要。実行後は既存の FileSystemWatcher により自動で再読込・再描画。

### 4.4 merge
- 「Merge into current」→ 対象ブランチを QuickPick で選択 → 確認 → `ssm.merge(<name>)` を `runner` で Python 実行。
- コンフリクト等は SessionSmith が返すメッセージ（`SSMMergeConflictError` 等）をそのまま通知に表示。

### 4.5 リサイズ可能な詳細ペイン
- グラフ/詳細の境界にドラッグ可能なスプリッター。幅は webview state（`getState`/`setState`）に保存し、再表示時に復元。
- 詳細ペインの折りたたみ/展開ボタン。

### 4.6 選択・ナビゲーション
- `↑`/`↓` でコミット選択移動、選択コミットへスムーズスクロール。
- ショートカット: `c`=checkout / `b`=branch / `t`=tag / `/`=検索 / `Esc`=検索解除。
- 選択行・hover 行のハイライトを強化。

---

## 5. 見た目 / UX（洗練3ゾーンレイアウト）

```
┌─────────────────────────────────────────────┐
│ S ⎇main  [🔍 search...]   +Commit ⟳ Fit ± ⋯ │  ツールバー
├──────────────────────────────┬──────────────┤
│ ● Training complete   main    │ Commit detail │
│ │                             │ ────────────  │
│ ● Add validation      v1.0 🏷 │ [Checkout]    │
│ ├─● experiment                │ [Branch][Tag] │
│ ●    Data loaded              │ [Merge][🗑][✎]│
│                     (graph)   │ vars (12)...  │
├──────────────────────────────┴──────────────┤
│ 24 commits · 3 branches · 2 tags     zoom100%│  ステータス
└─────────────────────────────────────────────┘
```

- **ツールバー**: 小さめ S アイコン＋現在ブランチバッジ / 検索ボックス / `+Commit` `⟳Refresh` `Fit` `±ズーム` / `⋯`（低頻度操作のオーバーフロー）。
- **グラフ（左）**: 角丸ノード＋淡い影、HEAD はリング強調、merge は二重丸。レーン色は既存パレットを踏襲しつつライト/ハイコントラストでコントラスト検証。ref バッジは branch/tag/HEAD をピル型で色分け・アイコン付き・現在ブランチ強調。
- **詳細（右・リサイズ可）**: メッセージ / ハッシュ（monospace）/ アクション（`Checkout` `Branch` `Tag` `Merge` `削除` `リネーム` `Copy`）/ author・date・parents・署名・変数一覧。
- **ステータス（下）**: commits/branches/tags 件数 ＋ ズーム率 ＋ ローディングスピナー。

**空状態・オンボーディング**（現行はエラー文のみ → 刷新）
- ワークスペース未オープン: 案内メッセージ。
- `.ssm` が無い: `from SessionSmith import ssm; ssm.init()` をコピーボタン付きで提示、手順を数ステップで表示。
- コミットが無い: `+Commit` を強調した初回ガイド。

**アニメーション・マイクロインタラクション**（`prefers-reduced-motion` を尊重して無効化可能）
- 読み込み時のノードのフェード / 段階描画、選択コミットへのスムーズスクロール、詳細ペインのフェード、hover/ボタンのトランジション。
- 操作後のトースト（checkout 完了 / 削除 / リネーム / ハッシュコピー 等）。

**アクセシビリティ**: キーボード操作（§4.6）、フォーカスリング、ハイコントラストテーマ対応、reduced-motion。

---

## 6. 拡張アイコン（icon.png）

- 既存の `docs/icon.png`（1254×1254・約1.8MB、青→緑グラデーションの「S」ロゴ）を素材とする。
- **256×256 に縮小**して `extension/icon.png` として配置（パッケージ肥大化を回避）。
- `extension/package.json` に `"icon": "icon.png"` を登録（マーケットプレイス表示用）。
- アクティビティバーのアイコンは現行の codicon（`$(git-commit)`）を維持（VSCode は色付き png をマスクするため、カラーロゴはバー用に不向き。将来モノクロ SVG を別途用意する余地は残す）。
- `.vscodeignore` は png を除外しない（現行のまま同梱される）。

---

## 7. テスト・検証

**ユニットテスト（`node:test`、ゼロ依存、VSCode ホスト不要な純ロジックに集中）**
- `ssmReader`: `.ssm/` フィクスチャからのグラフ解析（コミット/ブランチ/タグ/HEAD、マージ親、署名判定、topoSort）。
- `layout`: レーン割り当て（直線履歴・分岐・マージ・複数ブランチ）。
- `ssmRefs`: 削除・リネームを tmp ディレクトリで（正常系・ガード・`.bak` 退避・`config` 追従）。
- 検索フィルタ関数: マッチ判定（メッセージ/ハッシュ/author/ref/変数名）。

**手動検証（F5 デバッグホスト + チェックリスト）**
- webview の DOM/SVG 挙動（ズーム/パン/検索ハイライト/スプリッター/キーボード）。
- 実操作の疎通: commit / checkout / merge（Notebook・ターミナル双方）/ 削除 / リネーム。
- テーマ3種（ダーク/ライト/ハイコントラスト）での表示。
- 空状態3種（ワークスペース無し / `.ssm` 無し / コミット無し）。

**検証コマンド**: `npm run compile`（tsc + esbuild が成功）、`node --test`（ユニットテスト green）、`vsce package`（`.vsix` 生成）。

---

## 8. リリース

- `extension/package.json`: version `0.2.0` → `0.3.0`、`"icon"` 追加、必要な `contributes.commands`（merge/削除/リネーム等）追加、`esbuild` を devDependencies に追加。
- `extension/README.md`: 新機能の説明・スクリーンショット枠・操作ガイドを更新。
- `extension/CHANGELOG.md`: **新設**し v0.3.0 の変更点を記載。
- `.github/workflows/extension-release.yml`: ビルド手順に esbuild を反映（`npm run compile` が両方を実行するなら差分は最小）。
- Open VSX / Marketplace への公開は任意（本設計の必須要件ではない）。

---

## 9. リスクと緩和

| リスク | 緩和策 |
|---|---|
| `ssmRefs` の FS 操作で `.ssm/` を破損 | 削除前に `.bak` 退避、厳格なバリデーション、現在/唯一ブランチのガード、watcher で即再読込 |
| esbuild 導入で CI/リリースが壊れる | `npm run compile` に集約し、CI とローカルで同一手順。sourcemap 付きで調査容易に |
| 大量コミットで SVG 描画が重い | `viewBox` ズーム＋必要に応じ可視範囲のみ描画（将来最適化の余地）。まず 100+ コミットで実測 |
| webview モジュール分割による退行 | 純ロジックを `node:test` でカバー、手動チェックリストで UI 疎通を確認 |
| Windows パス / 改行での ref 操作差異 | `path` を用い、ref ファイルは trim して比較。tmp ディレクトリテストで検証 |

---

## 10. 完了の定義（Definition of Done）

- §2.3 の成功基準をすべて満たす。
- 新規/改修モジュールが §3.2 の構成に沿っている。
- `node:test` が green、`npm run compile` と `vsce package` が成功。
- README / CHANGELOG / version / icon が更新済み。
- 手動チェックリスト（§7）を通過。
