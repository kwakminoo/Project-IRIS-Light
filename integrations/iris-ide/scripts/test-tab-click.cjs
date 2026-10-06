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
const names = new Set(['onTabPointerDown', 'onTabPointerMove', 'onTabPointerUp']);
const methods = declaration.members.filter(node => names.has(node.name?.getText(source)))
    .map(node => node.getText(source)).join('\n');
const compiled = ts.transpile(`class Handlers { ${methods} }; Handlers`, {
    target: ts.ScriptTarget.ES2020,
});
const Handlers = vm.runInNewContext(compiled);
const handlers = new Handlers();
const editors = ['a.py', 'b.py', 'c.py'].map(id => ({ id, editor: { uri: { id } } }));
let reopenCount = 0;
handlers.editorManager = {
    all: editors,
    currentEditor: editors[0],
    open() { reopenCount++; },
};
handlers.isEditorTabTarget = target => target.tab;
handlers.beginCompanionDrag = uris => { handlers.draggedUri = uris[0]; };
handlers.finishCompanionDrag = () => { handlers.finished = true; };
function event(editor, close = false) {
    const tab = { id: `shell-tab-${editor.id}`, setAttribute() {}, removeAttribute() {} };
    return { button: 0, clientX: 10, clientY: 10, target: {
        tab, closest: () => close ? {} : null,
    } };
}
// Each single click starts with the previous editor focused. Native Lumino
// selects the new tab between the document capture handler and pointerup.
for (const index of [1, 2, 0, 2, 1, 0]) {
    const editor = editors[index];
    const ev = event(editor);
    handlers.onTabPointerDown(ev);
    assert.equal(handlers.tabDrag.uri, editor.editor.uri);
    handlers.editorManager.currentEditor = editor;
    handlers.onTabPointerUp(ev);
    assert.equal(handlers.editorManager.currentEditor, editor);
    assert.equal(reopenCount, 0, 'single click must not reopen an editor');
}
handlers.onTabPointerDown(event(editors[1], true));
assert.equal(handlers.tabDrag, null, 'close button must not start a file gesture');
handlers.onTabPointerDown(event({ id: 'settings' }));
assert.equal(handlers.tabDrag, null, 'screen tabs must not use the focused file URI');
handlers.onTabPointerDown(event(editors[2]));
handlers.onTabPointerMove({ clientX: 18, clientY: 10 });
assert.equal(handlers.draggedUri, editors[2].editor.uri);
handlers.onTabPointerUp({});
assert.equal(handlers.finished, true);
assert.equal(reopenCount, 0);
console.log('PASS: six alternating single clicks, close/screen tabs, and file drag');
