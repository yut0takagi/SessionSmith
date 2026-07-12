import * as fs from 'fs';
import * as path from 'path';

export type RefKind = 'branch' | 'tag';

export class RefError extends Error {
    constructor(message: string) {
        super(message);
        this.name = 'RefError';
    }
}

const NAME_RE = /^[A-Za-z0-9_.-]+$/;

function refDir(ssmPath: string, kind: RefKind): string {
    return path.join(ssmPath, kind === 'branch' ? 'branches' : 'tags');
}

function listRefNames(ssmPath: string, kind: RefKind): string[] {
    const dir = refDir(ssmPath, kind);
    try {
        return fs
            .readdirSync(dir)
            .filter((f) => !f.endsWith('.bak') && !f.endsWith('.tmp'));
    } catch {
        return [];
    }
}

function readConfig(ssmPath: string): Record<string, unknown> {
    try {
        return JSON.parse(fs.readFileSync(path.join(ssmPath, 'config'), 'utf8'));
    } catch {
        return {};
    }
}

function writeConfig(ssmPath: string, cfg: Record<string, unknown>): void {
    fs.writeFileSync(path.join(ssmPath, 'config'), JSON.stringify(cfg, null, 2));
}

/** branch/tag の参照ファイルを削除する（`.bak` に退避）。 */
export function deleteRef(ssmPath: string, kind: RefKind, name: string): void {
    const file = path.join(refDir(ssmPath, kind), name);
    if (!fs.existsSync(file)) {
        throw new RefError(`${kind} '${name}' が見つかりません`);
    }
    if (kind === 'branch') {
        const cfg = readConfig(ssmPath);
        if (cfg.current_branch === name) {
            throw new RefError(`現在のブランチ '${name}' は削除できません`);
        }
        if (listRefNames(ssmPath, 'branch').length <= 1) {
            throw new RefError('唯一のブランチは削除できません');
        }
    }
    let backup = file + '.bak';
    let i = 1;
    while (fs.existsSync(backup)) {
        backup = `${file}.bak.${i++}`;
    }
    fs.renameSync(file, backup);
}

/** branch/tag の参照ファイルをリネームする。branch が現在ブランチなら config を追従。 */
export function renameRef(
    ssmPath: string,
    kind: RefKind,
    oldName: string,
    newName: string
): void {
    if (!NAME_RE.test(newName)) {
        throw new RefError('名前には英数字・アンダースコア・ハイフン・ドットのみ使用できます');
    }
    const dir = refDir(ssmPath, kind);
    const src = path.join(dir, oldName);
    const dst = path.join(dir, newName);
    if (!fs.existsSync(src)) {
        throw new RefError(`${kind} '${oldName}' が見つかりません`);
    }
    if (fs.existsSync(dst)) {
        throw new RefError(`'${newName}' は既に存在します`);
    }
    fs.renameSync(src, dst);
    if (kind === 'branch') {
        const cfg = readConfig(ssmPath);
        if (cfg.current_branch === oldName) {
            cfg.current_branch = newName;
            writeConfig(ssmPath, cfg);
        }
    }
}
