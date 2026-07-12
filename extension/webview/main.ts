import type { HostToWebview } from '../src/messages';
import type { GraphData } from '../src/ssmReader';
import { Store } from './state';
import { renderGraph } from './render';
import { renderDetail } from './detail';
import { setupZoomPan, setupSplitter, setupKeyboard } from './interaction';
import { escapeHtml } from './format';

interface VsCodeApi {
    postMessage(msg: unknown): void;
    getState(): any;
    setState(s: any): void;
}
declare function acquireVsCodeApi(): VsCodeApi;

const vscode = acquireVsCodeApi();
const store = new Store(vscode);
let zoomPan: ReturnType<typeof setupZoomPan>;

const svg = document.getElementById('graph') as unknown as SVGSVGElement;
const detailPane = document.getElementById('detail-pane') as HTMLElement;
const statusEl = document.getElementById('status') as HTMLElement;
const currentBranchEl = document.getElementById('current-branch') as HTMLElement;
const emptyState = document.getElementById('empty-state') as HTMLElement;

let graph: GraphData | null = null;
let lastSize = { width: 0, height: 0 };
let lastRowY = new Map<string, number>();

function setStatus(text: string, isError: boolean): void {
    statusEl.textContent = text;
    statusEl.classList.toggle('error', isError);
}

function selectCommit(hash: string): void {
    store.set({ selectedHash: hash });
    draw();
}

function draw(): void {
    if (!graph) return;
    const st = store.get();
    currentBranchEl.textContent = graph.currentBranch ? '⎇ ' + graph.currentBranch : '';
    const res = renderGraph(svg, graph, st.query, st.selectedHash, selectCommit);
    lastSize = { width: res.width, height: res.height };
    lastRowY = res.rowY;
    zoomPan.apply();
    svg.querySelectorAll<SVGRectElement>('[data-ref-kind]').forEach((rect) => {
        const kind = rect.getAttribute('data-ref-kind');
        const name = rect.getAttribute('data-ref-name');
        if (kind === 'head' || !name || (kind !== 'branch' && kind !== 'tag')) return;
        rect.style.cursor = 'context-menu';
        rect.addEventListener('contextmenu', (e) => {
            e.preventDefault();
            showRefMenu(e.clientX, e.clientY, kind, name);
        });
    });
    const sel = graph.commits.find((c) => c.hash === st.selectedHash);
    renderDetail(detailPane, sel, graph, {
        checkout: (h) => vscode.postMessage({ type: 'checkout', hash: h }),
        branch: (h) => vscode.postMessage({ type: 'createBranch', hash: h }),
        tag: (h) => vscode.postMessage({ type: 'createTag', hash: h }),
        merge: () => vscode.postMessage({ type: 'merge' }),
        copy: (h) => vscode.postMessage({ type: 'copyHash', hash: h }),
    });
    setStatus(
        `${graph.commits.length} commits · ${graph.branches.length} branches · ${graph.tags.length} tags`,
        false
    );
}

function showRefMenu(cx: number, cy: number, kind: 'branch' | 'tag', name: string): void {
    document.getElementById('ref-menu')?.remove();
    const menu = document.createElement('div');
    menu.id = 'ref-menu';
    menu.className = 'context-menu';
    menu.style.left = cx + 'px';
    menu.style.top = cy + 'px';
    menu.innerHTML = `<div class="ctx-title">${kind}: ${name}</div>
        <button data-a="rename">✎ リネーム</button>
        <button data-a="delete">🗑 削除</button>`;
    document.body.appendChild(menu);
    const close = () => menu.remove();
    menu.querySelector('[data-a="rename"]')?.addEventListener('click', () => {
        vscode.postMessage({ type: 'renameRef', kind, name });
        close();
    });
    menu.querySelector('[data-a="delete"]')?.addEventListener('click', () => {
        vscode.postMessage({ type: 'deleteRef', kind, name });
        close();
    });
    setTimeout(() => window.addEventListener('click', close, { once: true }), 0);
}

window.addEventListener('message', (event: MessageEvent<HostToWebview>) => {
    const msg = event.data;
    if (msg.type === 'graph') {
        emptyState.classList.add('hidden');
        graph = msg.data;
        draw();
    } else if (msg.type === 'error') {
        graph = null;
        while (svg.firstChild) svg.removeChild(svg.firstChild);
        detailPane.innerHTML = '<div class="placeholder">コミットを選択してください</div>';
        setStatus('', false);
        renderEmptyState(msg.message);
    }
});

function renderEmptyState(kind: string): void {
    let html = '';
    if (kind === 'no-workspace') {
        html = `<div class="empty"><h3>ワークスペースが開かれていません</h3>
            <p>フォルダを開いてから Session Graph を表示してください。</p></div>`;
    } else if (kind === 'no-ssm') {
        html = `<div class="empty"><h3>.ssm がまだありません</h3>
            <p>Python 側で SSM を初期化してください:</p>
            <pre><code>from SessionSmith import ssm
ssm.init()
ssm.commit("first snapshot")</code></pre>
            <button id="copy-init">⧉ コードをコピー</button></div>`;
    } else {
        html = `<div class="empty"><h3>${escapeHtml(kind)}</h3></div>`;
    }
    emptyState.innerHTML = html;
    emptyState.classList.remove('hidden');
    document.getElementById('copy-init')?.addEventListener('click', () => {
        navigator.clipboard?.writeText('from SessionSmith import ssm\nssm.init()\nssm.commit("first snapshot")');
    });
}

document.getElementById('btn-refresh')?.addEventListener('click', () => vscode.postMessage({ type: 'refresh' }));
document.getElementById('btn-commit')?.addEventListener('click', () => vscode.postMessage({ type: 'commit' }));

const searchInput = document.getElementById('search') as HTMLInputElement | null;
searchInput?.addEventListener('input', () => {
    store.set({ query: searchInput.value });
    draw();
});

const graphPane = document.getElementById('graph-pane') as HTMLElement;
const splitter = document.getElementById('splitter') as HTMLElement;
zoomPan = setupZoomPan(graphPane, svg, store, () => lastSize);
setupSplitter(splitter, detailPane, store);

function moveSelection(delta: number): void {
    if (!graph || !graph.commits.length) return;
    const idx = graph.commits.findIndex((c) => c.hash === store.get().selectedHash);
    const next = Math.min(graph.commits.length - 1, Math.max(0, (idx < 0 ? 0 : idx) + delta));
    selectCommit(graph.commits[next].hash);
    const yy = lastRowY.get(graph.commits[next].hash);
    if (yy !== undefined) graphPane.scrollTo({ top: yy - graphPane.clientHeight / 2, behavior: 'smooth' });
}
setupKeyboard({
    focusSearch: () => searchInput?.focus(),
    clearSearch: () => { if (searchInput) { searchInput.value = ''; store.set({ query: '' }); draw(); } },
    move: moveSelection,
    checkout: () => { const h = store.get().selectedHash; if (h) vscode.postMessage({ type: 'checkout', hash: h }); },
    branch: () => { const h = store.get().selectedHash; if (h) vscode.postMessage({ type: 'createBranch', hash: h }); },
    tag: () => { const h = store.get().selectedHash; if (h) vscode.postMessage({ type: 'createTag', hash: h }); },
    resetZoom: () => zoomPan.reset(),
});
document.getElementById('btn-fit')?.addEventListener('click', () => zoomPan.fit());
document.getElementById('btn-reset')?.addEventListener('click', () => zoomPan.reset());

vscode.postMessage({ type: 'ready' });
