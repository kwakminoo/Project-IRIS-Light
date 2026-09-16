import { inject, injectable } from '@theia/core/shared/inversify';
import { FrontendApplicationContribution } from '@theia/core/lib/browser';
import { OpenerService, open } from '@theia/core/lib/browser';
import URI from '@theia/core/lib/common/uri';
import { FileUri } from '@theia/core/lib/common/file-uri';
import { EditorManager } from '@theia/editor/lib/browser';
import { TerminalService } from '@theia/terminal/lib/browser/base/terminal-service';
import { WorkspaceService } from '@theia/workspace/lib/browser';

interface PendingCommand {
    id: number;
    cmd: string;
    args: Record<string, unknown>;
}

@injectable()
export class IrisIdeBridgePoller implements FrontendApplicationContribution {

    @inject(EditorManager) protected readonly editorManager: EditorManager;

    @inject(OpenerService) protected readonly openerService: OpenerService;

    @inject(TerminalService) protected readonly terminalService: TerminalService;

    @inject(WorkspaceService) protected readonly workspaceService: WorkspaceService;

    protected bridgePort = 0;

    protected bridgeToken = '';

    protected pollTimer: number | undefined;

    onStart(): void {
        const params = new URLSearchParams(window.location.search);
        this.bridgePort = parseInt(params.get('iris_bridge_port') || '0', 10) || 0;
        this.bridgeToken = params.get('iris_bridge_token') || '';
        if (!this.bridgePort) {
            return;
        }
        this.pollTimer = window.setInterval(() => this.poll(), 320);
        window.setTimeout(() => this.poll(), 120);
    }

    onStop(): void {
        if (this.pollTimer !== undefined) {
            window.clearInterval(this.pollTimer);
            this.pollTimer = undefined;
        }
    }

    protected async poll(): Promise<void> {
        try {
            const data = await this.bridgeRequest('pollPendingCommands', { limit: 8 });
            const commands = Array.isArray(data.commands) ? data.commands as PendingCommand[] : [];
            for (const item of commands) {
                await this.execute(item);
            }
        } catch {
            /* ponytail: bridge may restart during workspace switch */
        }
    }

    protected async execute(item: PendingCommand): Promise<void> {
        try {
            const result = await this.dispatch(item.cmd, item.args || {});
            await this.bridgeRequest('completeCommand', { id: item.id, result });
        } catch (err) {
            const msg = err instanceof Error ? err.message : String(err);
            await this.bridgeRequest('completeCommand', { id: item.id, error: msg });
        }
    }

    protected async dispatch(cmd: string, args: Record<string, unknown>): Promise<Record<string, unknown>> {
        switch (cmd) {
            case 'openFile':
            case 'gotoFile':
                return this.openInEditor(args);
            case 'createTerminal':
                return this.createTerminal(args);
            case 'runTerminalCommand':
                return this.runInTerminal(args);
            default:
                throw new Error(`unsupported frontend command: ${cmd}`);
        }
    }

    protected async openInEditor(args: Record<string, unknown>): Promise<Record<string, unknown>> {
        const rel = String(args.path || '');
        const abs = String(args.abs || '');
        const roots = this.workspaceService.tryGetRoots();
        const rootUri = roots.length ? roots[0].resource : undefined;
        let uri: URI;
        if (abs) {
            uri = FileUri.create(abs);
        } else if (rootUri) {
            uri = rootUri.resolve(rel);
        } else {
            throw new Error(`file not found: ${rel}`);
        }
        await open(this.openerService, uri, { mode: 'activate' });
        const line = Math.max(1, parseInt(String(args.line || 1), 10) || 1);
        const column = Math.max(1, parseInt(String(args.column || 1), 10) || 1);
        const editor = await this.editorManager.open(uri, { mode: 'activate' });
        if (editor) {
            const pos = { line: line - 1, character: column - 1 };
            editor.editor.selection = { start: pos, end: pos } as never;
            editor.editor.cursor = pos as never;
            editor.editor.revealPosition(pos as never);
        }
        return { path: uri.toString(), opened: true, line, column };
    }

    protected async createTerminal(args: Record<string, unknown>): Promise<Record<string, unknown>> {
        const name = String(args.name || 'IRIS');
        const terminal = await this.terminalService.newTerminal({ title: name });
        terminal.start();
        this.terminalService.open(terminal);
        return { name, created: true };
    }

    protected async runInTerminal(args: Record<string, unknown>): Promise<Record<string, unknown>> {
        const command = String(args.command || '').trim();
        if (!command) {
            throw new Error('runTerminalCommand: empty command');
        }
        const terminal = await this.terminalService.newTerminal({ title: 'IRIS' });
        terminal.start();
        this.terminalService.open(terminal);
        // ponytail: Theia 1.74 sendText is (text) only — append \n for Enter
        terminal.sendText(command.endsWith('\n') ? command : `${command}\n`);
        return { command, queued: true, via: 'theia_terminal' };
    }

    protected async bridgeRequest(command: string, payload: Record<string, unknown>): Promise<Record<string, unknown>> {
        const res = await fetch(`http://127.0.0.1:${this.bridgePort}/${command}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                Authorization: `Bearer ${this.bridgeToken}`,
            },
            body: JSON.stringify(payload),
        });
        const data = await res.json() as { ok?: boolean; error?: string; result?: Record<string, unknown> };
        if (!data.ok) {
            throw new Error(String(data.error || `bridge ${command} failed`));
        }
        return (data.result && typeof data.result === 'object') ? data.result : {};
    }

}
