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
    /** True when the Monaco/Theia buffer has unsaved edits. */
    dirty?: boolean;
    /** Monaco model getVersionId when available. */
    version?: number;
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
    'setWorkspace',
    'getActiveEditor',
    'getOpenEditors',
    'getCursorPosition',
    'getSelection',
    'getDiagnostics',
    'setDiagnostics',
    'openFile',
    'saveFile',
    'saveAll',
    'reloadFromDisk',
    'createFile',
    'writeFile',
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
    'gotoDefinition',
    'createTerminal',
    'runTerminalCommand',
    'appendTerminalOutput',
    'getTerminalState',
    'runTask',
    'getTaskState',
    'startDebug',
    'stopDebug',
    'continueDebug',
    'pluginLoaded',
    'getGitStatus',
    'getGitDiff',
    'pollPendingCommands',
    'completeCommand',
] as const;

export type IrisBridgeCommand = typeof IRIS_BRIDGE_COMMANDS[number];
