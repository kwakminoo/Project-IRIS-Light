import { inject, injectable } from '@theia/core/shared/inversify';
import { BackendApplicationContribution } from '@theia/core/lib/node';
import { IrisIdeBridgeServer } from './iris-ide-bridge-server';

@injectable()
export class IrisIdeBackendContribution implements BackendApplicationContribution {
    @inject(IrisIdeBridgeServer) protected readonly bridge: IrisIdeBridgeServer;

    configure(): void {
        // ponytail: bridge는 별도 HTTP 포트 — onStart에서 기동
    }

    async onStart(): Promise<void> {
        await this.bridge.start();
    }

    async onStop(): Promise<void> {
        await this.bridge.stop();
    }
}
