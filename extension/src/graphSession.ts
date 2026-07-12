import * as vscode from 'vscode';
import * as path from 'path';
import { findSsmRoot, readGraph, GraphData } from './ssmReader';
import { runSsmCode } from './runner';
import { deleteRef, renameRef, RefError, RefKind } from './ssmRefs';

/**
 * セッショングラフ（gitgraph 風）Webview の HTML を生成する。
 * パネル／ビューいずれからも同じ Webview コンテンツを構築できるよう、
 * webview と extensionUri を明示的に受け取る。
 */
export function getGraphHtml(webview: vscode.Webview, extensionUri: vscode.Uri): string {
    const nonce = getNonce();
    const scriptUri = webview.asWebviewUri(
        vscode.Uri.joinPath(extensionUri, 'media', 'graph.js')
    );
    const styleUri = webview.asWebviewUri(
        vscode.Uri.joinPath(extensionUri, 'media', 'graph.css')
    );
    const csp =
        `default-src 'none'; ` +
        `style-src ${webview.cspSource} 'unsafe-inline'; ` +
        `script-src 'nonce-${nonce}'; ` +
        `font-src ${webview.cspSource};`;

    return `<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="Content-Security-Policy" content="${csp}">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link href="${styleUri}" rel="stylesheet">
    <title>SessionSmith Graph</title>
</head>
<body>
    <div id="toolbar">
        <span id="title">SessionSmith</span>
        <span id="current-branch" class="badge"></span>
        <input id="search" type="search" placeholder="🔍 search commits, vars, refs…" />
        <span class="spacer"></span>
        <button id="btn-commit" title="現在のセッションをコミット">＋ Commit</button>
        <button id="btn-refresh" title="再読み込み">⟳ Refresh</button>
        <button id="btn-fit" title="全体表示">⊡ Fit</button>
        <button id="btn-reset" title="等倍にリセット">1:1</button>
        <button id="btn-open-editor" title="エディタで全画面表示">⤢</button>
    </div>
    <div id="container">
        <div id="graph-pane"><svg id="graph"></svg><div id="empty-state" class="hidden"></div></div>
        <div id="splitter"></div>
        <div id="detail-pane"><div class="placeholder">コミットを選択してください</div></div>
    </div>
    <div id="status"></div>
    <script nonce="${nonce}" src="${scriptUri}"></script>
</body>
</html>`;
}

/**
 * セッショングラフ Webview の共有ロジック（データ更新・ファイル監視・メッセージハンドリング）。
 * エディタパネルとサイドバービューの両方から再利用できるよう、
 * WebviewPanel/WebviewView に依存しない vscode.Webview のみを保持する。
 */
export class GraphSession {
    private readonly webview: vscode.Webview;
    private disposables: vscode.Disposable[] = [];
    private watcher: vscode.FileSystemWatcher | undefined;
    private ssmPath: string | null = null;
    private refreshTimer: NodeJS.Timeout | undefined;

    constructor(webview: vscode.Webview) {
        this.webview = webview;

        this.webview.onDidReceiveMessage(
            (msg) => this.handleMessage(msg),
            null,
            this.disposables
        );

        this.setupWatcher();
    }

    /** ワークスペースの .ssm を探してデータを送る */
    public update(): void {
        const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
        if (!workspaceRoot) {
            this.postError('no-workspace');
            return;
        }

        const ssmPath = findSsmRoot(workspaceRoot);
        if (!ssmPath) {
            this.ssmPath = null;
            this.postError('no-ssm');
            return;
        }

        this.ssmPath = ssmPath;
        this.setupWatcher();

        let data: GraphData;
        try {
            data = readGraph(ssmPath);
        } catch (e: any) {
            this.postError(`グラフの読み込みに失敗しました: ${e.message}`);
            return;
        }
        this.webview.postMessage({ type: 'graph', data });
    }

    private setupWatcher(): void {
        const workspaceRoot = vscode.workspace.workspaceFolders?.[0];
        if (!workspaceRoot || this.watcher) {
            return;
        }
        // .ssm 配下の変更を監視（コミット・ブランチ・タグ・HEAD）
        this.watcher = vscode.workspace.createFileSystemWatcher(
            new vscode.RelativePattern(workspaceRoot, '**/.ssm/**')
        );
        const onChange = () => this.debouncedUpdate();
        this.watcher.onDidCreate(onChange, null, this.disposables);
        this.watcher.onDidChange(onChange, null, this.disposables);
        this.watcher.onDidDelete(onChange, null, this.disposables);
        this.disposables.push(this.watcher);
    }

    private debouncedUpdate(): void {
        if (this.refreshTimer) {
            clearTimeout(this.refreshTimer);
        }
        this.refreshTimer = setTimeout(() => this.update(), 300);
    }

    private postError(message: string): void {
        this.webview.postMessage({ type: 'error', message });
    }

    private async handleMessage(msg: any): Promise<void> {
        switch (msg?.type) {
            case 'ready':
                this.update();
                return;
            case 'refresh':
                this.update();
                return;
            case 'checkout':
                await this.doCheckout(msg.hash);
                return;
            case 'createBranch':
                await this.doCreateBranch(msg.hash);
                return;
            case 'createTag':
                await this.doCreateTag(msg.hash);
                return;
            case 'commit':
                await this.doCommit();
                return;
            case 'merge':
                await this.doMerge(msg.branch);
                return;
            case 'deleteRef':
                await this.doDeleteRef(msg.kind, msg.name);
                return;
            case 'renameRef':
                await this.doRenameRef(msg.kind, msg.name);
                return;
            case 'copyHash':
                if (msg.hash) {
                    await vscode.env.clipboard.writeText(msg.hash);
                    vscode.window.showInformationMessage(`Copied: ${msg.hash}`);
                }
                return;
            case 'openInEditor':
                vscode.commands.executeCommand('sessionsmith.showSessionGraph');
                return;
        }
    }

    private async doCheckout(hash: string): Promise<void> {
        if (!isValidHash(hash)) {
            return;
        }
        const choice = await vscode.window.showWarningMessage(
            `コミット ${hash.slice(0, 7)} をチェックアウトしますか？現在のセッション変数が置き換えられます。`,
            { modal: true },
            'チェックアウト'
        );
        if (choice !== 'チェックアウト') {
            return;
        }
        await runSsmCode(
            `from SessionSmith import ssm; ssm.checkout(${py(hash)})`,
            this.workspaceDir()
        );
    }

    private async doCreateBranch(hash: string): Promise<void> {
        const name = await vscode.window.showInputBox({
            prompt: 'ブランチ名を入力',
            placeHolder: 'feature-1',
            validateInput: (v) =>
                isValidRef(v) ? null : '英数字・アンダースコア・ハイフンのみ使用できます',
        });
        if (!name) {
            return;
        }
        // 指定コミットへ移動してからブランチを作成・切り替え
        const code =
            `from SessionSmith import ssm; ssm.checkout(${py(hash)}); ` +
            `ssm.branch(${py(name)}, create=True); ssm.checkout_branch(${py(name)})`;
        await runSsmCode(code, this.workspaceDir());
    }

    private async doCreateTag(hash: string): Promise<void> {
        const name = await vscode.window.showInputBox({
            prompt: 'タグ名を入力',
            placeHolder: 'v1.0.0',
            validateInput: (v) =>
                isValidRef(v) ? null : '英数字・アンダースコア・ハイフン・ドットのみ使用できます',
        });
        if (!name) {
            return;
        }
        await runSsmCode(
            `from SessionSmith import ssm; ssm.tag(${py(name)}, commit_hash=${py(hash)})`,
            this.workspaceDir()
        );
    }

    private async doCommit(): Promise<void> {
        const message = await vscode.window.showInputBox({
            prompt: 'コミットメッセージを入力',
            placeHolder: 'Snapshot',
        });
        if (message === undefined) {
            return;
        }
        await runSsmCode(
            `from SessionSmith import ssm; ssm.commit(${py(message || 'Snapshot')})`,
            this.workspaceDir()
        );
    }

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

    private workspaceDir(): string | undefined {
        if (this.ssmPath) {
            return path.dirname(this.ssmPath);
        }
        return vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
    }

    private currentGraph(): GraphData | null {
        if (!this.ssmPath) {
            return null;
        }
        try {
            return readGraph(this.ssmPath);
        } catch {
            return null;
        }
    }

    public dispose(): void {
        if (this.refreshTimer) {
            clearTimeout(this.refreshTimer);
        }
        while (this.disposables.length) {
            this.disposables.pop()?.dispose();
        }
        this.watcher = undefined;
    }
}

/** Python の文字列リテラルとして安全に埋め込む */
function py(value: string): string {
    return JSON.stringify(String(value));
}

function isValidHash(hash: string): boolean {
    return /^[0-9a-f]{4,64}$/i.test(hash);
}

function isValidRef(name: string): boolean {
    return /^[A-Za-z0-9_.-]+$/.test(name);
}

function getNonce(): string {
    let text = '';
    const possible = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
    for (let i = 0; i < 32; i++) {
        text += possible.charAt(Math.floor(Math.random() * possible.length));
    }
    return text;
}
