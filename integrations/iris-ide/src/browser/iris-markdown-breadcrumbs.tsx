import * as React from 'react';
import { inject, injectable } from '@theia/core/shared/inversify';
import { BreadcrumbsRenderer } from '@theia/core/lib/browser/breadcrumbs/breadcrumbs-renderer';
import { CommandRegistry } from '@theia/core/lib/common/command';

@injectable()
export class IrisMarkdownBreadcrumbsRenderer extends BreadcrumbsRenderer {

    @inject(CommandRegistry) protected readonly commandRegistry: CommandRegistry;

    protected renderBreadcrumbs(): React.ReactNode {
        const path = this.uri?.path.toString() || '';
        const previewable = /\.(?:md|mkd|mdwn|mdown|markdown|markdn|mdtxt|mdtext|workbook)$/i.test(path)
            || /(?:^|\/)\.cursor\/.*\.mdc$/i.test(path);
        const items = this.breadcrumbs.map(breadcrumb => this.breadcrumbRenderer.render(breadcrumb, this.togglePopup));
        const fileIndex = this.breadcrumbs.findIndex(breadcrumb => breadcrumb.containerClass === 'file');
        if (previewable && fileIndex >= 0) {
            items.splice(fileIndex + 1, 0, <li key="iris-markdown-preview" className="iris-markdown-preview-breadcrumb">
                <span aria-hidden="true">/</span>
                <button type="button" title="마크다운 프리뷰 열기"
                    onClick={() => void this.commandRegistry.executeCommand('markdown.showPreview')}>프리뷰</button>
            </li>);
        }
        return items;
    }
}
