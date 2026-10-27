// esbuild는 lib/ 를 묶는다. 이 상대경로는 src/browser 와 lib/browser 양쪽에서
// integrations/iris-ide/src/browser/style/iris-ide-start.css 로 닿는다.
import '../../src/browser/style/iris-ide-start.css';
import '../../src/browser/style/iris-pdf.css';

import { ContainerModule } from '@theia/core/shared/inversify';
import {
    FrontendApplicationContribution,
    NavigatableWidgetOptions,
    OpenHandler,
    WidgetFactory,
} from '@theia/core/lib/browser';
import { TabBarToolbarContribution } from '@theia/core/lib/browser/shell/tab-bar-toolbar';
import { CommandContribution, MenuContribution } from '@theia/core/lib/common';
import { WorkspaceOpenHandlerContribution } from '@theia/workspace/lib/browser';
import { IrisIdeFrontendContribution } from './iris-ide-frontend-contribution';
import { IrisIdeEditorStateService } from './iris-ide-editor-state';
import { IrisIdeBridgePoller } from './iris-ide-bridge-poller';
import { IrisIdeStartContribution } from './iris-ide-start-contribution';
import { IrisIdeStartWidget, IRIS_IDE_START_WIDGET_ID } from './iris-ide-start-widget';
import { IrisIdeRunToolbar } from './iris-ide-run-toolbar';
import { IrisPdfOpenHandler } from './iris-pdf-open-handler';
import {
    IrisPdfWidget,
    IrisPdfWidgetOptions,
    IRIS_PDF_WIDGET_FACTORY_ID,
} from './iris-pdf-widget';

export default new ContainerModule(bind => {
    bind(IrisIdeEditorStateService).toSelf().inSingletonScope();
    bind(IrisIdeBridgePoller).toSelf().inSingletonScope();
    bind(IrisIdeFrontendContribution).toSelf().inSingletonScope();
    bind(FrontendApplicationContribution).toService(IrisIdeFrontendContribution);
    bind(FrontendApplicationContribution).toService(IrisIdeBridgePoller);
    bind(CommandContribution).toService(IrisIdeFrontendContribution);
    bind(MenuContribution).toService(IrisIdeFrontendContribution);
    bind(WorkspaceOpenHandlerContribution).toService(IrisIdeFrontendContribution);

    bind(IrisIdeStartWidget).toSelf();
    bind(WidgetFactory).toDynamicValue(({ container }) => ({
        id: IRIS_IDE_START_WIDGET_ID,
        createWidget: () => container.get(IrisIdeStartWidget),
    })).inSingletonScope();

    bind(IrisIdeStartContribution).toSelf().inSingletonScope();
    bind(FrontendApplicationContribution).toService(IrisIdeStartContribution);
    bind(CommandContribution).toService(IrisIdeStartContribution);
    bind(MenuContribution).toService(IrisIdeStartContribution);

    bind(IrisIdeRunToolbar).toSelf().inSingletonScope();
    bind(CommandContribution).toService(IrisIdeRunToolbar);
    bind(MenuContribution).toService(IrisIdeRunToolbar);
    bind(TabBarToolbarContribution).toService(IrisIdeRunToolbar);

    bind(IrisPdfOpenHandler).toSelf().inSingletonScope();
    bind(OpenHandler).toService(IrisPdfOpenHandler);
    bind(WidgetFactory).toDynamicValue(({ container }) => ({
        id: IRIS_PDF_WIDGET_FACTORY_ID,
        createWidget: (options: NavigatableWidgetOptions) => {
            const child = container.createChild();
            child.bind(IrisPdfWidgetOptions).toConstantValue(options);
            child.bind(IrisPdfWidget).toSelf();
            return child.get(IrisPdfWidget);
        },
    })).inSingletonScope();
});
