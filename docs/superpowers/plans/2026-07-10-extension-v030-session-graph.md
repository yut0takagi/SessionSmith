# SessionSmith 拡張 v0.3.0 — Session Graph 全面刷新 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** VSCode/Cursor 拡張の Session Graph を、実用的なグラフ操作（ズーム/パン・検索・merge・branch/tag 削除リネーム・リサイズ可能ペイン）と全面的な見た目/UX 刷新に作り替え、webview を TypeScript 化 + esbuild バンドル化する。

**Architecture:** webview を `extension/webview/*.ts` に責務分割し `esbuild` で `media/graph.js` へバンドル。閲覧と branch/tag の削除・リネームは `.ssm/` を直接読む/書く FS 操作（Python 不要）、commit/checkout/merge/作成系は既存 `runner` 経由で Python 実行。純ロジック（layout・search・ssmRefs・ssmReader）は `node:test` でユニットテスト、UI は F5 デバッグホスト + 手動チェックリストで検証。

**Tech Stack:** TypeScript, VSCode Extension API, esbuild, `node:test`（ゼロ依存）, SVG（バニラ）, `vsce`。

**設計書:** `docs/superpowers/specs/2026-07-10-sessionsmith-extension-v030-session-graph-design.md`

**作業ディレクトリ:** リポジトリルート `/Users/s32747/SessionSmith`。拡張は `extension/` 配下。全コマンドは特記なき限り `extension/` で実行する（`cd extension` 済み前提、または各コマンドで明示）。

---

## File Structure

**新規作成**
- `extension/esbuild.js` — webview バンドルビルドスクリプト
- `extension/icon.png` — マーケットプレイス用アイコン（`docs/icon.png` を 256×256 に縮小）
- `extension/src/messages.ts` — extension ↔ webview のメッセージ型（discriminated union）
- `extension/src/ssmRefs.ts` — branch/tag の削除・リネーム（FS 操作・`.bak` 退避・検証）
- `extension/webview/main.ts` — webview エントリ、イベント配線、`acquireVsCodeApi()`
- `extension/webview/state.ts` — webview の状態と永続化（`getState`/`setState`）
- `extension/webview/layout.ts` — レーン割り当て（既存 `media/graph.js` の `layout()` を移設）
- `extension/webview/render.ts` — SVG 描画（ノード/エッジ/バッジ/行）
- `extension/webview/interaction.ts` — ズーム/パン/検索/キーボード/スプリッター
- `extension/webview/detail.ts` — 詳細ペイン描画とアクション配線
- `extension/webview/search.ts` — 検索フィルタ（純関数）
- `extension/webview/format.ts` — `truncate`/`formatDate`/`formatBytes`/`escapeHtml`
- `extension/webview/gtypes.ts` — webview 内で使うグラフ型の再エクスポート（`src/ssmReader` から `import type`）
- `extension/test/ssmReader.test.ts` — `.ssm` 解析のテスト
- `extension/test/layout.test.ts` — レーン割り当てのテスト
- `extension/test/search.test.ts` — 検索フィルタのテスト
- `extension/test/ssmRefs.test.ts` — 削除・リネームのテスト
- `extension/CHANGELOG.md` — 変更履歴（新設）

**変更**
- `extension/package.json` — scripts / esbuild devDep / `icon` / 新コマンド / version 0.3.0
- `extension/tsconfig.json` — `webview` と `test` を含め `out/` へ出力
- `extension/.vscodeignore` — `webview/**` `esbuild.js` `test/**` を除外
- `extension/src/graphPanel.ts` — merge/deleteRef/renameRef/loading ハンドラ、型付きメッセージ
- `extension/src/ssmReader.ts` — （必要最小限）検索・型の整理
- `extension/media/graph.css` — 3ゾーンレイアウト刷新
- `extension/media/graph.js` — 以後は esbuild 生成物（手編集しない）
- `extension/README.md` — 新機能の記載
- `.github/workflows/extension-release.yml` — esbuild を含むビルド手順の確認

**責務の原則（設計書 §3.1）**
- Python 不要: グラフ読み取り（`ssmReader`）、branch/tag 削除・リネーム（`ssmRefs`）
- Python 必須: commit / checkout / merge / branch 作成 / tag 作成（`runner`）

---

## Phase 0 — ビルド基盤とアイコン

### Task 1: esbuild ビルドパイプラインと tsconfig の整備

**Files:**
- Create: `extension/esbuild.js`
- Create: `extension/webview/main.ts`（暫定スタブ）
- Modify: `extension/tsconfig.json`
- Modify: `extension/package.json`
- Modify: `extension/.vscodeignore`

- [ ] **Step 1: esbuild を devDependency に追加**

Run（`extension/` で実行）:
```bash
npm install --save-dev esbuild@^0.23.0
```
Expected: `package.json` の `devDependencies` に `esbuild` が追加され、`node_modules/esbuild` が生成される。

- [ ] **Step 2: 暫定 webview エントリを作成**

Create `extension/webview/main.ts`:
```ts
// esbuild パイプライン疎通確認用の暫定エントリ。Task 8 で本実装に差し替える。
const vscode = acquireVsCodeApi();
vscode.postMessage({ type: 'ready' });

declare function acquireVsCodeApi(): { postMessage(msg: unknown): void; getState(): unknown; setState(s: unknown): void };
```

- [ ] **Step 3: esbuild ビルドスクリプトを作成**

Create `extension/esbuild.js`:
```js
// @ts-check
const esbuild = require('esbuild');

const watch = process.argv.includes('--watch');
const production = process.argv.includes('--production');

/** @type {import('esbuild').BuildOptions} */
const options = {
    entryPoints: ['webview/main.ts'],
    bundle: true,
    format: 'iife',
    platform: 'browser',
    target: 'es2020',
    outfile: 'media/graph.js',
    sourcemap: !production,
    minify: production,
    logLevel: 'info',
};

async function run() {
    if (watch) {
        const ctx = await esbuild.context(options);
        await ctx.watch();
        console.log('[esbuild] watching webview...');
    } else {
        await esbuild.build(options);
        console.log('[esbuild] webview bundle written to media/graph.js');
    }
}

run().catch((e) => {
    console.error(e);
    process.exit(1);
});
```

- [ ] **Step 4: tsconfig を webview / test を含む構成に更新**

Overwrite `extension/tsconfig.json`:
```json
{
    "compilerOptions": {
        "module": "commonjs",
        "target": "ES2020",
        "lib": ["ES2020", "DOM"],
        "outDir": "out",
        "rootDir": ".",
        "sourceMap": true,
        "strict": true,
        "esModuleInterop": true,
        "skipLibCheck": true,
        "resolveJsonModule": true
    },
    "include": ["src/**/*.ts", "webview/**/*.ts", "test/**/*.ts"],
    "exclude": ["node_modules", "out", ".vscode-test"]
}
```

Note: `tsc` は型チェックとテスト用 JS 出力（`out/`）を担当。webview のブラウザ向け成果物は esbuild が `media/graph.js` を生成する。両者は独立。

- [ ] **Step 5: package.json の scripts を更新**

Modify `extension/package.json` の `"scripts"` を次に置き換える:
```json
  "scripts": {
    "vscode:prepublish": "npm run compile -- --production",
    "compile": "tsc -p ./ && node esbuild.js",
    "watch": "tsc -watch -p ./ & node esbuild.js --watch",
    "test": "npm run compile && node --test out/test",
    "package": "vsce package"
  },
```

- [ ] **Step 6: .vscodeignore にソースを追加**

Overwrite `extension/.vscodeignore`:
```
.vscode/**
.vscode-test/**
src/**
webview/**
test/**
esbuild.js
.gitignore
.yarnrc
vsc-extension-quickstart.md
**/tsconfig.json
**/*.map
**/*.ts
!out/**/*.js
```

Note: `media/graph.js`（esbuild 生成物）と `media/graph.css` は同梱される。`webview/*.ts` はバンドル済みのため同梱不要。

- [ ] **Step 7: ビルド疎通を確認**

Run（`extension/`）:
```bash
npm run compile
```
Expected: エラーなく完了し、`media/graph.js` が esbuild により再生成される（`[esbuild] webview bundle written to media/graph.js`）。`out/` に tsc 出力が生成される。

- [ ] **Step 8: コミット**

```bash
git add extension/esbuild.js extension/webview/main.ts extension/tsconfig.json extension/package.json extension/package-lock.json extension/.vscodeignore
git commit -m "build(extension): esbuildでwebviewをバンドルする基盤を追加"
```

---

### Task 2: 拡張アイコン（icon.png）の登録

**Files:**
- Create: `extension/icon.png`
- Modify: `extension/package.json`

- [ ] **Step 1: docs/icon.png を 256×256 に縮小して配置**

Run（リポジトリルート `/Users/s32747/SessionSmith`）:
```bash
sips -Z 256 docs/icon.png --out extension/icon.png
```
Expected: `extension/icon.png` が 256×256 で生成される。macOS 以外なら ImageMagick 等で `convert docs/icon.png -resize 256x256 extension/icon.png` を使う。

- [ ] **Step 2: 生成物の寸法を確認**

Run:
```bash
sips -g pixelWidth -g pixelHeight extension/icon.png
```
Expected: `pixelWidth: 256` / `pixelHeight: 256`。

- [ ] **Step 3: package.json に icon を登録**

Modify `extension/package.json`。`"version"` 行の直後（トップレベル）に追加:
```json
  "icon": "icon.png",
```

- [ ] **Step 4: version を 0.3.0 に更新**

Modify `extension/package.json`:
```json
  "version": "0.3.0",
```

- [ ] **Step 5: コミット**

```bash
git add extension/icon.png extension/package.json
git commit -m "feat(extension): マーケットプレイス用アイコンを登録し v0.3.0 に更新"
```

---

## Phase 1 — 純ロジックとテスト（TDD）

### Task 3: ssmReader の特性テスト

**Files:**
- Create: `extension/test/ssmReader.test.ts`
- Modify: `extension/src/ssmReader.ts`（必要な場合のみ、export 追加）

- [ ] **Step 1: フィクスチャを生成するヘルパー付きテストを書く**

Create `extension/test/ssmReader.test.ts`:
```ts
import { test } from 'node:test';
import assert from 'node:assert';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import { readGraph } from '../src/ssmReader';

function makeSsm(): string {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), 'ssm-'));
    const ssm = path.join(root, '.ssm');
    fs.mkdirSync(path.join(ssm, 'commits'), { recursive: true });
    fs.mkdirSync(path.join(ssm, 'branches'), { recursive: true });
    fs.mkdirSync(path.join(ssm, 'tags'), { recursive: true });

    const c1 = {
        message: 'first', author: 'a', timestamp: '2026-01-01T00:00:00',
        variables: { x: { hash: 'h', type: 'int', size: 28 } },
    };
    const c2 = {
        message: 'second', author: 'a', timestamp: '2026-01-02T00:00:00',
        parent: 'aaa', signature: 'sig',
        variables: { y: { hash: 'h2', type: 'list', size: 64 } },
    };
    fs.writeFileSync(path.join(ssm, 'commits', 'aaa.json'), JSON.stringify(c1));
    fs.writeFileSync(path.join(ssm, 'commits', 'bbb.json'), JSON.stringify(c2));
    fs.writeFileSync(path.join(ssm, 'branches', 'main'), 'bbb');
    fs.writeFileSync(path.join(ssm, 'tags', 'v1'), 'aaa');
    fs.writeFileSync(path.join(ssm, 'HEAD'), 'bbb');
    return ssm;
}

test('readGraph parses commits, branches, tags, HEAD', () => {
    const ssm = makeSsm();
    const g = readGraph(ssm);
    assert.equal(g.commits.length, 2);
    assert.equal(g.branches.length, 1);
    assert.equal(g.branches[0].name, 'main');
    assert.equal(g.tags[0].name, 'v1');
    assert.equal(g.head, 'bbb');
});

test('readGraph orders commits newest-first (topoSort)', () => {
    const ssm = makeSsm();
    const g = readGraph(ssm);
    assert.equal(g.commits[0].hash, 'bbb');
    assert.equal(g.commits[1].hash, 'aaa');
});

test('readGraph detects signed commits and parents', () => {
    const ssm = makeSsm();
    const g = readGraph(ssm);
    const bbb = g.commits.find((c) => c.hash === 'bbb')!;
    assert.equal(bbb.signed, true);
    assert.deepEqual(bbb.parents, ['aaa']);
    const aaa = g.commits.find((c) => c.hash === 'aaa')!;
    assert.equal(aaa.signed, false);
});
```

- [ ] **Step 2: テストを実行して通ることを確認**

Run（`extension/`）:
```bash
npm run compile && node --test out/test/ssmReader.test.js
```
Expected: 3 tests pass。既存 `readGraph` は仕様を満たしているため、そのまま green になる（特性テスト）。失敗する場合は `src/ssmReader.ts` の該当挙動を確認・修正する。

- [ ] **Step 3: コミット**

```bash
git add extension/test/ssmReader.test.ts
git commit -m "test(extension): ssmReader のグラフ解析に特性テストを追加"
```

---

### Task 4: layout モジュールの抽出とテスト

**Files:**
- Create: `extension/webview/gtypes.ts`
- Create: `extension/webview/layout.ts`
- Create: `extension/test/layout.test.ts`

- [ ] **Step 1: webview 用のグラフ型を型再エクスポート**

Create `extension/webview/gtypes.ts`:
```ts
// webview 側で使うグラフ型。src/ssmReader の型を型として再利用する（実体は import されない）。
export type { CommitNode, BranchRef, TagRef, GraphData } from '../src/ssmReader';
```

- [ ] **Step 2: layout の失敗テストを書く**

Create `extension/test/layout.test.ts`:
```ts
import { test } from 'node:test';
import assert from 'node:assert';
import { layout } from '../webview/layout';
import type { CommitNode } from '../src/ssmReader';

function commit(hash: string, parents: string[]): CommitNode {
    return {
        hash, message: hash, author: 'a', timestamp: '', parents,
        isMerge: parents.length > 1, variables: {}, varCount: 0, totalSize: 0, signed: false,
    };
}

test('layout: linear history uses a single column', () => {
    const commits = [commit('c', ['b']), commit('b', ['a']), commit('a', [])];
    const { pos, maxCol } = layout(commits);
    assert.equal(maxCol, 0);
    assert.equal(pos.get('c')!.col, 0);
    assert.equal(pos.get('a')!.row, 2);
});

test('layout: a branch adds a lane', () => {
    // c(merge of b,d) -> b -> a ; d -> a
    const commits = [
        commit('c', ['b', 'd']),
        commit('b', ['a']),
        commit('d', ['a']),
        commit('a', []),
    ];
    const { pos, maxCol } = layout(commits);
    assert.ok(maxCol >= 1, 'merge should occupy more than one lane');
    assert.ok(pos.has('d'));
});
```

- [ ] **Step 3: テストを実行して失敗を確認**

Run:
```bash
npm run compile
```
Expected: `webview/layout` が未作成のためコンパイルエラー（`Cannot find module '../webview/layout'`）。

- [ ] **Step 4: layout を実装（既存 media/graph.js の layout() を TS 化して移設）**

Create `extension/webview/layout.ts`:
```ts
import type { CommitNode } from '../src/ssmReader';

export interface LayoutResult {
    pos: Map<string, { col: number; row: number }>;
    maxCol: number;
}

/** gitgraph 風のレーン割り当て。commits は新しい順（topoSort 済み）を前提とする。 */
export function layout(commits: CommitNode[]): LayoutResult {
    const pos = new Map<string, { col: number; row: number }>();
    const lanes: (string | null)[] = [];

    function firstFree(): number {
        for (let i = 0; i < lanes.length; i++) {
            if (lanes[i] === null || lanes[i] === undefined) {
                return i;
            }
        }
        lanes.push(null);
        return lanes.length - 1;
    }

    for (let row = 0; row < commits.length; row++) {
        const c = commits[row];
        let col = lanes.indexOf(c.hash);
        if (col === -1) {
            col = firstFree();
        }
        for (let i = 0; i < lanes.length; i++) {
            if (lanes[i] === c.hash && i !== col) {
                lanes[i] = null;
            }
        }
        pos.set(c.hash, { col, row });

        const parents = c.parents || [];
        if (parents.length === 0) {
            lanes[col] = null;
        } else {
            lanes[col] = parents[0];
            for (let p = 1; p < parents.length; p++) {
                if (lanes.indexOf(parents[p]) === -1) {
                    const nc = firstFree();
                    lanes[nc] = parents[p];
                }
            }
        }
    }

    let maxCol = 0;
    pos.forEach((p) => {
        if (p.col > maxCol) {
            maxCol = p.col;
        }
    });
    return { pos, maxCol };
}
```

- [ ] **Step 5: テストを実行して通ることを確認**

Run:
```bash
npm run compile && node --test out/test/layout.test.js
```
Expected: 2 tests pass。

- [ ] **Step 6: コミット**

```bash
git add extension/webview/gtypes.ts extension/webview/layout.ts extension/test/layout.test.ts
git commit -m "feat(extension): レーン割り当てを webview/layout.ts に抽出しテストを追加"
```

---

### Task 5: 検索フィルタ（純関数）

**Files:**
- Create: `extension/webview/search.ts`
- Create: `extension/test/search.test.ts`

- [ ] **Step 1: 検索の失敗テストを書く**

Create `extension/test/search.test.ts`:
```ts
import { test } from 'node:test';
import assert from 'node:assert';
import { matchesQuery } from '../webview/search';
import type { CommitNode } from '../src/ssmReader';

function commit(over: Partial<CommitNode>): CommitNode {
    return {
        hash: 'abcdef0', message: '', author: 'alice', timestamp: '',
        parents: [], isMerge: false, variables: {}, varCount: 0, totalSize: 0, signed: false,
        ...over,
    };
}

test('empty query matches everything', () => {
    assert.equal(matchesQuery(commit({}), ''), true);
    assert.equal(matchesQuery(commit({}), '   '), true);
});

test('matches message, hash, author case-insensitively', () => {
    const c = commit({ message: 'Fix Training loop', hash: 'deadbee' });
    assert.equal(matchesQuery(c, 'training'), true);
    assert.equal(matchesQuery(c, 'DEADBEE'), true);
    assert.equal(matchesQuery(c, 'alice'), true);
    assert.equal(matchesQuery(c, 'nope'), false);
});

test('matches variable names', () => {
    const c = commit({ variables: { model_weights: { hash: 'h', type: 'ndarray', size: 1 } } });
    assert.equal(matchesQuery(c, 'model_'), true);
    assert.equal(matchesQuery(c, 'ndarray'), true);
});
```

- [ ] **Step 2: テストを実行して失敗を確認**

Run:
```bash
npm run compile
```
Expected: `webview/search` 未作成でコンパイルエラー。

- [ ] **Step 3: search を実装**

Create `extension/webview/search.ts`:
```ts
import type { CommitNode } from '../src/ssmReader';

/**
 * コミットが検索クエリにマッチするか判定する（大文字小文字を無視）。
 * 対象: メッセージ / ハッシュ / author / 変数名 / 変数型。
 * 空クエリは常に true。
 */
export function matchesQuery(c: CommitNode, rawQuery: string): boolean {
    const q = rawQuery.trim().toLowerCase();
    if (!q) {
        return true;
    }
    if (c.message.toLowerCase().includes(q)) return true;
    if (c.hash.toLowerCase().includes(q)) return true;
    if (c.author.toLowerCase().includes(q)) return true;
    for (const name of Object.keys(c.variables || {})) {
        if (name.toLowerCase().includes(q)) return true;
        const t = c.variables[name]?.type;
        if (t && t.toLowerCase().includes(q)) return true;
    }
    return false;
}
```

- [ ] **Step 4: テストを実行して通ることを確認**

Run:
```bash
npm run compile && node --test out/test/search.test.js
```
Expected: 3 tests pass。

- [ ] **Step 5: コミット**

```bash
git add extension/webview/search.ts extension/test/search.test.ts
git commit -m "feat(extension): コミット横断検索フィルタ matchesQuery を追加"
```

---

### Task 6: ssmRefs — branch/tag の削除・リネーム（FS 操作）

**Files:**
- Create: `extension/src/ssmRefs.ts`
- Create: `extension/test/ssmRefs.test.ts`

- [ ] **Step 1: 失敗テストを書く**

Create `extension/test/ssmRefs.test.ts`:
```ts
import { test } from 'node:test';
import assert from 'node:assert';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import { deleteRef, renameRef, RefError } from '../src/ssmRefs';

function makeSsm(): string {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), 'ssmrefs-'));
    const ssm = path.join(root, '.ssm');
    fs.mkdirSync(path.join(ssm, 'branches'), { recursive: true });
    fs.mkdirSync(path.join(ssm, 'tags'), { recursive: true });
    fs.writeFileSync(path.join(ssm, 'branches', 'main'), 'aaa');
    fs.writeFileSync(path.join(ssm, 'branches', 'feature'), 'bbb');
    fs.writeFileSync(path.join(ssm, 'tags', 'v1'), 'aaa');
    fs.writeFileSync(path.join(ssm, 'config'), JSON.stringify({ current_branch: 'main' }));
    return ssm;
}

test('deleteRef removes a branch file and leaves a .bak', () => {
    const ssm = makeSsm();
    deleteRef(ssm, 'branch', 'feature');
    assert.equal(fs.existsSync(path.join(ssm, 'branches', 'feature')), false);
    assert.equal(fs.existsSync(path.join(ssm, 'branches', 'feature.bak')), true);
});

test('deleteRef refuses to delete the current branch', () => {
    const ssm = makeSsm();
    assert.throws(() => deleteRef(ssm, 'branch', 'main'), RefError);
});

test('deleteRef refuses to delete the only branch', () => {
    const ssm = makeSsm();
    fs.unlinkSync(path.join(ssm, 'branches', 'feature'));
    assert.throws(() => deleteRef(ssm, 'branch', 'main'), RefError);
});

test('renameRef moves the file and updates current_branch', () => {
    const ssm = makeSsm();
    renameRef(ssm, 'branch', 'main', 'trunk');
    assert.equal(fs.existsSync(path.join(ssm, 'branches', 'trunk')), true);
    assert.equal(fs.existsSync(path.join(ssm, 'branches', 'main')), false);
    const cfg = JSON.parse(fs.readFileSync(path.join(ssm, 'config'), 'utf8'));
    assert.equal(cfg.current_branch, 'trunk');
});

test('renameRef rejects invalid names and duplicates', () => {
    const ssm = makeSsm();
    assert.throws(() => renameRef(ssm, 'branch', 'feature', 'bad name'), RefError);
    assert.throws(() => renameRef(ssm, 'branch', 'feature', 'main'), RefError);
});
```

- [ ] **Step 2: テストを実行して失敗を確認**

Run:
```bash
npm run compile
```
Expected: `src/ssmRefs` 未作成でコンパイルエラー。

- [ ] **Step 3: ssmRefs を実装**

Create `extension/src/ssmRefs.ts`:
```ts
import * as fs from 'fs';
import * as path from 'path';

export type RefKind = 'branch' | 'tag';

export class RefError extends Error {
    constructor(message: string) {
        super(message);
        this.name = 'RefError';
    }
}

const NAME_RE = /^[A-Za-z0-9_.-]+$/;

function refDir(ssmPath: string, kind: RefKind): string {
    return path.join(ssmPath, kind === 'branch' ? 'branches' : 'tags');
}

function listRefNames(ssmPath: string, kind: RefKind): string[] {
    const dir = refDir(ssmPath, kind);
    try {
        return fs
            .readdirSync(dir)
            .filter((f) => !f.endsWith('.bak') && !f.endsWith('.tmp'));
    } catch {
        return [];
    }
}

function readConfig(ssmPath: string): Record<string, unknown> {
    try {
        return JSON.parse(fs.readFileSync(path.join(ssmPath, 'config'), 'utf8'));
    } catch {
        return {};
    }
}

function writeConfig(ssmPath: string, cfg: Record<string, unknown>): void {
    fs.writeFileSync(path.join(ssmPath, 'config'), JSON.stringify(cfg, null, 2));
}

/** branch/tag の参照ファイルを削除する（`.bak` に退避）。 */
export function deleteRef(ssmPath: string, kind: RefKind, name: string): void {
    const file = path.join(refDir(ssmPath, kind), name);
    if (!fs.existsSync(file)) {
        throw new RefError(`${kind} '${name}' が見つかりません`);
    }
    if (kind === 'branch') {
        const cfg = readConfig(ssmPath);
        if (cfg.current_branch === name) {
            throw new RefError(`現在のブランチ '${name}' は削除できません`);
        }
        if (listRefNames(ssmPath, 'branch').length <= 1) {
            throw new RefError('唯一のブランチは削除できません');
        }
    }
    fs.renameSync(file, file + '.bak');
}

/** branch/tag の参照ファイルをリネームする。branch が現在ブランチなら config を追従。 */
export function renameRef(
    ssmPath: string,
    kind: RefKind,
    oldName: string,
    newName: string
): void {
    if (!NAME_RE.test(newName)) {
        throw new RefError('名前には英数字・アンダースコア・ハイフン・ドットのみ使用できます');
    }
    const dir = refDir(ssmPath, kind);
    const src = path.join(dir, oldName);
    const dst = path.join(dir, newName);
    if (!fs.existsSync(src)) {
        throw new RefError(`${kind} '${oldName}' が見つかりません`);
    }
    if (fs.existsSync(dst)) {
        throw new RefError(`'${newName}' は既に存在します`);
    }
    fs.renameSync(src, dst);
    if (kind === 'branch') {
        const cfg = readConfig(ssmPath);
        if (cfg.current_branch === oldName) {
            cfg.current_branch = newName;
            writeConfig(ssmPath, cfg);
        }
    }
}
```

- [ ] **Step 4: テストを実行して通ることを確認**

Run:
```bash
npm run compile && node --test out/test/ssmRefs.test.js
```
Expected: 5 tests pass。

- [ ] **Step 5: 全テストをまとめて実行**

Run:
```bash
node --test out/test
```
Expected: ssmReader / layout / search / ssmRefs のすべてが pass。

- [ ] **Step 6: コミット**

```bash
git add extension/src/ssmRefs.ts extension/test/ssmRefs.test.ts
git commit -m "feat(extension): branch/tag の削除・リネームを FS 操作で実装(ssmRefs)"
```

---

## Phase 2 — メッセージ型と extension 側の配線

### Task 7: 共有メッセージ型と graphPanel の新ハンドラ

**Files:**
- Create: `extension/src/messages.ts`
- Modify: `extension/src/graphPanel.ts`

- [ ] **Step 1: メッセージ型を定義**

Create `extension/src/messages.ts`:
```ts
import type { GraphData } from './ssmReader';

/** extension → webview */
export type HostToWebview =
    | { type: 'graph'; data: GraphData }
    | { type: 'error'; message: string }
    | { type: 'loading'; value: boolean };

/** webview → extension */
export type WebviewToHost =
    | { type: 'ready' }
    | { type: 'refresh' }
    | { type: 'commit' }
    | { type: 'checkout'; hash: string }
    | { type: 'createBranch'; hash: string }
    | { type: 'createTag'; hash: string }
    | { type: 'merge'; branch?: string }
    | { type: 'deleteRef'; kind: 'branch' | 'tag'; name: string }
    | { type: 'renameRef'; kind: 'branch' | 'tag'; name: string }
    | { type: 'copyHash'; hash: string };
```

- [ ] **Step 2: graphPanel に新ハンドラを追加**

Modify `extension/src/graphPanel.ts`。先頭の import に追加:
```ts
import { deleteRef, renameRef, RefError, RefKind } from './ssmRefs';
```

`handleMessage` の `switch` に次の case を追加（`copyHash` case の前）:
```ts
            case 'merge':
                await this.doMerge(msg.branch);
                return;
            case 'deleteRef':
                await this.doDeleteRef(msg.kind, msg.name);
                return;
            case 'renameRef':
                await this.doRenameRef(msg.kind, msg.name);
                return;
```

- [ ] **Step 3: doMerge / doDeleteRef / doRenameRef を実装**

Modify `extension/src/graphPanel.ts`。`doCommit()` メソッドの直後に追加:
```ts
    private async doMerge(preselected?: string): Promise<void> {
        const data = this.currentGraph();
        if (!data) {
            return;
        }
        const current = data.currentBranch;
        const candidates = data.branches
            .map((b) => b.name)
            .filter((n) => n !== current);
        if (candidates.length === 0) {
            vscode.window.showInformationMessage('マージ可能なブランチがありません。');
            return;
        }
        const branch =
            preselected && candidates.includes(preselected)
                ? preselected
                : await vscode.window.showQuickPick(candidates, {
                      placeHolder: `${current ?? 'HEAD'} にマージするブランチを選択`,
                  });
        if (!branch) {
            return;
        }
        const ok = await vscode.window.showWarningMessage(
            `ブランチ '${branch}' を現在のブランチにマージしますか？`,
            { modal: true },
            'マージ'
        );
        if (ok !== 'マージ') {
            return;
        }
        await runSsmCode(
            `from SessionSmith import ssm; ssm.merge(${py(branch)})`,
            this.workspaceDir()
        );
    }

    private async doDeleteRef(kind: RefKind, name: string): Promise<void> {
        if (!this.ssmPath) {
            return;
        }
        const label = kind === 'branch' ? 'ブランチ' : 'タグ';
        const ok = await vscode.window.showWarningMessage(
            `${label} '${name}' を削除しますか？（.bak に退避されます）`,
            { modal: true },
            '削除'
        );
        if (ok !== '削除') {
            return;
        }
        try {
            deleteRef(this.ssmPath, kind, name);
            vscode.window.showInformationMessage(`${label} '${name}' を削除しました。`);
            this.update();
        } catch (e) {
            const message = e instanceof RefError ? e.message : String(e);
            vscode.window.showErrorMessage(`削除に失敗しました: ${message}`);
        }
    }

    private async doRenameRef(kind: RefKind, name: string): Promise<void> {
        if (!this.ssmPath) {
            return;
        }
        const label = kind === 'branch' ? 'ブランチ' : 'タグ';
        const newName = await vscode.window.showInputBox({
            prompt: `${label} '${name}' の新しい名前`,
            value: name,
            validateInput: (v) =>
                /^[A-Za-z0-9_.-]+$/.test(v) ? null : '英数字・_・-・. のみ使用できます',
        });
        if (!newName || newName === name) {
            return;
        }
        try {
            renameRef(this.ssmPath, kind, name, newName);
            vscode.window.showInformationMessage(`'${name}' を '${newName}' にリネームしました。`);
            this.update();
        } catch (e) {
            const message = e instanceof RefError ? e.message : String(e);
            vscode.window.showErrorMessage(`リネームに失敗しました: ${message}`);
        }
    }
```

- [ ] **Step 4: currentGraph ヘルパーを追加**

Modify `extension/src/graphPanel.ts`。`workspaceDir()` メソッドの直後に追加:
```ts
    private currentGraph(): import('./ssmReader').GraphData | null {
        if (!this.ssmPath) {
            return null;
        }
        try {
            const { readGraph } = require('./ssmReader');
            return readGraph(this.ssmPath);
        } catch {
            return null;
        }
    }
```

- [ ] **Step 5: コンパイルを確認**

Run（`extension/`）:
```bash
npm run compile
```
Expected: 型エラーなく完了。`msg` の型は今は `any` のままでも可（webview 実装後に厳密化）。

- [ ] **Step 6: コミット**

```bash
git add extension/src/messages.ts extension/src/graphPanel.ts
git commit -m "feat(extension): merge/削除/リネームのハンドラと共有メッセージ型を追加"
```

---

## Phase 3 — webview 本実装（UI）

> このフェーズは UI 中心で、`node:test` では検証できない。各タスクの最後は **F5 デバッグホストでの手動確認**。手動確認手順は Task 12 のチェックリストに集約する。

### Task 8: webview の骨組み（format / state / 描画パイプライン）

**Files:**
- Create: `extension/webview/format.ts`
- Create: `extension/webview/state.ts`
- Rewrite: `extension/webview/main.ts`
- Create: `extension/webview/render.ts`
- Create: `extension/webview/detail.ts`
- Reference: 既存 `extension/media/graph.js`（移設元）

- [ ] **Step 1: format ユーティリティを移設**

Create `extension/webview/format.ts`（既存 `media/graph.js` の該当関数を TS 化）:
```ts
export function truncate(s: string, n: number): string {
    return s.length > n ? s.slice(0, n - 1) + '…' : s;
}

export function formatDate(iso: string): string {
    if (!iso) return '';
    const d = new Date(iso);
    if (isNaN(d.getTime())) return iso;
    const pad = (x: number) => String(x).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(
        d.getHours()
    )}:${pad(d.getMinutes())}`;
}

export function formatBytes(n: number): string {
    if (n < 1024) return n + ' B';
    if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' KB';
    return (n / (1024 * 1024)).toFixed(1) + ' MB';
}

export function escapeHtml(s: string): string {
    return String(s)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}
```

- [ ] **Step 2: 状態管理を実装**

Create `extension/webview/state.ts`:
```ts
export interface ViewState {
    selectedHash: string | null;
    query: string;
    zoom: number;
    panX: number;
    panY: number;
    paneWidth: number;
    detailCollapsed: boolean;
}

const DEFAULT: ViewState = {
    selectedHash: null,
    query: '',
    zoom: 1,
    panX: 0,
    panY: 0,
    paneWidth: 340,
    detailCollapsed: false,
};

interface VsCodeApi {
    postMessage(msg: unknown): void;
    getState(): Partial<ViewState> | undefined;
    setState(s: ViewState): void;
}

export class Store {
    private state: ViewState;
    constructor(private readonly api: VsCodeApi) {
        this.state = { ...DEFAULT, ...(api.getState() ?? {}) };
    }
    get(): ViewState {
        return this.state;
    }
    set(patch: Partial<ViewState>): void {
        this.state = { ...this.state, ...patch };
        this.api.setState(this.state);
    }
    post(msg: unknown): void {
        this.api.postMessage(msg);
    }
}
```

- [ ] **Step 3: 詳細ペインを実装**

Create `extension/webview/detail.ts`:
```ts
import type { CommitNode, GraphData } from '../src/ssmReader';
import { escapeHtml, formatBytes } from './format';

export interface DetailActions {
    checkout(hash: string): void;
    branch(hash: string): void;
    tag(hash: string): void;
    merge(): void;
    copy(hash: string): void;
}

export function renderDetail(
    pane: HTMLElement,
    c: CommitNode | undefined,
    _graph: GraphData,
    actions: DetailActions
): void {
    if (!c) {
        pane.innerHTML = '<div class="placeholder">コミットを選択してください</div>';
        return;
    }
    const vars = c.variables || {};
    const varRows = Object.keys(vars)
        .map((name) => {
            const info = vars[name] || ({} as { type?: string; size?: number });
            return `<div class="var-item"><span>${escapeHtml(name)}</span><span class="vtype">${escapeHtml(
                info.type || '?'
            )} · ${formatBytes(info.size || 0)}</span></div>`;
        })
        .join('');
    const parentsHtml =
        (c.parents || []).map((p) => `<code>${escapeHtml(p.slice(0, 7))}</code>`).join(', ') || '—';

    pane.innerHTML = `
        <div class="detail-title">${escapeHtml(c.message || '(no message)')}</div>
        <div class="detail-hash">${escapeHtml(c.hash)}</div>
        <div class="detail-actions">
            <button data-act="checkout">⟲ Checkout</button>
            <button class="secondary" data-act="branch">⎇ Branch</button>
            <button class="secondary" data-act="tag">🏷 Tag</button>
            <button class="secondary" data-act="merge">⑃ Merge…</button>
            <button class="secondary" data-act="copy">⧉ Copy</button>
        </div>
        <div class="detail-row"><span class="k">Author</span><span class="v">${escapeHtml(c.author)}</span></div>
        <div class="detail-row"><span class="k">Parents</span><span class="v">${parentsHtml}</span></div>
        <div class="detail-row"><span class="k">Signed</span><span class="v ${
            c.signed ? 'sig-yes' : 'sig-no'
        }">${c.signed ? '🔒 yes (HMAC)' : 'no'}</span></div>
        <div class="var-list"><h4>Variables (${c.varCount})</h4>${
            varRows || '<div class="placeholder">変数なし</div>'
        }</div>
    `;
    pane.querySelectorAll<HTMLButtonElement>('button[data-act]').forEach((btn) => {
        btn.addEventListener('click', () => {
            const act = btn.getAttribute('data-act');
            if (act === 'checkout') actions.checkout(c.hash);
            else if (act === 'branch') actions.branch(c.hash);
            else if (act === 'tag') actions.tag(c.hash);
            else if (act === 'merge') actions.merge();
            else if (act === 'copy') actions.copy(c.hash);
        });
    });
}
```

- [ ] **Step 4: SVG 描画を実装（既存 render を TS 化 + dim 対応）**

Create `extension/webview/render.ts`:
```ts
import type { GraphData, CommitNode } from '../src/ssmReader';
import { layout } from './layout';
import { truncate, formatDate } from './format';
import { matchesQuery } from './search';

const SVG_NS = 'http://www.w3.org/2000/svg';
const ROW_H = 46;
const COL_W = 22;
const ORIGIN_X = 22;
const ORIGIN_Y = 30;
const NODE_R = 6;
const LANE_COLORS = [
    '#4daafc', '#73c991', '#e2c08d', '#cd72d6', '#f14c4c',
    '#46b1c9', '#d98c5f', '#9ccc65', '#ba68c8', '#ffb74d',
];

function el(name: string, attrs: Record<string, string | number>, text?: string): SVGElement {
    const node = document.createElementNS(SVG_NS, name) as SVGElement;
    for (const k in attrs) {
        node.setAttribute(k, String(attrs[k]));
    }
    if (text !== undefined) {
        node.textContent = text;
    }
    return node;
}
const laneColor = (col: number) => LANE_COLORS[col % LANE_COLORS.length];
const x = (col: number) => ORIGIN_X + col * COL_W;
const y = (row: number) => ORIGIN_Y + row * ROW_H;

export interface RenderResult {
    rowY: Map<string, number>;
    width: number;
    height: number;
}

export function renderGraph(
    svg: SVGSVGElement,
    graph: GraphData,
    query: string,
    selectedHash: string | null,
    onSelect: (hash: string) => void
): RenderResult {
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    const commits = graph.commits;
    const rowY = new Map<string, number>();
    if (!commits.length) {
        return { rowY, width: 0, height: 0 };
    }

    const { pos, maxCol } = layout(commits);
    const graphWidth = x(maxCol) + COL_W;
    const textX = graphWidth + 14;
    const totalHeight = y(commits.length) + 10;
    svg.setAttribute('height', String(totalHeight));

    const refs = new Map<string, { text: string; kind: string }[]>();
    const addRef = (hash: string, text: string, kind: string) => {
        if (!hash) return;
        if (!refs.has(hash)) refs.set(hash, []);
        refs.get(hash)!.push({ text, kind });
    };
    graph.branches.forEach((b) => addRef(b.head, b.name, 'branch'));
    graph.tags.forEach((t) => addRef(t.commit, t.name, 'tag'));
    if (graph.head) addRef(graph.head, 'HEAD', 'head');

    const dim = (c: CommitNode) => query.trim() !== '' && !matchesQuery(c, query);

    // 行背景
    commits.forEach((c, row) => {
        const bg = el('rect', {
            x: 0, y: y(row) - ROW_H / 2, width: '100%', height: ROW_H,
            class: 'commit-row-bg' + (c.hash === selectedHash ? ' selected' : '') + (dim(c) ? ' dim' : ''),
            'data-hash': c.hash,
        });
        bg.addEventListener('click', () => onSelect(c.hash));
        svg.appendChild(bg);
    });

    // エッジ
    commits.forEach((c) => {
        const cp = pos.get(c.hash)!;
        (c.parents || []).forEach((ph) => {
            const pp = pos.get(ph);
            if (!pp) return;
            const x1 = x(cp.col), y1 = y(cp.row), x2 = x(pp.col), y2 = y(pp.row);
            const midY = (y1 + y2) / 2;
            const d = `M ${x1} ${y1} C ${x1} ${midY}, ${x2} ${midY}, ${x2} ${y2}`;
            svg.appendChild(el('path', { d, class: 'edge', stroke: laneColor(Math.max(cp.col, pp.col)) }));
        });
    });

    // ノード + テキスト
    commits.forEach((c, row) => {
        const p = pos.get(c.hash)!;
        const cx = x(p.col), cy = y(row);
        rowY.set(c.hash, cy);
        let cls = 'node';
        if (c.hash === graph.head) cls += ' head';
        if (c.isMerge) cls += ' merge';
        if (dim(c)) cls += ' dim';
        svg.appendChild(el('circle', { cx, cy, r: NODE_R, class: cls, fill: laneColor(p.col) }));

        let labelX = textX;
        (refs.get(c.hash) || []).forEach((r) => {
            const w = r.text.length * 6.5 + 14;
            const g = el('g', {}) as SVGGElement;
            g.appendChild(el('rect', {
                x: labelX, y: cy - 9, width: w, height: 16, rx: 8,
                class: r.kind === 'tag' ? 'ref-bg-tag' : r.kind === 'head' ? 'ref-bg-head' : 'ref-bg-branch',
                'data-ref-kind': r.kind, 'data-ref-name': r.text,
            }));
            const prefix = r.kind === 'tag' ? '🏷 ' : r.kind === 'head' ? '' : '⎇ ';
            g.appendChild(el('text', { x: labelX + 7, y: cy + 3, class: 'ref-label ref-text' }, prefix + r.text));
            svg.appendChild(g);
            labelX += w + 6;
        });

        const msgCls = 'commit-msg' + (dim(c) ? ' dim' : '');
        svg.appendChild(el('text', { x: labelX, y: cy - 2, class: msgCls }, truncate(c.message || '(no message)', 60)));
        const meta = `${c.hash.slice(0, 7)} · ${c.author} · ${formatDate(c.timestamp)} · ${c.varCount} vars${c.signed ? ' · 🔒' : ''}`;
        svg.appendChild(el('text', { x: labelX, y: cy + 11, class: 'commit-meta' + (dim(c) ? ' dim' : '') }, meta));

        const hit = el('rect', { x: 0, y: cy - ROW_H / 2, width: '100%', height: ROW_H, fill: 'transparent', style: 'cursor:pointer' });
        hit.addEventListener('click', () => onSelect(c.hash));
        svg.appendChild(hit);
    });

    return { rowY, width: graphWidth, height: totalHeight };
}
```

- [ ] **Step 5: main.ts を本実装（描画パイプライン結線、操作の postMessage）**

Rewrite `extension/webview/main.ts`:
```ts
import type { HostToWebview } from '../src/messages';
import type { GraphData } from '../src/ssmReader';
import { Store } from './state';
import { renderGraph } from './render';
import { renderDetail } from './detail';

interface VsCodeApi {
    postMessage(msg: unknown): void;
    getState(): any;
    setState(s: any): void;
}
declare function acquireVsCodeApi(): VsCodeApi;

const vscode = acquireVsCodeApi();
const store = new Store(vscode);

const svg = document.getElementById('graph') as unknown as SVGSVGElement;
const detailPane = document.getElementById('detail-pane') as HTMLElement;
const statusEl = document.getElementById('status') as HTMLElement;
const currentBranchEl = document.getElementById('current-branch') as HTMLElement;

let graph: GraphData | null = null;

function setStatus(text: string, isError: boolean): void {
    statusEl.textContent = text;
    statusEl.classList.toggle('error', isError);
}

function selectCommit(hash: string): void {
    store.set({ selectedHash: hash });
    draw();
}

function draw(): void {
    if (!graph) return;
    const st = store.get();
    currentBranchEl.textContent = graph.currentBranch ? '⎇ ' + graph.currentBranch : '';
    renderGraph(svg, graph, st.query, st.selectedHash, selectCommit);
    const sel = graph.commits.find((c) => c.hash === st.selectedHash);
    renderDetail(detailPane, sel, graph, {
        checkout: (h) => vscode.postMessage({ type: 'checkout', hash: h }),
        branch: (h) => vscode.postMessage({ type: 'createBranch', hash: h }),
        tag: (h) => vscode.postMessage({ type: 'createTag', hash: h }),
        merge: () => vscode.postMessage({ type: 'merge' }),
        copy: (h) => vscode.postMessage({ type: 'copyHash', hash: h }),
    });
    setStatus(
        `${graph.commits.length} commits · ${graph.branches.length} branches · ${graph.tags.length} tags`,
        false
    );
}

window.addEventListener('message', (event: MessageEvent<HostToWebview>) => {
    const msg = event.data;
    if (msg.type === 'graph') {
        graph = msg.data;
        draw();
    } else if (msg.type === 'error') {
        graph = null;
        while (svg.firstChild) svg.removeChild(svg.firstChild);
        detailPane.innerHTML = '<div class="placeholder"></div>';
        setStatus(msg.message, true);
    }
});

document.getElementById('btn-refresh')?.addEventListener('click', () => vscode.postMessage({ type: 'refresh' }));
document.getElementById('btn-commit')?.addEventListener('click', () => vscode.postMessage({ type: 'commit' }));

const searchInput = document.getElementById('search') as HTMLInputElement | null;
searchInput?.addEventListener('input', () => {
    store.set({ query: searchInput.value });
    draw();
});

vscode.postMessage({ type: 'ready' });
```

- [ ] **Step 6: graphPanel の HTML にツールバー検索ボックスを追加**

Modify `extension/src/graphPanel.ts` の `getHtml()` 内の `#toolbar` を次に置き換える:
```ts
    <div id="toolbar">
        <span id="title">SessionSmith</span>
        <span id="current-branch" class="badge"></span>
        <input id="search" type="search" placeholder="🔍 search commits, vars, refs…" />
        <span class="spacer"></span>
        <button id="btn-commit" title="現在のセッションをコミット">＋ Commit</button>
        <button id="btn-refresh" title="再読み込み">⟳ Refresh</button>
    </div>
```

- [ ] **Step 7: ビルドして F5 で起動確認**

Run（`extension/`）:
```bash
npm run compile
```
Expected: 成功。VSCode で `extension/` を開き F5 → デバッグホストで、SSM 済みワークスペースを開き `SessionSmith: Open Session Graph` を実行 → グラフが表示され、コミット選択で詳細が出て、検索ボックスで dim/ハイライトが効く。

- [ ] **Step 8: コミット**

```bash
git add extension/webview extension/src/graphPanel.ts
git commit -m "feat(extension): webview を TS モジュール化し検索・詳細ペインを再実装"
```

---

### Task 9: ズーム / パン / スプリッター / キーボード

**Files:**
- Create: `extension/webview/interaction.ts`
- Modify: `extension/webview/main.ts`
- Modify: `extension/src/graphPanel.ts`（`getHtml` にズームボタン・スプリッター要素）

- [ ] **Step 1: interaction を実装**

Create `extension/webview/interaction.ts`:
```ts
import { Store } from './state';

/** SVG の viewBox を使ったズーム/パンを結線する。 */
export function setupZoomPan(
    graphPane: HTMLElement,
    svg: SVGSVGElement,
    store: Store,
    getSize: () => { width: number; height: number }
): { apply(): void; fit(): void; reset(): void } {
    function apply(): void {
        const { zoom, panX, panY } = store.get();
        const { width, height } = getSize();
        const w = Math.max(width, graphPane.clientWidth) / zoom;
        const h = Math.max(height, graphPane.clientHeight) / zoom;
        svg.setAttribute('viewBox', `${panX} ${panY} ${w} ${h}`);
        svg.setAttribute('preserveAspectRatio', 'xMinYMin meet');
    }
    function fit(): void {
        const { width, height } = getSize();
        const zx = graphPane.clientWidth / Math.max(width, 1);
        const zy = graphPane.clientHeight / Math.max(height, 1);
        store.set({ zoom: Math.min(1, Math.min(zx, zy)), panX: 0, panY: 0 });
        apply();
    }
    function reset(): void {
        store.set({ zoom: 1, panX: 0, panY: 0 });
        apply();
    }

    graphPane.addEventListener('wheel', (e) => {
        if (!e.ctrlKey && !e.metaKey) return;
        e.preventDefault();
        const st = store.get();
        const factor = e.deltaY < 0 ? 1.1 : 1 / 1.1;
        store.set({ zoom: Math.min(4, Math.max(0.2, st.zoom * factor)) });
        apply();
    }, { passive: false });

    let dragging = false;
    let lastX = 0;
    let lastY = 0;
    graphPane.addEventListener('mousedown', (e) => {
        if (e.button !== 0) return;
        dragging = true;
        lastX = e.clientX;
        lastY = e.clientY;
        graphPane.classList.add('panning');
    });
    window.addEventListener('mouseup', () => {
        dragging = false;
        graphPane.classList.remove('panning');
    });
    window.addEventListener('mousemove', (e) => {
        if (!dragging) return;
        const st = store.get();
        store.set({ panX: st.panX - (e.clientX - lastX) / st.zoom, panY: st.panY - (e.clientY - lastY) / st.zoom });
        lastX = e.clientX;
        lastY = e.clientY;
        apply();
    });

    return { apply, fit, reset };
}

/** グラフ/詳細ペイン間のリサイズスプリッターを結線する。 */
export function setupSplitter(splitter: HTMLElement, detailPane: HTMLElement, store: Store): void {
    detailPane.style.width = store.get().paneWidth + 'px';
    let dragging = false;
    splitter.addEventListener('mousedown', (e) => {
        dragging = true;
        e.preventDefault();
    });
    window.addEventListener('mouseup', () => (dragging = false));
    window.addEventListener('mousemove', (e) => {
        if (!dragging) return;
        const w = Math.min(640, Math.max(240, window.innerWidth - e.clientX));
        detailPane.style.width = w + 'px';
        store.set({ paneWidth: w });
    });
}

/** キーボードナビゲーション。selectDelta は ↑/↓ の相対移動。 */
export function setupKeyboard(handlers: {
    focusSearch(): void;
    clearSearch(): void;
    move(delta: number): void;
    checkout(): void;
    branch(): void;
    tag(): void;
    resetZoom(): void;
}): void {
    window.addEventListener('keydown', (e) => {
        const target = e.target as HTMLElement;
        const typing = target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA');
        if (e.key === '/' && !typing) {
            e.preventDefault();
            handlers.focusSearch();
        } else if (e.key === 'Escape') {
            handlers.clearSearch();
        } else if (!typing && e.key === 'ArrowDown') {
            e.preventDefault();
            handlers.move(1);
        } else if (!typing && e.key === 'ArrowUp') {
            e.preventDefault();
            handlers.move(-1);
        } else if (!typing && (e.key === 'c' || e.key === 'C')) {
            handlers.checkout();
        } else if (!typing && (e.key === 'b' || e.key === 'B')) {
            handlers.branch();
        } else if (!typing && (e.key === 't' || e.key === 'T')) {
            handlers.tag();
        } else if (!typing && e.key === '0') {
            handlers.resetZoom();
        }
    });
}
```

- [ ] **Step 2: main.ts に結線を追加**

Modify `extension/webview/main.ts`。`renderGraph` の戻り値を保持し、interaction を結線する。`draw()` を次のように更新（`renderGraph` の結果を `lastSize` に保存）:
```ts
import { setupZoomPan, setupSplitter, setupKeyboard } from './interaction';

let lastSize = { width: 0, height: 0 };
let lastRowY = new Map<string, number>();
```
`draw()` 内の `renderGraph(...)` 呼び出しを次に置換:
```ts
    const res = renderGraph(svg, graph, st.query, st.selectedHash, selectCommit);
    lastSize = { width: res.width, height: res.height };
    lastRowY = res.rowY;
    zoomPan.apply();
```
ファイル末尾（`vscode.postMessage({ type: 'ready' })` の直前）に結線を追加:
```ts
const graphPane = document.getElementById('graph-pane') as HTMLElement;
const splitter = document.getElementById('splitter') as HTMLElement;
const zoomPan = setupZoomPan(graphPane, svg, store, () => lastSize);
setupSplitter(splitter, detailPane, store);

function moveSelection(delta: number): void {
    if (!graph || !graph.commits.length) return;
    const idx = graph.commits.findIndex((c) => c.hash === store.get().selectedHash);
    const next = Math.min(graph.commits.length - 1, Math.max(0, (idx < 0 ? 0 : idx) + delta));
    selectCommit(graph.commits[next].hash);
    const yy = lastRowY.get(graph.commits[next].hash);
    if (yy !== undefined) graphPane.scrollTo({ top: yy - graphPane.clientHeight / 2, behavior: 'smooth' });
}
setupKeyboard({
    focusSearch: () => searchInput?.focus(),
    clearSearch: () => { if (searchInput) { searchInput.value = ''; store.set({ query: '' }); draw(); } },
    move: moveSelection,
    checkout: () => { const h = store.get().selectedHash; if (h) vscode.postMessage({ type: 'checkout', hash: h }); },
    branch: () => { const h = store.get().selectedHash; if (h) vscode.postMessage({ type: 'createBranch', hash: h }); },
    tag: () => { const h = store.get().selectedHash; if (h) vscode.postMessage({ type: 'createTag', hash: h }); },
    resetZoom: () => zoomPan.reset(),
});
document.getElementById('btn-fit')?.addEventListener('click', () => zoomPan.fit());
document.getElementById('btn-reset')?.addEventListener('click', () => zoomPan.reset());
```
Note: `zoomPan` は `draw()` より前に初期化される必要があるため、`const zoomPan = ...` の宣言は `draw` 関数定義より上（モジュール先頭側）へ移動するか、`let zoomPan: ReturnType<typeof setupZoomPan>;` を先に宣言して代入する。コンパイルエラーが出たらこの順序を調整すること。

- [ ] **Step 3: getHtml にズームボタン・グラフペインID・スプリッターを追加**

Modify `extension/src/graphPanel.ts` の `getHtml()`。ツールバーの `btn-refresh` の後（`</div>` 直前）に追加:
```ts
        <button id="btn-fit" title="全体表示">⊡ Fit</button>
        <button id="btn-reset" title="等倍にリセット">1:1</button>
```
`#container` を次に置換:
```ts
    <div id="container">
        <div id="graph-pane"><svg id="graph"></svg></div>
        <div id="splitter"></div>
        <div id="detail-pane"><div class="placeholder">コミットを選択してください</div></div>
    </div>
```

- [ ] **Step 4: ビルドして F5 で確認**

Run:
```bash
npm run compile
```
Expected: 成功。F5 で、Ctrl/Cmd+ホイールでズーム、ドラッグでパン、`Fit`/`1:1` ボタン、スプリッターで詳細ペイン幅変更、↑↓で選択移動・スムーズスクロール、`/`で検索フォーカス・`Esc`で解除が動作する。

- [ ] **Step 5: コミット**

```bash
git add extension/webview/interaction.ts extension/webview/main.ts extension/src/graphPanel.ts
git commit -m "feat(extension): ズーム/パン・スプリッター・キーボード操作を追加"
```

---

### Task 10: ref バッジからの削除・リネーム操作

**Files:**
- Modify: `extension/webview/render.ts`（バッジに data 属性は Task 8 で付与済み）
- Modify: `extension/webview/main.ts`（バッジのコンテキストメニュー/クリック）

- [ ] **Step 1: バッジ右クリックで削除・リネームを送る**

Modify `extension/webview/main.ts`。`draw()` の `renderGraph(...)` 呼び出し直後に、バッジのイベントを結線する処理を追加:
```ts
    svg.querySelectorAll<SVGRectElement>('[data-ref-kind]').forEach((rect) => {
        const kind = rect.getAttribute('data-ref-kind');
        const name = rect.getAttribute('data-ref-name');
        if (kind === 'head' || !name || (kind !== 'branch' && kind !== 'tag')) return;
        rect.style.cursor = 'context-menu';
        rect.addEventListener('contextmenu', (e) => {
            e.preventDefault();
            showRefMenu(e.clientX, e.clientY, kind, name);
        });
    });
```
`draw()` 関数の外（モジュールスコープ）に簡易メニューを実装:
```ts
function showRefMenu(cx: number, cy: number, kind: 'branch' | 'tag', name: string): void {
    document.getElementById('ref-menu')?.remove();
    const menu = document.createElement('div');
    menu.id = 'ref-menu';
    menu.className = 'context-menu';
    menu.style.left = cx + 'px';
    menu.style.top = cy + 'px';
    menu.innerHTML = `<div class="ctx-title">${kind}: ${name}</div>
        <button data-a="rename">✎ リネーム</button>
        <button data-a="delete">🗑 削除</button>`;
    document.body.appendChild(menu);
    const close = () => menu.remove();
    menu.querySelector('[data-a="rename"]')?.addEventListener('click', () => {
        vscode.postMessage({ type: 'renameRef', kind, name });
        close();
    });
    menu.querySelector('[data-a="delete"]')?.addEventListener('click', () => {
        vscode.postMessage({ type: 'deleteRef', kind, name });
        close();
    });
    setTimeout(() => window.addEventListener('click', close, { once: true }), 0);
}
```

- [ ] **Step 2: ビルドして F5 で確認**

Run:
```bash
npm run compile
```
Expected: 成功。F5 で、ブランチ/タグのバッジを右クリック → メニュー → リネーム/削除が動作し、確認ダイアログ後に `.ssm` が更新されてグラフが自動再描画される。現在ブランチ・唯一のブランチの削除は拒否メッセージが出る。

- [ ] **Step 3: コミット**

```bash
git add extension/webview/main.ts
git commit -m "feat(extension): ref バッジの右クリックから削除・リネームを実行"
```

---

## Phase 4 — 見た目仕上げ・空状態・アニメーション

### Task 11: CSS 全面刷新 + 空状態オンボーディング + reduced-motion

**Files:**
- Rewrite: `extension/media/graph.css`
- Modify: `extension/src/graphPanel.ts`（`update()` のエラー分岐に空状態種別を付与）
- Modify: `extension/webview/main.ts`（`error` 受信時に空状態テンプレートを表示）

- [ ] **Step 1: 空状態種別を error メッセージに付与**

Modify `extension/src/graphPanel.ts`。`update()` 内の `.ssm` 未検出分岐の `postError` を、種別付きに変更する。`postError` 呼び出しの箇所を次のように更新:
```ts
        if (!workspaceRoot) {
            this.panel.webview.postMessage({ type: 'error', message: 'no-workspace' });
            return;
        }
```
```ts
        if (!ssmPath) {
            this.ssmPath = null;
            this.panel.webview.postMessage({ type: 'error', message: 'no-ssm' });
            return;
        }
```
また `readGraph` 後に commits が空なら通常表示のままで良い（webview 側で空状態を出す）。

- [ ] **Step 2: main.ts で空状態テンプレートを表示**

Modify `extension/webview/main.ts` の `message` ハンドラの `error` 分岐を次に置換:
```ts
    } else if (msg.type === 'error') {
        graph = null;
        while (svg.firstChild) svg.removeChild(svg.firstChild);
        renderEmptyState(msg.message);
    }
```
モジュールスコープに `renderEmptyState` を追加:
```ts
function renderEmptyState(kind: string): void {
    const pane = document.getElementById('graph-pane') as HTMLElement;
    let html = '';
    if (kind === 'no-workspace') {
        html = `<div class="empty"><h3>ワークスペースが開かれていません</h3>
            <p>フォルダを開いてから Session Graph を表示してください。</p></div>`;
    } else if (kind === 'no-ssm') {
        html = `<div class="empty"><h3>.ssm がまだありません</h3>
            <p>Python 側で SSM を初期化してください:</p>
            <pre><code>from SessionSmith import ssm
ssm.init()
ssm.commit("first snapshot")</code></pre>
            <button id="copy-init">⧉ コードをコピー</button></div>`;
    } else {
        html = `<div class="empty"><h3>${kind}</h3></div>`;
    }
    pane.innerHTML = html + '<svg id="graph"></svg>';
    document.getElementById('copy-init')?.addEventListener('click', () => {
        navigator.clipboard?.writeText('from SessionSmith import ssm\nssm.init()\nssm.commit("first snapshot")');
    });
}
```
Note: `renderEmptyState` は `#graph-pane` の中身を置き換え、末尾に空の `<svg id="graph">` を再設置する。以降 `graph` メッセージ受信時は `draw()` が `document.getElementById('graph')` を取得し直すよう、`draw()` 冒頭で `svg` を再取得する実装に変更する（`const svgNow = document.getElementById('graph')`）。コンパイル/動作で不整合が出たら、`svg` 参照を毎回取得するヘルパー `getSvg()` に統一すること。

- [ ] **Step 3: CSS を 3ゾーン + バッジ + 空状態 + アニメで刷新**

Rewrite `extension/media/graph.css`:
```css
:root { --row-h: 46px; --ease: cubic-bezier(0.2, 0, 0, 1); }
* { box-sizing: border-box; }
html, body {
    height: 100%; margin: 0; padding: 0;
    font-family: var(--vscode-font-family); font-size: var(--vscode-font-size);
    color: var(--vscode-foreground); background: var(--vscode-editor-background);
}

#toolbar {
    display: flex; align-items: center; gap: 8px; padding: 6px 12px;
    border-bottom: 1px solid var(--vscode-panel-border); background: var(--vscode-sideBar-background);
}
#title { font-weight: 600; }
.spacer { flex: 1; }
#search {
    flex: 0 1 320px; padding: 3px 8px; border-radius: 4px;
    border: 1px solid var(--vscode-input-border, transparent);
    background: var(--vscode-input-background); color: var(--vscode-input-foreground);
}
#search:focus { outline: 1px solid var(--vscode-focusBorder); }

button {
    background: var(--vscode-button-background); color: var(--vscode-button-foreground);
    border: none; padding: 4px 10px; border-radius: 4px; cursor: pointer; font-size: 12px;
    transition: background 0.12s var(--ease), transform 0.08s var(--ease);
}
button:hover { background: var(--vscode-button-hoverBackground); }
button:active { transform: translateY(1px); }
button.secondary { background: var(--vscode-button-secondaryBackground); color: var(--vscode-button-secondaryForeground); }
button.secondary:hover { background: var(--vscode-button-secondaryHoverBackground); }

.badge {
    display: inline-block; padding: 1px 8px; border-radius: 10px; font-size: 11px;
    background: var(--vscode-badge-background); color: var(--vscode-badge-foreground);
}

#container { display: flex; height: calc(100vh - 76px); }
#graph-pane { flex: 1; overflow: auto; position: relative; }
#graph-pane.panning { cursor: grabbing; }
#splitter { width: 6px; cursor: col-resize; background: transparent; }
#splitter:hover { background: var(--vscode-focusBorder); opacity: 0.5; }
#detail-pane {
    width: 340px; min-width: 240px; max-width: 640px;
    border-left: 1px solid var(--vscode-panel-border); overflow: auto; padding: 14px;
    background: var(--vscode-sideBar-background);
}
#detail-pane .placeholder { color: var(--vscode-descriptionForeground); margin-top: 20px; text-align: center; }

#status {
    height: 22px; line-height: 22px; padding: 0 12px; font-size: 11px;
    color: var(--vscode-descriptionForeground); border-top: 1px solid var(--vscode-panel-border);
}
#status.error { color: var(--vscode-errorForeground); }

/* SVG */
svg text { fill: var(--vscode-foreground); font-family: var(--vscode-font-family); }
.commit-row-bg { fill: transparent; transition: fill 0.1s var(--ease); }
.commit-row-bg.selected { fill: var(--vscode-list-activeSelectionBackground); opacity: 0.35; }
.commit-row-bg:hover { fill: var(--vscode-list-hoverBackground); }
.edge { fill: none; stroke-width: 2; }
.node { stroke: var(--vscode-editor-background); stroke-width: 2; }
.node.head { stroke: var(--vscode-focusBorder); stroke-width: 3; }
.node.merge { stroke-dasharray: 2 2; }
.dim { opacity: 0.28; }
.commit-msg { font-size: 13px; }
.commit-meta { font-size: 11px; fill: var(--vscode-descriptionForeground); }

.ref-label { font-size: 11px; font-weight: 600; }
.ref-bg-branch { fill: var(--vscode-gitDecoration-modifiedResourceForeground, #4daafc); opacity: 0.9; }
.ref-bg-tag { fill: var(--vscode-gitDecoration-untrackedResourceForeground, #73c991); opacity: 0.9; }
.ref-bg-head { fill: var(--vscode-focusBorder, #007acc); }
.ref-text { fill: #ffffff; }

/* detail */
.detail-title { font-size: 15px; font-weight: 600; margin-bottom: 2px; word-break: break-word; }
.detail-hash { font-family: var(--vscode-editor-font-family, monospace); font-size: 12px; color: var(--vscode-descriptionForeground); margin-bottom: 12px; }
.detail-row { display: flex; margin: 4px 0; font-size: 12px; }
.detail-row .k { width: 90px; color: var(--vscode-descriptionForeground); flex-shrink: 0; }
.detail-row .v { word-break: break-word; }
.detail-actions { display: flex; flex-wrap: wrap; gap: 6px; margin: 14px 0; }
.sig-yes { color: var(--vscode-gitDecoration-untrackedResourceForeground, #73c991); }
.sig-no { color: var(--vscode-descriptionForeground); }
.var-list { margin-top: 12px; border-top: 1px solid var(--vscode-panel-border); padding-top: 8px; }
.var-list h4 { margin: 0 0 6px 0; font-size: 12px; }
.var-item { display: flex; justify-content: space-between; font-size: 12px; padding: 2px 0; border-bottom: 1px dotted var(--vscode-panel-border); }
.var-item .vtype { color: var(--vscode-descriptionForeground); font-family: var(--vscode-editor-font-family, monospace); }

/* empty state */
.empty { max-width: 420px; margin: 48px auto; text-align: center; color: var(--vscode-descriptionForeground); }
.empty h3 { color: var(--vscode-foreground); }
.empty pre { text-align: left; background: var(--vscode-textCodeBlock-background); padding: 10px; border-radius: 6px; overflow: auto; }

/* context menu */
.context-menu { position: fixed; z-index: 100; background: var(--vscode-menu-background, var(--vscode-editor-background)); border: 1px solid var(--vscode-menu-border, var(--vscode-panel-border)); border-radius: 6px; padding: 4px; box-shadow: 0 2px 8px rgba(0,0,0,0.3); }
.context-menu .ctx-title { font-size: 11px; color: var(--vscode-descriptionForeground); padding: 2px 8px; }
.context-menu button { display: block; width: 100%; text-align: left; background: transparent; color: var(--vscode-foreground); }
.context-menu button:hover { background: var(--vscode-list-hoverBackground); }

/* animations */
@keyframes fadein { from { opacity: 0; } to { opacity: 1; } }
#graph { animation: fadein 0.2s var(--ease); }
@media (prefers-reduced-motion: reduce) {
    *, #graph { animation: none !important; transition: none !important; }
    html { scroll-behavior: auto; }
}
```

- [ ] **Step 4: ビルドして 3 テーマ + 空状態を確認**

Run:
```bash
npm run compile
```
Expected: 成功。F5 で、ダーク/ライト/ハイコントラストの各テーマで表示が破綻しない。`.ssm` 無しワークスペースで空状態＋コピーボタンが出る。`prefers-reduced-motion` 有効時にアニメが無効化される。

- [ ] **Step 5: コミット**

```bash
git add extension/media/graph.css extension/src/graphPanel.ts extension/webview/main.ts
git commit -m "feat(extension): 3ゾーンUI刷新・空状態オンボーディング・reduced-motion対応"
```

---

## Phase 5 — 手動検証・ドキュメント・リリース

### Task 12: 手動検証チェックリスト

**Files:** なし（検証のみ）

- [ ] **Step 1: 全自動テストを実行**

Run（`extension/`）:
```bash
npm test
```
Expected: tsc + esbuild 成功後、`node --test out/test` が ssmReader/layout/search/ssmRefs すべて pass。

- [ ] **Step 2: F5 デバッグホストで手動チェックリストを実施**

以下をすべて確認（Notebook とターミナルの両経路で checkout を確認）:
- [ ] グラフ表示：直線・分岐・マージを含む履歴が正しく描画される
- [ ] 選択：クリック/↑↓で選択、詳細ペイン更新、スムーズスクロール
- [ ] 検索：メッセージ/ハッシュ/author/変数名で dim・ハイライト、`/`・`Esc`
- [ ] ズーム/パン：Ctrl+ホイール・ドラッグ・`Fit`・`1:1`・`0`
- [ ] スプリッター：詳細ペイン幅変更が再表示後も保持される
- [ ] commit：`＋ Commit` でコミットされグラフ更新
- [ ] checkout：詳細/`c` から実行（Notebook・ターミナル）
- [ ] branch 作成 / tag 作成：詳細/`b`/`t` から実行
- [ ] merge：詳細の `Merge…` → QuickPick → 実行
- [ ] 削除：ブランチ/タグのバッジ右クリック → 削除（`.bak` 生成）
- [ ] リネーム：バッジ右クリック → リネーム（現在ブランチは config 追従）
- [ ] ガード：現在ブランチ・唯一のブランチの削除が拒否される
- [ ] 空状態：no-workspace / no-ssm（コピーボタン）/ コミット0件
- [ ] テーマ：ダーク/ライト/ハイコントラストで破綻なし

- [ ] **Step 3: 問題があれば修正してコミット**

チェックリストで見つかった不具合は該当タスクのファイルを修正し、`fix(extension): ...` でコミットする。

---

### Task 13: README / CHANGELOG / CI 更新とパッケージング

**Files:**
- Modify: `extension/README.md`
- Create: `extension/CHANGELOG.md`
- Modify: `.github/workflows/extension-release.yml`

- [ ] **Step 1: 拡張 CHANGELOG を新設**

Create `extension/CHANGELOG.md`:
```markdown
# Change Log

## [0.3.0] - 2026-07-10

### Added
- Session Graph の全面刷新（洗練3ゾーンレイアウト）
- ズーム / パン（Ctrl+ホイール・ドラッグ・Fit・1:1・キーボード）
- 横断検索（メッセージ / ハッシュ / author / 変数名）とハイライト・dim
- GUI からの **merge**（QuickPick でブランチ選択）
- ブランチ / タグの **削除・リネーム**（`.ssm` の参照ファイルを直接操作、Python 不要・`.bak` 退避）
- リサイズ可能な詳細ペイン（幅を永続化）
- 空状態オンボーディング（`ssm.init()` のコピー）、reduced-motion 対応
- 拡張アイコン（icon.png）

### Changed
- webview を TypeScript 化し esbuild でバンドル、レンダラをモジュール分割
- 純ロジック（layout / search / ssmReader / ssmRefs）に `node:test` のユニットテストを追加
```

- [ ] **Step 2: README に新機能を反映**

Modify `extension/README.md` の「機能」節（v0.2.0 の Session Graph 説明の直後）に追加:
```markdown
- **v0.3.0 の新機能**:
  - ズーム / パン、横断検索（メッセージ・ハッシュ・author・変数名）
  - GUI から **merge**、ブランチ / タグの **削除・リネーム**
  - リサイズ可能な詳細ペイン、空状態オンボーディング、テーマ整合の刷新
```

- [ ] **Step 3: リリースワークフローのビルド手順を確認**

Read `.github/workflows/extension-release.yml`。ビルドステップが `npm run compile`（tsc + esbuild）を実行しているか確認する。`tsc` 単体や `npm run vscode:prepublish` のみになっている場合は、`vsce package` の前に `npm ci` と `npm run compile` が走るよう修正する。esbuild が devDependencies にあるため `npm ci` で解決される。

- [ ] **Step 4: パッケージングを確認**

Run（`extension/`）:
```bash
npx --yes @vscode/vsce package --no-dependencies
```
Expected: `sessionsmith-0.3.0.vsix` が生成される。アイコンが同梱され、`webview/**` と `test/**` は含まれない（`media/graph.js` は含まれる）。

- [ ] **Step 5: 生成 vsix の中身を確認**

Run:
```bash
npx --yes @vscode/vsce ls --no-dependencies | grep -E "icon.png|media/graph.js|graph.css"
```
Expected: `icon.png` / `media/graph.js` / `media/graph.css` が含まれ、`webview/` や `src/` の `.ts` が含まれない。

- [ ] **Step 6: コミット**

```bash
git add extension/README.md extension/CHANGELOG.md .github/workflows/extension-release.yml
git commit -m "docs(extension): v0.3.0 の README/CHANGELOG 更新とリリース手順の整備"
```

---

## Self-Review（計画作成者による確認）

**1. Spec coverage（設計書 §2.1 の各要件 → タスク対応）**
- ズーム/パン → Task 9 ✓
- 検索・フィルタ → Task 5（ロジック）+ Task 8（結線）✓
- merge → Task 7（ハンドラ）+ Task 8/9（UI 呼び出し、詳細の Merge…）✓
- branch/tag 削除・リネーム → Task 6（FS）+ Task 7（ハンドラ）+ Task 10（UI）✓
- リサイズ可能ペイン → Task 9（splitter）✓
- キーボード → Task 9 ✓
- 3ゾーン刷新・バッジ・テーマ → Task 8（HTML）+ Task 11（CSS）✓
- 空状態・オンボーディング → Task 11 ✓
- アニメ・reduced-motion → Task 11 ✓
- webview TS化 + esbuild → Task 1 + Task 8 ✓
- メッセージ型共有 → Task 7 ✓
- node:test → Task 3/4/5/6 ✓
- アイコン → Task 2 ✓
- README/CHANGELOG/version/CI → Task 2（version）+ Task 13 ✓
- スコープ外（diff/値/メトリクス/remote GUI）はタスク無し（意図通り）✓

**2. Placeholder scan:** 各コードステップに実コードを記載。「適切なエラー処理を追加」等の曖昧表現なし。Task 8 Step 5 / Task 11 Step 2 に順序調整の注記があるが、これは実装上の既知の落とし穴の明示であり TODO ではない。

**3. Type consistency:**
- `readGraph` / `GraphData` / `CommitNode`：`src/ssmReader.ts`（既存）と一致。
- `deleteRef(ssmPath, kind, name)` / `renameRef(ssmPath, kind, old, new)` / `RefError`：Task 6 定義と Task 7 利用が一致。
- `matchesQuery(c, query)`：Task 5 定義と `render.ts`（Task 8）利用が一致。
- `layout(commits) → { pos, maxCol }`：Task 4 定義と `render.ts` 利用が一致。
- メッセージ型 `HostToWebview` / `WebviewToHost`：Task 7 定義。webview 側は現状 `postMessage` に文字列リテラル型を渡しており矛盾なし（厳密な型付けは任意強化）。
- `Store` の `get/set/post`、`ViewState`：Task 8 定義と Task 9/10/11 利用が一致。

矛盾・欠落は検出されず。

---

## Execution Handoff

計画は `docs/superpowers/plans/2026-07-10-extension-v030-session-graph.md` に保存済み。次の実行方式を選択してください。
