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
    const target = path.resolve(root, rel || '.');
    if (!target.startsWith(root)) throw new Error('path escapes workspace');
    return target;
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

async function dispatch(cmd, args) {
    switch (cmd) {
        case 'health':
            return { product: 'IRIS IDE', theia: '1.74.0', workspace: workspaceRoot };
        case 'getWorkspace':
            return { root: workspaceRoot };
        case 'setEditorState':
            editorState = args && typeof args === 'object' ? args : null;
            return { saved: true };
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
            editorState = { uri: abs, path: rel, line: args.line || 1, column: args.column || 1 };
            return { path: abs, opened: true };
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
        case 'runTerminalCommand': {
            const command = String(args.command || args.cmd || 'echo IRIS_IDE_TEST');
            const cwd = args.cwd ? resolvePath(String(args.cwd)) : workspaceRoot;
            const out = execSync(command, { cwd, encoding: 'utf8', timeout: 30000 });
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
        case 'getGitStatus':
            try {
                return { porcelain: execSync('git status --porcelain', { cwd: workspaceRoot, encoding: 'utf8' }) };
            } catch {
                return { porcelain: '' };
            }
        case 'getGitDiff':
            try {
                const rel = String(args.path || '');
                const cmd = rel ? `git diff -- ${rel}` : 'git diff';
                return { diff: execSync(cmd, { cwd: workspaceRoot, encoding: 'utf8' }) };
            } catch {
                return { diff: '' };
            }
        default:
            throw new Error(`unknown command: ${cmd}`);
    }
}

const server = http.createServer(async (req, res) => {
    const send = (code, body) => {
        const raw = JSON.stringify(body);
        res.writeHead(code, { 'Content-Type': 'application/json; charset=utf-8', 'Content-Length': Buffer.byteLength(raw) });
        res.end(raw);
    };
    try {
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
