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
                return { root: this.workspaceRoot };
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
                const { execSync } = require('child_process') as typeof import('child_process');
                const command = String(args.command || args.cmd || 'echo IRIS_IDE_TEST');
                const cwd = args.cwd ? this.resolvePath(String(args.cwd)) : this.workspaceRoot;
                const out = execSync(command, { cwd, encoding: 'utf-8', timeout: 30000 });
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
