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
        // Python IrisIdeRuntimeManager가 standalone-bridge.js를 이미 띄운 경우
        // 같은 IRIS_IDE_BRIDGE_PORT에 또 listen 하면 EADDRINUSE → 백엔드 onStart 실패
        // → 터미널 RPC/폴링이 깨져 runTerminalCommand가 frontend timeout 난다.
        const standalone = (process.env.IRIS_IDE_STANDALONE_BRIDGE || '').trim();
        if (standalone === '1' || standalone.toLowerCase() === 'true') {
            return;
        }
        await this.bridge.start();
    }

    async onStop(): Promise<void> {
        const standalone = (process.env.IRIS_IDE_STANDALONE_BRIDGE || '').trim();
        if (standalone === '1' || standalone.toLowerCase() === 'true') {
            return;
        }
        await this.bridge.stop();
    }
}
