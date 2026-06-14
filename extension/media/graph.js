// @ts-nocheck
(function () {
    const vscode = acquireVsCodeApi();

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

    let currentGraph = null;
    let selectedHash = null;

    const svg = document.getElementById('graph');
    const detailPane = document.getElementById('detail-pane');
    const statusEl = document.getElementById('status');
    const currentBranchEl = document.getElementById('current-branch');

    document.getElementById('btn-refresh').addEventListener('click', () => {
        vscode.postMessage({ type: 'refresh' });
    });
    document.getElementById('btn-commit').addEventListener('click', () => {
        vscode.postMessage({ type: 'commit' });
    });

    window.addEventListener('message', (event) => {
        const msg = event.data;
        if (msg.type === 'graph') {
            currentGraph = msg.data;
            render(msg.data);
            setStatus(
                `${msg.data.commits.length} commits · ${msg.data.branches.length} branches · ${msg.data.tags.length} tags`,
                false
            );
        } else if (msg.type === 'error') {
            currentGraph = null;
            clearSvg();
            detailPane.innerHTML = '<div class="placeholder"></div>';
            setStatus(msg.message, true);
        }
    });

    function setStatus(text, isError) {
        statusEl.textContent = text;
        statusEl.classList.toggle('error', !!isError);
    }

    function clearSvg() {
        while (svg.firstChild) {
            svg.removeChild(svg.firstChild);
        }
    }

    function el(name, attrs, text) {
        const node = document.createElementNS(SVG_NS, name);
        for (const k in attrs) {
            node.setAttribute(k, attrs[k]);
        }
        if (text !== undefined) {
            node.textContent = text;
        }
        return node;
    }

    function laneColor(col) {
        return LANE_COLORS[col % LANE_COLORS.length];
    }

    // --- レーン割り当て（gitgraph 風レイアウト） ---
    function layout(commits) {
        const pos = new Map(); // hash -> {col, row}
        const lanes = []; // lanes[i] = 次に期待するコミットhash or null

        function firstFree() {
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
            // 同じコミットを期待していた他のレーンは、このコミットに合流するので解放
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
                    // 既にその親を期待しているレーンが無ければ新規確保
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

    function x(col) {
        return ORIGIN_X + col * COL_W;
    }
    function y(row) {
        return ORIGIN_Y + row * ROW_H;
    }

    function render(graph) {
        clearSvg();
        const commits = graph.commits;
        if (!commits.length) {
            setStatus('コミットがまだありません。', false);
            detailPane.innerHTML = '<div class="placeholder">コミットがありません</div>';
            return;
        }

        currentBranchEl.textContent = graph.currentBranch ? '⎇ ' + graph.currentBranch : '';

        const { pos, maxCol } = layout(commits);
        const graphWidth = x(maxCol) + COL_W;
        const textX = graphWidth + 14;
        const totalHeight = y(commits.length) + 10;

        svg.setAttribute('height', totalHeight);
        svg.setAttribute('width', '100%');

        // ref ラベルのマップ（hash -> [{text, kind}]）
        const refs = new Map();
        function addRef(hash, text, kind) {
            if (!hash) return;
            if (!refs.has(hash)) refs.set(hash, []);
            refs.get(hash).push({ text, kind });
        }
        graph.branches.forEach((b) => addRef(b.head, b.name, 'branch'));
        graph.tags.forEach((t) => addRef(t.commit, t.name, 'tag'));
        if (graph.head) addRef(graph.head, 'HEAD', 'head');

        // 行の背景（クリック領域）
        commits.forEach((c, row) => {
            const bg = el('rect', {
                x: 0,
                y: y(row) - ROW_H / 2,
                width: '100%',
                height: ROW_H,
                class: 'commit-row-bg' + (c.hash === selectedHash ? ' selected' : ''),
                'data-hash': c.hash,
            });
            bg.addEventListener('click', () => selectCommit(c.hash));
            svg.appendChild(bg);
        });

        // エッジ（親へ）
        commits.forEach((c) => {
            const cp = pos.get(c.hash);
            (c.parents || []).forEach((ph) => {
                const pp = pos.get(ph);
                if (!pp) return;
                const x1 = x(cp.col);
                const y1 = y(cp.row);
                const x2 = x(pp.col);
                const y2 = y(pp.row);
                const midY = (y1 + y2) / 2;
                const d = `M ${x1} ${y1} C ${x1} ${midY}, ${x2} ${midY}, ${x2} ${y2}`;
                svg.appendChild(
                    el('path', { d, class: 'edge', stroke: laneColor(Math.max(cp.col, pp.col)) })
                );
            });
        });

        // ノード + テキスト
        commits.forEach((c, row) => {
            const p = pos.get(c.hash);
            const cx = x(p.col);
            const cy = y(row);
            const isHead = c.hash === graph.head;

            let cls = 'node';
            if (isHead) cls += ' head';
            if (c.isMerge) cls += ' merge';
            svg.appendChild(
                el('circle', { cx, cy, r: NODE_R, class: cls, fill: laneColor(p.col) })
            );

            // ref ラベル
            let labelX = textX;
            const rlist = refs.get(c.hash) || [];
            rlist.forEach((r) => {
                const w = r.text.length * 6.5 + 14;
                const g = el('g', {});
                g.appendChild(
                    el('rect', {
                        x: labelX,
                        y: cy - 9,
                        width: w,
                        height: 16,
                        rx: 8,
                        class:
                            r.kind === 'tag'
                                ? 'ref-bg-tag'
                                : r.kind === 'head'
                                ? 'ref-bg-head'
                                : 'ref-bg-branch',
                    })
                );
                const prefix = r.kind === 'tag' ? '🏷 ' : r.kind === 'head' ? '' : '⎇ ';
                g.appendChild(
                    el(
                        'text',
                        { x: labelX + 7, y: cy + 3, class: 'ref-label ref-text' },
                        prefix + r.text
                    )
                );
                svg.appendChild(g);
                labelX += w + 6;
            });

            // メッセージ
            const msg = el(
                'text',
                { x: labelX, y: cy - 2, class: 'commit-msg' },
                truncate(c.message || '(no message)', 60)
            );
            svg.appendChild(msg);

            // メタ
            const meta = `${c.hash.slice(0, 7)} · ${c.author} · ${formatDate(c.timestamp)} · ${c.varCount} vars${
                c.signed ? ' · 🔒' : ''
            }`;
            svg.appendChild(el('text', { x: labelX, y: cy + 11, class: 'commit-meta' }, meta));

            // クリック領域（テキスト側も）
            const hit = el('rect', {
                x: 0,
                y: cy - ROW_H / 2,
                width: '100%',
                height: ROW_H,
                fill: 'transparent',
                style: 'cursor:pointer',
            });
            hit.addEventListener('click', () => selectCommit(c.hash));
            svg.appendChild(hit);
        });

        if (selectedHash && pos.has(selectedHash)) {
            showDetail(commits.find((c) => c.hash === selectedHash));
        }
    }

    function selectCommit(hash) {
        selectedHash = hash;
        document.querySelectorAll('.commit-row-bg').forEach((n) => {
            n.classList.toggle('selected', n.getAttribute('data-hash') === hash);
        });
        const c = currentGraph.commits.find((x) => x.hash === hash);
        if (c) showDetail(c);
    }

    function showDetail(c) {
        if (!c) return;
        const vars = c.variables || {};
        const varRows = Object.keys(vars)
            .map((name) => {
                const info = vars[name] || {};
                return `<div class="var-item"><span>${escapeHtml(name)}</span><span class="vtype">${escapeHtml(
                    info.type || '?'
                )} · ${formatBytes(info.size || 0)}</span></div>`;
            })
            .join('');

        const parentsHtml =
            (c.parents || [])
                .map((p) => `<code>${p.slice(0, 7)}</code>`)
                .join(', ') || '—';

        detailPane.innerHTML = `
            <div class="detail-title">${escapeHtml(c.message || '(no message)')}</div>
            <div class="detail-hash">${c.hash}</div>
            <div class="detail-actions">
                <button data-act="checkout">⟲ Checkout</button>
                <button class="secondary" data-act="branch">⎇ Branch here</button>
                <button class="secondary" data-act="tag">🏷 Tag here</button>
                <button class="secondary" data-act="copy">⧉ Copy hash</button>
            </div>
            <div class="detail-row"><span class="k">Author</span><span class="v">${escapeHtml(
                c.author
            )}</span></div>
            <div class="detail-row"><span class="k">Date</span><span class="v">${escapeHtml(
                c.timestamp
            )}</span></div>
            <div class="detail-row"><span class="k">Parents</span><span class="v">${parentsHtml}</span></div>
            <div class="detail-row"><span class="k">Type</span><span class="v">${
                c.isMerge ? 'merge commit' : 'commit'
            }</span></div>
            <div class="detail-row"><span class="k">Signed</span><span class="v ${
                c.signed ? 'sig-yes' : 'sig-no'
            }">${c.signed ? '🔒 yes (HMAC)' : 'no'}</span></div>
            <div class="detail-row"><span class="k">Variables</span><span class="v">${
                c.varCount
            } (${formatBytes(c.totalSize)})</span></div>
            ${
                c.caller && c.caller.filename && c.caller.filename !== '<unknown>'
                    ? `<div class="detail-row"><span class="k">File</span><span class="v">${escapeHtml(
                          c.caller.filename
                      )}</span></div>`
                    : ''
            }
            <div class="var-list">
                <h4>Variables (${c.varCount})</h4>
                ${varRows || '<div class="placeholder">変数なし</div>'}
            </div>
        `;

        detailPane.querySelectorAll('button[data-act]').forEach((btn) => {
            btn.addEventListener('click', () => {
                const act = btn.getAttribute('data-act');
                if (act === 'checkout') vscode.postMessage({ type: 'checkout', hash: c.hash });
                else if (act === 'branch') vscode.postMessage({ type: 'createBranch', hash: c.hash });
                else if (act === 'tag') vscode.postMessage({ type: 'createTag', hash: c.hash });
                else if (act === 'copy') vscode.postMessage({ type: 'copyHash', hash: c.hash });
            });
        });
    }

    // --- ユーティリティ ---
    function truncate(s, n) {
        return s.length > n ? s.slice(0, n - 1) + '…' : s;
    }
    function formatDate(iso) {
        if (!iso) return '';
        const d = new Date(iso);
        if (isNaN(d.getTime())) return iso;
        const pad = (x) => String(x).padStart(2, '0');
        return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(
            d.getHours()
        )}:${pad(d.getMinutes())}`;
    }
    function formatBytes(n) {
        if (n < 1024) return n + ' B';
        if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' KB';
        return (n / (1024 * 1024)).toFixed(1) + ' MB';
    }
    function escapeHtml(s) {
        return String(s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    // 初期化完了を通知
    vscode.postMessage({ type: 'ready' });
})();
