import * as fs from 'fs';
import * as path from 'path';

/**
 * .ssm/ ディレクトリを読み取り、コミットグラフのモデルを構築する。
 *
 * Python パッケージに依存せず、ファイルシステムから直接 SSM リポジトリの
 * 状態（コミット・ブランチ・タグ・HEAD）を読み込む。これにより
 * SessionSmith が未インストールの環境でもグラフを可視化できる。
 */

export interface CommitNode {
    hash: string;
    message: string;
    author: string;
    timestamp: string;
    parents: string[];
    isMerge: boolean;
    variables: Record<string, { hash: string; type: string; size: number }>;
    varCount: number;
    totalSize: number;
    signed: boolean;
    caller?: { filename?: string; function_name?: string; line_number?: string };
}

export interface BranchRef {
    name: string;
    head: string;
}

export interface TagRef {
    name: string;
    commit: string;
    message?: string;
}

export interface GraphData {
    commits: CommitNode[];
    branches: BranchRef[];
    tags: TagRef[];
    head: string;
    currentBranch: string | null;
    ssmPath: string;
}

const SSM_DIR = '.ssm';

/** ワークスペース配下で .ssm ディレクトリを探す（直下を優先） */
export function findSsmRoot(workspaceRoot: string): string | null {
    const direct = path.join(workspaceRoot, SSM_DIR);
    if (isDir(direct)) {
        return direct;
    }
    // 直下に無ければ 1 階層だけサブディレクトリを探索
    try {
        for (const entry of fs.readdirSync(workspaceRoot, { withFileTypes: true })) {
            if (entry.isDirectory() && !entry.name.startsWith('.')) {
                const candidate = path.join(workspaceRoot, entry.name, SSM_DIR);
                if (isDir(candidate)) {
                    return candidate;
                }
            }
        }
    } catch {
        // 読み取り失敗は無視
    }
    return null;
}

function isDir(p: string): boolean {
    try {
        return fs.statSync(p).isDirectory();
    } catch {
        return false;
    }
}

function isFile(p: string): boolean {
    try {
        return fs.statSync(p).isFile();
    } catch {
        return false;
    }
}

function readJsonSafe(p: string): any | null {
    try {
        return JSON.parse(fs.readFileSync(p, 'utf8'));
    } catch {
        return null;
    }
}

function readTextSafe(p: string): string {
    try {
        return fs.readFileSync(p, 'utf8').trim();
    } catch {
        return '';
    }
}

/**
 * .ssm ディレクトリからグラフデータを読み込む。
 * @param ssmPath `.ssm` ディレクトリの絶対パス
 */
export function readGraph(ssmPath: string): GraphData {
    const commits = readCommits(ssmPath);
    const branches = readBranches(ssmPath);
    const tags = readTags(ssmPath);
    const head = readTextSafe(path.join(ssmPath, 'HEAD'));
    const currentBranch = readCurrentBranch(ssmPath, branches, head);

    const ordered = topoSort(commits);

    return {
        commits: ordered,
        branches,
        tags,
        head,
        currentBranch,
        ssmPath,
    };
}

function readCommits(ssmPath: string): Map<string, CommitNode> {
    const commitsDir = path.join(ssmPath, 'commits');
    const map = new Map<string, CommitNode>();
    if (!isDir(commitsDir)) {
        return map;
    }

    for (const file of fs.readdirSync(commitsDir)) {
        if (!file.endsWith('.json') || file.endsWith('.bak') || file.endsWith('.tmp')) {
            continue;
        }
        const data = readJsonSafe(path.join(commitsDir, file));
        if (!data) {
            continue;
        }
        const hash = file.replace(/\.json$/, '');
        const parents: string[] = [];
        if (data.parent) {
            parents.push(data.parent);
        }
        if (data.merge_parent) {
            parents.push(data.merge_parent);
        }

        const variables = data.variables || {};
        let totalSize = 0;
        for (const key of Object.keys(variables)) {
            totalSize += variables[key]?.size || 0;
        }

        map.set(hash, {
            hash,
            message: data.message || '',
            author: data.author || 'unknown',
            timestamp: data.timestamp || '',
            parents,
            isMerge: parents.length > 1,
            variables,
            varCount: Object.keys(variables).length,
            totalSize,
            signed: data.signature !== undefined && data.signature !== null,
            caller: data.caller,
        });
    }
    return map;
}

function readBranches(ssmPath: string): BranchRef[] {
    const branchesDir = path.join(ssmPath, 'branches');
    const branches: BranchRef[] = [];
    if (!isDir(branchesDir)) {
        return branches;
    }
    for (const file of fs.readdirSync(branchesDir)) {
        const full = path.join(branchesDir, file);
        if (!isFile(full) || file.endsWith('.bak') || file.endsWith('.tmp')) {
            continue;
        }
        branches.push({ name: file, head: readTextSafe(full) });
    }
    branches.sort((a, b) => a.name.localeCompare(b.name));
    return branches;
}

function readTags(ssmPath: string): TagRef[] {
    const tagsDir = path.join(ssmPath, 'tags');
    const tags: TagRef[] = [];
    if (!isDir(tagsDir)) {
        return tags;
    }
    for (const file of fs.readdirSync(tagsDir)) {
        const full = path.join(tagsDir, file);
        if (!isFile(full) || file.endsWith('.bak') || file.endsWith('.tmp')) {
            continue;
        }
        // タグは JSON ({commit, message}) かプレーンなハッシュのどちらか
        const json = readJsonSafe(full);
        if (json && typeof json === 'object') {
            tags.push({ name: file, commit: json.commit || '', message: json.message });
        } else {
            tags.push({ name: file, commit: readTextSafe(full) });
        }
    }
    tags.sort((a, b) => a.name.localeCompare(b.name));
    return tags;
}

function readCurrentBranch(
    ssmPath: string,
    branches: BranchRef[],
    head: string
): string | null {
    // config の current_branch を優先
    const config = readJsonSafe(path.join(ssmPath, 'config'));
    if (config && config.current_branch) {
        return config.current_branch;
    }
    // HEAD が指すコミットと一致するブランチを探す
    const match = branches.find((b) => b.head === head && head !== '');
    return match ? match.name : null;
}

/**
 * コミットをトポロジカル順（新しい順）に並べる。
 * timestamp 降順をベースに、親が子より後ろに来るよう調整する。
 */
function topoSort(map: Map<string, CommitNode>): CommitNode[] {
    const all = Array.from(map.values());
    // まず timestamp 降順（新しいものが先頭）
    all.sort((a, b) => (a.timestamp < b.timestamp ? 1 : a.timestamp > b.timestamp ? -1 : 0));
    return all;
}
