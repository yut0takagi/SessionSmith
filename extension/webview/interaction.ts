import { Store } from './state';

/** SVG の viewBox を使ったズーム/パンを結線する。 */
export function setupZoomPan(
    graphPane: HTMLElement,
    svg: SVGSVGElement,
    store: Store,
    getSize: () => { width: number; height: number }
): { apply(): void; fit(): void; reset(): void } {
    function apply(): void {
        const { zoom } = store.get();
        const { width, height } = getSize();
        const w = Math.max(width, 1);
        const h = Math.max(height, 1);
        // viewBox は常にコンテンツ全体。物理サイズを zoom 倍し、はみ出しは #graph-pane のスクロールで見せる。
        svg.setAttribute('viewBox', `0 0 ${w} ${h}`);
        svg.setAttribute('preserveAspectRatio', 'xMinYMin meet');
        svg.setAttribute('width', String(w * zoom));
        svg.setAttribute('height', String(h * zoom));
    }
    function fit(): void {
        const { width, height } = getSize();
        const zx = graphPane.clientWidth / Math.max(width, 1);
        const zy = graphPane.clientHeight / Math.max(height, 1);
        // 全体が収まる倍率。1 を超えて拡大はしない（小さいグラフは等倍表示）。
        store.set({ zoom: Math.max(0.1, Math.min(1, Math.min(zx, zy))) });
        apply();
        graphPane.scrollTo({ top: 0, left: 0 });
    }
    function reset(): void {
        store.set({ zoom: 1 });
        apply();
        graphPane.scrollTo({ top: 0, left: 0 });
    }

    graphPane.addEventListener('wheel', (e) => {
        if (!e.ctrlKey && !e.metaKey) return;
        e.preventDefault();
        const st = store.get();
        const factor = e.deltaY < 0 ? 1.1 : 1 / 1.1;
        store.set({ zoom: Math.min(4, Math.max(0.2, st.zoom * factor)) });
        apply();
    }, { passive: false });

    // ドラッグでパン（ネイティブスクロールを動かす）。プレーンなクリックは移動が無いので選択に影響しない。
    let dragging = false;
    let lastX = 0;
    let lastY = 0;
    graphPane.addEventListener('mousedown', (e) => {
        if (e.button !== 0) return;
        dragging = true;
        lastX = e.clientX;
        lastY = e.clientY;
        graphPane.classList.add('panning');
    });
    window.addEventListener('mouseup', () => {
        dragging = false;
        graphPane.classList.remove('panning');
    });
    window.addEventListener('mousemove', (e) => {
        if (!dragging) return;
        graphPane.scrollLeft -= e.clientX - lastX;
        graphPane.scrollTop -= e.clientY - lastY;
        lastX = e.clientX;
        lastY = e.clientY;
    });

    return { apply, fit, reset };
}

/** グラフ/詳細ペイン間のリサイズスプリッターを結線する。 */
export function setupSplitter(splitter: HTMLElement, detailPane: HTMLElement, store: Store): void {
    detailPane.style.width = store.get().paneWidth + 'px';
    let dragging = false;
    splitter.addEventListener('mousedown', (e) => {
        dragging = true;
        e.preventDefault();
    });
    window.addEventListener('mouseup', () => (dragging = false));
    window.addEventListener('mousemove', (e) => {
        if (!dragging) return;
        const w = Math.min(640, Math.max(240, window.innerWidth - e.clientX));
        detailPane.style.width = w + 'px';
        store.set({ paneWidth: w });
    });
}

/** キーボードナビゲーション。 */
export function setupKeyboard(handlers: {
    focusSearch(): void;
    clearSearch(): void;
    move(delta: number): void;
    checkout(): void;
    branch(): void;
    tag(): void;
    resetZoom(): void;
}): void {
    window.addEventListener('keydown', (e) => {
        const target = e.target as HTMLElement;
        const typing = target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA');
        if (e.key === '/' && !typing) {
            e.preventDefault();
            handlers.focusSearch();
        } else if (e.key === 'Escape') {
            handlers.clearSearch();
        } else if (!typing && e.key === 'ArrowDown') {
            e.preventDefault();
            handlers.move(1);
        } else if (!typing && e.key === 'ArrowUp') {
            e.preventDefault();
            handlers.move(-1);
        } else if (!typing && (e.key === 'c' || e.key === 'C')) {
            handlers.checkout();
        } else if (!typing && (e.key === 'b' || e.key === 'B')) {
            handlers.branch();
        } else if (!typing && (e.key === 't' || e.key === 'T')) {
            handlers.tag();
        } else if (!typing && e.key === '0') {
            handlers.resetZoom();
        }
    });
}
