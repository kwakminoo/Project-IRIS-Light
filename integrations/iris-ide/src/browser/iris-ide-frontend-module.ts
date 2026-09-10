// esbuild bundles from the compiled lib/ output, not src/ — this path resolves
// correctly both here (tsc checks relative to src/browser/) and post-compile
// (lib/browser/ sits at the same depth, so ../../src/browser/... still lands
// on the real file).
import '../../src/browser/style/iris-ide-start.css';

import { ContainerModule } from '@theia/core/shared/inversify';
import { FrontendApplicationContribution, WidgetFactory } from '@theia/core/lib/browser';
import { CommandContribution, MenuContribution } from '@theia/core/lib/common';
import { IrisIdeFrontendContribution } from './iris-ide-frontend-contribution';
import { IrisIdeEditorStateService } from './iris-ide-editor-state';
import { IrisIdeStartContribution } from './iris-ide-start-contribution';
import { IrisIdeStartWidget, IRIS_IDE_START_WIDGET_ID } from './iris-ide-start-widget';

export default new ContainerModule(bind => {
    bind(IrisIdeEditorStateService).toSelf().inSingletonScope();
    bind(IrisIdeFrontendContribution).toSelf().inSingletonScope();
    bind(FrontendApplicationContribution).toService(IrisIdeFrontendContribution);
    bind(CommandContribution).toService(IrisIdeFrontendContribution);
    bind(MenuContribution).toService(IrisIdeFrontendContribution);

    bind(IrisIdeStartWidget).toSelf();
    bind(WidgetFactory).toDynamicValue(({ container }) => ({
        id: IRIS_IDE_START_WIDGET_ID,
        createWidget: () => container.get(IrisIdeStartWidget),
    })).inSingletonScope();

    bind(IrisIdeStartContribution).toSelf().inSingletonScope();
    bind(FrontendApplicationContribution).toService(IrisIdeStartContribution);
    bind(CommandContribution).toService(IrisIdeStartContribution);
    bind(MenuContribution).toService(IrisIdeStartContribution);
});
