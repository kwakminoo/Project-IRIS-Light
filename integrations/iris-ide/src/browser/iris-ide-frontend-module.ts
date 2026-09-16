import { ContainerModule } from '@theia/core/shared/inversify';
import { FrontendApplicationContribution } from '@theia/core/lib/browser';
import { CommandContribution, MenuContribution } from '@theia/core/lib/common';
import { WorkspaceOpenHandlerContribution } from '@theia/workspace/lib/browser';
import { IrisIdeFrontendContribution } from './iris-ide-frontend-contribution';
import { IrisIdeEditorStateService } from './iris-ide-editor-state';
import { IrisIdeBridgePoller } from './iris-ide-bridge-poller';

export default new ContainerModule(bind => {
    bind(IrisIdeEditorStateService).toSelf().inSingletonScope();
    bind(IrisIdeBridgePoller).toSelf().inSingletonScope();
    bind(IrisIdeFrontendContribution).toSelf().inSingletonScope();
    bind(FrontendApplicationContribution).toService(IrisIdeFrontendContribution);
    bind(FrontendApplicationContribution).toService(IrisIdeBridgePoller);
    bind(CommandContribution).toService(IrisIdeFrontendContribution);
    bind(MenuContribution).toService(IrisIdeFrontendContribution);
    bind(WorkspaceOpenHandlerContribution).toService(IrisIdeFrontendContribution);
});
