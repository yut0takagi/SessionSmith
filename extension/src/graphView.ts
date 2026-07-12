import * as vscode from 'vscode';
import { getGraphHtml, GraphSession } from './graphSession';

/** アクティビティバーのサイドバーに Session Graph を表示する WebviewViewProvider。 */
export class SessionGraphViewProvider implements vscode.WebviewViewProvider {
    public static readonly viewType = 'sessionsmithGraph';
    private session: GraphSession | undefined;

    constructor(private readonly extensionUri: vscode.Uri) {}

    resolveWebviewView(webviewView: vscode.WebviewView): void {
        webviewView.webview.options = {
            enableScripts: true,
            localResourceRoots: [vscode.Uri.joinPath(this.extensionUri, 'media')],
        };
        webviewView.webview.html = getGraphHtml(webviewView.webview, this.extensionUri);
        this.session = new GraphSession(webviewView.webview);
        webviewView.onDidDispose(() => {
            this.session?.dispose();
            this.session = undefined;
        });
    }
}
