import { test } from 'node:test';
import assert from 'node:assert';
import { matchesQuery } from '../webview/search';
import type { CommitNode } from '../src/ssmReader';

function commit(over: Partial<CommitNode>): CommitNode {
    return {
        hash: 'abcdef0', message: '', author: 'alice', timestamp: '',
        parents: [], isMerge: false, variables: {}, varCount: 0, totalSize: 0, signed: false,
        ...over,
    };
}

test('empty query matches everything', () => {
    assert.equal(matchesQuery(commit({}), ''), true);
    assert.equal(matchesQuery(commit({}), '   '), true);
});

test('matches message, hash, author case-insensitively', () => {
    const c = commit({ message: 'Fix Training loop', hash: 'deadbee' });
    assert.equal(matchesQuery(c, 'training'), true);
    assert.equal(matchesQuery(c, 'DEADBEE'), true);
    assert.equal(matchesQuery(c, 'alice'), true);
    assert.equal(matchesQuery(c, 'nope'), false);
});

test('matches variable names', () => {
    const c = commit({ variables: { model_weights: { hash: 'h', type: 'ndarray', size: 1 } } });
    assert.equal(matchesQuery(c, 'model_'), true);
    assert.equal(matchesQuery(c, 'ndarray'), true);
});
