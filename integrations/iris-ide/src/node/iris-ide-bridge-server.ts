import * as crypto from 'crypto';
import * as fs from 'fs';
import * as http from 'http';
import * as path from 'path';
import { inject, injectable } from '@theia/core/shared/inversify';
import { IRIS_IDE_PRODUCT_NAME } from '../common/iris-ide-protocol';

type Json = Record<string, unknown>;

// Theia(QWebEngine) 페이지는 브리지와 포트가 달라 cross-origin — ACAO 없으면 프런트엔드의
// setEditorState / pollPendingCommands fetch가 전부 차단된다 (control_surface와 동일 처리).
const CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Authorization, Content-Type',
};

@injectable()
export class IrisIdeBridgeServer {
    protected server: http.Server | null = null;
    protected port = 0;
    protected token = '';
    protected workspaceRoot = '';
    protected workspaceOpen = false;
    protected editorState: Json | null = null;
    protected openEditors: Json[] = [];

    async start(): Promise<void> {
        const envWs = (process.env.IRIS_IDE_WORKSPACE || '').trim();
        this.workspaceRoot = envWs || process.cwd();
        this.workspaceOpen = Boolean(envWs);
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
            ...CORS_HEADERS,
            'Content-Type': 'application/json; charset=utf-8',
            'Content-Length': Buffer.byteLength(raw),
        });
        res.end(raw);
    }

    protected resolvePath(p: string): string {
        const root = path.resolve(this.workspaceRoot);
        const raw = String(p || '').trim();
        const target = path.isAbsolute(raw) ? path.resolve(raw) : path.resolve(root, raw || '.');
        const rel = path.relative(root, target);
        const escapes = rel === '..' || rel.startsWith(`..${path.sep}`) || path.isAbsolute(rel);
        if (rel !== '' && escapes) {
            throw new Error('path escapes workspace');
        }
        return target;
    }

    /** 식별자(path|uri) 없는 상태는 「편집기 없음」이다 — 프런트엔드는 편집기가 닫히면 {}를 보낸다. */
    protected normalizeEditorState(info: Json | null): Json | null {
        if (!info || typeof info !== 'object' || Array.isArray(info)) {
            return null;
        }
        const copy: Json = { ...info };
        delete copy.editors;
        const hasId = Boolean(String(copy.path || '').trim() || String(copy.uri || '').trim());
        return hasId ? copy : null;
    }

    protected normalizeEditorList(list: unknown, fallback: Json | null): Json[] {
        const out: Json[] = [];
        if (Array.isArray(list)) {
            for (const item of list) {
                const row = this.normalizeEditorState(item && typeof item === 'object' ? item as Json : null);
                if (row) {
                    out.push(row);
                }
            }
        }
        if (!out.length && fallback) {
            out.push(fallback);
        }
        return out;
    }

    protected async handle(req: http.IncomingMessage, res: http.ServerResponse): Promise<void> {
        try {
            // preflight에는 Authorization이 실려오지 않는다 — 인증 앞에서 응답할 것.
            if (req.method === 'OPTIONS') {
                res.writeHead(204, { ...CORS_HEADERS, 'Content-Length': '0' });
                res.end();
                return;
            }
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
                this.editorState = this.normalizeEditorState(args);
                this.openEditors = this.normalizeEditorList(args.editors, this.editorState);
                return { saved: true };
            case 'getActiveEditor':
                return { editor: this.editorState || null };
            case 'getOpenEditors':
                return { editors: this.openEditors };
            case 'getCursorPosition':
                return {
                    line: (this.editorState?.line as number) || 1,
                    column: (this.editorState?.column as number) || 1,
                };
            case 'getSelection':
                return { selection: this.editorState?.selection || null };
            case 'getDiagnostics':
                throw new Error('diagnostics are reported by the standalone bridge frontend');
            case 'openFile':
            case 'gotoFile':
                // Honesty: do not claim opened:true without the frontend poller.
                // Product path uses standalone-bridge.js (IRIS_IDE_STANDALONE_BRIDGE=1).
                throw new Error(
                    `${cmd} must go through standalone-bridge frontend queue (IRIS IDE editor)`
                );
            case 'saveFile':
            case 'saveAll':
                throw new Error('save goes through the standalone bridge frontend');
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
            case 'replaceRange':
                throw new Error(`${cmd} goes through the standalone bridge frontend`);
            case 'formatDocument':
            case 'gotoLine':
            case 'gotoSymbol':
            case 'findReferences':
            case 'gotoDefinition':
                throw new Error(`${cmd} goes through the standalone bridge frontend`);
            case 'createTerminal':
            case 'runTerminalCommand': {
                const command = String(args.command || args.cmd || 'echo IRIS_IDE_TEST');
                const cwd = args.cwd ? this.resolvePath(String(args.cwd)) : this.workspaceRoot;
                throw new Error(
                    'runTerminalCommand must go through standalone-bridge frontend queue (IRIS IDE integrated terminal)',
                );
            }
            case 'getTerminalState':
                return { active: false };
            case 'runTask':
            case 'getTaskState':
            case 'startDebug':
            case 'stopDebug':
            case 'continueDebug':
            case 'pluginLoaded':
                throw new Error(`${cmd} goes through the standalone bridge frontend`);
            case 'getGitStatus': {
                try {
                    const { execSync } = require('child_process') as typeof import('child_process');
                    const out = execSync('git status --porcelain', {
                        cwd: this.workspaceRoot,
                        encoding: 'utf-8',
                        timeout: 15000,
                        windowsHide: true,
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
                    const out = execSync(cmd, {
                        cwd: this.workspaceRoot,
                        encoding: 'utf-8',
                        timeout: 15000,
                        windowsHide: true,
                    });
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
