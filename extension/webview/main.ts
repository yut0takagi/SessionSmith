import type { HostToWebview } from '../src/messages';
import type { GraphData } from '../src/ssmReader';
import { Store } from './state';
import { renderGraph } from './render';
import { renderDetail } from './detail';

interface VsCodeApi {
    postMessage(msg: unknown): void;
    getState(): any;
    setState(s: any): void;
}
declare function acquireVsCodeApi(): VsCodeApi;

const vscode = acquireVsCodeApi();
const store = new Store(vscode);

const svg = document.getElementById('graph') as unknown as SVGSVGElement;
const detailPane = document.getElementById('detail-pane') as HTMLElement;
const statusEl = document.getElementById('status') as HTMLElement;
const currentBranchEl = document.getElementById('current-branch') as HTMLElement;

let graph: GraphData | null = null;

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
    renderGraph(svg, graph, st.query, st.selectedHash, selectCommit);
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

vscode.postMessage({ type: 'ready' });
