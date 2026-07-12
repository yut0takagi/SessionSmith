import { test } from 'node:test';
import assert from 'node:assert';
import { layout } from '../webview/layout';
import type { CommitNode } from '../src/ssmReader';

function commit(hash: string, parents: string[]): CommitNode {
    return {
        hash, message: hash, author: 'a', timestamp: '', parents,
        isMerge: parents.length > 1, variables: {}, varCount: 0, totalSize: 0, signed: false,
    };
}

test('layout: linear history uses a single column', () => {
    const commits = [commit('c', ['b']), commit('b', ['a']), commit('a', [])];
    const { pos, maxCol } = layout(commits);
    assert.equal(maxCol, 0);
    assert.equal(pos.get('c')!.col, 0);
    assert.equal(pos.get('a')!.row, 2);
});

test('layout: a branch adds a lane', () => {
    // c(merge of b,d) -> b -> a ; d -> a
    const commits = [
        commit('c', ['b', 'd']),
        commit('b', ['a']),
        commit('d', ['a']),
        commit('a', []),
    ];
    const { pos, maxCol } = layout(commits);
    assert.ok(maxCol >= 1, 'merge should occupy more than one lane');
    assert.ok(pos.has('d'));
});
