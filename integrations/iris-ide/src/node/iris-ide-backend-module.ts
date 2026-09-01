import { ContainerModule } from '@theia/core/shared/inversify';
import { BackendApplicationContribution } from '@theia/core/lib/node';
import { IrisIdeBackendContribution } from './iris-ide-backend-contribution';
import { IrisIdeBridgeServer } from './iris-ide-bridge-server';

export default new ContainerModule(bind => {
    bind(IrisIdeBridgeServer).toSelf().inSingletonScope();
    bind(IrisIdeBackendContribution).toSelf().inSingletonScope();
    bind(BackendApplicationContribution).toService(IrisIdeBackendContribution);
});
