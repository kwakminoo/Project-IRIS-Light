/**
 * IDE ▶ 와 project.run 이 같은 워크스페이스 .venv 를 고르게 한다.
 * exists 는 Theia FileService / 테스트 스텁이 주입한다.
 */

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

export function venvPythonAt(root: string): string {
    const trimmed = root.replace(/[\\/]+$/, '');
    const win = /^[a-zA-Z]:[\\/]/.test(trimmed) || trimmed.includes('\\');
    if (win) {
        return `${trimmed}\\.venv\\Scripts\\python.exe`;
    }
    return `${trimmed}/.venv/bin/python`;
}

function underRoot(fileAbs: string, root: string): boolean {
    const file = fileAbs.replace(/\\/g, '/').toLowerCase();
    const base = root.replace(/\\/g, '/').replace(/\/+$/, '').toLowerCase();
    return file === base || file.startsWith(base + '/');
}

/** 워크스페이스 루트 우선, 그다음 파일 조상 디렉터리를 올라가며 .venv python 을 찾는다. */
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
        return { argv: ['python', absPath], cwd: fileDir };
    }
    if (ext === 'js' || ext === 'mjs' || ext === 'cjs') {
        return { argv: ['node', absPath], cwd: fileDir };
    }
    return { argv: [absPath], cwd: fileDir };
}
