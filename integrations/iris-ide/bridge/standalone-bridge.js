#!/usr/bin/env node
/** Standalone IRIS IDE bridge — 127.0.0.1 only. Started by IrisIdeRuntimeManager. */
'use strict';

const crypto = require('crypto');
const fs = require('fs');
const http = require('http');
const path = require('path');
const { execSync } = require('child_process');

const envWorkspace = (process.env.IRIS_IDE_WORKSPACE || '').trim();
let workspaceRoot = path.resolve(envWorkspace || process.cwd());
// Welcome vs folder-open — sandbox root may stay populated even when closed.
let workspaceOpen = Boolean(envWorkspace);
const token = (process.env.IRIS_IDE_BRIDGE_TOKEN || '').trim() || crypto.randomBytes(24).toString('hex');
const wantPort = parseInt(process.env.IRIS_IDE_BRIDGE_PORT || '0', 10);
const stateFile = (process.env.IRIS_IDE_STATE_FILE || '').trim();

let editorState = null;
let openEditors = [];
let pendingCommands = [];
let commandResults = {};
let nextCommandId = 1;
let boundPort = 0;
let lastFrontendPollAt = 0;
// null = 프런트가 마커를 아직 안 읽음. [] 는 읽었는데 문제가 없을 때만.
let diagnosticsReport = null;

function writeState(port) {
    boundPort = port || boundPort;
    if (!stateFile) return;
    let existing = {};
    try {
        if (fs.existsSync(stateFile)) {
            existing = JSON.parse(fs.readFileSync(stateFile, 'utf8'));
        }
    } catch (_) { /* ignore */ }
    const payload = {
        ...existing,
        bridge_port: boundPort,
        token,
        workspace: workspaceRoot,
        workspace_open: workspaceOpen,
        bridge_pid: process.pid,
    };
    fs.mkdirSync(path.dirname(stateFile), { recursive: true });
    fs.writeFileSync(stateFile, JSON.stringify(payload, null, 2));
}

function isInsideWorkspace(root, target) {
    const rel = path.relative(path.resolve(root), path.resolve(target));
    if (rel === '') return true;
    if (rel === '..' || rel.startsWith('..' + path.sep) || path.isAbsolute(rel)) return false;
    return true;
}

function resolvePath(rel) {
    const root = path.resolve(workspaceRoot);
    const raw = String(rel || '').trim();
    const target = path.isAbsolute(raw) ? path.resolve(raw) : path.resolve(root, raw || '.');
    if (!isInsideWorkspace(root, target)) throw new Error('path escapes workspace');
    return target;
}

/** 식별자(path|uri) 없는 상태는 「편집기 없음」이다 — 프런트엔드는 편집기가 닫히면 {}를 보낸다. */
function normalizeEditorState(info) {
    if (!info || typeof info !== 'object' || Array.isArray(info)) return null;
    const copy = Object.assign({}, info);
    delete copy.editors;
    const hasId = Boolean(String(copy.path || '').trim() || String(copy.uri || '').trim());
    return hasId ? copy : null;
}

function normalizeEditorList(list, fallback) {
    const out = [];
    if (Array.isArray(list)) {
        for (const item of list) {
            const row = normalizeEditorState(item);
            if (row) out.push(row);
        }
    }
    if (!out.length && fallback) out.push(fallback);
    return out;
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
                const age = lastFrontendPollAt ? (Date.now() - lastFrontendPollAt) : -1;
                const hint = lastFrontendPollAt
                    ? `last frontend poll ${age}ms ago`
                    : 'no frontend poll yet — is IRIS IDE loaded?';
                const timed = new Error(`frontend command timeout (${hint})`);
                timed.code = 'timeout';
                reject(timed);
                return;
            }
            setTimeout(tick, 80);
        };
        setTimeout(tick, 80);
    });
}

function waitForPoll(ms) {
    return new Promise(resolve => {
        const start = Date.now();
        const tick = () => {
            if (lastFrontendPollAt || Date.now() - start >= ms) {
                resolve(Boolean(lastFrontendPollAt));
                return;
            }
            setTimeout(tick, 80);
        };
        setTimeout(tick, 80);
    });
}

async function enqueueFrontend(cmd, args, timeoutMs = 30000, pollWaitMs = 800) {
    if (!lastFrontendPollAt) {
        const seen = await waitForPoll(pollWaitMs);
        if (!seen) {
            throw new Error('no frontend poll yet — is IRIS IDE loaded?');
        }
    }
    const id = nextCommandId++;
    pendingCommands.push({ id, cmd, args: args || {} });
    return waitForFrontendCommand(id, timeoutMs);
}

function readExitLog(cwd, timeoutMs) {
    const log = path.join(cwd || workspaceRoot, '.iris', 'last_run.log');
    const deadline = Date.now() + timeoutMs;
    const pull = () => {
        if (!fs.existsSync(log)) return '';
        return fs.readFileSync(log, 'utf8');
    };
    return new Promise(resolve => {
        const tick = () => {
            const text = pull();
            const match = text.match(/^IRIS_EXIT:(-?\d+)\s*$/m);
            if (match) {
                const output = text.replace(/^IRIS_EXIT:(-?\d+)\s*$/m, '').trim().slice(0, 8000);
                resolve({ completed: true, exit_code: parseInt(match[1], 10), output });
                return;
            }
            if (Date.now() >= deadline) {
                resolve({ completed: false, exit_code: null, output: text.trim().slice(0, 8000) });
                return;
            }
            setTimeout(tick, 200);
        };
        tick();
    });
}

function diskEdit(cmd, args) {
    const rel = String(args.path || editorState?.path || '');
    const abs = resolvePath(rel);
    let text = fs.readFileSync(abs, 'utf8');
    const insert = String(args.text ?? args.content ?? '');
    let applied = 'replace';
    if (cmd === 'insertText' || cmd === 'replaceSelection') {
        text += insert;
        applied = 'append';
    } else if (cmd === 'replaceRange') {
        const start = parseInt(String(args.start || 0), 10) || 0;
        const end = parseInt(String(args.end || text.length), 10) || text.length;
        text = text.slice(0, start) + insert + text.slice(end);
        applied = 'range';
    } else {
        text = insert;
    }
    fs.writeFileSync(abs, text, 'utf8');
    return { path: abs, length: text.length, via: 'disk', applied };
}

async function dispatch(cmd, args) {
    switch (cmd) {
        case 'health':
            return { product: 'IRIS IDE', theia: '1.74.0', workspace: workspaceRoot };
        case 'getWorkspace':
            return { root: workspaceRoot, opened: workspaceOpen };
        case 'setWorkspace': {
            // Frontend pushes File > Open/Close Folder changes so bridge state stays live.
            const root = String(args.root || '').trim();
            if (root) {
                const abs = path.resolve(root);
                if (!fs.existsSync(abs) || !fs.statSync(abs).isDirectory()) {
                    throw new Error(`not a directory: ${root}`);
                }
                workspaceRoot = abs;
            }
            workspaceOpen = args.opened !== undefined ? Boolean(args.opened) : Boolean(root);
            writeState(boundPort);
            return { root: workspaceRoot, opened: workspaceOpen };
        }
        case 'setEditorState':
            editorState = normalizeEditorState(args);
            openEditors = normalizeEditorList(args.editors, editorState);
            return { saved: true };
        case 'pollPendingCommands': {
            lastFrontendPollAt = Date.now();
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
            return { editors: openEditors };
        case 'getCursorPosition':
            return { line: editorState?.line || 1, column: editorState?.column || 1 };
        case 'getSelection':
            return { selection: editorState?.selection || null };
        case 'setDiagnostics':
            diagnosticsReport = Array.isArray(args.diagnostics) ? args.diagnostics : [];
            return { reported: true, count: diagnosticsReport.length };
        case 'getDiagnostics':
            if (diagnosticsReport === null) return { diagnostics: null, reported: false };
            return { diagnostics: diagnosticsReport, reported: true };
        case 'openFile':
        case 'gotoFile': {
            const rel = String(args.path || '');
            const abs = resolvePath(rel);
            if (!fs.existsSync(abs)) throw new Error(`file not found: ${rel}`);
            // No bridge_fallback: timeout/miss is a hard error (HTTP 400), not a fake open.
            return await enqueueFrontend(cmd, { path: rel, abs, line: args.line || 1, column: args.column || 1 }, 3500);
        }
        case 'saveFile':
        case 'saveAll': {
            // No disk-only soft success: without a frontend editor flush this is a hard error
            // (same honesty contract as openFile — no via:'disk' saved:true disguise).
            const front = await enqueueFrontend(cmd, args, 4000);
            if (!front || front.saved !== true) {
                throw new Error(String((front && front.reason) || 'save failed'));
            }
            if (front.via === 'disk' || front.editor === false) {
                throw new Error('IRIS IDE editor did not save (disk-only save is not an editor flush)');
            }
            return front;
        }
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
        case 'insertText': {
            // No disk-append soft success: selection/insert/document edits need Monaco.
            const edited = await enqueueFrontend(cmd, args, 4000);
            if (!edited || edited.noEditor) {
                throw new Error(String((edited && (edited.reason || edited.error)) || 'IRIS IDE editor did not apply buffer edit'));
            }
            if (edited.via !== 'editor') {
                throw new Error('IRIS IDE buffer edit requires via=editor (disk append is not a selection replace)');
            }
            return edited;
        }
        case 'replaceRange': {
            // Disk range write kept for non-ide.edit callers; ide.edit rejects via≠editor.
            try {
                const edited = await enqueueFrontend(cmd, args, 4000);
                if (!edited || !edited.noEditor) return edited;
            } catch (err) {
                if (!String(err && err.message || err).includes('no frontend poll')) throw err;
            }
            return diskEdit(cmd, args);
        }
        case 'formatDocument':
        case 'gotoLine':
        case 'gotoSymbol':
        case 'findReferences':
        case 'gotoDefinition':
            return await enqueueFrontend(cmd, args, 8000);
        case 'createTerminal':
            return await enqueueFrontend('createTerminal', { name: String(args.name || 'IRIS') }, 3500);
        case 'runTerminalCommand': {
            const command = String(args.command || args.cmd || '').trim();
            const argv = Array.isArray(args.argv) ? args.argv.map(item => String(item)) : [];
            if (!command && argv.length === 0) {
                throw new Error('runTerminalCommand: empty command');
            }
            const cwd = args.cwd ? String(args.cwd) : workspaceRoot;
            // ponytail: execSync 폴백 금지 — Hermes/브릿지 셸이 아니라 Theia 통합 터미널만.
            const sent = await enqueueFrontend('runTerminalCommand', { command, cwd, argv }, 15000);
            const log = await readExitLog(cwd, 12000);
            return { ...sent, ...log, queued: false };
        }
        case 'getTerminalState':
            return await enqueueFrontend('getTerminalState', {}, 3000);
        case 'runTask':
        case 'getTaskState':
        case 'startDebug':
        case 'stopDebug':
        case 'continueDebug':
        case 'pluginLoaded':
            return await enqueueFrontend(cmd, args, cmd === 'pluginLoaded' ? 8000 : 20000, cmd === 'pluginLoaded' ? 7000 : 800);
        case 'getGitStatus':
            try {
                return {
                    porcelain: execSync('git status --porcelain', {
                        cwd: workspaceRoot,
                        encoding: 'utf8',
                        windowsHide: true,
                    }),
                };
            } catch {
                return { porcelain: '' };
            }
        case 'getGitDiff':
            try {
                const rel = String(args.path || '');
                const gitCmd = rel ? `git diff -- ${rel}` : 'git diff';
                return {
                    diff: execSync(gitCmd, {
                        cwd: workspaceRoot,
                        encoding: 'utf8',
                        windowsHide: true,
                    }),
                };
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
        const fail = { ok: false, error: err.message || String(err) };
        if (err && err.code === 'timeout') fail.code = 'timeout';
        send(400, fail);
    }
});

if (process.argv[2] === '--resolve-check') {
    const root = path.resolve(process.env.IRIS_IDE_WORKSPACE || process.cwd());
    workspaceRoot = root;
    const inside = resolvePath('apple.txt');
    if (!inside.toLowerCase().endsWith(`${path.sep}apple.txt`.toLowerCase())) process.exit(2);
    resolvePath(path.join(root, 'apple.txt'));
    for (const bad of ['../outside.txt', path.resolve(root, '..', 'outside.txt')]) {
        try {
            resolvePath(bad);
            process.exit(4);
        } catch (err) {
            if (!String(err.message).includes('path escapes workspace')) process.exit(5);
        }
    }
    console.log('resolvePath ok');
    process.exit(0);
}

server.listen(wantPort > 0 ? wantPort : 0, '127.0.0.1', () => {
    const addr = server.address();
    const port = typeof addr === 'object' && addr ? addr.port : 0;
    writeState(port);
    console.log(`IRIS IDE bridge listening on 127.0.0.1:${port}`);
});

process.on('SIGINT', () => server.close(() => process.exit(0)));
process.on('SIGTERM', () => server.close(() => process.exit(0)));
