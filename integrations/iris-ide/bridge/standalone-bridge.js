#!/usr/bin/env node
/** Standalone IRIS IDE bridge — 127.0.0.1 only. Started by IrisIdeRuntimeManager. */
'use strict';

const crypto = require('crypto');
const fs = require('fs');
const http = require('http');
const path = require('path');
const { execSync } = require('child_process');

const workspaceRoot = path.resolve(process.env.IRIS_IDE_WORKSPACE || process.cwd());
const token = (process.env.IRIS_IDE_BRIDGE_TOKEN || '').trim() || crypto.randomBytes(24).toString('hex');
const wantPort = parseInt(process.env.IRIS_IDE_BRIDGE_PORT || '0', 10);
const stateFile = (process.env.IRIS_IDE_STATE_FILE || '').trim();

let editorState = null;
let pendingCommands = [];
let commandResults = {};
let nextCommandId = 1;

function writeState(port) {
    if (!stateFile) return;
    let existing = {};
    try {
        if (fs.existsSync(stateFile)) {
            existing = JSON.parse(fs.readFileSync(stateFile, 'utf8'));
        }
    } catch (_) { /* ignore */ }
    const payload = {
        ...existing,
        bridge_port: port,
        token,
        workspace: workspaceRoot,
        bridge_pid: process.pid,
    };
    fs.mkdirSync(path.dirname(stateFile), { recursive: true });
    fs.writeFileSync(stateFile, JSON.stringify(payload, null, 2));
}

function resolvePath(rel) {
    const root = workspaceRoot;
    const raw = String(rel || '').trim();
    if (path.isAbsolute(raw)) {
        const abs = path.resolve(raw);
        if (!abs.startsWith(root)) throw new Error('path escapes workspace');
        return abs;
    }
    const target = path.resolve(root, raw || '.');
    if (!target.startsWith(root)) throw new Error('path escapes workspace');
    return target;
}

/** 식별자(path|uri) 없는 상태는 「편집기 없음」이다 — 프런트엔드는 편집기가 닫히면 {}를 보낸다. */
function normalizeEditorState(info) {
    if (!info || typeof info !== 'object' || Array.isArray(info)) return null;
    const hasId = Boolean(String(info.path || '').trim() || String(info.uri || '').trim());
    return hasId ? info : null;
}

function readBody(req) {
    return new Promise((resolve) => {
        const chunks = [];
        req.on('data', (c) => chunks.push(Buffer.isBuffer(c) ? c : Buffer.from(c)));
        req.on('end', () => {
            if (!chunks.length) return resolve({});
            try {
                resolve(JSON.parse(Buffer.concat(chunks).toString('utf8')));
            } catch {
                resolve({});
            }
        });
        req.on('error', () => resolve({}));
    });
}

function authOk(req) {
    const hdr = (req.headers.authorization || '').trim();
    if (hdr === `Bearer ${token}`) return true;
    const url = new URL(req.url || '/', 'http://127.0.0.1');
    return url.searchParams.get('token') === token;
}

function waitForFrontendCommand(id, timeoutMs = 30000) {
    return new Promise((resolve, reject) => {
        const deadline = Date.now() + timeoutMs;
        const tick = () => {
            const slot = commandResults[id];
            if (slot) {
                delete commandResults[id];
                if (slot.error) reject(new Error(slot.error));
                else resolve(slot.result || {});
                return;
            }
            if (Date.now() > deadline) {
                reject(new Error('frontend command timeout'));
                return;
            }
            setTimeout(tick, 80);
        };
        setTimeout(tick, 80);
    });
}

function enqueueFrontend(cmd, args, timeoutMs = 30000) {
    const id = nextCommandId++;
    pendingCommands.push({ id, cmd, args: args || {} });
    return waitForFrontendCommand(id, timeoutMs);
}

async function dispatch(cmd, args) {
    switch (cmd) {
        case 'health':
            return { product: 'IRIS IDE', theia: '1.74.0', workspace: workspaceRoot };
        case 'getWorkspace':
            return { root: workspaceRoot };
        case 'setEditorState':
            editorState = normalizeEditorState(args);
            return { saved: true };
        case 'pollPendingCommands': {
            const limit = Math.min(parseInt(String(args.limit || 8), 10) || 8, 20);
            const batch = pendingCommands.splice(0, limit);
            return { commands: batch };
        }
        case 'completeCommand': {
            const id = parseInt(String(args.id || 0), 10);
            if (!id) throw new Error('completeCommand: id required');
            commandResults[id] = {
                result: args.result && typeof args.result === 'object' ? args.result : { value: args.result },
                error: args.error ? String(args.error) : '',
            };
            return { ok: true };
        }
        case 'getActiveEditor':
            return { editor: editorState };
        case 'getOpenEditors':
            return { editors: editorState ? [editorState] : [] };
        case 'getCursorPosition':
            return { line: editorState?.line || 1, column: editorState?.column || 1 };
        case 'getSelection':
            return { selection: editorState?.selection || null };
        case 'getDiagnostics':
            return { diagnostics: [] };
        case 'openFile':
        case 'gotoFile': {
            const rel = String(args.path || '');
            const abs = resolvePath(rel);
            if (!fs.existsSync(abs)) throw new Error(`file not found: ${rel}`);
            try {
                return await enqueueFrontend(cmd, { path: rel, abs, line: args.line || 1, column: args.column || 1 }, 3500);
            } catch {
                editorState = { uri: abs, path: rel, line: args.line || 1, column: args.column || 1 };
                return { path: abs, opened: true, via: 'bridge_fallback' };
            }
        }
        case 'saveFile':
        case 'saveAll':
            return { saved: true };
        case 'createFile': {
            const rel = String(args.path || '');
            const abs = resolvePath(rel);
            fs.mkdirSync(path.dirname(abs), { recursive: true });
            fs.writeFileSync(abs, String(args.content ?? ''), 'utf8');
            return { path: abs, created: true };
        }
        case 'deleteFile': {
            const abs = resolvePath(String(args.path || ''));
            fs.unlinkSync(abs);
            return { path: abs, deleted: true };
        }
        case 'renameFile': {
            const from = resolvePath(String(args.from || args.path || ''));
            const to = resolvePath(String(args.to || args.newPath || ''));
            fs.mkdirSync(path.dirname(to), { recursive: true });
            fs.renameSync(from, to);
            return { from, to };
        }
        case 'replaceSelection':
        case 'applyTextEdit':
        case 'insertText':
        case 'replaceRange': {
            const rel = String(args.path || editorState?.path || '');
            const abs = resolvePath(rel);
            let text = fs.readFileSync(abs, 'utf8');
            const insert = String(args.text ?? args.content ?? '');
            if (cmd === 'insertText' || cmd === 'replaceSelection') text += insert;
            else if (cmd === 'replaceRange') {
                const start = parseInt(String(args.start || 0), 10) || 0;
                const end = parseInt(String(args.end || text.length), 10) || text.length;
                text = text.slice(0, start) + insert + text.slice(end);
            } else text = insert;
            fs.writeFileSync(abs, text, 'utf8');
            return { path: abs, length: text.length };
        }
        case 'formatDocument':
            return { formatted: false };
        case 'gotoLine':
            return { line: parseInt(String(args.line || 1), 10) || 1 };
        case 'gotoSymbol':
        case 'findReferences':
            return { items: [] };
        case 'createTerminal':
            try {
                return await enqueueFrontend('createTerminal', { name: String(args.name || 'IRIS') }, 3500);
            } catch {
                return { name: String(args.name || 'IRIS'), created: false, via: 'bridge_fallback' };
            }
        case 'runTerminalCommand': {
            const command = String(args.command || args.cmd || '').trim();
            if (!command) {
                throw new Error('runTerminalCommand: empty command');
            }
            const cwd = args.cwd ? String(args.cwd) : workspaceRoot;
            // ponytail: execSync 폴백 금지 — Hermes/브릿지 셸이 아니라 Theia 통합 터미널만.
            return await enqueueFrontend('runTerminalCommand', { command, cwd }, 15000);
        }
        case 'getTerminalState':
            return { active: pendingCommands.some(c => c.cmd === 'runTerminalCommand') };
        case 'runTask':
            return { started: false };
        case 'getTaskState':
            return { running: false };
        case 'startDebug':
        case 'stopDebug':
        case 'continueDebug':
            return { hooked: true };
        case 'getGitStatus':
            try {
                return { porcelain: execSync('git status --porcelain', { cwd: workspaceRoot, encoding: 'utf8' }) };
            } catch {
                return { porcelain: '' };
            }
        case 'getGitDiff':
            try {
                const rel = String(args.path || '');
                const gitCmd = rel ? `git diff -- ${rel}` : 'git diff';
                return { diff: execSync(gitCmd, { cwd: workspaceRoot, encoding: 'utf8' }) };
            } catch {
                return { diff: '' };
            }
        default:
            throw new Error(`unknown command: ${cmd}`);
    }
}

// Theia(QWebEngine) 페이지는 브리지와 포트가 달라 cross-origin — ACAO 없으면 프런트엔드의
// setEditorState / pollPendingCommands fetch가 전부 차단된다 (control_surface와 동일 처리).
const CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Authorization, Content-Type',
};

const server = http.createServer(async (req, res) => {
    const send = (code, body) => {
        const raw = JSON.stringify(body);
        res.writeHead(code, {
            ...CORS_HEADERS,
            'Content-Type': 'application/json; charset=utf-8',
            'Content-Length': Buffer.byteLength(raw),
        });
        res.end(raw);
    };
    try {
        // preflight에는 Authorization이 실려오지 않는다 — 인증 앞에서 응답할 것.
        if (req.method === 'OPTIONS') {
            res.writeHead(204, { ...CORS_HEADERS, 'Content-Length': '0' });
            return res.end();
        }
        if (!authOk(req)) return send(401, { ok: false, error: 'unauthorized' });
        const url = new URL(req.url || '/', 'http://127.0.0.1');
        const cmd = url.pathname.replace(/^\/+/, '').split('/')[0] || 'health';
        const body = req.method === 'POST' ? await readBody(req) : {};
        const result = await dispatch(cmd, body);
        send(200, { ok: true, command: cmd, result });
    } catch (err) {
        send(400, { ok: false, error: err.message || String(err) });
    }
});

server.listen(wantPort > 0 ? wantPort : 0, '127.0.0.1', () => {
    const addr = server.address();
    const port = typeof addr === 'object' && addr ? addr.port : 0;
    writeState(port);
    console.log(`IRIS IDE bridge listening on 127.0.0.1:${port}`);
});

process.on('SIGINT', () => server.close(() => process.exit(0)));
process.on('SIGTERM', () => server.close(() => process.exit(0)));
