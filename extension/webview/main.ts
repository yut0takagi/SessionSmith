import type { HostToWebview } from '../src/messages';
import type { GraphData } from '../src/ssmReader';
import { Store } from './state';
import { renderGraph } from './render';
import { renderDetail } from './detail';
import { setupZoomPan, setupSplitter, setupKeyboard } from './interaction';

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

window.addEventListener('message', (event: MessageEvent<HostToWebview>) => {
    const msg = event.data;
    if (msg.type === 'graph') {
        graph = msg.data;
        draw();
    } else if (msg.type === 'error') {
        graph = null;
        while (svg.firstChild) svg.removeChild(svg.firstChild);
        detailPane.innerHTML = '<div class="placeholder"></div>';
        setStatus(msg.message, true);
    }
});

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
