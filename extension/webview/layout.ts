import type { CommitNode } from '../src/ssmReader';

export interface LayoutResult {
    pos: Map<string, { col: number; row: number }>;
    maxCol: number;
}

/** gitgraph 風のレーン割り当て。commits は新しい順（topoSort 済み）を前提とする。 */
export function layout(commits: CommitNode[]): LayoutResult {
    const pos = new Map<string, { col: number; row: number }>();
    const lanes: (string | null)[] = [];

    function firstFree(): number {
        for (let i = 0; i < lanes.length; i++) {
            if (lanes[i] === null || lanes[i] === undefined) {
                return i;
            }
        }
        lanes.push(null);
        return lanes.length - 1;
    }

    for (let row = 0; row < commits.length; row++) {
        const c = commits[row];
        let col = lanes.indexOf(c.hash);
        if (col === -1) {
            col = firstFree();
        }
        for (let i = 0; i < lanes.length; i++) {
            if (lanes[i] === c.hash && i !== col) {
                lanes[i] = null;
            }
        }
        pos.set(c.hash, { col, row });

        const parents = c.parents || [];
        if (parents.length === 0) {
            lanes[col] = null;
        } else {
            lanes[col] = parents[0];
            for (let p = 1; p < parents.length; p++) {
                if (lanes.indexOf(parents[p]) === -1) {
                    const nc = firstFree();
                    lanes[nc] = parents[p];
                }
            }
        }
    }

    let maxCol = 0;
    pos.forEach((p) => {
        if (p.col > maxCol) {
            maxCol = p.col;
        }
    });
    return { pos, maxCol };
}
