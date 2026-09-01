import { injectable } from '@theia/core/shared/inversify';
import { IrisIdeEditorInfo } from '../common/iris-ide-protocol';

@injectable()
export class IrisIdeEditorStateService {
    protected current: IrisIdeEditorInfo | null = null;

    update(info: IrisIdeEditorInfo): void {
        this.current = info;
    }

    clear(): void {
        this.current = null;
    }

    snapshot(): IrisIdeEditorInfo | null {
        return this.current ? { ...this.current } : null;
    }
}
