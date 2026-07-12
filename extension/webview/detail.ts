import type { CommitNode, GraphData } from '../src/ssmReader';
import { escapeHtml, formatBytes } from './format';

export interface DetailActions {
    checkout(hash: string): void;
    branch(hash: string): void;
    tag(hash: string): void;
    merge(): void;
    copy(hash: string): void;
}

export function renderDetail(
    pane: HTMLElement,
    c: CommitNode | undefined,
    _graph: GraphData,
    actions: DetailActions
): void {
    if (!c) {
        pane.innerHTML = '<div class="placeholder">コミットを選択してください</div>';
        return;
    }
    const vars = c.variables || {};
    const varRows = Object.keys(vars)
        .map((name) => {
            const info = vars[name] || ({} as { type?: string; size?: number });
            return `<div class="var-item"><span>${escapeHtml(name)}</span><span class="vtype">${escapeHtml(
                info.type || '?'
            )} · ${formatBytes(info.size || 0)}</span></div>`;
        })
        .join('');
    const parentsHtml =
        (c.parents || []).map((p) => `<code>${escapeHtml(p.slice(0, 7))}</code>`).join(', ') || '—';

    pane.innerHTML = `
        <div class="detail-title">${escapeHtml(c.message || '(no message)')}</div>
        <div class="detail-hash">${escapeHtml(c.hash)}</div>
        <div class="detail-actions">
            <button data-act="checkout">⟲ Checkout</button>
            <button class="secondary" data-act="branch">⎇ Branch</button>
            <button class="secondary" data-act="tag">🏷 Tag</button>
            <button class="secondary" data-act="merge">⑃ Merge…</button>
            <button class="secondary" data-act="copy">⧉ Copy</button>
        </div>
        <div class="detail-row"><span class="k">Author</span><span class="v">${escapeHtml(c.author)}</span></div>
        <div class="detail-row"><span class="k">Parents</span><span class="v">${parentsHtml}</span></div>
        <div class="detail-row"><span class="k">Signed</span><span class="v ${
            c.signed ? 'sig-yes' : 'sig-no'
        }">${c.signed ? '🔒 yes (HMAC)' : 'no'}</span></div>
        <div class="var-list"><h4>Variables (${c.varCount})</h4>${
            varRows || '<div class="placeholder">変数なし</div>'
        }</div>
    `;
    pane.querySelectorAll<HTMLButtonElement>('button[data-act]').forEach((btn) => {
        btn.addEventListener('click', () => {
            const act = btn.getAttribute('data-act');
            if (act === 'checkout') actions.checkout(c.hash);
            else if (act === 'branch') actions.branch(c.hash);
            else if (act === 'tag') actions.tag(c.hash);
            else if (act === 'merge') actions.merge();
            else if (act === 'copy') actions.copy(c.hash);
        });
    });
}
