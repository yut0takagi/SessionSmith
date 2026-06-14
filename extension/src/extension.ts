import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';
import {
    getPythonPath,
    getActiveNotebook,
    executeCodeInNotebook,
} from './runner';
import { SessionGraphPanel } from './graphPanel';
import { SessionTreeProvider } from './treeView';

export function activate(context: vscode.ExtensionContext) {
    console.log('SessionSmith extension is now active!');

    // === セッショングラフ GUI ===
    const showGraphCommand = vscode.commands.registerCommand(
        'sessionsmith.showSessionGraph',
        () => {
            SessionGraphPanel.createOrShow(context.extensionUri);
        }
    );

    // === アクティビティバーのツリービュー ===
    const treeProvider = new SessionTreeProvider();
    const treeView = vscode.window.createTreeView('sessionsmithSessions', {
        treeDataProvider: treeProvider,
    });
    const refreshTreeCommand = vscode.commands.registerCommand(
        'sessionsmith.refreshTree',
        () => treeProvider.refresh()
    );

    // .ssm の変更でツリーを自動更新
    const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
    if (workspaceFolder) {
        const watcher = vscode.workspace.createFileSystemWatcher(
            new vscode.RelativePattern(workspaceFolder, '**/.ssm/**')
        );
        const refresh = () => treeProvider.refresh();
        watcher.onDidCreate(refresh);
        watcher.onDidChange(refresh);
        watcher.onDidDelete(refresh);
        context.subscriptions.push(watcher);
    }

    // === Save Session ===
    const saveSessionCommand = vscode.commands.registerCommand(
        'sessionsmith.saveSession',
        async () => {
            const notebook = getActiveNotebook();
            if (notebook) {
                const notebookDir = path.dirname(notebook.uri.fsPath);
                const fileName = await vscode.window.showInputBox({
                    prompt: 'Enter session file name',
                    placeHolder: 'session.pkl',
                    value: 'session.pkl',
                });
                if (!fileName) {
                    return;
                }
                const filePath = path.join(notebookDir, fileName);
                const escapedPath = filePath.replace(/\\/g, '\\\\').replace(/'/g, "\\'");
                const code = `from SessionSmith import save_session
import os
g = globals()
save_session('${escapedPath}', globals_dict=g, verbose=True)
if os.path.exists('${escapedPath}'):
    file_size = os.path.getsize('${escapedPath}')
    print(f'✓ Session saved to ${fileName} ({file_size} bytes)')
else:
    print(f'ERROR: File was not saved to ${escapedPath}')`;
                await executeCodeInNotebook(notebook, code);
                vscode.window.showInformationMessage(`Session saved to ${fileName}`);
                return;
            }

            const editor = vscode.window.activeTextEditor;
            if (!editor || editor.document.languageId !== 'python') {
                vscode.window.showWarningMessage('Please open a Python file or Notebook first.');
                return;
            }
            const fileName = await vscode.window.showInputBox({
                prompt: 'Enter session file name',
                placeHolder: 'session.pkl',
                value: 'session.pkl',
            });
            if (!fileName) {
                return;
            }
            const activeFileDir = path.dirname(editor.document.uri.fsPath);
            const filePath = path.join(activeFileDir, fileName);
            try {
                const pythonPath = await getPythonPath(vscode.workspace.workspaceFolders?.[0]);
                const tempScriptPath = path.join(activeFileDir, '.sessionsmith_save_temp.py');
                const scriptContent = `import sys
import os
sys.path.insert(0, ${JSON.stringify(activeFileDir)})
try:
    from SessionSmith import save_session
    save_session(${JSON.stringify(filePath)}, verbose=True)
    print('✓ Session saved to ${fileName}')
    print('\\nYou can continue working in this Python REPL.')
except ImportError:
    print('ERROR: SessionSmith is not installed. Run: pip install SessionSmith')
    sys.exit(1)
except Exception as e:
    print(f'ERROR: {str(e)}')
    sys.exit(1)
`;
                fs.writeFileSync(tempScriptPath, scriptContent, 'utf8');
                const terminal = vscode.window.createTerminal('SessionSmith');
                terminal.sendText(`${pythonPath} -i ${JSON.stringify(tempScriptPath)}`);
                terminal.show();
                setTimeout(() => {
                    try {
                        if (fs.existsSync(tempScriptPath)) {
                            fs.unlinkSync(tempScriptPath);
                        }
                    } catch {
                        /* ignore */
                    }
                }, 1000);
                vscode.window.showInformationMessage(`Session will be saved to ${fileName}`);
            } catch (error: any) {
                vscode.window.showErrorMessage(`Failed to save session: ${error}`);
            }
        }
    );

    // === Load Session ===
    const loadSessionCommand = vscode.commands.registerCommand(
        'sessionsmith.loadSession',
        async () => {
            const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
            if (!workspaceFolder) {
                vscode.window.showErrorMessage('No workspace folder found.');
                return;
            }
            const fileUri = await vscode.window.showOpenDialog({
                canSelectFiles: true,
                canSelectFolders: false,
                canSelectMany: false,
                filters: { 'Session Files': ['pkl', 'json', 'msgpack', 'h5'] },
                defaultUri: workspaceFolder.uri,
            });
            if (!fileUri || fileUri.length === 0) {
                return;
            }
            const filePath = fileUri[0].fsPath;

            const notebook = getActiveNotebook();
            if (notebook) {
                const escapedPath = filePath.replace(/\\/g, '\\\\').replace(/'/g, "\\'");
                const fileName = path.basename(filePath);
                const code = `from SessionSmith import load_session
g = globals()
loaded = load_session('${escapedPath}', globals_dict=g, verbose=True)
print(f'✓ Session loaded from ${fileName}')
print(f'Loaded {len(loaded)} variables')`;
                await executeCodeInNotebook(notebook, code);
                vscode.window.showInformationMessage(`Session loaded from ${fileName}`);
                return;
            }

            try {
                const pythonPath = await getPythonPath(workspaceFolder);
                const fileName = path.basename(filePath);
                const tempScriptPath = path.join(
                    workspaceFolder.uri.fsPath,
                    '.sessionsmith_load_temp.py'
                );
                const scriptContent = `import sys
import os
sys.path.insert(0, ${JSON.stringify(workspaceFolder.uri.fsPath)})
try:
    from SessionSmith import load_session
    loaded = load_session(${JSON.stringify(filePath)}, verbose=True)
    print(f'✓ Session loaded from ${fileName}')
    print(f'Loaded {len(loaded)} variables into global scope')
except ImportError:
    print('ERROR: SessionSmith is not installed. Run: pip install SessionSmith')
    sys.exit(1)
except Exception as e:
    print(f'ERROR: {str(e)}')
    sys.exit(1)
`;
                fs.writeFileSync(tempScriptPath, scriptContent, 'utf8');
                const terminal = vscode.window.createTerminal('SessionSmith');
                terminal.sendText(`${pythonPath} -i ${JSON.stringify(tempScriptPath)}`);
                terminal.show();
                setTimeout(() => {
                    try {
                        if (fs.existsSync(tempScriptPath)) {
                            fs.unlinkSync(tempScriptPath);
                        }
                    } catch {
                        /* ignore */
                    }
                }, 1000);
                vscode.window.showInformationMessage(`Session loaded from ${fileName}`);
            } catch (error: any) {
                vscode.window.showErrorMessage(`Failed to load session: ${error}`);
            }
        }
    );

    // === Show Session Info ===
    const showSessionInfoCommand = vscode.commands.registerCommand(
        'sessionsmith.showSessionInfo',
        async (uri?: vscode.Uri) => {
            let filePath: string;
            const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
            if (uri) {
                filePath = uri.fsPath;
            } else {
                if (!workspaceFolder) {
                    vscode.window.showErrorMessage('No workspace folder found.');
                    return;
                }
                const fileUri = await vscode.window.showOpenDialog({
                    canSelectFiles: true,
                    canSelectFolders: false,
                    canSelectMany: false,
                    filters: { 'Session Files': ['pkl', 'json', 'msgpack', 'h5'] },
                    defaultUri: workspaceFolder.uri,
                });
                if (!fileUri || fileUri.length === 0) {
                    return;
                }
                filePath = fileUri[0].fsPath;
            }

            try {
                if (!workspaceFolder) {
                    return;
                }
                const pythonPath = await getPythonPath(workspaceFolder);
                const escapedPath = filePath.replace(/\\/g, '\\\\').replace(/'/g, "\\'");
                const escapedWorkspace = workspaceFolder.uri.fsPath
                    .replace(/\\/g, '\\\\')
                    .replace(/'/g, "\\'");
                const pythonCode = `import sys; import json; sys.path.insert(0, '${escapedWorkspace}'); exec("""try:
    from SessionSmith import get_session_info
    info = get_session_info('${escapedPath}')
    print(json.dumps(info, indent=2, default=str))
except ImportError:
    print('ERROR: SessionSmith is not installed. Run: pip install SessionSmith')
except Exception as e:
    print(f'ERROR: {str(e)}')
""")`;
                const terminal = vscode.window.createTerminal('SessionSmith');
                terminal.sendText(`${pythonPath} -c ${JSON.stringify(pythonCode)}`);
                terminal.show();
            } catch (error: any) {
                vscode.window.showErrorMessage(`Failed to get session info: ${error}`);
            }
        }
    );

    context.subscriptions.push(
        showGraphCommand,
        refreshTreeCommand,
        treeView,
        saveSessionCommand,
        loadSessionCommand,
        showSessionInfoCommand
    );
}

export function deactivate() {}
