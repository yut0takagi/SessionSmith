import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';

/**
 * Python の実行・Notebook 連携に関する共通ヘルパー。
 */

/**
 * Python インタープリターのパスを取得
 * 優先順位: 仮想環境 > python3 > python
 */
export async function getPythonPath(
    workspaceFolder?: vscode.WorkspaceFolder
): Promise<string> {
    if (workspaceFolder) {
        const venvPaths = [
            path.join(workspaceFolder.uri.fsPath, '.venv', 'bin', 'python'),
            path.join(workspaceFolder.uri.fsPath, 'venv', 'bin', 'python'),
            path.join(workspaceFolder.uri.fsPath, '.env', 'bin', 'python'),
            path.join(workspaceFolder.uri.fsPath, 'env', 'bin', 'python'),
            path.join(workspaceFolder.uri.fsPath, '.venv', 'Scripts', 'python.exe'),
            path.join(workspaceFolder.uri.fsPath, 'venv', 'Scripts', 'python.exe'),
            path.join(workspaceFolder.uri.fsPath, '.env', 'Scripts', 'python.exe'),
            path.join(workspaceFolder.uri.fsPath, 'env', 'Scripts', 'python.exe'),
        ];
        for (const venvPath of venvPaths) {
            if (fs.existsSync(venvPath)) {
                return venvPath;
            }
        }
    }

    const { execSync } = require('child_process');
    for (const candidate of ['python3', 'python']) {
        try {
            execSync(`${candidate} --version`, { stdio: 'ignore' });
            return candidate;
        } catch {
            // 次の候補へ
        }
    }
    return 'python3';
}

/** アクティブな Notebook を取得 */
export function getActiveNotebook(): vscode.NotebookDocument | undefined {
    return vscode.window.activeNotebookEditor?.notebook;
}

/**
 * Notebook の kernel にコードを実行（一時セルを追加して実行後に削除）
 */
export async function executeCodeInNotebook(
    notebook: vscode.NotebookDocument,
    code: string
): Promise<void> {
    const edit = new vscode.WorkspaceEdit();
    const newCell = new vscode.NotebookCellData(vscode.NotebookCellKind.Code, code, 'python');
    const notebookEdit = vscode.NotebookEdit.insertCells(notebook.cellCount, [newCell]);
    edit.set(notebook.uri, [notebookEdit]);
    const success = await vscode.workspace.applyEdit(edit);
    if (!success) {
        vscode.window.showErrorMessage('Failed to insert cell into notebook.');
        return;
    }

    await new Promise((resolve) => setTimeout(resolve, 200));

    try {
        const updatedNotebook = vscode.workspace.notebookDocuments.find(
            (doc) => doc.uri.toString() === notebook.uri.toString()
        );
        if (!updatedNotebook) {
            vscode.window.showWarningMessage('Notebook not found. Please run the cell manually.');
            return;
        }
        const cellIndex = updatedNotebook.cellCount - 1;
        await vscode.commands.executeCommand('notebook.cell.execute', {
            ranges: [{ start: cellIndex, end: cellIndex + 1 }],
        });

        // 実行完了を待つ
        const maxWaitTime = 10000;
        const checkInterval = 200;
        const startTime = Date.now();
        let executionCompleted = false;
        while (!executionCompleted && Date.now() - startTime < maxWaitTime) {
            await new Promise((resolve) => setTimeout(resolve, checkInterval));
            const currentNotebook = vscode.workspace.notebookDocuments.find(
                (doc) => doc.uri.toString() === notebook.uri.toString()
            );
            if (currentNotebook && cellIndex < currentNotebook.cellCount) {
                const currentCell = currentNotebook.cellAt(cellIndex);
                if (currentCell.executionSummary?.success !== undefined) {
                    executionCompleted = true;
                    break;
                }
            } else {
                executionCompleted = true;
                break;
            }
        }

        await new Promise((resolve) => setTimeout(resolve, 300));
        const finalNotebook = vscode.workspace.notebookDocuments.find(
            (doc) => doc.uri.toString() === notebook.uri.toString()
        );
        if (finalNotebook && cellIndex < finalNotebook.cellCount) {
            const deleteEdit = new vscode.WorkspaceEdit();
            const deleteNotebookEdit = vscode.NotebookEdit.deleteCells(
                new vscode.NotebookRange(cellIndex, cellIndex + 1)
            );
            deleteEdit.set(notebook.uri, [deleteNotebookEdit]);
            await vscode.workspace.applyEdit(deleteEdit);
        }
    } catch (e: any) {
        vscode.window.showWarningMessage(
            `Failed to execute automatically: ${e.message}. The cell has been added for manual execution.`
        );
    }
}

/**
 * SessionSmith のコードを実行する。
 * アクティブな Notebook があればその kernel で、無ければ統合ターミナルで実行する。
 *
 * @param code 実行する Python コード
 * @param cwd ターミナル実行時の作業ディレクトリ
 */
export async function runSsmCode(code: string, cwd?: string): Promise<void> {
    const notebook = getActiveNotebook();
    if (notebook) {
        await executeCodeInNotebook(notebook, code);
        return;
    }

    const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
    const pythonPath = await getPythonPath(workspaceFolder);
    const terminal = vscode.window.createTerminal({
        name: 'SessionSmith',
        cwd: cwd || workspaceFolder?.uri.fsPath,
    });
    // 一行コマンドとして実行（複数行は ; で連結済みを想定）
    terminal.sendText(`${pythonPath} -c ${JSON.stringify(code)}`);
    terminal.show();
}
