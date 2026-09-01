import { ContainerModule } from '@theia/core/shared/inversify';
import { FrontendApplicationContribution } from '@theia/core/lib/browser';
import { CommandContribution, MenuContribution } from '@theia/core/lib/common';
import { IrisIdeFrontendContribution } from './iris-ide-frontend-contribution';
import { IrisIdeEditorStateService } from './iris-ide-editor-state';

export default new ContainerModule(bind => {
    bind(IrisIdeEditorStateService).toSelf().inSingletonScope();
    bind(IrisIdeFrontendContribution).toSelf().inSingletonScope();
    bind(FrontendApplicationContribution).toService(IrisIdeFrontendContribution);
    bind(CommandContribution).toService(IrisIdeFrontendContribution);
    bind(MenuContribution).toService(IrisIdeFrontendContribution);
});
