import * as fs from 'fs';
import * as path from 'path';

export type RefKind = 'branch' | 'tag';

export class RefError extends Error {
    constructor(message: string) {
        super(message);
        this.name = 'RefError';
    }
}

// Python 側 SessionSmith/validation.py の validate_ref_name() と同一のルール。
// 一方を変更する場合は両方を同時に更新すること。
const NAME_RE = /^[A-Za-z0-9_.-]+$/;
const MAX_NAME_LENGTH = 255;

// Windows の予約デバイス名。ディレクトリ配下でもデバイスとして解決されるため、
// `branches/NUL` への書き込みはヌルデバイスに吸われてしまう。
const WINDOWS_RESERVED_NAMES = new Set([
    'CON', 'PRN', 'AUX', 'NUL',
    'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
    'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9',
]);

/**
 * ブランチ/タグ名として妥当か検証する（パストラバーサル対策）。
 *
 * 許可: ASCII の英数字・`_`・`-`・`.` のみで構成された 1〜255文字の名前。
 * 拒否: `.` / `..` / ドットのみの名前、`-` から始まる名前、
 *       上記の許可文字セット以外を含む名前（`/` や `\` を含む）。
 */
export function isValidRefName(name: string): boolean {
    if (typeof name !== 'string' || name.length === 0 || name.length > MAX_NAME_LENGTH) {
        return false;
    }
    if (!NAME_RE.test(name)) {
        return false;
    }
    if (/^\.+$/.test(name)) {
        return false;
    }
    if (name.startsWith('-')) {
        return false;
    }
    // Windows はファイル名末尾のドットを削除するため、'v2.' と 'v2' が衝突する
    if (name.endsWith('.')) {
        return false;
    }
    // 予約デバイス名は拡張子付き（NUL.txt など）でも予約扱いになる
    if (WINDOWS_RESERVED_NAMES.has(name.split('.')[0].toUpperCase())) {
        return false;
    }
    return true;
}

const INVALID_NAME_MESSAGE =
    '名前には英数字・アンダースコア・ハイフン・ドットのみ使用でき、"." や ".." は使用できません';

function refDir(ssmPath: string, kind: RefKind): string {
    return path.join(ssmPath, kind === 'branch' ? 'branches' : 'tags');
}

/** target が base ディレクトリ配下に収まっていることを確認する（多層防御）。 */
function ensureWithin(base: string, target: string): void {
    const resolvedBase = path.resolve(base);
    const resolvedTarget = path.resolve(target);
    if (resolvedTarget !== resolvedBase && !resolvedTarget.startsWith(resolvedBase + path.sep)) {
        throw new RefError('無効なパスです');
    }
}

/**
 * 参照が存在するかを、大文字小文字を区別して判定する。
 *
 * macOS（APFS の既定）と Windows のファイルシステムは大文字小文字を区別しないため、
 * `fs.existsSync()` では `feature` しか無いのに `FEATURE` が「存在する」と判定される。
 * 判定は必ずディレクトリを列挙して行う（Python 側 SSM._ref_exists() と同じ考え方）。
 */
function refExists(ssmPath: string, kind: RefKind, name: string): boolean {
    return listRefNames(ssmPath, kind).includes(name);
}

/**
 * 大文字小文字だけが異なる既存の参照名を返す（無ければ undefined）。
 *
 * 大文字小文字を区別しないファイルシステムでは同じファイルになるため、
 * リネーム先に指定されたら既存の参照を壊してしまう。
 */
function findCaseConflictingRef(
    ssmPath: string,
    kind: RefKind,
    name: string
): string | undefined {
    const lowered = name.toLowerCase();
    return listRefNames(ssmPath, kind).find(
        (existing) => existing !== name && existing.toLowerCase() === lowered
    );
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
    if (!isValidRefName(name)) {
        throw new RefError(INVALID_NAME_MESSAGE);
    }
    const dir = refDir(ssmPath, kind);
    const file = path.join(dir, name);
    ensureWithin(dir, file);
    if (!refExists(ssmPath, kind, name)) {
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
    if (!isValidRefName(oldName) || !isValidRefName(newName)) {
        throw new RefError(INVALID_NAME_MESSAGE);
    }
    const dir = refDir(ssmPath, kind);
    const src = path.join(dir, oldName);
    const dst = path.join(dir, newName);
    ensureWithin(dir, src);
    ensureWithin(dir, dst);
    if (!refExists(ssmPath, kind, oldName)) {
        throw new RefError(`${kind} '${oldName}' が見つかりません`);
    }
    if (refExists(ssmPath, kind, newName)) {
        throw new RefError(`'${newName}' は既に存在します`);
    }
    const conflicting = findCaseConflictingRef(ssmPath, kind, newName);
    if (conflicting !== undefined && conflicting !== oldName) {
        throw new RefError(
            `'${newName}' は既存の '${conflicting}' と大文字小文字しか違いません。` +
                'macOS や Windows では同じファイルになるため使用できません'
        );
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
