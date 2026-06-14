import * as vscode from 'vscode';
import * as path from 'path';
import { findSsmRoot, readGraph, GraphData } from './ssmReader';
import { runSsmCode } from './runner';

/**
 * セッショングラフ（gitgraph 風）を表示する Webview パネル。
 * シングルトンとして管理し、.ssm の変更を監視して自動更新する。
 */
export class SessionGraphPanel {
    public static current: SessionGraphPanel | undefined;
    private static readonly viewType = 'sessionsmith.graph';

    private readonly panel: vscode.WebviewPanel;
    private readonly extensionUri: vscode.Uri;
    private disposables: vscode.Disposable[] = [];
    private watcher: vscode.FileSystemWatcher | undefined;
    private ssmPath: string | null = null;
    private refreshTimer: NodeJS.Timeout | undefined;

    public static createOrShow(extensionUri: vscode.Uri): void {
        const column = vscode.window.activeTextEditor?.viewColumn ?? vscode.ViewColumn.One;

        if (SessionGraphPanel.current) {
            SessionGraphPanel.current.panel.reveal(column);
            SessionGraphPanel.current.update();
            return;
        }

        const panel = vscode.window.createWebviewPanel(
            SessionGraphPanel.viewType,
            'SessionSmith Graph',
            column,
            {
                enableScripts: true,
                retainContextWhenHidden: true,
                localResourceRoots: [vscode.Uri.joinPath(extensionUri, 'media')],
            }
        );

        SessionGraphPanel.current = new SessionGraphPanel(panel, extensionUri);
    }

    private constructor(panel: vscode.WebviewPanel, extensionUri: vscode.Uri) {
        this.panel = panel;
        this.extensionUri = extensionUri;

        this.panel.webview.html = this.getHtml();
        this.panel.onDidDispose(() => this.dispose(), null, this.disposables);

        this.panel.webview.onDidReceiveMessage(
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
            this.postError('ワークスペースが開かれていません。');
            return;
        }

        const ssmPath = findSsmRoot(workspaceRoot);
        if (!ssmPath) {
            this.ssmPath = null;
            this.postError(
                'このワークスペースに .ssm が見つかりません。Python 側で ssm.init() を実行してください。'
            );
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
        this.panel.webview.postMessage({ type: 'graph', data });
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
        this.panel.webview.postMessage({ type: 'error', message });
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
            case 'copyHash':
                if (msg.hash) {
                    await vscode.env.clipboard.writeText(msg.hash);
                    vscode.window.showInformationMessage(`Copied: ${msg.hash}`);
                }
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

    private workspaceDir(): string | undefined {
        if (this.ssmPath) {
            return path.dirname(this.ssmPath);
        }
        return vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
    }

    private getHtml(): string {
        const webview = this.panel.webview;
        const nonce = getNonce();
        const scriptUri = webview.asWebviewUri(
            vscode.Uri.joinPath(this.extensionUri, 'media', 'graph.js')
        );
        const styleUri = webview.asWebviewUri(
            vscode.Uri.joinPath(this.extensionUri, 'media', 'graph.css')
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
        <span class="spacer"></span>
        <button id="btn-commit" title="現在のセッションをコミット">＋ Commit</button>
        <button id="btn-refresh" title="再読み込み">⟳ Refresh</button>
    </div>
    <div id="container">
        <div id="graph-pane"><svg id="graph"></svg></div>
        <div id="detail-pane"><div class="placeholder">コミットを選択してください</div></div>
    </div>
    <div id="status"></div>
    <script nonce="${nonce}" src="${scriptUri}"></script>
</body>
</html>`;
    }

    public dispose(): void {
        SessionGraphPanel.current = undefined;
        this.panel.dispose();
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
