import { inject, injectable } from '@theia/core/shared/inversify';
import { FrontendApplicationContribution } from '@theia/core/lib/browser';
import { OpenerService, open } from '@theia/core/lib/browser';
import URI from '@theia/core/lib/common/uri';
import { FileUri } from '@theia/core/lib/common/file-uri';
import { EditorManager } from '@theia/editor/lib/browser';
import { TerminalService } from '@theia/terminal/lib/browser/base/terminal-service';
import { TerminalWidget } from '@theia/terminal/lib/browser/base/terminal-widget';
import { WorkspaceService } from '@theia/workspace/lib/browser';
import { resolveBridgeIdentity } from './iris-ide-bridge-identity';

interface PendingCommand {
    id: number;
    cmd: string;
    args: Record<string, unknown>;
}

type ShellKind = 'cmd' | 'powershell' | 'sh';

async function shellOf(terminal: TerminalWidget): Promise<ShellKind> {
    const raw = terminal as unknown as {
        shellPath?: string;
        options?: { shellPath?: string; executable?: string };
        title?: { label?: string; caption?: string };
        processInfo?: Promise<{ executable?: string; command?: string; shellPath?: string }>;
    };
    let infoText = '';
    try {
        const info = await raw.processInfo;
        infoText = [info?.executable, info?.command, info?.shellPath].filter(Boolean).join(' ');
    } catch {
        /* terminal not started yet — fall through to widget hints */
    }
    const blob = [raw.shellPath, raw.options?.shellPath, raw.options?.executable, raw.title?.label, raw.title?.caption, infoText]
        .filter(Boolean)
        .join(' ')
        .toLowerCase();
    if (blob.includes('powershell') || blob.includes('pwsh')) {
        return 'powershell';
    }
    if (blob.includes('cmd')) {
        return 'cmd';
    }
    const ua = typeof navigator !== 'undefined' ? navigator.userAgent : '';
    if (/windows/i.test(ua)) {
        return 'cmd';
    }
    return 'sh';
}

function cdCommand(cwd: string, shell: ShellKind): string {
    if (shell === 'cmd') {
        return `cd /d "${cwd.replace(/"/g, '""')}"`;
    }
    if (shell === 'powershell') {
        return `Set-Location -LiteralPath '${cwd.replace(/'/g, "''")}'`;
    }
    return `cd ${JSON.stringify(cwd)}`;
}

function cmdQuote(arg: string): string {
    if (arg === '') {
        return '""';
    }
    if (/[ \t&|<>^%!"]/.test(arg)) {
        return `"${arg.replace(/"/g, '""')}"`;
    }
    return arg;
}

function wrapRun(argv: string[], shell: ShellKind): string {
    if (shell === 'cmd') {
        const quoted = argv.map(cmdQuote).join(' ');
        return [
            'if not exist .iris mkdir .iris',
            'del /f /q .iris\\last_run.log 2>nul',
            `${quoted} > .iris\\last_run.log 2>&1`,
            'echo IRIS_EXIT:%ERRORLEVEL% >> .iris\\last_run.log',
            'type .iris\\last_run.log',
        ].join('\n');
    }
    if (shell === 'powershell') {
        const invoke = '& ' + argv.map(arg => `'${arg.replace(/'/g, "''")}'`).join(' ');
        return [
            'New-Item -ItemType Directory -Force -Path .iris | Out-Null',
            'Remove-Item -Force -ErrorAction SilentlyContinue .iris\\last_run.log',
            `${invoke} 2>&1 | Tee-Object -FilePath .iris\\last_run.log`,
            '$code = if ($null -ne $LASTEXITCODE) { $LASTEXITCODE } else { 0 }',
            'Add-Content -Path .iris\\last_run.log -Value "IRIS_EXIT:$code"',
            'exit $code',
        ].join('; ');
    }
    const quoted = argv.map(arg => JSON.stringify(arg)).join(' ');
    return `mkdir -p .iris; rm -f .iris/last_run.log; { ${quoted}; } 2>&1 | tee .iris/last_run.log; code=\${PIPESTATUS[0]}; printf "IRIS_EXIT:%s\\n" "$code" >> .iris/last_run.log; exit "$code"`;
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

    protected pollBusy = false;

    onStart(): void {
        // 포트 미해결이어도 타이머는 건다 — onStart에서 포기하면 복구 기회가 영구히 없다.
        this.resolveBridge();
        this.pollTimer = window.setInterval(() => this.poll(), 320);
        window.setTimeout(() => this.poll(), 120);
    }

    onStop(): void {
        if (this.pollTimer !== undefined) {
            window.clearInterval(this.pollTimer);
            this.pollTimer = undefined;
        }
    }

    /** 매 tick 재조회 — 워크스페이스 전환·토큰 회전 후 구포트에 고착되면 안 된다. */
    protected resolveBridge(): boolean {
        const identity = resolveBridgeIdentity();
        if (identity.port && identity.token) {
            this.bridgePort = identity.port;
            this.bridgeToken = identity.token;
            return true;
        }
        return !!(this.bridgePort && this.bridgeToken);
    }

    protected async poll(): Promise<void> {
        if (this.pollBusy) {
            return;
        }
        if (!this.resolveBridge()) {
            return;
        }
        this.pollBusy = true;
        try {
            const data = await this.bridgeRequest('pollPendingCommands', { limit: 8 });
            const commands = Array.isArray(data.commands) ? data.commands as PendingCommand[] : [];
            for (const item of commands) {
                await this.execute(item);
            }
        } catch {
            /* ponytail: bridge may restart during workspace switch — next tick retries */
            this.bridgePort = 0;
            this.bridgeToken = '';
        } finally {
            this.pollBusy = false;
        }
    }

    protected async execute(item: PendingCommand): Promise<void> {
        try {
            const result = await this.dispatch(item.cmd, item.args || {});
            await this.bridgeRequest('completeCommand', { id: item.id, result });
        } catch (err) {
            const msg = err instanceof Error ? err.message : String(err);
            try {
                await this.bridgeRequest('completeCommand', { id: item.id, error: msg });
            } catch {
                /* bridge gone — queue wait will time out with diagnostics */
            }
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
        await this.withTimeout(terminal.start(), 10000, 'terminal.start');
        this.terminalService.open(terminal);
        return { name, created: true };
    }

    protected async runInTerminal(args: Record<string, unknown>): Promise<Record<string, unknown>> {
        const argv = Array.isArray(args.argv) ? args.argv.map(item => String(item)) : [];
        const command = String(args.command || '').trim();
        if (!command && argv.length === 0) {
            throw new Error('runTerminalCommand: empty command');
        }
        const cwd = String(args.cwd || '').trim();
        const terminal = await this.ensureTerminal(cwd);
        const shell = await shellOf(terminal);
        const body = argv.length > 0 ? wrapRun(argv, shell) : command;
        const lines = [...(cwd ? [cdCommand(cwd, shell)] : []), ...body.split(/\r?\n/)].filter(line => line.trim());
        // cmd.exe submits a line on CR. A single LF-joined paste stays on one prompt.
        for (const line of lines) {
            terminal.sendText(`${line}\r\n`);
            await new Promise(resolve => window.setTimeout(resolve, 150));
        }
        return { command: body, queued: true, via: 'theia_terminal', cwd, shell, delivered: true };
    }

    /** 기존 터미널 재사용 — newTerminal+start 가 Windows ConPTY에서 자주 멈춘다. */
    protected async ensureTerminal(cwd: string): Promise<TerminalWidget> {
        const reuse = this.terminalService.currentTerminal || this.terminalService.lastUsedTerminal;
        if (reuse) {
            try {
                this.terminalService.open(reuse);
                return reuse;
            } catch {
                /* fall through — create fresh */
            }
        }
        // cwd: string|URI 둘 다 허용 — FileUri만 쓰면 toString()이 꼬이는 빌드가 있다.
        const options = cwd
            ? { title: 'IRIS', cwd }
            : { title: 'IRIS' };
        const terminal = await this.terminalService.newTerminal(options);
        await this.withTimeout(terminal.start(), 10000, 'terminal.start');
        this.terminalService.open(terminal);
        return terminal;
    }

    protected withTimeout<T>(promise: Promise<T>, ms: number, label: string): Promise<T> {
        return new Promise<T>((resolve, reject) => {
            const timer = window.setTimeout(() => reject(new Error(`${label} timeout (${ms}ms)`)), ms);
            promise.then(
                value => {
                    window.clearTimeout(timer);
                    resolve(value);
                },
                err => {
                    window.clearTimeout(timer);
                    reject(err);
                },
            );
        });
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
