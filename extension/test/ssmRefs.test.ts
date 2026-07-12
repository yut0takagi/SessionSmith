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
