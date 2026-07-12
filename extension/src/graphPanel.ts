import * as vscode from 'vscode';
import { getGraphHtml, GraphSession } from './graphSession';

/**
 * セッショングラフ（gitgraph 風）を表示する Webview パネル。
 * シングルトンとして管理し、Webview 固有のロジック（データ更新・監視・
 * メッセージハンドリング）は GraphSession に委譲する。
 */
export class SessionGraphPanel {
    public static current: SessionGraphPanel | undefined;
    private static readonly viewType = 'sessionsmith.graph';

    private readonly panel: vscode.WebviewPanel;
    private readonly session: GraphSession;
    private disposables: vscode.Disposable[] = [];

    public static createOrShow(extensionUri: vscode.Uri): void {
        const column = vscode.window.activeTextEditor?.viewColumn ?? vscode.ViewColumn.One;

        if (SessionGraphPanel.current) {
            SessionGraphPanel.current.panel.reveal(column);
            SessionGraphPanel.current.session.update();
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

        this.panel.webview.html = getGraphHtml(this.panel.webview, extensionUri);
        this.panel.onDidDispose(() => this.dispose(), null, this.disposables);

        this.session = new GraphSession(this.panel.webview);
    }

    public dispose(): void {
        SessionGraphPanel.current = undefined;
        this.session.dispose();
        this.panel.dispose();
        while (this.disposables.length) {
            this.disposables.pop()?.dispose();
        }
    }
}
