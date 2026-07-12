import type { GraphData, CommitNode } from '../src/ssmReader';
import { layout } from './layout';
import { truncate, formatDate } from './format';
import { matchesQuery } from './search';

const SVG_NS = 'http://www.w3.org/2000/svg';
const ROW_H = 46;
const COL_W = 22;
const ORIGIN_X = 22;
const ORIGIN_Y = 30;
const NODE_R = 6;
const LANE_COLORS = [
    '#4daafc', '#73c991', '#e2c08d', '#cd72d6', '#f14c4c',
    '#46b1c9', '#d98c5f', '#9ccc65', '#ba68c8', '#ffb74d',
];

function el(name: string, attrs: Record<string, string | number>, text?: string): SVGElement {
    const node = document.createElementNS(SVG_NS, name) as SVGElement;
    for (const k in attrs) {
        node.setAttribute(k, String(attrs[k]));
    }
    if (text !== undefined) {
        node.textContent = text;
    }
    return node;
}
const laneColor = (col: number) => LANE_COLORS[col % LANE_COLORS.length];
const x = (col: number) => ORIGIN_X + col * COL_W;
const y = (row: number) => ORIGIN_Y + row * ROW_H;

export interface RenderResult {
    rowY: Map<string, number>;
    width: number;
    height: number;
}

export function renderGraph(
    svg: SVGSVGElement,
    graph: GraphData,
    query: string,
    selectedHash: string | null,
    onSelect: (hash: string) => void
): RenderResult {
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    const commits = graph.commits;
    const rowY = new Map<string, number>();
    if (!commits.length) {
        return { rowY, width: 0, height: 0 };
    }

    const { pos, maxCol } = layout(commits);
    const graphWidth = x(maxCol) + COL_W;
    const textX = graphWidth + 14;
    const totalHeight = y(commits.length) + 10;
    svg.setAttribute('height', String(totalHeight));

    const refs = new Map<string, { text: string; kind: string }[]>();
    const addRef = (hash: string, text: string, kind: string) => {
        if (!hash) return;
        if (!refs.has(hash)) refs.set(hash, []);
        refs.get(hash)!.push({ text, kind });
    };
    graph.branches.forEach((b) => addRef(b.head, b.name, 'branch'));
    graph.tags.forEach((t) => addRef(t.commit, t.name, 'tag'));
    if (graph.head) addRef(graph.head, 'HEAD', 'head');

    const dim = (c: CommitNode) => query.trim() !== '' && !matchesQuery(c, query);

    // 行背景
    commits.forEach((c, row) => {
        const bg = el('rect', {
            x: 0, y: y(row) - ROW_H / 2, width: '100%', height: ROW_H,
            class: 'commit-row-bg' + (c.hash === selectedHash ? ' selected' : '') + (dim(c) ? ' dim' : ''),
            'data-hash': c.hash,
        });
        svg.appendChild(bg);
    });

    // エッジ
    commits.forEach((c) => {
        const cp = pos.get(c.hash)!;
        (c.parents || []).forEach((ph) => {
            const pp = pos.get(ph);
            if (!pp) return;
            const x1 = x(cp.col), y1 = y(cp.row), x2 = x(pp.col), y2 = y(pp.row);
            const midY = (y1 + y2) / 2;
            const d = `M ${x1} ${y1} C ${x1} ${midY}, ${x2} ${midY}, ${x2} ${y2}`;
            svg.appendChild(el('path', { d, class: 'edge', stroke: laneColor(Math.max(cp.col, pp.col)) }));
        });
    });

    // ノード + テキスト
    commits.forEach((c, row) => {
        const p = pos.get(c.hash)!;
        const cx = x(p.col), cy = y(row);
        rowY.set(c.hash, cy);
        let cls = 'node';
        if (c.hash === graph.head) cls += ' head';
        if (c.isMerge) cls += ' merge';
        if (dim(c)) cls += ' dim';
        svg.appendChild(el('circle', { cx, cy, r: NODE_R, class: cls, fill: laneColor(p.col) }));

        // ref バッジは先に構築して幅（labelX）を確定するが、appendChild は hit rect の後（最前面）に行う
        let labelX = textX;
        const badgeNodes: SVGGElement[] = [];
        (refs.get(c.hash) || []).forEach((r) => {
            const w = r.text.length * 6.5 + 14;
            const g = el('g', {}) as SVGGElement;
            g.appendChild(el('rect', {
                x: labelX, y: cy - 9, width: w, height: 16, rx: 8,
                class: r.kind === 'tag' ? 'ref-bg-tag' : r.kind === 'head' ? 'ref-bg-head' : 'ref-bg-branch',
                'data-ref-kind': r.kind, 'data-ref-name': r.text,
            }));
            const prefix = r.kind === 'tag' ? '🏷 ' : r.kind === 'head' ? '' : '⎇ ';
            g.appendChild(el('text', { x: labelX + 7, y: cy + 3, class: 'ref-label ref-text' }, prefix + r.text));
            badgeNodes.push(g);
            labelX += w + 6;
        });

        const msgCls = 'commit-msg' + (dim(c) ? ' dim' : '');
        svg.appendChild(el('text', { x: labelX, y: cy - 2, class: msgCls }, truncate(c.message || '(no message)', 60)));
        const meta = `${c.hash.slice(0, 7)} · ${c.author} · ${formatDate(c.timestamp)} · ${c.varCount} vars${c.signed ? ' · 🔒' : ''}`;
        svg.appendChild(el('text', { x: labelX, y: cy + 11, class: 'commit-meta' + (dim(c) ? ' dim' : '') }, meta));

        // 行全体の透明ヒット領域（選択用）。バッジより下に置き、バッジが自前のイベントを受けられるようにする。
        const hit = el('rect', { x: 0, y: cy - ROW_H / 2, width: '100%', height: ROW_H, fill: 'transparent', style: 'cursor:pointer' });
        hit.addEventListener('click', () => onSelect(c.hash));
        svg.appendChild(hit);

        // バッジは最後に append して hit rect より前面へ（右クリックメニューを機能させる）。左クリックでも選択できるようにする。
        badgeNodes.forEach((g) => {
            const rect = g.firstChild as SVGRectElement | null;
            if (rect) rect.addEventListener('click', () => onSelect(c.hash));
            svg.appendChild(g);
        });
    });

    // 実際のコンテンツ幅（テキスト・refバッジ含む）を測って width に反映する。
    // getBBox はレイアウト前などに失敗し得るので graphWidth をフォールバックにする。
    let contentWidth = graphWidth;
    try {
        const bb = svg.getBBox();
        contentWidth = Math.max(graphWidth, Math.ceil(bb.x + bb.width + 12));
    } catch {
        /* getBBox 不可時は graphWidth を使う */
    }
    svg.setAttribute('width', String(contentWidth));

    return { rowY, width: contentWidth, height: totalHeight };
}
