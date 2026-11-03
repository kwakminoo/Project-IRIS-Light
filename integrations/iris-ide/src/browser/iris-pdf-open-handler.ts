import { injectable } from '@theia/core/shared/inversify';
import { NavigatableWidgetOpenHandler } from '@theia/core/lib/browser';
import URI from '@theia/core/lib/common/uri';
import { IrisPdfWidget, IRIS_PDF_WIDGET_FACTORY_ID } from './iris-pdf-widget';

/** Beat Monaco (~100) for *.pdf so binary tabs never win. */
const PDF_OPEN_PRIORITY = 500;

@injectable()
export class IrisPdfOpenHandler extends NavigatableWidgetOpenHandler<IrisPdfWidget> {

    readonly id = IRIS_PDF_WIDGET_FACTORY_ID;
    readonly label = 'Iris PDF';

    canHandle(uri: URI): number {
        const path = uri.path.toString().toLowerCase();
        return path.endsWith('.pdf') ? PDF_OPEN_PRIORITY : 0;
    }

}
