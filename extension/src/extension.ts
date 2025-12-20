import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';

/**
 * Pythonインタープリターのパスを取得
 * 優先順位: 仮想環境 > python3 > python
 */
async function getPythonPath(workspaceFolder?: vscode.WorkspaceFolder): Promise<string> {
    // 1. ワークスペース内の仮想環境を検索
    if (workspaceFolder) {
        const venvPaths = [
            path.join(workspaceFolder.uri.fsPath, '.venv', 'bin', 'python'),
            path.join(workspaceFolder.uri.fsPath, 'venv', 'bin', 'python'),
            path.join(workspaceFolder.uri.fsPath, '.env', 'bin', 'python'),
            path.join(workspaceFolder.uri.fsPath, 'env', 'bin', 'python'),
        ];

        for (const venvPath of venvPaths) {
            if (fs.existsSync(venvPath)) {
                return venvPath;
            }
        }

        // Windows用の仮想環境パス
        const venvPathsWin = [
            path.join(workspaceFolder.uri.fsPath, '.venv', 'Scripts', 'python.exe'),
            path.join(workspaceFolder.uri.fsPath, 'venv', 'Scripts', 'python.exe'),
            path.join(workspaceFolder.uri.fsPath, '.env', 'Scripts', 'python.exe'),
            path.join(workspaceFolder.uri.fsPath, 'env', 'Scripts', 'python.exe'),
        ];

        for (const venvPath of venvPathsWin) {
            if (fs.existsSync(venvPath)) {
                return venvPath;
            }
        }
    }

    // 2. python3を試す
    try {
        const { execSync } = require('child_process');
        execSync('python3 --version', { stdio: 'ignore' });
        return 'python3';
    } catch {
        // python3が見つからない場合は次へ
    }

    // 3. pythonを試す
    try {
        const { execSync } = require('child_process');
        execSync('python --version', { stdio: 'ignore' });
        return 'python';
    } catch {
        // pythonも見つからない場合はエラー
    }

    // デフォルトはpython3
    return 'python3';
}

/**
 * アクティブなNotebookを取得
 */
function getActiveNotebook(): vscode.NotebookDocument | undefined {
    const notebookEditor = vscode.window.activeNotebookEditor;
    return notebookEditor?.notebook;
}

/**
 * Notebookのkernelにコードを実行（セルを追加せずに実行）
 */
async function executeCodeInNotebook(notebook: vscode.NotebookDocument, code: string): Promise<void> {
    // 一時的なセルを作成して実行し、実行後に削除する
    const edit = new vscode.WorkspaceEdit();
    const newCell = new vscode.NotebookCellData(
        vscode.NotebookCellKind.Code,
        code,
        'python'
    );
    
    // 最後にセルを追加
    const notebookEdit = vscode.NotebookEdit.insertCells(
        notebook.cellCount,
        [newCell]
    );
    edit.set(notebook.uri, [notebookEdit]);
    const success = await vscode.workspace.applyEdit(edit);
    
    if (!success) {
        vscode.window.showErrorMessage('Failed to insert cell into notebook.');
        return;
    }
    
    // 少し待ってからセルを実行（Notebookが更新されるのを待つ）
    await new Promise(resolve => setTimeout(resolve, 200));
    
    // セルを実行
    try {
        // Notebookが更新された後のセル数を取得
        const updatedNotebook = vscode.workspace.notebookDocuments.find(doc => doc.uri.toString() === notebook.uri.toString());
        if (updatedNotebook) {
            const cellIndex = updatedNotebook.cellCount - 1;
            const cell = updatedNotebook.cellAt(cellIndex);
            
            // セルを実行
            await vscode.commands.executeCommand('notebook.cell.execute', {
                ranges: [{ start: cellIndex, end: cellIndex + 1 }]
            });
            
            // セル実行の完了を待つ（セルの実行状態を監視）
            let executionCompleted = false;
            const maxWaitTime = 10000; // 10秒のタイムアウト
            const checkInterval = 200; // 200msごとにチェック
            const startTime = Date.now();
            
            while (!executionCompleted && (Date.now() - startTime) < maxWaitTime) {
                await new Promise(resolve => setTimeout(resolve, checkInterval));
                
                // Notebookを再取得してセルの状態を確認
                const currentNotebook = vscode.workspace.notebookDocuments.find(
                    doc => doc.uri.toString() === notebook.uri.toString()
                );
                
                if (currentNotebook && cellIndex < currentNotebook.cellCount) {
                    const currentCell = currentNotebook.cellAt(cellIndex);
                    // セルが実行中でない場合（成功または失敗）、完了とみなす
                    if (currentCell.executionSummary?.success !== undefined) {
                        executionCompleted = true;
                        break;
                    }
                } else {
                    // セルが存在しない場合は削除されたとみなす
                    executionCompleted = true;
                    break;
                }
            }
            
            // セルを削除（実行完了後、少し待ってから削除）
            await new Promise(resolve => setTimeout(resolve, 300));
            
            // Notebookを再取得してセルがまだ存在するか確認
            const finalNotebook = vscode.workspace.notebookDocuments.find(
                doc => doc.uri.toString() === notebook.uri.toString()
            );
            
            if (finalNotebook && cellIndex < finalNotebook.cellCount) {
                const deleteEdit = new vscode.WorkspaceEdit();
                const deleteNotebookEdit = vscode.NotebookEdit.deleteCells(
                    new vscode.NotebookRange(cellIndex, cellIndex + 1)
                );
                deleteEdit.set(notebook.uri, [deleteNotebookEdit]);
                await vscode.workspace.applyEdit(deleteEdit);
            }
        } else {
            vscode.window.showWarningMessage('Notebook not found. Please run the cell manually.');
        }
    } catch (e: any) {
        // 実行に失敗した場合は、セルを残してユーザーに手動で実行してもらう
        vscode.window.showWarningMessage(`Failed to execute automatically: ${e.message}. The cell has been added for manual execution.`);
    }
}

export function activate(context: vscode.ExtensionContext) {
    console.log('SessionSmith extension is now active!');

    // Save Session コマンド
    const saveSessionCommand = vscode.commands.registerCommand(
        'sessionsmith.saveSession',
        async () => {
            // Notebookが開いている場合はNotebookで実行
            const notebook = getActiveNotebook();
            if (notebook) {
                // Notebookファイルがあるディレクトリを取得
                const notebookDir = path.dirname(notebook.uri.fsPath);
                
                const fileName = await vscode.window.showInputBox({
                    prompt: 'Enter session file name',
                    placeHolder: 'session.pkl',
                    value: 'session.pkl'
                });

                if (!fileName) {
                    return;
                }

                const filePath = path.join(notebookDir, fileName);
                const escapedPath = filePath.replace(/\\/g, '\\\\').replace(/'/g, "\\'");
                
                const code = `from SessionSmith import save_session
import os
# Notebookのkernelのグローバルスコープから変数を保存
g = globals()
save_session('${escapedPath}', globals_dict=g, verbose=True)
# ファイルが実際に保存されたか確認
if os.path.exists('${escapedPath}'):
    file_size = os.path.getsize('${escapedPath}')
    print(f'✓ Session saved to ${fileName} ({file_size} bytes)')
    print(f'Location: ${escapedPath}')
else:
    print(f'ERROR: File was not saved to ${escapedPath}')`;

                await executeCodeInNotebook(notebook, code);
                vscode.window.showInformationMessage(`Session saved to ${fileName} in ${path.dirname(filePath)}`);
                return;
            }

            // 通常のPythonファイルの場合
            const editor = vscode.window.activeTextEditor;
            if (!editor || editor.document.languageId !== 'python') {
                vscode.window.showWarningMessage('Please open a Python file or Notebook first.');
                return;
            }

            // ファイル名を入力
            const fileName = await vscode.window.showInputBox({
                prompt: 'Enter session file name',
                placeHolder: 'session.pkl',
                value: 'session.pkl'
            });

            if (!fileName) {
                return;
            }

            // アクティブなファイルがあるディレクトリを取得
            const activeFileDir = path.dirname(editor.document.uri.fsPath);
            const filePath = path.join(activeFileDir, fileName);

            try {
                // ワークスペースフォルダを取得（Pythonパス検出用）
                const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
                // Pythonインタープリターのパスを取得
                const pythonPath = await getPythonPath(workspaceFolder);
                
                // 一時的なPythonスクリプトを生成して、-iオプションで実行
                // -iオプションにより、スクリプト実行後に対話的シェルが起動し、変数が利用可能になる
                const tempScriptPath = path.join(activeFileDir, '.sessionsmith_save_temp.py');
                const scriptContent = `import sys
import os
sys.path.insert(0, ${JSON.stringify(activeFileDir)})

try:
    from SessionSmith import save_session
    # グローバルスコープから変数を保存
    save_session(${JSON.stringify(filePath)}, verbose=True)
    print('✓ Session saved to ${fileName}')
    print('\\nYou can continue working in this Python REPL.')
    print('Type "exit()" or press Ctrl+D to exit.')
except ImportError:
    print('ERROR: SessionSmith is not installed. Please install it with: pip install SessionSmith')
    sys.exit(1)
except Exception as e:
    print(f'ERROR: {str(e)}')
    sys.exit(1)
`;

                // 一時スクリプトを書き込む
                fs.writeFileSync(tempScriptPath, scriptContent, 'utf8');

                // -iオプションで実行（スクリプト実行後に対話的シェルを起動）
                const terminal = vscode.window.createTerminal('SessionSmith');
                terminal.sendText(`${pythonPath} -i ${JSON.stringify(tempScriptPath)}`);
                terminal.show();

                // スクリプト実行後に一時ファイルを削除（少し遅延を入れる）
                setTimeout(() => {
                    try {
                        if (fs.existsSync(tempScriptPath)) {
                            fs.unlinkSync(tempScriptPath);
                        }
                    } catch (e) {
                        // 削除に失敗しても無視（既に削除されている可能性がある）
                    }
                }, 1000);

                vscode.window.showInformationMessage(`Session will be saved to ${fileName} in ${activeFileDir}`);
            } catch (error: any) {
                vscode.window.showErrorMessage(`Failed to save session: ${error}`);
            }
        }
    );

    // Load Session コマンド
    const loadSessionCommand = vscode.commands.registerCommand(
        'sessionsmith.loadSession',
        async () => {
            const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
            if (!workspaceFolder) {
                vscode.window.showErrorMessage('No workspace folder found.');
                return;
            }

            // セッションファイルを選択
            const fileUri = await vscode.window.showOpenDialog({
                canSelectFiles: true,
                canSelectFolders: false,
                canSelectMany: false,
                filters: {
                    'Session Files': ['pkl', 'json', 'msgpack', 'h5']
                },
                defaultUri: workspaceFolder.uri
            });

            if (!fileUri || fileUri.length === 0) {
                return;
            }

            const filePath = fileUri[0].fsPath;

            // Notebookが開いている場合はNotebookで実行
            const notebook = getActiveNotebook();
            if (notebook) {
                const escapedPath = filePath.replace(/\\/g, '\\\\').replace(/'/g, "\\'");
                const fileName = path.basename(filePath);
                
                const code = `from SessionSmith import load_session
# Notebookのkernelのグローバルスコープに変数を読み込む
g = globals()
loaded = load_session('${escapedPath}', globals_dict=g, verbose=True)
print(f'✓ Session loaded from ${fileName}')
print(f'Loaded {len(loaded)} variables')
user_vars = [k for k in loaded.keys() if not k.startswith('_') and k not in ['Optional', 'List', 'Dict', 'Union', 'Callable', 'Literal']]
if user_vars:
    print('Variables:', ', '.join(user_vars))
    print('\\nYou can now use these variables in other cells.')`;

                await executeCodeInNotebook(notebook, code);
                vscode.window.showInformationMessage(`Session loaded from ${fileName}`);
                return;
            }

            try {
                // Pythonインタープリターのパスを取得
                const pythonPath = await getPythonPath(workspaceFolder);
                
                const escapedPath = filePath.replace(/\\/g, '\\\\').replace(/'/g, "\\'");
                const escapedWorkspace = workspaceFolder.uri.fsPath.replace(/\\/g, '\\\\').replace(/'/g, "\\'");
                const fileName = path.basename(filePath);
                
                // 一時的なPythonスクリプトを生成して、-iオプションで実行
                // -iオプションにより、スクリプト実行後に対話的シェルが起動し、変数が利用可能になる
                const tempScriptPath = path.join(workspaceFolder.uri.fsPath, '.sessionsmith_load_temp.py');
                const scriptContent = `import sys
import os
sys.path.insert(0, ${JSON.stringify(workspaceFolder.uri.fsPath)})

try:
    from SessionSmith import load_session
    # グローバルスコープに変数を読み込む
    loaded = load_session(${JSON.stringify(filePath)}, verbose=True)
    print(f'✓ Session loaded from ${fileName}')
    print(f'Loaded {len(loaded)} variables into global scope')
    # ユーザー定義変数のみを表示（型ヒントなどを除外）
    user_vars = [k for k in loaded.keys() if not k.startswith('_') and k not in ['Optional', 'List', 'Dict', 'Union', 'Callable', 'Literal']]
    if user_vars:
        print('Variables:', ', '.join(user_vars))
    print('\\nYou can now use the loaded variables in this Python REPL.')
    print('Type "exit()" or press Ctrl+D to exit.')
except ImportError:
    print('ERROR: SessionSmith is not installed. Please install it with: pip install SessionSmith')
    sys.exit(1)
except Exception as e:
    print(f'ERROR: {str(e)}')
    sys.exit(1)
`;

                // 一時スクリプトを書き込む
                fs.writeFileSync(tempScriptPath, scriptContent, 'utf8');

                // -iオプションで実行（スクリプト実行後に対話的シェルを起動）
                const terminal = vscode.window.createTerminal('SessionSmith');
                terminal.sendText(`${pythonPath} -i ${JSON.stringify(tempScriptPath)}`);
                terminal.show();

                // スクリプト実行後に一時ファイルを削除（少し遅延を入れる）
                setTimeout(() => {
                    try {
                        if (fs.existsSync(tempScriptPath)) {
                            fs.unlinkSync(tempScriptPath);
                        }
                    } catch (e) {
                        // 削除に失敗しても無視（既に削除されている可能性がある）
                    }
                }, 1000);

                vscode.window.showInformationMessage(`Session loaded from ${path.basename(filePath)}`);
            } catch (error: any) {
                vscode.window.showErrorMessage(`Failed to load session: ${error}`);
            }
        }
    );

    // Show Session Info コマンド
    const showSessionInfoCommand = vscode.commands.registerCommand(
        'sessionsmith.showSessionInfo',
        async (uri?: vscode.Uri) => {
            let filePath: string;

            if (uri) {
                filePath = uri.fsPath;
            } else {
                const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
                if (!workspaceFolder) {
                    vscode.window.showErrorMessage('No workspace folder found.');
                    return;
                }

                const fileUri = await vscode.window.showOpenDialog({
                    canSelectFiles: true,
                    canSelectFolders: false,
                    canSelectMany: false,
                    filters: {
                        'Session Files': ['pkl', 'json', 'msgpack', 'h5']
                    },
                    defaultUri: workspaceFolder.uri
                });

                if (!fileUri || fileUri.length === 0) {
                    return;
                }

                filePath = fileUri[0].fsPath;
            }

            try {
                const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
                if (!workspaceFolder) {
                    return;
                }

                // Pythonインタープリターのパスを取得
                const pythonPath = await getPythonPath(workspaceFolder);

                const escapedPath = filePath.replace(/\\/g, '\\\\').replace(/'/g, "\\'");
                const escapedWorkspace = workspaceFolder.uri.fsPath.replace(/\\/g, '\\\\').replace(/'/g, "\\'");
                
                const pythonCode = `import sys; import json; sys.path.insert(0, '${escapedWorkspace}'); exec("""try:
    from SessionSmith import get_session_info
    info = get_session_info('${escapedPath}')
    print(json.dumps(info, indent=2, default=str))
except ImportError:
    print('ERROR: SessionSmith is not installed. Please install it with: pip install SessionSmith')
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

    context.subscriptions.push(saveSessionCommand, loadSessionCommand, showSessionInfoCommand);
}

export function deactivate() {}

