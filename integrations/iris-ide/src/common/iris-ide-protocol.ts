/** IRIS IDE Bridge protocol — shared command names. */

export const IRIS_IDE_PRODUCT_NAME = 'IRIS IDE';

export interface IrisIdeBridgeHealth {
    ok: boolean;
    product: string;
    theia: string;
}

export interface IrisIdeEditorInfo {
    uri: string;
    path?: string;
    languageId: string;
    line: number;
    column: number;
    selection: { start: { line: number; column: number }; end: { line: number; column: number } } | null;
}

export interface IrisIdeDiagnostic {
    uri: string;
    message: string;
    severity: number;
    line: number;
    column: number;
}

export const IRIS_BRIDGE_COMMANDS = [
    'health',
    'getWorkspace',
    'getActiveEditor',
    'getOpenEditors',
    'getCursorPosition',
    'getSelection',
    'getDiagnostics',
    'openFile',
    'saveFile',
    'saveAll',
    'createFile',
    'deleteFile',
    'renameFile',
    'replaceSelection',
    'applyTextEdit',
    'insertText',
    'replaceRange',
    'formatDocument',
    'gotoFile',
    'gotoLine',
    'gotoSymbol',
    'findReferences',
    'createTerminal',
    'runTerminalCommand',
    'getTerminalState',
    'runTask',
    'getTaskState',
    'startDebug',
    'stopDebug',
    'continueDebug',
    'getGitStatus',
    'getGitDiff',
] as const;

export type IrisBridgeCommand = typeof IRIS_BRIDGE_COMMANDS[number];
