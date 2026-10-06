import { inject, injectable } from '@theia/core/shared/inversify';

import { CommonMenus, FrontendApplicationContribution, OpenerService, open, ApplicationShell } from '@theia/core/lib/browser';
import { SHELL_TABBAR_CONTEXT_MENU } from '@theia/core/lib/browser/shell/tab-bars';
import { ThemeService } from '@theia/core/lib/browser/theming';
import { Command, CommandContribution, CommandRegistry, MenuContribution, MenuModelRegistry, SelectionService, UriSelection } from '@theia/core/lib/common';
import URI from '@theia/core/lib/common/uri';
import { FileUri } from '@theia/core/lib/common/file-uri';
import { VSXCommands } from '@theia/vsx-registry/lib/browser/vsx-extensions-contribution';
import { FileDialogService } from '@theia/filesystem/lib/browser';
import { FileService } from '@theia/filesystem/lib/browser/file-service';
import { FileStat } from '@theia/filesystem/lib/common/files';
import { WorkspaceOpenHandlerContribution, WorkspaceService } from '@theia/workspace/lib/browser';

import { EditorManager } from '@theia/editor/lib/browser';
import { ProblemManager } from '@theia/markers/lib/browser/problem/problem-manager';

import { NAVIGATOR_CONTEXT_MENU } from '@theia/navigator/lib/browser/navigator-contribution';

import { IrisIdeEditorStateService } from './iris-ide-editor-state';
import { resolveBridgeIdentity, resolveControlIdentity } from './iris-ide-bridge-identity';

import { IRIS_IDE_PRODUCT_NAME, IrisIdeEditorInfo } from '../common/iris-ide-protocol';
import { readProblems } from './iris-ide-bridge-ops';

export namespace IrisIdeMarketplaceCommands {
    export const OPEN: Command = {
        id: 'iris.ide.openMarketplace',
        label: 'Extensions Marketplace',
    };
}

export namespace IrisIdeWorkspaceCommands {
    export const OPEN_FOLDER: Command = {
        id: 'iris.ide.openFolder',
        label: 'Open Folder…',
    };
    export const OPEN_FILE: Command = {
        id: 'iris.ide.openFile',
        label: 'Open File…',
    };
    export const ATTACH_TO_CHAT: Command = {
        id: 'iris.ide.attachToChat',
        label: 'Attach to IRIS Chat',
    };
}

function asUriList(result: URI | URI[] | undefined): URI[] {
    if (!result) {
        return [];
    }
    return Array.isArray(result) ? result : [result];
}

@injectable()
export class IrisIdeFrontendContribution implements FrontendApplicationContribution, CommandContribution, MenuContribution, WorkspaceOpenHandlerContribution {

    @inject(EditorManager) protected readonly editorManager: EditorManager;

    @inject(ProblemManager) protected readonly problemManager: ProblemManager;

    @inject(IrisIdeEditorStateService) protected readonly state: IrisIdeEditorStateService;

    @inject(ThemeService) protected readonly themeService: ThemeService;

    @inject(WorkspaceService) protected readonly workspaceService: WorkspaceService;

    @inject(FileDialogService) protected readonly fileDialogService: FileDialogService;

    @inject(FileService) protected readonly fileService: FileService;

    @inject(OpenerService) protected readonly openerService: OpenerService;

    @inject(SelectionService) protected readonly selectionService: SelectionService;

    protected bridgePort = 0;

    protected bridgeToken = '';

    protected controlPort = 0;

    protected controlToken = '';

    protected lastPush = '';

    protected lastDiagnosticsPush = '';

    protected lastWorkspacePush = '';

    /** 탭 합성 드래그 — Lumino가 pointerdown에서 preventDefault 해서 HTML5 dragstart가 안 뜬다. */
    protected tabDrag: {
        uri: URI;
        x: number;
        y: number;
        armed: boolean;
        tab: HTMLElement;
    } | null = null;

    /** companion DnD — drag_start fetch가 drag_end보다 늦을 수 있어 프런트에도 경로를 보관. */
    protected companionDragPaths: string[] = [];

    /** 탭 HTML5 드래그 고스트(+ 칩) — setDragImage용. */
    protected tabDragGhost: HTMLDivElement | null = null;

    onStart(): void {
        document.title = IRIS_IDE_PRODUCT_NAME;
        this.ensureDarkTheme();
        const lockTitle = (): void => { document.title = IRIS_IDE_PRODUCT_NAME; };
        window.setInterval(lockTitle, 900);
        this.resolveBridge();
        this.resolveControl();
        this.editorManager.onCurrentEditorChanged(() => this.syncEditor());
        window.setInterval(() => this.syncEditor(), 450);
        this.syncEditor();
        this.workspaceService.onWorkspaceLocationChanged(stat => this.pushWorkspace(stat));
        this.pushWorkspace(this.workspaceService.workspace);
        this.installComposerDragBridge();
    }

    /** Theia Open… 폴더 선택 → window.open 대신 Iris가 Theia를 워크스페이스 재기동. */
    async canHandle(uri: URI): Promise<boolean> {
        try {
            const stat = await this.fileService.resolve(uri);
            return !!stat.isDirectory;
        } catch {
            return false;
        }
    }

    async openWorkspace(uri: URI): Promise<void> {
        const fsPath = FileUri.fsPath(uri);
        if (!fsPath) {
            return;
        }
        const current = (new URLSearchParams(window.location.search).get('iris_ws') || '').trim();
        if (current && this.sameFsPath(current, fsPath)) {
            return;
        }
        await this.askIris('ide.open_folder', { path: fsPath, new_window: false });
    }

    protected sameFsPath(a: string, b: string): boolean {
        const na = a.replace(/\\/g, '/').replace(/\/+$/, '').toLowerCase();
        const nb = b.replace(/\\/g, '/').replace(/\/+$/, '').toLowerCase();
        return na === nb;
    }

    protected async askIris(action: string, args: Record<string, unknown> = {}): Promise<boolean> {
        this.resolveControl();
        if (!this.controlPort || !this.controlToken) {
            return false;
        }
        try {
            const res = await fetch(`http://127.0.0.1:${this.controlPort}/v1/invoke`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    Authorization: `Bearer ${this.controlToken}`,
                },
                body: JSON.stringify({ action, args }),
            });
            const data = await res.json() as { ok?: boolean };
            return !!data.ok;
        } catch {
            return false;
        }
    }

    /**
     * QWebEngine → Qt 창 경계에서 OS OLE DnD MIME가 거의 전달되지 않는다.
     * 대신 Control Surface로 경로를 넘기고, dragend 때 Iris가 커서 위치로 첨부한다.
     *
     * Theia FileTreeWidget.handleDragStartEvent는 stopPropagation()을 호출하고,
     * Chromium은 dragstart 핸들러가 끝난 뒤 getData를 잠근다. 그래서 Theia가
     * setData('theia-editor-dnd' | 'selected-tree-nodes') 하는 순간을 가로채 경로를 얻는다.
     */
    protected installComposerDragBridge(): void {
        this.patchDataTransferForCompanionDrag();
        document.addEventListener('dragend', () => {
            this.teardownTabHtml5Drag();
            void this.finishCompanionDrag();
        }, true);
        // capture: Lumino TabBar preventDefault보다 먼저 — HTML5 copy 드래그 허용
        document.addEventListener('pointerdown', (ev: PointerEvent) => this.onTabPointerDown(ev), true);
        document.addEventListener('pointermove', (ev: PointerEvent) => this.onTabPointerMove(ev), true);
        document.addEventListener('dragstart', (ev: DragEvent) => this.onTabHtml5DragStart(ev), true);
        document.addEventListener('pointerup', (ev: PointerEvent) => this.onTabPointerUp(ev), true);
        document.addEventListener('pointercancel', () => { this.tabDrag = null; }, true);
    }

    protected patchDataTransferForCompanionDrag(): void {
        const proto = DataTransfer.prototype as DataTransfer & { __irisCompanionPatched?: boolean };
        if (proto.__irisCompanionPatched) {
            return;
        }
        const self = this;
        const original = proto.setData;
        proto.setData = function (this: DataTransfer, type: string, data: string): void {
            original.call(this, type, data);
            // Explorer writes workspace-prefixed tree IDs first. Only the final
            // editor MIME contains authoritative URIs for every dragged file.
            if (type === 'theia-editor-dnd') {
                self.onTheiaExplorerDragMime(this);
            }
        };
        proto.__irisCompanionPatched = true;
    }

    protected onTheiaExplorerDragMime(dt: DataTransfer): void {
        if (this.companionDragPaths.length) {
            return; // 같은 dragstart에서 setData가 여러 번 불림
        }
        const uris = this.urisFromDragDataTransfer(dt);
        if (!uris.length) {
            return;
        }
        try {
            const ref = this.toComposerRef(uris[0]);
            if (ref) {
                dt.setData('text/plain', ref);
                dt.setData('text/uri-list', uris.map(u => u.toString()).join('\n'));
                dt.setData('text/x-iris-ref', ref);
                dt.effectAllowed = 'copy';
            }
        } catch {
            /* ponytail: private mode / sandbox may block setData */
        }
        void this.beginCompanionDrag(uris);
    }

    /** Theia explorer MIME + UriSelection. DOM의 file: 속성은 탐색기에 없다. */
    protected urisFromDragDataTransfer(dt: DataTransfer): URI[] {
        try {
            return ApplicationShell.getDraggedEditorUris(dt).filter(uri => uri.scheme === 'file');
        } catch {
            return [];
        }
    }

    /**
     * Theia FileTree.toNodeId = uri.path.toString() (예: /C:/proj/a.py).
     * 루트만 uri.toString() (file:///...).
     */
    protected uriFromTreeNodeId(id: string | null | undefined): URI | undefined {
        const raw = (id || '').trim();
        if (!raw) {
            return undefined;
        }
        if (raw.startsWith('file:')) {
            try {
                return new URI(raw);
            } catch {
                return undefined;
            }
        }
        try {
            // /C:/Users/... → C:/Users/...
            const fs = raw.replace(/^\/([A-Za-z]:)/, '$1');
            return FileUri.create(fs);
        } catch {
            return undefined;
        }
    }

    protected async beginCompanionDrag(uris: URI[]): Promise<void> {
        const paths = uris.map(u => FileUri.fsPath(u)).filter(Boolean);
        if (!paths.length) {
            return;
        }
        this.companionDragPaths = paths;
        // await 금지 — Iris pending을 최대한 빨리 심어 Copy 커서 수락에 맞춤
        void this.askIris('chat.drag_start', { paths });
    }

    protected async finishCompanionDrag(): Promise<void> {
        const paths = this.companionDragPaths;
        this.companionDragPaths = [];
        // drag_start가 아직 도착하지 않았어도 paths를 실어 보내면 Iris가 첨부할 수 있다.
        await this.askIris('chat.drag_end', paths.length ? { paths } : {});
    }

    protected isEditorTabTarget(target: EventTarget | null): HTMLElement | null {
        const el = target as HTMLElement | null;
        if (!el || typeof el.closest !== 'function') {
            return null;
        }
        return el.closest(
            '.theia-tab, .lm-TabBar-tab, .p-TabBar-tab, [class*="TabBar-tab"], [class*="tabBar-tab"]',
        ) as HTMLElement | null;
    }

    protected onTabPointerDown(ev: PointerEvent): void {
        if (ev.button !== 0) {
            return;
        }
        const tab = this.isEditorTabTarget(ev.target);
        if (!tab) {
            this.tabDrag = null;
            return;
        }
        // Close buttons must remain ordinary Lumino close gestures.
        if ((ev.target as HTMLElement).closest('.lm-TabBar-tabCloseIcon, .p-TabBar-tabCloseIcon')) {
            this.tabDrag = null;
            return;
        }
        // Theia tab IDs identify widgets, not filesystem paths. Never fall back
        // to the previously focused editor while pointerdown is still capturing.
        const widget = this.editorManager.all.find(editor =>
            tab.id === `shell-tab-${editor.id}` || tab.id === `shell-tab-${editor.id}-hidden`);
        const uri = widget?.editor.uri;
        if (!uri) {
            this.tabDrag = null;
            return;
        }
        // 클릭은 Lumino에 넘긴다. 움직인 뒤에만 채팅 드래그다.
        this.tabDrag = { uri, x: ev.clientX, y: ev.clientY, armed: false, tab };
    }

    protected onTabPointerMove(ev: PointerEvent): void {
        const drag = this.tabDrag;
        if (!drag || drag.armed) {
            return;
        }
        const dx = ev.clientX - drag.x;
        const dy = ev.clientY - drag.y;
        if ((dx * dx) + (dy * dy) < 36) {
            return;
        }
        drag.armed = true;
        drag.tab.setAttribute('draggable', 'true');
        void this.beginCompanionDrag([drag.uri]);
    }

    protected onTabPointerUp(_ev: PointerEvent): void {
        const drag = this.tabDrag;
        this.tabDrag = null;
        if (!drag) {
            return;
        }
        if (drag.armed) {
            drag.tab.removeAttribute('draggable');
            void this.finishCompanionDrag();
            return;
        }
        // Lumino already selects and activates the clicked title on pointerdown.
        // Reopening here can steal focus and undo that selection with a stale URI.
    }

    protected onTabHtml5DragStart(ev: DragEvent): void {
        const drag = this.tabDrag;
        const tab = this.isEditorTabTarget(ev.target);
        if (!drag || !tab || tab !== drag.tab) {
            return;
        }
        drag.armed = true;
        const dt = ev.dataTransfer;
        if (!dt) {
            return;
        }
        try {
            const ref = this.toComposerRef(drag.uri);
            const href = drag.uri.toString();
            dt.effectAllowed = 'copyMove';
            dt.setData('text/plain', ref || href);
            dt.setData('text/uri-list', href);
            dt.setData('text/x-iris-ref', ref || href);
            // Chromium → OS OLE: 일부 환경에서 uri-list만으로 Copy 커서
            const ghost = this.ensureTabDragGhost(ref || href);
            dt.setDragImage(ghost, 12, 12);
        } catch {
            /* ignore */
        }
        void this.beginCompanionDrag([drag.uri]);
    }

    protected ensureTabDragGhost(label: string): HTMLDivElement {
        let ghost = this.tabDragGhost;
        if (!ghost) {
            ghost = document.createElement('div');
            ghost.style.cssText = [
                'position:fixed', 'top:-1000px', 'left:-1000px', 'z-index:99999',
                'display:flex', 'align-items:center', 'gap:6px',
                'padding:4px 10px', 'border-radius:6px',
                'background:#0f172a', 'color:#e2e8f0', 'border:1px solid #22d3ee',
                'font:12px/1.2 Segoe UI,sans-serif', 'pointer-events:none',
            ].join(';');
            document.body.appendChild(ghost);
            this.tabDragGhost = ghost;
        }
        const name = (label || '').replace(/^@/, '').split('/').pop() || label;
        ghost.innerHTML = `<span style="color:#22d3ee;font-weight:700">+</span><span>${this.escapeHtml(name)}</span>`;
        return ghost;
    }

    protected escapeHtml(s: string): string {
        return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    protected teardownTabHtml5Drag(): void {
        const tab = this.tabDrag?.tab;
        if (tab) {
            tab.removeAttribute('draggable');
        }
        this.tabDrag = null;
    }

    /** 탭·탐색기 우클릭 → 현재 선택/파일을 IRIS 컴포저 칩으로 첨부. */
    protected async attachToChat(): Promise<boolean> {
        const uri = UriSelection.getUri(this.selectionService.selection)
            || this.editorManager.currentEditor?.editor.uri;
        if (!uri) {
            return false;
        }
        return this.askIris('chat.attach', { path: FileUri.fsPath(uri) });
    }

    protected uriFromElement(el: HTMLElement): URI | undefined {
        const attrs = ['data-uri', 'data-node-id', 'data-id', 'id'];
        for (const key of attrs) {
            const raw = (el.getAttribute(key) || '').trim();
            if (!raw) {
                continue;
            }
            const uri = this.uriFromTreeNodeId(raw);
            if (uri) {
                return uri;
            }
        }
        return undefined;
    }

    protected toComposerRef(uri: URI): string {
        const fsPath = FileUri.fsPath(uri).replace(/\\/g, '/');
        const roots = this.workspaceService.tryGetRoots();
        const root = roots.length ? FileUri.fsPath(roots[0].resource).replace(/\\/g, '/') : '';
        if (root && fsPath.startsWith(`${root.replace(/\/$/, '')}/`)) {
            const rel = fsPath.slice(root.length).replace(/^\//, '');
            return `@${rel}`;
        }
        return `@${fsPath}`;
    }

    registerCommands(commands: CommandRegistry): void {
        commands.registerCommand(IrisIdeMarketplaceCommands.OPEN, {
            execute: () => commands.executeCommand(VSXCommands.TOGGLE_EXTENSIONS.id),
        });
        commands.registerCommand(IrisIdeWorkspaceCommands.OPEN_FOLDER, {
            execute: () => this.openFolderDialog(),
        });
        commands.registerCommand(IrisIdeWorkspaceCommands.OPEN_FILE, {
            execute: () => this.openFileDialog(),
        });
        commands.registerCommand(IrisIdeWorkspaceCommands.ATTACH_TO_CHAT, {
            execute: () => this.attachToChat(),
        });
    }

    registerMenus(menus: MenuModelRegistry): void {
        menus.registerMenuAction(CommonMenus.FILE_OPEN, {
            commandId: IrisIdeWorkspaceCommands.OPEN_FOLDER.id,
            label: IrisIdeWorkspaceCommands.OPEN_FOLDER.label,
            order: 'a000',
        });
        menus.registerMenuAction(CommonMenus.FILE_OPEN, {
            commandId: IrisIdeWorkspaceCommands.OPEN_FILE.id,
            label: IrisIdeWorkspaceCommands.OPEN_FILE.label,
            order: 'a001',
        });
        menus.registerMenuAction(CommonMenus.VIEW, {
            commandId: IrisIdeMarketplaceCommands.OPEN.id,
            label: IrisIdeMarketplaceCommands.OPEN.label,
            order: '6',
        });
        menus.registerMenuAction(SHELL_TABBAR_CONTEXT_MENU, {
            commandId: IrisIdeWorkspaceCommands.ATTACH_TO_CHAT.id,
            label: IrisIdeWorkspaceCommands.ATTACH_TO_CHAT.label,
            order: 'z_iris',
        });
        menus.registerMenuAction([...NAVIGATOR_CONTEXT_MENU, 'navigation'], {
            commandId: IrisIdeWorkspaceCommands.ATTACH_TO_CHAT.id,
            label: IrisIdeWorkspaceCommands.ATTACH_TO_CHAT.label,
            order: 'z_iris',
        });
    }

    protected async openFolderDialog(): Promise<void> {
        if (await this.askIris('ide.pick_open_folder', {})) {
            return;
        }
        const result = await this.fileDialogService.showOpenDialog({
            title: 'Open Folder',
            canSelectFiles: false,
            canSelectFolders: true,
            canSelectMany: false,
        });
        const uris = asUriList(result as URI | URI[] | undefined);
        if (!uris.length) {
            return;
        }
        await this.openWorkspace(uris[0]);
    }

    protected async openFileDialog(): Promise<void> {
        if (await this.askIris('ide.pick_open_file', {})) {
            return;
        }
        const result = await this.fileDialogService.showOpenDialog({
            title: 'Open File',
            canSelectFiles: true,
            canSelectFolders: false,
            canSelectMany: true,
        });
        const uris = asUriList(result as URI | URI[] | undefined);
        for (const uri of uris) {
            await open(this.openerService, uri, { mode: 'activate' });
        }
    }

    protected ensureDarkTheme(): void {
        try {
            window.localStorage.setItem('theme-id', 'dark');
        } catch {
            /* ponytail: private mode may block storage */
        }
        if (this.themeService.getCurrentTheme().type !== 'dark') {
            this.themeService.setCurrentTheme('dark');
        }
    }

    protected infoFromWidget(widget: { editor?: { uri: URI; document?: { languageId?: string }; cursor?: { line: number; character: number }; selection?: { start: { line: number; character: number }; end: { line: number; character: number } } | null } } | undefined): IrisIdeEditorInfo | null {
        const editor = widget?.editor;
        if (!editor?.uri) {
            return null;
        }
        const rel = editor.uri.path.toString();
        const sel = editor.selection;
        const pos = editor.cursor;
        return {
            uri: editor.uri.toString(),
            path: rel.replace(/^\/([A-Za-z]:)/, '$1').replace(/^\//, ''),
            languageId: editor.document?.languageId || 'plaintext',
            line: (pos?.line ?? 0) + 1,
            column: (pos?.character ?? 0) + 1,
            selection: sel
                ? {
                    start: { line: sel.start.line + 1, column: sel.start.character + 1 },
                    end: { line: sel.end.line + 1, column: sel.end.character + 1 },
                }
                : null,
        };
    }

    protected editorInfos(): IrisIdeEditorInfo[] {
        const bag = this.editorManager as unknown as { all?: Array<{ editor?: { uri: URI } }> };
        const widgets = Array.isArray(bag.all) ? bag.all : [];
        const infos: IrisIdeEditorInfo[] = [];
        for (const widget of widgets) {
            const info = this.infoFromWidget(widget);
            if (info) {
                infos.push(info);
            }
        }
        if (!infos.length) {
            const current = this.infoFromWidget(this.editorManager.currentEditor);
            if (current) {
                infos.push(current);
            }
        }
        return infos;
    }

    protected syncEditor(): void {
        const infos = this.editorInfos();
        const current = this.infoFromWidget(this.editorManager.currentEditor) || infos[0] || null;
        if (!current) {
            this.state.clear();
            this.pushBridge(null, []);
            this.pushDiagnostics();
            return;
        }
        this.state.update(current);
        this.pushBridge(current, infos.length ? infos : [current]);
        this.pushDiagnostics();
    }

    /** 미해결 상태면 매 tick 재시도 — sessionStorage 조회뿐이라 비용이 없다. */
    protected resolveBridge(): boolean {
        if (this.bridgePort && this.bridgeToken) {
            return true;
        }
        const identity = resolveBridgeIdentity();
        this.bridgePort = identity.port;
        this.bridgeToken = identity.token;
        return !!this.bridgePort;
    }

    protected resolveControl(): boolean {
        const identity = resolveControlIdentity();
        this.controlPort = identity.port;
        this.controlToken = identity.token;
        return !!this.controlPort && !!this.controlToken;
    }

    protected pushWorkspace(stat: FileStat | undefined): void {
        if (!this.bridgePort) {
            return;
        }
        const opened = Boolean(stat && stat.isDirectory);
        const root = stat
            ? stat.resource.path.toString().replace(/^\/([A-Za-z]:)/, '$1').replace(/^\//, '')
            : '';
        const payload = JSON.stringify({ root, opened });
        if (payload === this.lastWorkspacePush) {
            return;
        }
        this.lastWorkspacePush = payload;
        fetch(`http://127.0.0.1:${this.bridgePort}/setWorkspace`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                Authorization: `Bearer ${this.bridgeToken}`,
            },
            body: payload,
        }).catch(() => undefined);
    }

    protected pushDiagnostics(): void {
        if (!this.resolveBridge()) {
            return;
        }
        let items: Record<string, unknown>[];
        try {
            items = readProblems(this.problemManager);
        } catch {
            return;
        }
        const payload = JSON.stringify({ diagnostics: items });
        if (payload === this.lastDiagnosticsPush) {
            return;
        }
        this.lastDiagnosticsPush = payload;
        fetch(`http://127.0.0.1:${this.bridgePort}/setDiagnostics`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                Authorization: `Bearer ${this.bridgeToken}`,
            },
            body: payload,
        }).catch(() => undefined);
    }

    protected pushBridge(info: IrisIdeEditorInfo | null, editors: IrisIdeEditorInfo[] = []): void {
        if (!this.resolveBridge()) {
            return;
        }
        const payload = JSON.stringify({ ...(info || {}), editors });
        if (payload === this.lastPush) {
            return;
        }
        this.lastPush = payload;
        fetch(`http://127.0.0.1:${this.bridgePort}/setEditorState`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                Authorization: `Bearer ${this.bridgeToken}`,
            },
            body: payload,
        }).catch(() => undefined);
    }

}
