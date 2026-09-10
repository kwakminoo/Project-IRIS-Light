import * as crypto from 'crypto';
import * as fs from 'fs';
import * as http from 'http';
import * as path from 'path';
import { inject, injectable } from '@theia/core/shared/inversify';
import { IRIS_IDE_PRODUCT_NAME } from '../common/iris-ide-protocol';

type Json = Record<string, unknown>;

@injectable()
export class IrisIdeBridgeServer {
    protected server: http.Server | null = null;
    protected port = 0;
    protected token = '';
    protected workspaceRoot = '';
    // Whether Theia currently has a folder open (vs. the "new window" welcome
    // screen). workspaceRoot itself stays populated even when this is false —
    // file-API sandboxing always needs a valid root — so callers must check
    // this flag to tell "no folder open" apart from "folder open at X".
    protected workspaceOpen = true;
    protected editorState: Json | null = null;

    async start(): Promise<void> {
        this.workspaceRoot = (process.env.IRIS_IDE_WORKSPACE || process.cwd()).trim();
        this.token = (process.env.IRIS_IDE_BRIDGE_TOKEN || '').trim() || crypto.randomBytes(24).toString('hex');
        const wantPort = parseInt(process.env.IRIS_IDE_BRIDGE_PORT || '0', 10);
        this.server = http.createServer((req, res) => this.handle(req, res));
        await new Promise<void>((resolve, reject) => {
            this.server!.listen(wantPort > 0 ? wantPort : 0, '127.0.0.1', () => {
                const addr = this.server!.address();
                this.port = typeof addr === 'object' && addr ? addr.port : 0;
                this.writeStateFile();
                resolve();
            }).on('error', reject);
        });
    }

    async stop(): Promise<void> {
        if (this.server) {
            await new Promise<void>(resolve => this.server!.close(() => resolve()));
            this.server = null;
        }
    }

    protected writeStateFile(): void {
        const statePath = (process.env.IRIS_IDE_STATE_FILE || '').trim();
        if (!statePath) {
            return;
        }
        try {
            const payload = {
                pid: process.pid,
                port: parseInt(process.env.THEIA_BACKEND_PORT || process.env.PORT || '0', 10) || 0,
                bridge_port: this.port,
                token: this.token,
                workspace: this.workspaceRoot,
                workspace_open: this.workspaceOpen,
            };
            fs.mkdirSync(path.dirname(statePath), { recursive: true });
            fs.writeFileSync(statePath, JSON.stringify(payload, null, 2));
        } catch {
            // ignore
        }
    }

    protected authOk(req: http.IncomingMessage): boolean {
        const hdr = (req.headers.authorization || '').trim();
        if (hdr === `Bearer ${this.token}`) {
            return true;
        }
        const url = new URL(req.url || '/', 'http://127.0.0.1');
        return url.searchParams.get('token') === this.token;
    }

    protected readBody(req: http.IncomingMessage): Promise<Json> {
        return new Promise((resolve) => {
            const chunks: Buffer[] = []
            req.on('data', chunk => chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk)));
            req.on('end', () => {
                if (!chunks.length) {
                    resolve({});
                    return;
                }
                try {
                    const parsed = JSON.parse(Buffer.concat(chunks).toString('utf-8'));
                    resolve(typeof parsed === 'object' && parsed ? parsed as Json : {});
                } catch {
                    resolve({});
                }
            });
            req.on('error', () => resolve({}));
        });
    }

    protected json(res: http.ServerResponse, code: number, body: Json): void {
        const raw = JSON.stringify(body);
        res.writeHead(code, {
            'Content-Type': 'application/json; charset=utf-8',
            'Content-Length': Buffer.byteLength(raw),
        });
        res.end(raw);
    }

    protected resolvePath(p: string): string {
        const root = path.resolve(this.workspaceRoot);
        const target = path.resolve(root, p || '.');
        if (!target.startsWith(root)) {
            throw new Error('path escapes workspace');
        }
        return target;
    }

    /**
     * Runs `command` without blocking Node's single event-loop thread (unlike
     * the previous `execSync`, which stalled every other bridge request —
     * including the frontend's periodic editor-state push — for as long as
     * the command ran). Always settles: on timeout the process (and, on
     * Windows, its full child tree — a plain SIGTERM/kill() often leaves
     * cmd.exe's grandchild processes running and the stdout pipe open,
     * which is what let `execSync`'s own timeout hang past its deadline)
     * is force-killed and the promise rejects with a clear message.
     */
    protected execWithTimeout(command: string, cwd: string, timeoutMs: number): Promise<string> {
        const { exec } = require('child_process') as typeof import('child_process');
        return new Promise<string>((resolve, reject) => {
            let settled = false;
            let killedByUs = false;

            const finish = (fn: () => void): void => {
                if (settled) {
                    return;
                }
                settled = true;
                clearTimeout(killTimer);
                clearTimeout(hardTimer);
                fn();
            };

            // Deliberately NOT using exec()'s own `timeout` option: on Windows it only
            // signals the direct child (cmd.exe), whose grandchildren (e.g. a dev server
            // or script cmd.exe launched) survive as orphans — and since node considers
            // the command "done" the moment cmd.exe exits, our own tree-kill below would
            // never even run. We drive the timeout ourselves so the full tree is always
            // killed *before* anything is allowed to settle as timed out.
            const child = exec(
                command,
                { cwd, encoding: 'utf-8', maxBuffer: 10 * 1024 * 1024 },
                (error, stdout, stderr) => {
                    finish(() => {
                        if (error) {
                            const timedOut = Boolean(error.killed) || killedByUs;
                            reject(
                                new Error(
                                    timedOut
                                        ? `command timed out after ${timeoutMs}ms: ${command}`
                                        : (stderr || error.message).trim(),
                                ),
                            );
                            return;
                        }
                        resolve(stdout || stderr || '');
                    });
                },
            );

            const killTimer = setTimeout(() => {
                if (settled || typeof child.pid !== 'number') {
                    return;
                }
                killedByUs = true;
                try {
                    if (process.platform === 'win32') {
                        // /T kills the whole process tree, not just cmd.exe itself —
                        // plain child.kill() here would leave grandchildren running.
                        require('child_process').exec(`taskkill /pid ${child.pid} /T /F`);
                    } else {
                        child.kill('SIGKILL');
                    }
                } catch {
                    // best-effort — the hard timeout below still settles this promise
                }
            }, timeoutMs);

            // last-resort: if even the force-kill above doesn't make the callback fire
            // (e.g. the process is unkillable), never leave the caller waiting forever.
            const hardTimer = setTimeout(() => {
                finish(() =>
                    reject(new Error(`command timed out after ${timeoutMs}ms and could not be killed: ${command}`)),
                );
            }, timeoutMs + 3000);
        });
    }

    protected async handle(req: http.IncomingMessage, res: http.ServerResponse): Promise<void> {
        try {
            if (!this.authOk(req)) {
                this.json(res, 401, { ok: false, error: 'unauthorized' });
                return;
            }
            const url = new URL(req.url || '/', 'http://127.0.0.1');
            const parts = url.pathname.replace(/^\/+/, '').split('/').filter(Boolean);
            const cmd = parts[0] || 'health';
            const body = req.method === 'POST' ? await this.readBody(req) : {};
            const result = await this.dispatch(cmd, body, url.searchParams);
            this.json(res, 200, { ok: true, command: cmd, result });
        } catch (err) {
            const msg = err instanceof Error ? err.message : String(err);
            this.json(res, 400, { ok: false, error: msg });
        }
    }

    protected async dispatch(cmd: string, args: Json, params: URLSearchParams): Promise<Json> {
        switch (cmd) {
            case 'health':
                return {
                    product: IRIS_IDE_PRODUCT_NAME,
                    theia: '1.74.0',
                    bridge_port: this.port,
                    workspace: this.workspaceRoot,
                };
            case 'getWorkspace':
                return { root: this.workspaceRoot, opened: this.workspaceOpen };
            case 'setWorkspace': {
                // Pushed by the frontend whenever Theia's own File > Open Folder /
                // Close Folder changes the active workspace — keeps this process
                // (which outlives a single workspace, unlike the env var it booted
                // with) from going on reporting whatever folder was open at start.
                const root = String(args.root || '').trim();
                if (root) {
                    const abs = path.resolve(root);
                    if (!fs.existsSync(abs) || !fs.statSync(abs).isDirectory()) {
                        throw new Error(`not a directory: ${root}`);
                    }
                    this.workspaceRoot = abs;
                }
                this.workspaceOpen = args.opened !== undefined ? Boolean(args.opened) : Boolean(root);
                this.writeStateFile();
                return { root: this.workspaceRoot, opened: this.workspaceOpen };
            }
            case 'setEditorState':
                this.editorState = args;
                return { saved: true };
            case 'getActiveEditor':
                return { editor: this.editorState || null };
            case 'getOpenEditors':
                return { editors: this.editorState ? [this.editorState] : [] };
            case 'getCursorPosition':
                return {
                    line: (this.editorState?.line as number) || 1,
                    column: (this.editorState?.column as number) || 1,
                };
            case 'getSelection':
                return { selection: this.editorState?.selection || null };
            case 'getDiagnostics':
                return { diagnostics: [] };
            case 'openFile':
            case 'gotoFile': {
                const rel = String(args.path || params.get('path') || '');
                const abs = this.resolvePath(rel);
                if (!fs.existsSync(abs)) {
                    throw new Error(`file not found: ${rel}`);
                }
                this.editorState = {
                    uri: abs,
                    path: rel,
                    line: parseInt(String(args.line || 1), 10) || 1,
                    column: parseInt(String(args.column || 1), 10) || 1,
                };
                return { path: abs, opened: true };
            }
            case 'saveFile':
            case 'saveAll':
                return { saved: true };
            case 'createFile': {
                const rel = String(args.path || '');
                const abs = this.resolvePath(rel);
                fs.mkdirSync(path.dirname(abs), { recursive: true });
                const content = String(args.content ?? '');
                fs.writeFileSync(abs, content, 'utf-8');
                return { path: abs, created: true };
            }
            case 'deleteFile': {
                const rel = String(args.path || '');
                const abs = this.resolvePath(rel);
                fs.unlinkSync(abs);
                return { path: abs, deleted: true };
            }
            case 'renameFile': {
                const from = this.resolvePath(String(args.from || args.path || ''));
                const to = this.resolvePath(String(args.to || args.newPath || ''));
                fs.mkdirSync(path.dirname(to), { recursive: true });
                fs.renameSync(from, to);
                return { from, to };
            }
            case 'replaceSelection':
            case 'applyTextEdit':
            case 'insertText':
            case 'replaceRange': {
                const rel = String(args.path || (this.editorState?.path as string) || '');
                const abs = this.resolvePath(rel);
                let text = fs.readFileSync(abs, 'utf-8');
                const insert = String(args.text ?? args.content ?? '');
                if (cmd === 'insertText' || cmd === 'replaceSelection') {
                    text += insert;
                } else if (cmd === 'replaceRange') {
                    const start = parseInt(String(args.start || 0), 10) || 0;
                    const end = parseInt(String(args.end || text.length), 10) || text.length;
                    text = text.slice(0, start) + insert + text.slice(end);
                } else {
                    text = insert;
                }
                fs.writeFileSync(abs, text, 'utf-8');
                return { path: abs, length: text.length };
            }
            case 'formatDocument':
                return { formatted: false, reason: 'not implemented' };
            case 'gotoLine':
                return { line: parseInt(String(args.line || 1), 10) || 1 };
            case 'gotoSymbol':
            case 'findReferences':
                return { items: [] };
            case 'createTerminal':
            case 'runTerminalCommand': {
                const command = String(args.command || args.cmd || 'echo IRIS_IDE_TEST');
                const cwd = args.cwd ? this.resolvePath(String(args.cwd)) : this.workspaceRoot;
                const out = await this.execWithTimeout(command, cwd, 30000);
                return { command, output: out, cwd };
            }
            case 'getTerminalState':
                return { active: false };
            case 'runTask':
                return { started: false };
            case 'getTaskState':
                return { running: false };
            case 'startDebug':
            case 'stopDebug':
            case 'continueDebug':
                return { hooked: true };
            case 'getGitStatus': {
                try {
                    const { execSync } = require('child_process') as typeof import('child_process');
                    const out = execSync('git status --porcelain', {
                        cwd: this.workspaceRoot,
                        encoding: 'utf-8',
                        timeout: 15000,
                    });
                    return { porcelain: out };
                } catch {
                    return { porcelain: '' };
                }
            }
            case 'getGitDiff': {
                try {
                    const { execSync } = require('child_process') as typeof import('child_process');
                    const rel = String(args.path || '');
                    const cmd = rel ? `git diff -- ${rel}` : 'git diff';
                    const out = execSync(cmd, { cwd: this.workspaceRoot, encoding: 'utf-8', timeout: 15000 });
                    return { diff: out };
                } catch {
                    return { diff: '' };
                }
            }
            default:
                throw new Error(`unknown command: ${cmd}`);
        }
    }
}
