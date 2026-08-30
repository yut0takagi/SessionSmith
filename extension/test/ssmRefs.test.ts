import { test } from 'node:test';
import assert from 'node:assert';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import { deleteRef, isValidRefName, renameRef, RefError } from '../src/ssmRefs';

function makeSsm(): string {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), 'ssmrefs-'));
    const ssm = path.join(root, '.ssm');
    fs.mkdirSync(path.join(ssm, 'branches'), { recursive: true });
    fs.mkdirSync(path.join(ssm, 'tags'), { recursive: true });
    fs.writeFileSync(path.join(ssm, 'branches', 'main'), 'aaa');
    fs.writeFileSync(path.join(ssm, 'branches', 'feature'), 'bbb');
    fs.writeFileSync(path.join(ssm, 'tags', 'v1'), 'aaa');
    fs.writeFileSync(path.join(ssm, 'config'), JSON.stringify({ current_branch: 'main' }));
    return ssm;
}

test('deleteRef removes a branch file and leaves a .bak', () => {
    const ssm = makeSsm();
    deleteRef(ssm, 'branch', 'feature');
    assert.equal(fs.existsSync(path.join(ssm, 'branches', 'feature')), false);
    assert.equal(fs.existsSync(path.join(ssm, 'branches', 'feature.bak')), true);
});

test('deleteRef refuses to delete the current branch', () => {
    const ssm = makeSsm();
    assert.throws(() => deleteRef(ssm, 'branch', 'main'), RefError);
});

test('deleteRef refuses to delete the only branch', () => {
    const ssm = makeSsm();
    fs.unlinkSync(path.join(ssm, 'branches', 'feature'));
    assert.throws(() => deleteRef(ssm, 'branch', 'main'), RefError);
});

test('renameRef moves the file and updates current_branch', () => {
    const ssm = makeSsm();
    renameRef(ssm, 'branch', 'main', 'trunk');
    assert.equal(fs.existsSync(path.join(ssm, 'branches', 'trunk')), true);
    assert.equal(fs.existsSync(path.join(ssm, 'branches', 'main')), false);
    const cfg = JSON.parse(fs.readFileSync(path.join(ssm, 'config'), 'utf8'));
    assert.equal(cfg.current_branch, 'trunk');
});

test('renameRef rejects invalid names and duplicates', () => {
    const ssm = makeSsm();
    assert.throws(() => renameRef(ssm, 'branch', 'feature', 'bad name'), RefError);
    assert.throws(() => renameRef(ssm, 'branch', 'feature', 'main'), RefError);
});

test('deleteRef does not clobber an existing .bak (uses a unique name)', () => {
    const ssm = makeSsm();
    // first delete of 'feature' -> feature.bak
    deleteRef(ssm, 'branch', 'feature');
    assert.equal(fs.existsSync(path.join(ssm, 'branches', 'feature.bak')), true);
    // re-create 'feature' and delete again -> must NOT overwrite feature.bak
    fs.writeFileSync(path.join(ssm, 'branches', 'feature'), 'ccc');
    deleteRef(ssm, 'branch', 'feature');
    assert.equal(fs.existsSync(path.join(ssm, 'branches', 'feature.bak')), true);
    assert.equal(fs.existsSync(path.join(ssm, 'branches', 'feature.bak.1')), true);
});

test('isValidRefName accepts normal names and rejects traversal/invalid names', () => {
    for (const name of ['main', 'v1.0.0', 'feature-1', 'exp_2', 'feature', 'experiment']) {
        assert.equal(isValidRefName(name), true, `expected '${name}' to be valid`);
    }
    for (const name of ['..', '.', '...', 'a/b', 'a\\b', '../evil', '', '-leading', 'bad name']) {
        assert.equal(isValidRefName(name), false, `expected '${name}' to be invalid`);
    }
});

test('deleteRef rejects path-traversal and invalid names (RefError)', () => {
    const ssm = makeSsm();
    assert.throws(() => deleteRef(ssm, 'branch', '..'), RefError);
    assert.throws(() => deleteRef(ssm, 'branch', '.'), RefError);
    assert.throws(() => deleteRef(ssm, 'branch', 'a/b'), RefError);
    assert.throws(() => deleteRef(ssm, 'branch', '../feature'), RefError);
    // Files outside branches/ must remain untouched.
    assert.equal(fs.existsSync(path.join(path.dirname(ssm), 'feature')), false);
});

test('renameRef rejects path-traversal and invalid names in either argument (RefError)', () => {
    const ssm = makeSsm();
    assert.throws(() => renameRef(ssm, 'branch', '..', 'trunk'), RefError);
    assert.throws(() => renameRef(ssm, 'branch', 'feature', '..'), RefError);
    assert.throws(() => renameRef(ssm, 'branch', 'feature', '.'), RefError);
    assert.throws(() => renameRef(ssm, 'branch', 'feature', 'a/b'), RefError);
    assert.throws(() => renameRef(ssm, 'branch', 'feature', '../evil'), RefError);
    // 'feature' must not have been touched by any of the rejected attempts.
    assert.equal(fs.existsSync(path.join(ssm, 'branches', 'feature')), true);
});

test('deleteRef and renameRef still work for valid names after validation was added', () => {
    const ssm = makeSsm();
    renameRef(ssm, 'tag', 'v1', 'v1.0.0');
    assert.equal(fs.existsSync(path.join(ssm, 'tags', 'v1.0.0')), true);
    deleteRef(ssm, 'tag', 'v1.0.0');
    assert.equal(fs.existsSync(path.join(ssm, 'tags', 'v1.0.0.bak')), true);
});

// ---------------------------------------------------------------------------
// 参照名の大文字小文字（issue #62）
//
// macOS（APFS の既定）と Windows のファイルシステムは大文字小文字を区別しない。
// 存在確認を fs.existsSync() に任せると、'feature' しか無いのに 'FEATURE' が
// 「存在する」と判定され、安全ガードを迂回して実体を壊せてしまう。
// 大文字小文字を区別するFS（Linux）でも同じ結果になるように検証する。
// ---------------------------------------------------------------------------

test('deleteRef rejects a name that differs only in case', () => {
    const ssm = makeSsm();
    assert.throws(() => deleteRef(ssm, 'branch', 'FEATURE'), RefError);
    // 実体が壊れていないこと
    assert.equal(fs.existsSync(path.join(ssm, 'branches', 'feature')), true);
});

test('deleteRef cannot bypass the current-branch guard with a different case', () => {
    // 修正前は current_branch === name の文字列比較を素通りし、
    // 現在のブランチ 'main' の実体が 'MAIN.bak' に退避されていた
    const ssm = makeSsm();
    assert.throws(() => deleteRef(ssm, 'branch', 'MAIN'), RefError);
    assert.equal(fs.existsSync(path.join(ssm, 'branches', 'main')), true);
    assert.equal(fs.existsSync(path.join(ssm, 'branches', 'MAIN.bak')), false);
});

test('deleteRef rejects a tag name that differs only in case', () => {
    const ssm = makeSsm();
    assert.throws(() => deleteRef(ssm, 'tag', 'V1'), RefError);
    assert.equal(fs.existsSync(path.join(ssm, 'tags', 'v1')), true);
});

test('renameRef rejects a source name that differs only in case', () => {
    const ssm = makeSsm();
    assert.throws(() => renameRef(ssm, 'branch', 'FEATURE', 'renamed'), RefError);
    assert.equal(fs.existsSync(path.join(ssm, 'branches', 'feature')), true);
});

test('renameRef rejects a destination that differs only in case from an existing ref', () => {
    const ssm = makeSsm();
    assert.throws(() => renameRef(ssm, 'branch', 'feature', 'Main'), RefError);
    assert.equal(fs.existsSync(path.join(ssm, 'branches', 'feature')), true);
});

test('renameRef still allows changing the case of the ref itself', () => {
    const ssm = makeSsm();
    renameRef(ssm, 'branch', 'feature', 'Feature');
    assert.equal(fs.readFileSync(path.join(ssm, 'branches', 'Feature'), 'utf8'), 'bbb');
});

test('renameRef keeps current_branch in sync', () => {
    const ssm = makeSsm();
    renameRef(ssm, 'branch', 'main', 'trunk');
    const cfg = JSON.parse(fs.readFileSync(path.join(ssm, 'config'), 'utf8'));
    assert.equal(cfg.current_branch, 'trunk');
});

// ---------------------------------------------------------------------------
// Windows のファイル名規則（Python 側 validate_ref_name() と揃える）
// ---------------------------------------------------------------------------

test('isValidRefName rejects Windows reserved device names', () => {
    for (const name of ['NUL', 'nul', 'CON', 'prn', 'AUX', 'COM1', 'LPT9', 'NUL.txt']) {
        assert.equal(isValidRefName(name), false, `${name} should be rejected`);
    }
});

test('isValidRefName rejects names ending with a dot', () => {
    for (const name of ['v2.', 'release.']) {
        assert.equal(isValidRefName(name), false, `${name} should be rejected`);
    }
});

test('isValidRefName still accepts ordinary names', () => {
    for (const name of ['feature', 'v1.0.0', 'exp_2', 'a.b-c']) {
        assert.equal(isValidRefName(name), true, `${name} should be accepted`);
    }
});
