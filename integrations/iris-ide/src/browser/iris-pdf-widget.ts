import { inject, injectable, postConstruct } from '@theia/core/shared/inversify';
import { BaseWidget, Message } from '@theia/core/lib/browser';
import { Navigatable, NavigatableWidgetOptions } from '@theia/core/lib/browser/navigatable-types';
import { LabelProvider } from '@theia/core/lib/browser/label-provider';
import { Disposable } from '@theia/core/lib/common/disposable';
import URI from '@theia/core/lib/common/uri';
import { FileService } from '@theia/filesystem/lib/browser/file-service';

export const IRIS_PDF_WIDGET_FACTORY_ID = 'iris-pdf';
export const IrisPdfWidgetOptions = Symbol('IrisPdfWidgetOptions');

interface PdfJsDocument {
    numPages: number;
    getPage(pageNumber: number): Promise<PdfJsPage>;
    destroy(): void;
}

interface PdfJsPage {
    getViewport(params: { scale: number }): { width: number; height: number };
    render(params: { canvasContext: CanvasRenderingContext2D; viewport: { width: number; height: number } }): { promise: Promise<void> };
}

interface PdfJsApi {
    GlobalWorkerOptions: { workerSrc: string };
    getDocument(src: { data: Uint8Array }): { promise: Promise<PdfJsDocument> };
}

let pdfJsApi: PdfJsApi | undefined;

async function loadPdfJs(): Promise<PdfJsApi> {
    if (pdfJsApi) {
        return pdfJsApi;
    }
    const moduleUrl = new URL('pdfjs/pdf.mjs', window.location.href).toString();
    const workerUrl = new URL('pdfjs/pdf.worker.mjs', window.location.href).toString();
    // Keep Mozilla PDF.js out of the Theia esbuild bundle; serve from /pdfjs/.
    const dynamicImport = new Function('u', 'return import(u)') as (u: string) => Promise<PdfJsApi>;
    const api = await dynamicImport(moduleUrl);
    api.GlobalWorkerOptions.workerSrc = workerUrl;
    pdfJsApi = api;
    return api;
}

@injectable()
export class IrisPdfWidget extends BaseWidget implements Navigatable {

    static readonly FACTORY_ID = IRIS_PDF_WIDGET_FACTORY_ID;

    protected readonly resourceUri: URI;
    protected scroll: HTMLDivElement;
    protected status: HTMLDivElement;
    protected pdfDoc: PdfJsDocument | undefined;
    protected cancelled = false;

    constructor(
        @inject(IrisPdfWidgetOptions) options: NavigatableWidgetOptions,
        @inject(FileService) protected readonly fileService: FileService,
        @inject(LabelProvider) protected readonly labelProvider: LabelProvider,
    ) {
        super();
        this.resourceUri = new URI(options.uri);
        this.id = `${IRIS_PDF_WIDGET_FACTORY_ID}:${this.resourceUri.toString()}`;
        this.title.closable = true;
        this.title.label = this.labelProvider.getName(this.resourceUri) || this.resourceUri.path.base;
        this.title.caption = this.resourceUri.toString();
        this.addClass('iris-pdf-widget');
        this.node.tabIndex = 0;
    }

    @postConstruct()
    protected init(): void {
        this.status = document.createElement('div');
        this.status.className = 'iris-pdf-status';
        this.status.textContent = 'PDF 불러오는 중…';
        this.node.appendChild(this.status);

        this.scroll = document.createElement('div');
        this.scroll.className = 'iris-pdf-scroll';
        this.node.appendChild(this.scroll);

        this.toDispose.push(Disposable.create(() => {
            this.cancelled = true;
            this.pdfDoc?.destroy();
            this.pdfDoc = undefined;
        }));
        void this.loadAndRender();
    }

    getResourceUri(): URI | undefined {
        return this.resourceUri;
    }

    createMoveToUri(resourceUri: URI): URI | undefined {
        return this.resourceUri && this.resourceUri.withPath(resourceUri.path);
    }

    protected onActivateRequest(msg: Message): void {
        super.onActivateRequest(msg);
        this.node.focus();
    }

    protected async loadAndRender(): Promise<void> {
        try {
            const content = await this.fileService.readFile(this.resourceUri);
            if (this.cancelled) {
                return;
            }
            const data = content.value.buffer.slice();
            const pdfjs = await loadPdfJs();
            if (this.cancelled) {
                return;
            }
            this.pdfDoc = await pdfjs.getDocument({ data }).promise;
            const total = this.pdfDoc.numPages;
            this.status.textContent = `페이지 렌더 중… 0/${total}`;
            this.scroll.replaceChildren();
            for (let pageNum = 1; pageNum <= total; pageNum++) {
                if (this.cancelled) {
                    return;
                }
                await this.renderPage(pageNum);
                this.status.textContent = `페이지 ${pageNum}/${total}`;
            }
            this.status.textContent = `${total}페이지`;
        } catch (err) {
            if (this.cancelled) {
                return;
            }
            const msg = err instanceof Error ? err.message : String(err);
            this.status.textContent = '';
            const error = document.createElement('div');
            error.className = 'iris-pdf-error';
            error.textContent = `PDF를 열 수 없습니다.\n${msg}`;
            this.scroll.replaceChildren(error);
        }
    }

    protected async renderPage(pageNum: number): Promise<void> {
        if (!this.pdfDoc) {
            return;
        }
        const page = await this.pdfDoc.getPage(pageNum);
        const viewport = page.getViewport({ scale: 1.25 });
        const canvas = document.createElement('canvas');
        canvas.width = Math.floor(viewport.width);
        canvas.height = Math.floor(viewport.height);
        canvas.dataset.page = String(pageNum);
        const ctx = canvas.getContext('2d');
        if (!ctx) {
            throw new Error('canvas 2d unavailable');
        }
        this.scroll.appendChild(canvas);
        await page.render({ canvasContext: ctx, viewport }).promise;
    }

}
