import { test } from 'node:test';
import assert from 'node:assert';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import { readGraph } from '../src/ssmReader';

function makeSsm(): string {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), 'ssm-'));
    const ssm = path.join(root, '.ssm');
    fs.mkdirSync(path.join(ssm, 'commits'), { recursive: true });
    fs.mkdirSync(path.join(ssm, 'branches'), { recursive: true });
    fs.mkdirSync(path.join(ssm, 'tags'), { recursive: true });

    const c1 = {
        message: 'first', author: 'a', timestamp: '2026-01-01T00:00:00',
        variables: { x: { hash: 'h', type: 'int', size: 28 } },
    };
    const c2 = {
        message: 'second', author: 'a', timestamp: '2026-01-02T00:00:00',
        parent: 'aaa', signature: 'sig',
        variables: { y: { hash: 'h2', type: 'list', size: 64 } },
    };
    fs.writeFileSync(path.join(ssm, 'commits', 'aaa.json'), JSON.stringify(c1));
    fs.writeFileSync(path.join(ssm, 'commits', 'bbb.json'), JSON.stringify(c2));
    fs.writeFileSync(path.join(ssm, 'branches', 'main'), 'bbb');
    fs.writeFileSync(path.join(ssm, 'tags', 'v1'), 'aaa');
    fs.writeFileSync(path.join(ssm, 'HEAD'), 'bbb');
    return ssm;
}

test('readGraph parses commits, branches, tags, HEAD', () => {
    const ssm = makeSsm();
    const g = readGraph(ssm);
    assert.equal(g.commits.length, 2);
    assert.equal(g.branches.length, 1);
    assert.equal(g.branches[0].name, 'main');
    assert.equal(g.tags[0].name, 'v1');
    assert.equal(g.head, 'bbb');
});

test('readGraph orders commits newest-first (topoSort)', () => {
    const ssm = makeSsm();
    const g = readGraph(ssm);
    assert.equal(g.commits[0].hash, 'bbb');
    assert.equal(g.commits[1].hash, 'aaa');
});

test('readGraph detects signed commits and parents', () => {
    const ssm = makeSsm();
    const g = readGraph(ssm);
    const bbb = g.commits.find((c) => c.hash === 'bbb')!;
    assert.equal(bbb.signed, true);
    assert.deepEqual(bbb.parents, ['aaa']);
    const aaa = g.commits.find((c) => c.hash === 'aaa')!;
    assert.equal(aaa.signed, false);
});
