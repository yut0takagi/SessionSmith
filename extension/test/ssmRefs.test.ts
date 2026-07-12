import { test } from 'node:test';
import assert from 'node:assert';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import { deleteRef, renameRef, RefError } from '../src/ssmRefs';

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
