import { inject, injectable } from '@theia/core/shared/inversify';

import { CommonMenus, FrontendApplicationContribution } from '@theia/core/lib/browser';
import { ThemeService } from '@theia/core/lib/browser/theming';
import { Command, CommandContribution, CommandRegistry, MenuContribution, MenuModelRegistry } from '@theia/core/lib/common';
import { VSXCommands } from '@theia/vsx-registry/lib/browser/vsx-extensions-contribution';

import { EditorManager } from '@theia/editor/lib/browser';

import { IrisIdeEditorStateService } from './iris-ide-editor-state';

import { IRIS_IDE_PRODUCT_NAME, IrisIdeEditorInfo } from '../common/iris-ide-protocol';

export namespace IrisIdeMarketplaceCommands {
    export const OPEN: Command = {
        id: 'iris.ide.openMarketplace',
        label: 'Extensions Marketplace',
    };
}

@injectable()
export class IrisIdeFrontendContribution implements FrontendApplicationContribution, CommandContribution, MenuContribution {

    @inject(EditorManager) protected readonly editorManager: EditorManager;

    @inject(IrisIdeEditorStateService) protected readonly state: IrisIdeEditorStateService;

    @inject(ThemeService) protected readonly themeService: ThemeService;

    protected bridgePort = 0;

    protected bridgeToken = '';

    protected lastPush = '';

    onStart(): void {

        document.title = IRIS_IDE_PRODUCT_NAME;

        this.ensureDarkTheme();

        const lockTitle = (): void => { document.title = IRIS_IDE_PRODUCT_NAME; };

        window.setInterval(lockTitle, 900);

        const params = new URLSearchParams(window.location.search);

        this.bridgePort = parseInt(params.get('iris_bridge_port') || '0', 10) || 0;

        this.bridgeToken = params.get('iris_bridge_token') || '';

        this.editorManager.onCurrentEditorChanged(() => this.syncEditor());

        window.setInterval(() => this.syncEditor(), 450);

        this.syncEditor();

    }

    registerCommands(commands: CommandRegistry): void {

        commands.registerCommand(IrisIdeMarketplaceCommands.OPEN, {
            execute: () => commands.executeCommand(VSXCommands.TOGGLE_EXTENSIONS.id),
        });

    }

    registerMenus(menus: MenuModelRegistry): void {

        menus.registerMenuAction(CommonMenus.VIEW, {
            commandId: IrisIdeMarketplaceCommands.OPEN.id,
            label: IrisIdeMarketplaceCommands.OPEN.label,
            order: '6',
        });

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
