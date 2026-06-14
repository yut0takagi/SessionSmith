import * as vscode from 'vscode';
import { findSsmRoot, readGraph, GraphData, CommitNode } from './ssmReader';

/**
 * アクティビティバーに表示するセッションツリー。
 * 現在のブランチ・ブランチ一覧・タグ一覧・最近のコミットを表示する。
 */
export class SessionTreeProvider implements vscode.TreeDataProvider<TreeNode> {
    private _onDidChangeTreeData = new vscode.EventEmitter<TreeNode | undefined | void>();
    readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

    refresh(): void {
        this._onDidChangeTreeData.fire();
    }

    getTreeItem(element: TreeNode): vscode.TreeItem {
        return element;
    }

    getChildren(element?: TreeNode): TreeNode[] {
        const graph = this.loadGraph();
        if (!graph) {
            return [new TreeNode('.ssm が見つかりません', vscode.TreeItemCollapsibleState.None, 'info')];
        }

        if (!element) {
            // ルート: セクション
            const sections: TreeNode[] = [];
            const cur = new TreeNode(
                `現在: ${graph.currentBranch || '(detached)'}`,
                vscode.TreeItemCollapsibleState.None,
                'current'
            );
            cur.iconPath = new vscode.ThemeIcon('source-control');
            sections.push(cur);

            sections.push(section(`ブランチ (${graph.branches.length})`, 'branches'));
            sections.push(section(`タグ (${graph.tags.length})`, 'tags'));
            sections.push(section(`コミット (${graph.commits.length})`, 'commits'));
            return sections;
        }

        if (element.kind === 'branches') {
            return graph.branches.map((b) => {
                const n = new TreeNode(b.name, vscode.TreeItemCollapsibleState.None, 'branch');
                n.description = b.head.slice(0, 7);
                n.iconPath = new vscode.ThemeIcon('git-branch');
                return n;
            });
        }
        if (element.kind === 'tags') {
            return graph.tags.map((t) => {
                const n = new TreeNode(t.name, vscode.TreeItemCollapsibleState.None, 'tag');
                n.description = t.commit.slice(0, 7);
                n.iconPath = new vscode.ThemeIcon('tag');
                return n;
            });
        }
        if (element.kind === 'commits') {
            return graph.commits.slice(0, 50).map((c: CommitNode) => {
                const n = new TreeNode(
                    `${c.message || '(no message)'}`,
                    vscode.TreeItemCollapsibleState.None,
                    'commit'
                );
                n.description = `${c.hash.slice(0, 7)} · ${c.varCount} vars`;
                n.tooltip = `${c.hash}\n${c.author}\n${c.timestamp}`;
                n.iconPath = new vscode.ThemeIcon(c.isMerge ? 'git-merge' : 'git-commit');
                n.command = {
                    command: 'sessionsmith.showSessionGraph',
                    title: 'Open Graph',
                };
                return n;
            });
        }
        return [];
    }

    private loadGraph(): GraphData | null {
        const root = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
        if (!root) {
            return null;
        }
        const ssmPath = findSsmRoot(root);
        if (!ssmPath) {
            return null;
        }
        try {
            return readGraph(ssmPath);
        } catch {
            return null;
        }
    }
}

type NodeKind =
    | 'current'
    | 'branches'
    | 'tags'
    | 'commits'
    | 'branch'
    | 'tag'
    | 'commit'
    | 'info';

class TreeNode extends vscode.TreeItem {
    constructor(
        label: string,
        collapsibleState: vscode.TreeItemCollapsibleState,
        public readonly kind: NodeKind
    ) {
        super(label, collapsibleState);
        this.contextValue = kind;
    }
}

function section(label: string, kind: NodeKind): TreeNode {
    return new TreeNode(label, vscode.TreeItemCollapsibleState.Expanded, kind);
}
