# Session Graph をサイドバーにも表示 設計書

- **日付**: 2026-07-12
- **対象**: `extension/`（VSCode/Cursor 拡張）
- **取り込み先**: 未マージの PR #33（ブランチ `feature/extension-v0.3.0-session-graph`）に追加。v0.3.0 の一部。

## 背景・狙い

現状 Session Graph はエディタ領域の `WebviewPanel` としてのみ開く。アクティビティバーの SessionSmith パネルには `Sessions` ツリーだけがある。グラフを**サイドバーでも常時見られる**ようにする。

## 決定事項（ブレスト）

- サイドバー構成: **Sessions ツリーと併存**（`sessionsmith` ビューコンテナに「Session Graph」webview ビューを追加、ツリーの上）。両方とも折りたたみ可。
- 詳細の見せ方: **縦積み**（狭い時はグラフの下にコミット詳細をスタック）。
- エディタ全画面パネル（`Open Session Graph`）は**維持**。サイドバーのツールバーに「全画面で開く」導線を追加。
- 追加するのは既存機能のサイドバー表示のみ。新しいグラフ機能追加はしない。

## アーキテクチャ

現在ロジックが全て `SessionGraphPanel` に集中しているため、Panel/View 両対応にするための共有化を行う。

- **`getGraphHtml(webview, extensionUri)`（共有関数）**: 現 `SessionGraphPanel.getHtml()` の中身を切り出す。`vscode.Webview` を受け取り CSP/nonce/スクリプト/スタイル URI を解決して HTML を返す。
- **`GraphSession`（新クラス）**: `vscode.Webview` と「ワークスペース root 取得手段」を受け取り、以下を提供：
  - `update()` … `.ssm` を探して `readGraph` 結果を `postMessage({type:'graph'})`、無ければ `error` コード
  - `handleMessage(msg)` … `ready`/`refresh`/`checkout`/`createBranch`/`createTag`/`commit`/`merge`/`deleteRef`/`renameRef`/`copyHash`（現 `SessionGraphPanel` の `do*` 一式を移設）
  - `.ssm/**` の FileSystemWatcher（デバウンス付き自動更新）
  - `dispose()`
- **`SessionGraphPanel`（既存・改修）**: 自身の `WebviewPanel` を持ち、`GraphSession` に委譲するだけの薄いラッパに。挙動は不変（エディタ全画面パネルは従来通り動く）。
- **`SessionGraphViewProvider implements vscode.WebviewViewProvider`（新規）**: `resolveWebviewView` で `webview.options`（enableScripts, localResourceRoots）を設定、`getGraphHtml` を流し込み、`GraphSession` を生成して結線。`onDidChangeVisibility`/`onDidDispose` を扱う。
- **`extension.ts`**: `vscode.window.registerWebviewViewProvider('sessionsmithGraph', provider, { webviewOptions: { retainContextWhenHidden: true } })` を登録。

## contributes（package.json）

`contributes.views.sessionsmith` を、webview ビュー（グラフ）＋既存ツリーの2つにする（グラフを上に）:
```json
"views": {
  "sessionsmith": [
    { "id": "sessionsmithGraph", "name": "Session Graph", "type": "webview", "icon": "$(git-commit)", "contextualTitle": "SessionSmith" },
    { "id": "sessionsmithSessions", "name": "Sessions", "icon": "$(git-commit)", "contextualTitle": "SessionSmith" }
  ]
}
```
（既存の `sessionsmithSessions` ツリーはそのまま。`view/title` メニューの `when: view == sessionsmithSessions` は維持。）

## レスポンシブ（幅で自動切替）

webview が自身の幅を測り、閾値未満なら container に `.narrow` を付与。ウィンドウ resize でも再判定。

- JS（`webview/main.ts`）: `updateNarrow()` = `container.classList.toggle('narrow', graphPaneOrContainerWidth < 600)`。load 時と `window` の `resize` で呼ぶ。
- CSS（`media/graph.css`）:
  - `.narrow #container { flex-direction: column; }`
  - `.narrow #splitter { display: none; }`
  - `.narrow #detail-pane { width: auto; max-width: none; border-left: none; border-top: 1px solid var(--vscode-panel-border); max-height: 45%; }`
  - `.narrow #graph-pane { flex: 1 1 auto; min-height: 0; }`
- レイアウト堅牢化: `body { display:flex; flex-direction:column; }`、`#container { flex: 1 1 auto; min-height: 0; }` に変更（`calc(100vh - 76px)` 依存をやめ、狭い/低いビューでも破綻しないように）。
- 狭い時は保存済みペイン幅（`paneWidth`）を無視。

## サイドバーのツールバー導線

グラフ webview のツールバーに「⤢ 全画面で開く」ボタンを追加し、`postMessage({type:'openInEditor'})` → ホスト側で `sessionsmith.showSessionGraph` を実行。（`GraphSession.handleMessage` に `openInEditor` を追加。Panel 側では自分自身なので no-op で可。）

## テスト・検証

- 既存 `node:test` 14件は不変（純ロジック非改修）。`getGraphHtml`/`GraphSession` はVSCode API 依存のため単体テストは追加せず、F5 手動検証。
- ビルド: `npm run compile`（tsc+esbuild）成功、`vsce package` 成功。
- 手動: サイドバーの Session Graph にグラフが出る／狭い時に縦積み／`⤢` でエディタ全画面／ツリーと併存。

## リリース

- `extension/CHANGELOG.md` の 0.3.0 に「サイドバー表示（Session Graph webview ビュー）」を追記。version は 0.3.0 のまま（未リリースの PR に同梱）。

## スコープ外

新しいグラフ機能（diff/メトリクス/値インスペクション）は後続フェーズ。
