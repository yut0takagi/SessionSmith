import type { CommitNode } from '../src/ssmReader';

/**
 * コミットが検索クエリにマッチするか判定する（大文字小文字を無視）。
 * 対象: メッセージ / ハッシュ / author / 変数名 / 変数型。
 * 空クエリは常に true。
 */
export function matchesQuery(c: CommitNode, rawQuery: string): boolean {
    const q = rawQuery.trim().toLowerCase();
    if (!q) {
        return true;
    }
    if (c.message.toLowerCase().includes(q)) return true;
    if (c.hash.toLowerCase().includes(q)) return true;
    if (c.author.toLowerCase().includes(q)) return true;
    for (const name of Object.keys(c.variables || {})) {
        if (name.toLowerCase().includes(q)) return true;
        const t = c.variables[name]?.type;
        if (t && t.toLowerCase().includes(q)) return true;
    }
    return false;
}
