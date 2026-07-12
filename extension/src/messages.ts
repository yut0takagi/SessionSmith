import type { GraphData } from './ssmReader';

/** extension → webview */
export type HostToWebview =
    | { type: 'graph'; data: GraphData }
    | { type: 'error'; message: string }
    | { type: 'loading'; value: boolean };

/** webview → extension */
export type WebviewToHost =
    | { type: 'ready' }
    | { type: 'refresh' }
    | { type: 'commit' }
    | { type: 'checkout'; hash: string }
    | { type: 'createBranch'; hash: string }
    | { type: 'createTag'; hash: string }
    | { type: 'merge'; branch?: string }
    | { type: 'deleteRef'; kind: 'branch' | 'tag'; name: string }
    | { type: 'renameRef'; kind: 'branch' | 'tag'; name: string }
    | { type: 'copyHash'; hash: string };
