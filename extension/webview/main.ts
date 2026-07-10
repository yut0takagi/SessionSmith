// esbuild パイプライン疎通確認用の暫定エントリ。Task 8 で本実装に差し替える。
const vscode = acquireVsCodeApi();
vscode.postMessage({ type: 'ready' });

declare function acquireVsCodeApi(): { postMessage(msg: unknown): void; getState(): unknown; setState(s: unknown): void };
