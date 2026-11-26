import { FileUri } from '@theia/core/lib/common/file-uri';
import { EditorManager, EditorWidget } from '@theia/editor/lib/browser';
import { MonacoEditor } from '@theia/monaco/lib/browser/monaco-editor';
import { DebugSessionManager } from '@theia/debug/lib/browser/debug-session-manager';
import { DebugState } from '@theia/debug/lib/browser/debug-session';
import { ProblemManager } from '@theia/markers/lib/browser/problem/problem-manager';
import { HostedPluginSupport } from '@theia/plugin-ext/lib/hosted/browser/hosted-plugin';
import { TaskService } from '@theia/task/lib/browser/task-service';

type CmdService = { executeCommand(id: string, ...args: unknown[]): Promise<unknown> };

function widgets(manager: EditorManager): EditorWidget[] {
    const bag = manager as unknown as { all?: EditorWidget[] };
    return Array.isArray(bag.all) ? bag.all : [];
}

function samePath(uriPath: string, abs: string, rel: string): boolean {
    const got = uriPath.replace(/\\/g, '/').toLowerCase();
    const wantAbs = abs.replace(/\\/g, '/').toLowerCase();
    const wantRel = rel.replace(/\\/g, '/').replace(/^\/+/, '').toLowerCase();
    if (wantAbs && got === wantAbs) {
        return true;
    }
    return Boolean(wantRel) && (got.endsWith('/' + wantRel) || got.endsWith(wantRel));
}

export function widgetFor(manager: EditorManager, args: Record<string, unknown>): EditorWidget | undefined {
    const abs = String(args.abs || '');
    const rel = String(args.path || '');
    if (!abs && !rel) {
        return manager.currentEditor;
    }
    for (const widget of widgets(manager)) {
        const uri = widget.editor?.uri;
        if (!uri) {
            continue;
        }
        if (samePath(FileUri.fsPath(uri), abs, rel)) {
            return widget;
        }
    }
    return undefined;
}

export function readProblems(manager: ProblemManager): Record<string, unknown>[] {
    return manager.findMarkers().slice(0, 200).map(marker => {
        const data = marker.data as {
            message?: string;
            severity?: number;
            source?: string;
            range?: { start?: { line?: number; character?: number }; end?: { line?: number; character?: number } };
        };
        const start = data.range?.start || {};
        const end = data.range?.end || {};
        return {
            uri: marker.uri,
            message: String(data.message || ''),
            severity: Number(data.severity || 0),
            source: String(data.source || ''),
            line: Number(start.line || 0) + 1,
            column: Number(start.character || 0) + 1,
            endLine: Number(end.line ?? start.line ?? 0) + 1,
            endColumn: Number(end.character ?? start.character ?? 0) + 1,
        };
    });
}

function commandService(widget: EditorWidget): CmdService {
    const editor = widget.editor as MonacoEditor;
    if (!editor || typeof editor.getControl !== 'function') {
        throw new Error('monaco editor control unavailable');
    }
    const control = editor.getControl() as unknown as { _commandService?: CmdService };
    if (!control._commandService) {
        throw new Error('monaco command service unavailable');
    }
    return control._commandService;
}

function modelOf(widget: EditorWidget): { uri: { toString(): string }; getValue(): string } {
    const editor = widget.editor as MonacoEditor;
    const model = editor.getControl().getModel();
    if (!model) {
        throw new Error('editor model missing');
    }
    return model;
}

function monacoPosition(widget: EditorWidget, args: Record<string, unknown>): { lineNumber: number; column: number } {
    const line = parseInt(String(args.line || ''), 10);
    const column = parseInt(String(args.column || ''), 10);
    if (line > 0) {
        return { lineNumber: line, column: column > 0 ? column : 1 };
    }
    const cursor = widget.editor.cursor;
    return { lineNumber: cursor.line + 1, column: cursor.character + 1 };
}

function asRecord(value: unknown): Record<string, unknown> {
    return value && typeof value === 'object' ? value as Record<string, unknown> : {};
}

function locItem(raw: unknown): Record<string, unknown> {
    const row = asRecord(raw);
    const range = asRecord(row.range);
    const start = asRecord(range.start);
    const end = asRecord(range.end);
    const line = Number(start.lineNumber ?? (Number(start.line ?? 0) + 1));
    const column = Number(start.column ?? (Number(start.character ?? 0) + 1));
    return {
        name: String(row.name || ''),
        uri: String(asRecord(row.uri).fsPath || row.uri || ''),
        line: line || 1,
        column: column || 1,
        endLine: Number(end.lineNumber ?? (Number(end.line ?? start.line ?? 0) + 1)) || line || 1,
        endColumn: Number(end.column ?? (Number(end.character ?? start.character ?? 0) + 1)) || column || 1,
    };
}

function flattenSymbols(raw: unknown, out: Record<string, unknown>[]): void {
    if (!Array.isArray(raw) || out.length >= 80) {
        return;
    }
    for (const item of raw) {
        if (out.length >= 80) {
            return;
        }
        const row = asRecord(item);
        out.push(locItem(item));
        flattenSymbols(row.children, out);
    }
}

export async function saveOne(manager: EditorManager, args: Record<string, unknown>): Promise<Record<string, unknown>> {
    const widget = widgetFor(manager, args);
    if (!widget?.editor?.document) {
        return { noEditor: true };
    }
    await widget.editor.document.save();
    return { saved: true, via: 'editor', path: FileUri.fsPath(widget.editor.uri) };
}

export async function saveEvery(manager: EditorManager): Promise<Record<string, unknown>> {
    const open = widgets(manager).filter(widget => widget.editor?.document);
    if (!open.length) {
        return { saved: false, reason: 'no open editor' };
    }
    let count = 0;
    for (const widget of open) {
        if (widget.editor.document.dirty) {
            await widget.editor.document.save();
            count += 1;
        }
    }
    return { saved: true, via: 'editor', count };
}

/**
 * Reload open editor buffers from disk. Dirty buffers are refused (no save/discard).
 * Paths not open are skipped — not a failure.
 */
export async function reloadFromDisk(
    manager: EditorManager,
    args: Record<string, unknown>,
): Promise<Record<string, unknown>> {
    const raw = args.paths ?? args.path;
    const paths = Array.isArray(raw)
        ? raw.map(item => String(item || '').trim()).filter(Boolean)
        : String(raw || '').trim()
            ? [String(raw).trim()]
            : [];
    if (!paths.length) {
        return { results: [], reloaded: 0, refused: 0 };
    }
    const results: Record<string, unknown>[] = [];
    let reloaded = 0;
    let refused = 0;
    for (const path of paths) {
        const widget = widgetFor(manager, { path, abs: path });
        if (!widget?.editor?.document) {
            results.push({ path, skipped: true, reason: 'not open' });
            continue;
        }
        const doc = widget.editor.document as {
            dirty?: boolean;
            revert?: (options?: { force?: boolean }) => Promise<void>;
        };
        if (doc.dirty) {
            refused += 1;
            results.push({
                path: FileUri.fsPath(widget.editor.uri),
                reloaded: false,
                reason: 'dirty',
            });
            continue;
        }
        if (typeof doc.revert !== 'function') {
            refused += 1;
            results.push({
                path: FileUri.fsPath(widget.editor.uri),
                reloaded: false,
                reason: 'revert unavailable',
            });
            continue;
        }
        await doc.revert();
        reloaded += 1;
        results.push({
            path: FileUri.fsPath(widget.editor.uri),
            reloaded: true,
            via: 'editor',
        });
    }
    return { results, reloaded, refused, via: 'editor' };
}

export async function editBuffer(
    manager: EditorManager,
    cmd: string,
    args: Record<string, unknown>,
): Promise<Record<string, unknown>> {
    const widget = widgetFor(manager, args);
    if (!widget?.editor) {
        return { noEditor: true };
    }
    const editor = widget.editor;
    const insert = String(args.text ?? args.content ?? '');
    const doc = editor.document;
    let range: { start: { line: number; character: number }; end: { line: number; character: number } } = editor.selection;
    let applied = 'selection';
    if (cmd === 'insertText') {
        const cursor = editor.cursor;
        range = { start: cursor, end: cursor };
        applied = 'cursor';
    } else if (cmd === 'replaceRange') {
        const start = parseInt(String(args.start || 0), 10) || 0;
        const end = parseInt(String(args.end ?? doc.getText().length), 10);
        range = { start: doc.positionAt(start), end: doc.positionAt(end) };
        applied = 'range';
    } else if (cmd === 'applyTextEdit') {
        const text = doc.getText();
        range = { start: doc.positionAt(0), end: doc.positionAt(text.length) };
        applied = 'document';
    }
    const ok = editor.executeEdits([{ range, newText: insert }]);
    if (!ok) {
        throw new Error(`${cmd} rejected by editor`);
    }
    return { via: 'editor', applied, path: FileUri.fsPath(editor.uri) };
}

export async function writeFile(manager: EditorManager, args: Record<string, unknown>): Promise<Record<string, unknown>> {
    const doc = widgetFor(manager, args)?.editor?.document;
    if (!doc) {
        throw new Error('file must be open in the editor');
    }
    if (doc.dirty) {
        throw new Error('open editor has unsaved (dirty) changes');
    }
    const result = await editBuffer(manager, 'applyTextEdit', args);
    await doc.save();
    return { ...result, saved: true };
}

export async function formatDocument(manager: EditorManager, args: Record<string, unknown>): Promise<Record<string, unknown>> {
    const widget = widgetFor(manager, args);
    if (!widget?.editor) {
        throw new Error('no open editor to format');
    }
    const model = modelOf(widget);
    const edits = await commandService(widget).executeCommand('_executeFormatDocumentProvider', model.uri, {
        tabSize: 4,
        insertSpaces: true,
    });
    const list = Array.isArray(edits) ? edits : [];
    if (!list.length) {
        return { formatted: false, reason: 'no formatting provider', via: 'theia' };
    }
    const lspEdits = list.map(item => {
        const row = asRecord(item);
        const range = asRecord(row.range);
        if (typeof asRecord(range.start).line === 'number') {
            return { range, newText: String(row.newText ?? row.text ?? '') };
        }
        return {
            range: {
                start: {
                    line: Number(range.startLineNumber || 1) - 1,
                    character: Number(range.startColumn || 1) - 1,
                },
                end: {
                    line: Number(range.endLineNumber || 1) - 1,
                    character: Number(range.endColumn || 1) - 1,
                },
            },
            newText: String(row.newText ?? row.text ?? ''),
        };
    });
    const ok = widget.editor.executeEdits(lspEdits as never);
    if (!ok) {
        throw new Error('format edits rejected by editor');
    }
    return { formatted: true, via: 'editor', count: lspEdits.length };
}

export async function gotoLine(manager: EditorManager, args: Record<string, unknown>): Promise<Record<string, unknown>> {
    const widget = manager.currentEditor;
    if (!widget?.editor) {
        throw new Error('no open editor');
    }
    const line = Math.max(1, parseInt(String(args.line || 1), 10) || 1);
    const pos = { line: line - 1, character: 0 };
    widget.editor.selection = { start: pos, end: pos } as never;
    widget.editor.cursor = pos as never;
    widget.editor.revealPosition(pos as never);
    return { line, via: 'editor' };
}

export async function querySymbols(manager: EditorManager, args: Record<string, unknown>): Promise<Record<string, unknown>> {
    const widget = widgetFor(manager, args) || manager.currentEditor;
    if (!widget?.editor) {
        throw new Error('no open editor');
    }
    const model = modelOf(widget);
    const raw = await commandService(widget).executeCommand('_executeDocumentSymbolProvider', model.uri);
    const items: Record<string, unknown>[] = [];
    flattenSymbols(raw, items);
    const q = String(args.symbol || '').trim().toLowerCase();
    const matched = q ? items.filter(item => String(item.name || '').toLowerCase().includes(q)) : items;
    return { items: matched, via: 'theia', queried: true };
}

export async function queryLocations(
    manager: EditorManager,
    command: string,
    args: Record<string, unknown>,
): Promise<Record<string, unknown>> {
    const widget = widgetFor(manager, args) || manager.currentEditor;
    if (!widget?.editor) {
        throw new Error('no open editor');
    }
    const model = modelOf(widget);
    const position = monacoPosition(widget, args);
    const raw = await commandService(widget).executeCommand(command, model.uri, position);
    const items = (Array.isArray(raw) ? raw : []).slice(0, 80).map(locItem);
    return { items, via: 'theia', queried: true, line: position.lineNumber, column: position.column };
}

export async function runNamedTask(tasks: TaskService, args: Record<string, unknown>): Promise<Record<string, unknown>> {
    const label = String(args.name || args.label || '').trim();
    if (!label) {
        throw new Error('runTask: name required');
    }
    const token = tasks.startUserAction();
    const configured = await tasks.getConfiguredTasks(token);
    const match = configured.find(task => task.label === label);
    if (!match) {
        throw new Error(`task not found: ${label}`);
    }
    await tasks.runConfiguredTask(token, match._scope, match.label);
    return { started: true, label, via: 'theia' };
}

export async function taskState(tasks: TaskService): Promise<Record<string, unknown>> {
    const running = await tasks.getRunningTasks();
    return {
        running: running.length > 0,
        tasks: running.map(task => ({ taskId: task.taskId, label: task.config?.label || '' })),
        via: 'theia',
    };
}

export async function startDebug(sessions: DebugSessionManager, args: Record<string, unknown>): Promise<Record<string, unknown>> {
    const name = String(args.name || args.configuration || '').trim();
    if (!name) {
        throw new Error('startDebug: configuration name required');
    }
    const session = await sessions.start(name);
    if (!session) {
        throw new Error('debug session did not start');
    }
    if (session === true) {
        return { started: true, name, via: 'theia' };
    }
    return { started: true, name, id: session.id, via: 'theia' };
}

export async function stopDebug(sessions: DebugSessionManager): Promise<Record<string, unknown>> {
    if (!sessions.currentSession) {
        throw new Error('no debug session');
    }
    await sessions.terminateSession();
    return { stopped: true, via: 'theia' };
}

export async function continueDebug(sessions: DebugSessionManager): Promise<Record<string, unknown>> {
    const session = sessions.currentSession;
    if (!session) {
        throw new Error('no debug session');
    }
    if (sessions.state !== DebugState.Stopped) {
        throw new Error('debug session is not paused');
    }
    const thread = sessions.currentThread;
    if (!thread) {
        throw new Error('no paused debug thread');
    }
    await thread.continue();
    return { continued: true, via: 'theia' };
}

export function pluginLoaded(plugins: HostedPluginSupport, args: Record<string, unknown>): Record<string, unknown> {
    const id = String(args.id || '').trim();
    if (!id) {
        throw new Error('pluginLoaded: id required');
    }
    type PluginId = Parameters<HostedPluginSupport['getPlugin']>[0];
    const found = plugins.getPlugin(id as PluginId) || plugins.getPlugin(`vscode:extension/${id}` as PluginId);
    return { id, loaded: Boolean(found), via: 'theia' };
}
