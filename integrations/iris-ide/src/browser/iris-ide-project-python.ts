export type PathExists = (absPath: string) => boolean | Promise<boolean>;

const PYTHON_EXTS = new Set(['py', 'pyw']);

export function parentDir(absPath: string): string {
    const norm = absPath.replace(/\\/g, '/');
    const i = norm.lastIndexOf('/');
    if (i <= 0) {
        return absPath;
    }
    const parent = norm.slice(0, i);
    return absPath.includes('\\') ? parent.replace(/\//g, '\\') : parent;
}

function isWinPathStyle(path: string): boolean {
    const trimmed = path.replace(/[\\/]+$/, '');
    return /^[a-zA-Z]:[\\/]/.test(trimmed) || trimmed.includes('\\');
}

export function venvPythonAt(root: string): string {
    const trimmed = root.replace(/[\\/]+$/, '');
    if (isWinPathStyle(trimmed)) {
        return `${trimmed}\\.venv\\Scripts\\python.exe`;
    }
    return `${trimmed}/.venv/bin/python`;
}

/** Prefer user/system launcher when no project .venv — never bare `python` (Iris PATH). */
export function defaultPythonArgv(absPath: string): string[] {
    if (isWinPathStyle(absPath)) {
        return ['py', '-3', absPath];
    }
    return ['python3', absPath];
}

function underRoot(fileAbs: string, root: string): boolean {
    const file = fileAbs.replace(/\\/g, '/').toLowerCase();
    const base = root.replace(/\\/g, '/').replace(/\/+$/, '').toLowerCase();
    return file === base || file.startsWith(base + '/');
}

export async function findProjectPython(
    fileAbs: string,
    workspaceRoots: string[],
    exists: PathExists,
): Promise<{ python: string; root: string } | undefined> {
    const ordered: string[] = [];
    const seen = new Set<string>();
    const push = (p: string): void => {
        const key = p.replace(/\\/g, '/').replace(/\/+$/, '').toLowerCase();
        if (!key || seen.has(key)) {
            return;
        }
        seen.add(key);
        ordered.push(p);
    };

    for (const root of workspaceRoots) {
        if (underRoot(fileAbs, root)) {
            push(root);
        }
    }
    let dir = parentDir(fileAbs);
    for (let n = 0; n < 64; n++) {
        push(dir);
        const up = parentDir(dir);
        if (up === dir) {
            break;
        }
        dir = up;
    }

    for (const root of ordered) {
        const python = venvPythonAt(root);
        if (await exists(python)) {
            return { python, root };
        }
    }
    return undefined;
}

export async function argvForRunnableFile(
    absPath: string,
    workspaceRoots: string[],
    exists: PathExists,
): Promise<{ argv: string[]; cwd: string }> {
    const ext = absPath.replace(/\\/g, '/').split('.').pop()?.toLowerCase() ?? '';
    const fileDir = parentDir(absPath);
    if (PYTHON_EXTS.has(ext)) {
        const hit = await findProjectPython(absPath, workspaceRoots, exists);
        if (hit) {
            return { argv: [hit.python, absPath], cwd: hit.root };
        }
        return { argv: defaultPythonArgv(absPath), cwd: fileDir };
    }
    if (ext === 'js' || ext === 'mjs' || ext === 'cjs') {
        return { argv: ['node', absPath], cwd: fileDir };
    }
    return { argv: [absPath], cwd: fileDir };
}
