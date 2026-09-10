import { inject, injectable } from '@theia/core/shared/inversify';

import { ApplicationShell, CommonMenus, FrontendApplicationContribution } from '@theia/core/lib/browser';
import { Command, CommandContribution, CommandRegistry, MenuContribution, MenuModelRegistry } from '@theia/core/lib/common';
import { WidgetManager } from '@theia/core/lib/browser/widget-manager';
import { WorkspaceService } from '@theia/workspace/lib/browser/workspace-service';

import { IrisIdeStartWidget, IRIS_IDE_START_WIDGET_ID } from './iris-ide-start-widget';

export namespace IrisIdeStartCommands {
    export const SHOW: Command = {
        id: 'iris.ide.showStartScreen',
        label: 'IRIS IDE: 시작 화면 열기',
    };
}

/**
 * 워크스페이스가 열려 있지 않은 "새 창" 상태에서 시작 화면(IrisIdeStartWidget)을
 * 메인 영역에 띄운다 — Cursor의 New Window 화면과 동등한 역할.
 */
@injectable()
export class IrisIdeStartContribution implements FrontendApplicationContribution, CommandContribution, MenuContribution {

    @inject(WidgetManager) protected readonly widgetManager: WidgetManager;

    @inject(WorkspaceService) protected readonly workspaceService: WorkspaceService;

    @inject(ApplicationShell) protected readonly shell: ApplicationShell;

    async onDidInitializeLayout(): Promise<void> {
        if (this.workspaceService.opened) {
            return;
        }
        await this.showStartWidget();
    }

    protected async showStartWidget(): Promise<void> {
        const widget = await this.widgetManager.getOrCreateWidget<IrisIdeStartWidget>(IRIS_IDE_START_WIDGET_ID);
        if (!widget.isAttached) {
            await this.shell.addWidget(widget, { area: 'main' });
        }
        await this.shell.activateWidget(widget.id);
    }

    registerCommands(commands: CommandRegistry): void {
        commands.registerCommand(IrisIdeStartCommands.SHOW, {
            execute: () => this.showStartWidget(),
        });
    }

    registerMenus(menus: MenuModelRegistry): void {
        menus.registerMenuAction(CommonMenus.VIEW, {
            commandId: IrisIdeStartCommands.SHOW.id,
            label: IrisIdeStartCommands.SHOW.label,
            order: '7',
        });
    }
}
