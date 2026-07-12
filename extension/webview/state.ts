export interface ViewState {
    selectedHash: string | null;
    query: string;
    zoom: number;
    panX: number;
    panY: number;
    paneWidth: number;
    detailCollapsed: boolean;
}

const DEFAULT: ViewState = {
    selectedHash: null,
    query: '',
    zoom: 1,
    panX: 0,
    panY: 0,
    paneWidth: 340,
    detailCollapsed: false,
};

interface VsCodeApi {
    postMessage(msg: unknown): void;
    getState(): Partial<ViewState> | undefined;
    setState(s: ViewState): void;
}

export class Store {
    private state: ViewState;
    constructor(private readonly api: VsCodeApi) {
        this.state = { ...DEFAULT, ...(api.getState() ?? {}) };
    }
    get(): ViewState {
        return this.state;
    }
    set(patch: Partial<ViewState>): void {
        this.state = { ...this.state, ...patch };
        this.api.setState(this.state);
    }
    post(msg: unknown): void {
        this.api.postMessage(msg);
    }
}
