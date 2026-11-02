'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

// Exercise the production pointer handlers without booting the Theia backend.
const source = ts.createSourceFile('contribution.ts', fs.readFileSync(path.join(
    __dirname, '../src/browser/iris-ide-frontend-contribution.ts'), 'utf8'),
    ts.ScriptTarget.Latest, true);
const declaration = source.statements.find(node => ts.isClassDeclaration(node));
const names = new Set([
    'isEditorTabTarget', 'uriFromShellTab', 'widgetIdFromShellTab',
    'onTabPointerDown', 'onTabPointerMove', 'onTabPointerUp', 'onTabHtml5DragStart',
]);
const methods = declaration.members.filter(node => names.has(node.name?.getText(source)))
    .map(node => node.getText(source)).join('\n');
const compiled = ts.transpile(`class Handlers { ${methods} }; Handlers`, {
    target: ts.ScriptTarget.ES2020,
});
const Handlers = vm.runInNewContext(compiled);
const handlers = new Handlers();
const editors = ['a.py', 'b.py', 'c.py'].map(id => ({ id, editor: { uri: { id, scheme: 'file' } } }));
let reopenCount = 0;
const shellWidgets = new Map();
handlers.editorManager = {
    all: editors,
    currentEditor: editors[0],
    open() { reopenCount++; },
};
handlers.shell = {
    getWidgetById(id) { return shellWidgets.get(id); },
};
handlers.beginCompanionDrag = uris => { handlers.draggedUri = uris[0]; };
handlers.finishCompanionDrag = () => { handlers.finished = true; };
handlers.toComposerRef = uri => `@${uri.id || uri}`;
handlers.ensureTabDragGhost = () => ({});
handlers.escapeHtml = s => s;

/** Minimal DOM closest — same substring rules browsers use for [class*="…"]. */
function el(className, id = '', parent = null) {
    const node = {
        className,
        id,
        parentElement: parent,
        closest(selector) {
            let cur = this;
            while (cur) {
                const classes = String(cur.className || '').split(/\s+/).filter(Boolean);
                for (const part of selector.split(',').map(s => s.trim())) {
                    if (part.startsWith('.') && classes.includes(part.slice(1))) {
                        return cur;
                    }
                    const m = /^\[class\*="(.+)"\]$/.exec(part);
                    if (m && classes.some(c => c.includes(m[1]))) {
                        return cur;
                    }
                }
                cur = cur.parentElement;
            }
            return null;
        },
    };
    return node;
}

function tabTree(editorId) {
    const tab = el('lm-TabBar-tab', `shell-tab-${editorId}`);
    const labelWrap = el('theia-tab-icon-label', '', tab);
    const label = el('lm-TabBar-tabLabel', '', labelWrap);
    const close = el('lm-TabBar-tabCloseIcon', '', tab);
    tab.setAttribute = () => {};
    tab.removeAttribute = () => {};
    return { tab, label, close };
}

function pointerEvent(target, xy = { clientX: 10, clientY: 10 }) {
    return { button: 0, clientX: xy.clientX, clientY: xy.clientY, target };
}

// Pointerdown on the visible label (not the li) must still arm the file URI.
// Broad [class*="TabBar-tab"] matches lm-TabBar-tabLabel first → empty id → abort.
{
    const editor = editors[1];
    const { label } = tabTree(editor.id);
    handlers.tabDrag = null;
    handlers.onTabPointerDown(pointerEvent(label));
    assert.ok(handlers.tabDrag, 'label click must arm tab drag');
    assert.equal(handlers.tabDrag.uri, editor.editor.uri);
    handlers.onTabPointerMove({ clientX: 20, clientY: 10 });
    assert.equal(handlers.draggedUri, editor.editor.uri);
    handlers.onTabPointerUp({});
    assert.equal(handlers.finished, true);
}

// Each single click starts with the previous editor focused. Native Lumino
// selects the new tab between the document capture handler and pointerup.
handlers.draggedUri = undefined;
handlers.finished = false;
for (const index of [1, 2, 0, 2, 1, 0]) {
    const editor = editors[index];
    const { tab } = tabTree(editor.id);
    const ev = pointerEvent(tab);
    handlers.onTabPointerDown(ev);
    assert.equal(handlers.tabDrag.uri, editor.editor.uri);
    handlers.editorManager.currentEditor = editor;
    handlers.onTabPointerUp(ev);
    assert.equal(handlers.editorManager.currentEditor, editor);
    assert.equal(reopenCount, 0, 'single click must not reopen an editor');
}
{
    const { close } = tabTree(editors[1].id);
    handlers.onTabPointerDown(pointerEvent(close));
    assert.equal(handlers.tabDrag, null, 'close button must not start a file gesture');
}
handlers.onTabPointerDown(pointerEvent(el('lm-TabBar-tab', 'shell-tab-settings')));
assert.equal(handlers.tabDrag, null, 'screen tabs must not use the focused file URI');
{
    const { tab } = tabTree(editors[2].id);
    handlers.onTabPointerDown(pointerEvent(tab));
    handlers.onTabPointerMove({ clientX: 18, clientY: 10 });
    assert.equal(handlers.draggedUri, editors[2].editor.uri);
    handlers.onTabPointerUp({});
    assert.equal(handlers.finished, true);
}
assert.equal(reopenCount, 0);

// PDF / any Navigatable tab — not in EditorManager; shell widget carries getResourceUri.
{
    const pdfUri = { id: 'doc.pdf', scheme: 'file', toString: () => 'file:///doc.pdf' };
    const pdfWidgetId = 'iris-pdf:file:///doc.pdf';
    shellWidgets.set(pdfWidgetId, { getResourceUri: () => pdfUri });
    const { label } = tabTree(pdfWidgetId);
    handlers.tabDrag = null;
    handlers.draggedUri = undefined;
    handlers.onTabPointerDown(pointerEvent(label));
    assert.ok(handlers.tabDrag, 'PDF tab label must arm companion drag');
    assert.equal(handlers.tabDrag.uri, pdfUri);
    handlers.onTabPointerMove({ clientX: 20, clientY: 10 });
    assert.equal(handlers.draggedUri, pdfUri);
    handlers.onTabPointerUp({});
    shellWidgets.clear();
}

// Tab HTML5 drag must advertise copy (same as explorer), not copyMove → forbid cursor.
{
    const editor = editors[0];
    const { tab } = tabTree(editor.id);
    handlers.tabDrag = { uri: editor.editor.uri, x: 0, y: 0, armed: false, tab };
    const dt = {
        effectAllowed: '',
        setData() {},
        setDragImage() {},
    };
    handlers.onTabHtml5DragStart({ target: tab, dataTransfer: dt });
    assert.equal(dt.effectAllowed, 'copy', 'tab HTML5 must use copy like explorer');
}

console.log('PASS: label+li tab drag, six clicks, close/screen tabs, pdf+copy cursor');
