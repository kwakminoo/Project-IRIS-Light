import * as React from '@theia/core/shared/react';
import { inject, injectable, postConstruct } from '@theia/core/shared/inversify';
import { ReactWidget } from '@theia/core/lib/browser/widgets/react-widget';
import { LabelProvider } from '@theia/core/lib/browser/label-provider';
import { CommandRegistry } from '@theia/core/lib/common/command';
import URI from '@theia/core/lib/common/uri';
import { WorkspaceService } from '@theia/workspace/lib/browser/workspace-service';
import { WorkspaceCommands } from '@theia/workspace/lib/browser/workspace-commands';
import { IRIS_IDE_PRODUCT_NAME } from '../common/iris-ide-protocol';

export const IRIS_IDE_START_WIDGET_ID = 'iris-ide-start';
export const IRIS_IDE_START_WIDGET_FACTORY_ID = IRIS_IDE_START_WIDGET_ID;

const SHOW_ON_STARTUP_KEY = 'iris.ide.startScreen.showOnStartup';
const MAX_RECENT = 8;

interface RecentEntry {
    uri: URI;
    name: string;
    detail: string;
    icon: string;
}

/**
 * "새 창" 시작 화면 — 커서(Cursor)의 New Window 레이아웃을 참고해
 * 폴더 열기 / 최근 프로젝트를 한 화면에서 바로 고를 수 있게 한다.
 * 워크스페이스가 열려 있지 않을 때 IrisIdeStartContribution이 메인 영역에 띄운다.
 */
@injectable()
export class IrisIdeStartWidget extends ReactWidget {

    static readonly ID = IRIS_IDE_START_WIDGET_ID;

    @inject(CommandRegistry) protected readonly commands: CommandRegistry;
    @inject(WorkspaceService) protected readonly workspaceService: WorkspaceService;
    @inject(LabelProvider) protected readonly labelProvider: LabelProvider;

    protected recent: RecentEntry[] = [];
    protected recentLoaded = false;

    @postConstruct()
    protected init(): void {
        this.id = IrisIdeStartWidget.ID;
        this.title.label = IRIS_IDE_PRODUCT_NAME;
        this.title.caption = IRIS_IDE_PRODUCT_NAME;
        this.title.closable = true;
        this.addClass('iris-ide-start');
        this.update();
        this.loadRecent();
    }

    protected async loadRecent(): Promise<void> {
        try {
            const uris = await this.workspaceService.recentWorkspaces();
            this.recent = uris.slice(0, MAX_RECENT).map(raw => {
                const uri = new URI(raw);
                return {
                    uri,
                    name: this.labelProvider.getName(uri) || uri.displayName,
                    detail: this.labelProvider.getLongName(uri) || uri.toString(),
                    icon: this.labelProvider.getIcon(uri),
                };
            });
        } catch {
            this.recent = [];
        } finally {
            this.recentLoaded = true;
            this.update();
        }
    }

    protected readonly openFolder = (): void => {
        this.commands.executeCommand(WorkspaceCommands.OPEN_FOLDER.id);
    };

    protected readonly openRecent = (uri: URI): void => {
        this.workspaceService.open(uri);
    };

    protected get showOnStartup(): boolean {
        try {
            return window.localStorage.getItem(SHOW_ON_STARTUP_KEY) !== 'false';
        } catch {
            return true;
        }
    }

    protected readonly toggleShowOnStartup = (): void => {
        try {
            window.localStorage.setItem(SHOW_ON_STARTUP_KEY, String(!this.showOnStartup));
        } catch {
            // 스토리지 접근 불가 — 조용히 무시
        }
        this.update();
    };

    protected render(): React.ReactNode {
        return (
            <div className="iris-ide-start__scroll">
                <div className="iris-ide-start__inner">
                    <header className="iris-ide-start__header">
                        <div className="iris-ide-start__brand">
                            <span className="iris-ide-start__logo" />
                            <h1>{IRIS_IDE_PRODUCT_NAME}</h1>
                        </div>
                        <p className="iris-ide-start__tagline">Iris와 함께 코드를 실행하고 다듬는 공간</p>
                    </header>
                    <div className="iris-ide-start__columns">
                        <section className="iris-ide-start__col">
                            <h2>시작하기</h2>
                            <button type="button" className="iris-ide-start__action" onClick={this.openFolder}>
                                <span className="codicon codicon-folder-opened" />
                                <span>폴더 열기…</span>
                            </button>
                        </section>
                        <section className="iris-ide-start__col iris-ide-start__col--recent">
                            <h2>최근 프로젝트</h2>
                            {this.renderRecent()}
                        </section>
                    </div>
                    <footer className="iris-ide-start__footer">
                        <label className="iris-ide-start__checkbox">
                            <input
                                type="checkbox"
                                checked={this.showOnStartup}
                                onChange={this.toggleShowOnStartup}
                            />
                            시작 시 항상 이 화면 표시
                        </label>
                    </footer>
                </div>
            </div>
        );
    }

    protected renderRecent(): React.ReactNode {
        if (!this.recentLoaded) {
            return <p className="iris-ide-start__muted">불러오는 중…</p>;
        }
        if (this.recent.length === 0) {
            return <p className="iris-ide-start__muted">최근에 연 프로젝트가 없습니다.</p>;
        }
        return (
            <ul className="iris-ide-start__recent-list">
                {this.recent.map(entry => (
                    <li key={entry.uri.toString()}>
                        <button
                            type="button"
                            className="iris-ide-start__recent-item"
                            title={entry.detail}
                            onClick={() => this.openRecent(entry.uri)}
                        >
                            <span className={entry.icon} />
                            <span className="iris-ide-start__recent-text">
                                <span className="iris-ide-start__recent-name">{entry.name}</span>
                                <span className="iris-ide-start__recent-detail">{entry.detail}</span>
                            </span>
                        </button>
                    </li>
                ))}
            </ul>
        );
    }
}
