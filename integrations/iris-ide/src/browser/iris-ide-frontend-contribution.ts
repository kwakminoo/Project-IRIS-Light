import { inject, injectable } from '@theia/core/shared/inversify';

import { CommonMenus, FrontendApplicationContribution, OpenerService, open } from '@theia/core/lib/browser';
import { ThemeService } from '@theia/core/lib/browser/theming';
import { Command, CommandContribution, CommandRegistry, MenuContribution, MenuModelRegistry } from '@theia/core/lib/common';
import URI from '@theia/core/lib/common/uri';
import { FileUri } from '@theia/core/lib/common/file-uri';
import { VSXCommands } from '@theia/vsx-registry/lib/browser/vsx-extensions-contribution';
import { FileDialogService } from '@theia/filesystem/lib/browser';
import { FileService } from '@theia/filesystem/lib/browser/file-service';
import { WorkspaceOpenHandlerContribution, WorkspaceService } from '@theia/workspace/lib/browser';

import { EditorManager } from '@theia/editor/lib/browser';

import { IrisIdeEditorStateService } from './iris-ide-editor-state';

import { IRIS_IDE_PRODUCT_NAME, IrisIdeEditorInfo } from '../common/iris-ide-protocol';

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

    @inject(IrisIdeEditorStateService) protected readonly state: IrisIdeEditorStateService;

    @inject(ThemeService) protected readonly themeService: ThemeService;

    @inject(WorkspaceService) protected readonly workspaceService: WorkspaceService;

    @inject(FileDialogService) protected readonly fileDialogService: FileDialogService;

    @inject(FileService) protected readonly fileService: FileService;

    @inject(OpenerService) protected readonly openerService: OpenerService;

    protected bridgePort = 0;

    protected bridgeToken = '';

    protected controlPort = 0;

    protected controlToken = '';

    protected lastPush = '';

    onStart(): void {
        document.title = IRIS_IDE_PRODUCT_NAME;
        this.ensureDarkTheme();
        const lockTitle = (): void => { document.title = IRIS_IDE_PRODUCT_NAME; };
        window.setInterval(lockTitle, 900);
        const params = new URLSearchParams(window.location.search);
        this.bridgePort = parseInt(params.get('iris_bridge_port') || '0', 10) || 0;
        this.bridgeToken = params.get('iris_bridge_token') || '';
        this.controlPort = parseInt(params.get('iris_control_port') || '0', 10) || 0;
        this.controlToken = params.get('iris_control_token') || '';
        this.editorManager.onCurrentEditorChanged(() => this.syncEditor());
        window.setInterval(() => this.syncEditor(), 450);
        this.syncEditor();
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

    /** 탭·익스플로러 → IRIS 채팅 입력창 드롭용 OS mime. */
    protected installComposerDragBridge(): void {
        document.addEventListener('dragstart', (ev: DragEvent) => this.onComposerDragStart(ev), true);
    }

    protected onComposerDragStart(ev: DragEvent): void {
        const uri = this.uriFromDragEvent(ev);
        if (!uri || !ev.dataTransfer) {
            return;
        }
        const ref = this.toComposerRef(uri);
        if (!ref) {
            return;
        }
        try {
            ev.dataTransfer.setData('text/plain', ref);
            ev.dataTransfer.setData('text/uri-list', uri.toString());
            ev.dataTransfer.setData('text/x-iris-ref', ref);
            ev.dataTransfer.effectAllowed = 'copy';
        } catch {
            /* ponytail: private mode / sandbox may block setData */
        }
    }

    protected uriFromDragEvent(ev: DragEvent): URI | undefined {
        const target = ev.target as HTMLElement | null;
        if (!target) {
            return undefined;
        }
        let el: HTMLElement | null = target;
        while (el) {
            const fromEl = this.uriFromElement(el);
            if (fromEl) {
                return fromEl;
            }
            el = el.parentElement;
        }
        const tab = target.closest(
            '.theia-tab, .lm-TabBar-tab, .p-TabBar-tab, [class*="TabBar-tab"], [class*="tabBar-tab"]'
        ) as HTMLElement | null;
        if (tab) {
            const fromTab = this.uriFromElement(tab);
            if (fromTab) {
                return fromTab;
            }
        }
        if (target.closest('.lm-TabBar, .p-TabBar, .theia-tabBar, [class*="TabBar"]')) {
            const editor = this.editorManager.currentEditor;
            if (editor) {
                return editor.editor.uri;
            }
        }
        return undefined;
    }

    protected uriFromElement(el: HTMLElement): URI | undefined {
        const attrs = ['data-uri', 'data-id', 'id'];
        for (const key of attrs) {
            const raw = (el.getAttribute(key) || '').trim();
            if (raw.startsWith('file:')) {
                try {
                    return new URI(raw);
                } catch {
                    return undefined;
                }
            }
        }
        return undefined;
    }

    protected toComposerRef(uri: URI): string {
        const fsPath = FileUri.fsPath(uri).replace(/\\/g, '/');
        const roots = this.workspaceService.tryGetRoots();
        const root = roots.length ? FileUri.fsPath(roots[0].resource).replace(/\\/g, '/') : '';
        if (root && fsPath.startsWith(root)) {
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

    protected syncEditor(): void {
        const editor = this.editorManager.currentEditor;
        if (!editor) {
            this.state.clear();
            this.pushBridge(null);
            return;
        }
        const uri = editor.editor.uri.toString();
        const rel = editor.editor.uri.path.toString();
        const sel = editor.editor.selection;
        const pos = editor.editor.cursor;
        const info: IrisIdeEditorInfo = {
            uri,
            path: rel.replace(/^\/([A-Za-z]:)/, '$1').replace(/^\//, ''),
            languageId: editor.editor.document.languageId || 'plaintext',
            line: pos.line + 1,
            column: pos.character + 1,
            selection: sel
                ? {
                    start: { line: sel.start.line + 1, column: sel.start.character + 1 },
                    end: { line: sel.end.line + 1, column: sel.end.character + 1 },
                }
                : null,
        };
        this.state.update(info);
        this.pushBridge(info);
    }

    protected pushBridge(info: IrisIdeEditorInfo | null): void {
        if (!this.bridgePort) {
            return;
        }
        const payload = JSON.stringify(info || {});
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
