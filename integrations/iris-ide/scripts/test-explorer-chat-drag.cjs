'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const URI = require('@theia/core/lib/common/uri').default;
const { FileUri } = require('@theia/core/lib/common/file-uri');

// Run production handlers with Theia URI conversion and its real MIME order.
const source = ts.createSourceFile('contribution.ts', fs.readFileSync(path.join(
    __dirname, '../src/browser/iris-ide-frontend-contribution.ts'), 'utf8'), ts.ScriptTarget.Latest, true);
const names = new Set(['patchDataTransferForCompanionDrag', 'onTheiaExplorerDragMime',
    'urisFromDragDataTransfer', 'beginCompanionDrag', 'finishCompanionDrag', 'toComposerRef']);
const methods = source.statements.find(ts.isClassDeclaration).members
    .filter(node => names.has(node.name?.getText(source))).map(node => node.getText(source)).join('\n');
class DataTransfer {
    constructor() { this.data = new Map(); }
    setData(type, value) { this.data.set(type, value); }
    getData(type) { return this.data.get(type) || ''; }
}
const Handlers = vm.runInNewContext(ts.transpile(`class Handlers { ${methods} }; Handlers`, {
    target: ts.ScriptTarget.ES2020,
}), { DataTransfer, FileUri, ApplicationShell: {
    getDraggedEditorUris(dt) {
        const raw = dt.getData('theia-editor-dnd');
        return raw ? raw.split('\n').map(value => new URI(value)) : [];
    },
} });
const handlers = new Handlers();
handlers.companionDragPaths = [];
handlers.workspaceService = { tryGetRoots: () => [{ resource: FileUri.create('C:/workspace') }] };
handlers.editorManager = { currentEditor: { editor: { uri: FileUri.create('C:/wrong.py') } } };
const calls = [];
handlers.askIris = async (action, args) => { calls.push({ action, paths: Array.from(args.paths || []) }); };
handlers.patchDataTransferForCompanionDrag();

async function drag(paths) {
    const dt = new DataTransfer();
    const ids = paths.map(p => `/C:/workspace:/${p}`);
    dt.setData('tree-node', ids[0]);
    dt.setData('selected-tree-nodes', JSON.stringify(ids));
    assert.equal(handlers.companionDragPaths.length, 0, 'tree IDs must not start attachment');
    const uris = paths.map(FileUri.create);
    dt.setData('theia-editor-dnd', uris.map(u => u.toString()).join('\n'));
    const expected = uris.map(FileUri.fsPath);
    assert.deepEqual(Array.from(handlers.companionDragPaths), expected);
    assert.deepEqual(calls.at(-1), { action: 'chat.drag_start', paths: expected });
    assert.equal(dt.getData('text/uri-list'), uris.map(u => u.toString()).join('\n'));
    const root = FileUri.fsPath(FileUri.create('C:/workspace')).replace(/\\/g, '/');
    const first = expected[0].replace(/\\/g, '/');
    const ref = '@' + (first.startsWith(root + '/') ? first.slice(root.length + 1) : first);
    assert.equal(dt.getData('text/x-iris-ref'), ref);
    assert.equal(dt.getData('text/plain'), ref);
    assert.equal(dt.effectAllowed, 'copy');
    await handlers.finishCompanionDrag();
    assert.deepEqual(calls.at(-1), { action: 'chat.drag_end', paths: expected });
    assert.equal(handlers.companionDragPaths.length, 0);
}
(async () => {
    await drag(['C:/workspace/src/app.py']);
    await drag(['C:/workspace/한글 폴더/보고서 #1%.txt', 'C:/workspace/other/app.py']);
    await drag(['C:/outside/app.py']);
    await drag(['C:/workspace/IRIS_TEST_A']);
    await drag(['C:/workspace/한글 폴더', 'C:/outside/IRIS_TEST_B']);
    await drag(['C:/workspace']);
    const dt = new DataTransfer();
    dt.setData('theia-editor-dnd', 'untitled:Untitled-1');
    assert.equal(handlers.companionDragPaths.length, 0);
    assert.equal(handlers.urisFromDragDataTransfer(new DataTransfer()).length, 0,
        'missing MIME must not attach the focused editor');
    console.log('PASS: Explorer MIME order, exact filenames/paths, multiple files, Unicode, repeated drags');
})().catch(error => { console.error(error); process.exitCode = 1; });
